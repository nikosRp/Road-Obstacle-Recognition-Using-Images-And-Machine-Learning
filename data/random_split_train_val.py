import numpy as np

# image_set_dir = 'C:/Users/nikpop/PycharmProjects/squeezeDet/data/KITTI/ImageSets'
image_set_dir = 'C:/Users/Popjo/Desktop/sqDET/KITTI/ImageSets'
trainval_file = image_set_dir+'/trainval.txt'
train_file = image_set_dir+'/train.txt'
val_file = image_set_dir+'/val.txt'

idx = []
data = []
with open(trainval_file) as f:
  for line in f:
    idx.append(line.strip())
    data.append(line.strip())
f.close()

idx = np.random.permutation(idx)
idx = list(map(int, idx))

limit1 = int(len(idx)/2)
train_idx = sorted(idx[:limit1])
val_idx = sorted(idx[limit1:])
# train_idx = sorted(idx[:len(idx)/2])
# val_idx = sorted(idx[len(idx)/2:])

# with open(train_file, 'w') as f:
#   for i in train_idx:
#     f.write('{}\n'.format(i))
# f.close()
with open(train_file, 'w') as f:
  for i in train_idx:
    f.write('{}\n'.format(data[i]))
f.close()

# with open(val_file, 'w') as f:
#   for i in val_idx:
#     f.write('{}\n'.format(i))
# f.close
with open(val_file, 'w') as f:
  for i in val_idx:
    f.write('{}\n'.format(data[i]))
f.close()

print('Trainining set is saved to ' + train_file)
print('Validation set is saved to ' + val_file)
