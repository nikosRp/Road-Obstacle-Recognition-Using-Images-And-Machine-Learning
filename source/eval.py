# Author: Bichen Wu (bichen@berkeley.edu) 08/25/2016

"""Evaluation"""

import cv2
from datetime import datetime
import os.path
import sys
import time

import numpy as np
from six.moves import xrange
import tensorflow as tf

from src.config import *
from src.dataset import pascal_voc, kitti
from src.utils.util import bbox_transform, Timer
from src.nets import *

FLAGS = tf.app.flags.FLAGS

tf.app.flags.DEFINE_string('dataset', 'KITTI',
                           """Currently support PASCAL_VOC or KITTI dataset.""")
tf.app.flags.DEFINE_string('data_path', 'C:/Users/Popjo/Desktop/sqDET/KITTI', """Root directory of data""")
tf.app.flags.DEFINE_string('image_set', 'test',
                           """Only used for VOC data."""
                           """Can be train, trainval, val, or test""")
tf.app.flags.DEFINE_string('year', '2007',
                           """VOC challenge year. 2007 or 2012"""
                           """Only used for VOC data""")
tf.app.flags.DEFINE_string('eval_dir', '/tmp/bichen/logs/squeezeDet/eval',
                           """Directory where to write event logs """)
tf.app.flags.DEFINE_string('checkpoint_path', '/tmp/bichen/logs/squeezeDet/train',
                           """Path to the training checkpoint.""")
tf.app.flags.DEFINE_integer('eval_interval_secs', 60 * 1,
                            """How often to check if new cpt is saved.""")
tf.app.flags.DEFINE_boolean('run_once', False,
                            """Whether to run eval only once.""")
tf.app.flags.DEFINE_string('net', 'squeezeDet',
                           """Neural net architecture.""")
tf.app.flags.DEFINE_string('gpu', '0', """gpu id.""")


def eval_once(
        saver, ckpt_path, summary_writer, eval_summary_ops, eval_summary_phs, imdb,
        model):
    ckpt_path = ckpt_path.replace("\\", "/")
    with tf.Session(config=tf.ConfigProto(allow_soft_placement=True)) as sess:
        # pa8=ckpt_path
        # pa8=pa8.replace("\\", "/")
        # ckpt_path.replace("\\", "/")
        # Restores from checkpoint
        saver.restore(sess, ckpt_path)
        # Assuming model_checkpoint_path looks something like:
        #   /ckpt_dir/model.ckpt-0,
        # extract global_step from it.
        global_step = ckpt_path.split('/')[-1].split('-')[-1]

        num_images = len(imdb.image_idx)

        all_boxes = [[[] for _ in range(num_images)]
                     for _ in range(imdb.num_classes)]

        _t = {'im_detect': Timer(), 'im_read': Timer(), 'misc': Timer()}

        num_detection = 0.0
        for i in range(num_images):
            _t['im_read'].tic()
            images, scales = imdb.read_image_batch(shuffle=False)
            _t['im_read'].toc()

            _t['im_detect'].tic()
            det_boxes, det_probs, det_class = sess.run(
                [model.det_boxes, model.det_probs, model.det_class],
                feed_dict={model.image_input: images})
            _t['im_detect'].toc()

            _t['misc'].tic()
            for j in range(len(det_boxes)):  # batch
                # rescale
                det_boxes[j, :, 0::2] /= scales[j][0]
                det_boxes[j, :, 1::2] /= scales[j][1]

                det_bbox, score, det_class = model.filter_prediction(
                    det_boxes[j], det_probs[j], det_class[j])

                num_detection += len(det_bbox)
                for c, b, s in zip(det_class, det_bbox, score):
                    all_boxes[c][i].append(bbox_transform(b) + [s])
            _t['misc'].toc()

            print('im_detect: {:d}/{:d} im_read: {:.3f}s '
                  'detect: {:.3f}s misc: {:.3f}s'.format(
                i + 1, num_images, _t['im_read'].average_time,
                _t['im_detect'].average_time, _t['misc'].average_time))

        print('Evaluating detections...')
        aps, ap_names = imdb.evaluate_detections(
            FLAGS.eval_dir, global_step, all_boxes)
        num_images = num_images + 1
        print('Evaluation summary:')
        print('  Average number of detections per image: {}:'.format(
            num_detection / num_images))
        print('  Timing:')
        print('    im_read: {:.3f}s detect: {:.3f}s misc: {:.3f}s'.format(
            _t['im_read'].average_time, _t['im_detect'].average_time,
            _t['misc'].average_time))
        print('  Average precisions:')

        feed_dict = {}
        for cls, ap in zip(ap_names, aps):
            feed_dict[eval_summary_phs['APs/' + cls]] = ap
            print('    {}: {:.3f}'.format(cls, ap))

        print('    Mean average precision: {:.3f}'.format(np.mean(aps)))
        feed_dict[eval_summary_phs['APs/mAP']] = np.mean(aps)
        feed_dict[eval_summary_phs['timing/im_detect']] = \
            _t['im_detect'].average_time
        feed_dict[eval_summary_phs['timing/im_read']] = \
            _t['im_read'].average_time
        feed_dict[eval_summary_phs['timing/post_proc']] = \
            _t['misc'].average_time
        feed_dict[eval_summary_phs['num_det_per_image']] = \
            num_detection / num_images

        print('Analyzing detections...')
        stats, ims = imdb.do_detection_analysis_in_eval(
            FLAGS.eval_dir, global_step)

        eval_summary_str = sess.run(eval_summary_ops, feed_dict=feed_dict)
        for sum_str in eval_summary_str:
            summary_writer.add_summary(sum_str, global_step)


def evaluate():
    a = FLAGS.checkpoint_path
    """Evaluate."""
    assert FLAGS.dataset == 'KITTI', \
        'Currently only supports KITTI dataset'

    os.environ['CUDA_VISIBLE_DEVICES'] = FLAGS.gpu
    # os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


    with tf.Graph().as_default() as g:

        assert FLAGS.net == 'vgg16' or FLAGS.net == 'resnet50' \
               or FLAGS.net == 'squeezeDet' or FLAGS.net == 'squeezeDet+', \
            'Selected neural net architecture not supported: {}'.format(FLAGS.net)
        if FLAGS.net == 'vgg16':
            mc = kitti_vgg16_config()
            mc.BATCH_SIZE = 1  # TODO(bichen): allow batch size > 1
            mc.LOAD_PRETRAINED_MODEL = False
            model = VGG16ConvDet(mc)
        elif FLAGS.net == 'resnet50':
            mc = kitti_res50_config()
            mc.BATCH_SIZE = 1  # TODO(bichen): allow batch size > 1
            mc.LOAD_PRETRAINED_MODEL = False
            model = ResNet50ConvDet(mc)
        elif FLAGS.net == 'squeezeDet':
            mc = kitti_squeezeDet_config()
            mc.BATCH_SIZE = 1  # TODO(bichen): allow batch size > 1
            mc.LOAD_PRETRAINED_MODEL = False
            model = SqueezeDet(mc)
        elif FLAGS.net == 'squeezeDet+':
            mc = kitti_squeezeDetPlus_config()
            mc.BATCH_SIZE = 1  # TODO(bichen): allow batch size > 1
            mc.LOAD_PRETRAINED_MODEL = False
            model = SqueezeDetPlus(mc)

        imdb = kitti(FLAGS.image_set, FLAGS.data_path, mc)

        # add summary ops and placeholders
        ap_names = []
        for cls in imdb.classes:
            ap_names.append(cls + '_easy')
            ap_names.append(cls + '_medium')
            ap_names.append(cls + '_hard')

        eval_summary_ops = []
        eval_summary_phs = {}
        for ap_name in ap_names:
            ph = tf.placeholder(tf.float32)
            eval_summary_phs['APs/' + ap_name] = ph
            eval_summary_ops.append(tf.summary.scalar('APs/' + ap_name, ph))

        ph = tf.placeholder(tf.float32)
        eval_summary_phs['APs/mAP'] = ph
        eval_summary_ops.append(tf.summary.scalar('APs/mAP', ph))

        ph = tf.placeholder(tf.float32)
        eval_summary_phs['timing/im_detect'] = ph
        eval_summary_ops.append(tf.summary.scalar('timing/im_detect', ph))

        ph = tf.placeholder(tf.float32)
        eval_summary_phs['timing/im_read'] = ph
        eval_summary_ops.append(tf.summary.scalar('timing/im_read', ph))

        ph = tf.placeholder(tf.float32)
        eval_summary_phs['timing/post_proc'] = ph
        eval_summary_ops.append(tf.summary.scalar('timing/post_proc', ph))

        ph = tf.placeholder(tf.float32)
        eval_summary_phs['num_det_per_image'] = ph
        eval_summary_ops.append(tf.summary.scalar('num_det_per_image', ph))

        saver = tf.train.Saver(model.model_params)

        summary_writer = tf.summary.FileWriter(FLAGS.eval_dir, g)

        ckpts = set()
        # tex = ckpts[0]
        # ckpts[0].replace("\\", "/")
        while True:
            if FLAGS.run_once:
                # When run_once is true, checkpoint_path should point to the exact
                # checkpoint file.
                eval_once(
                    saver, FLAGS.checkpoint_path, summary_writer, eval_summary_ops,
                    eval_summary_phs, imdb, model)
                return
            else:
                # When run_once is false, checkpoint_path should point to the directory
                # that stores checkpoint files.
                ckpath = FLAGS.checkpoint_path
                ckpath = ckpath.replace("\\", "/")
                ckpt = tf.train.get_checkpoint_state(ckpath)
                # ckpt.replace("\\", "/")
                if ckpt and ckpt.model_checkpoint_path:
                    wat = ckpt.model_checkpoint_path
                    wat = wat.replace("\\", "/")
                    bl = ckpts
                    if ckpt.model_checkpoint_path in ckpts:
                        # Do not evaluate on the same checkpoint
                        print('Wait {:d}s for new checkpoints to be saved ... '
                              .format(FLAGS.eval_interval_secs))
                        time.sleep(FLAGS.eval_interval_secs)
                    else:
                        tex = ckpt.model_checkpoint_path
                        # pa8 = ckpt.model_checkpoint_path
                        # p999 = pa8.replace("\\", "/")
                        tex = tex.replace("\\", "/")
                        ckpts.add(tex)
                        # ckpts.add(ckpt.model_checkpoint_path)

                        print('Evaluating {}...'.format(tex))
                        eval_once(
                            saver, tex, summary_writer,
                            eval_summary_ops, eval_summary_phs, imdb, model)
                else:
                    print('No checkpoint file found')
                    if not FLAGS.run_once:
                        print('Wait {:d}s for new checkpoints to be saved ... '
                              .format(FLAGS.eval_interval_secs))
                        time.sleep(FLAGS.eval_interval_secs)


def main(argv=None):  # pylint: disable=unused-argument
    if tf.gfile.Exists(FLAGS.eval_dir):
        tf.gfile.DeleteRecursively(FLAGS.eval_dir)
    tf.gfile.MakeDirs(FLAGS.eval_dir)
    evaluate()


if __name__ == '__main__':
    tf.app.run()
