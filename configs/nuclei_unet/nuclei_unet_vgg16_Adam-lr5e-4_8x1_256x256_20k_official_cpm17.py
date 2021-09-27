_base_ = [
    '../_base_/datasets/official_cpm17_256x256.py',
    './_base_/nuclei_unet_runtime.py',
    './_base_/nuclei_unet_vgg16.py',
    './_base_/nuclei_unet_schedule_20k.py',
]

optimizer = dict(_delete_=True, type='Adam', lr=0.0005, weight_decay=0.0005)

lr_config = dict(
    _delete_=True,
    policy='poly',
    warmup='linear',
    warmup_iters=1500,
    warmup_ratio=1e-6,
    power=1.0,
    min_lr=0.0,
    by_epoch=False)

model = dict(
    train_cfg=dict(),
    test_cfg=dict(mode='slide', crop_size=(256, 256), stride=(216, 216)),
)

data = dict(samples_per_gpu=8, workers_per_gpu=8)
