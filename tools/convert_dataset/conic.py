import os
import os.path as osp

import numpy as np
from PIL import Image
from tqdm import tqdm


def pillow_save(save_path, array, palette=None):
    """storage image array by using pillow."""
    image = Image.fromarray(array.astype(np.uint8))
    if palette is not None:
        image = image.convert('P')
        image.putpalette(palette)
    image.save(save_path)


def main():
    data_root = 'data/conic/'  # Change this according to the root path where the data is located # noqa

    images_path = f'{data_root}/conic/images.npy'  # images array Nx256x256x3
    labels_path = f'{data_root}/conic/labels.npy'  # labels array Nx256x256x2
    # counts_path = f"{data_root}/conic/counts.csv"  # csv of counts per nuclear type for each patch # noqa
    # info_path = f"{data_root}/conic/patch_info.csv"  # csv indicating which image from Lizard each patch comes from # noqa

    images = np.load(images_path)
    labels = np.load(labels_path)

    print('Images Shape:', images.shape)
    print('Labels Shape:', labels.shape)

    for split in ['train']:
        new_root = osp.join(data_root, split)

        if not osp.exists(new_root):
            os.makedirs(new_root, 0o775)

        for i in tqdm(range(images.shape[0])):
            img_path = osp.join(new_root, f'{i}.png')
            instance_path = osp.join(new_root, f'{i}_instance.npy')
            semantic_path = osp.join(new_root, f'{i}_semantic.png')
            pillow_save(img_path, images[i])
            np.save(instance_path, labels[i, :, :, 0])
            pillow_save(semantic_path, labels[i, :, :, 1])

        item_list = [
            x.rstrip('_instance.npy') for x in os.listdir(new_root)
            if '_instance.npy' in x
        ]

        with open(osp.join(data_root, f'{split}.txt'), 'w') as fp:
            [fp.write(item + '\n') for item in item_list]


if __name__ == '__main__':
    main()