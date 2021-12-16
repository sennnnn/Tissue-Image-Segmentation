# dataset settings
dataset_type = 'NucleiCoNICDataset'
data_root = 'data/conic'
process_cfg = dict(
    if_flip=True,
    if_jitter=True,
    if_elastic=True,
    if_blur=True,
    if_crop=True,
    if_norm=False,
    with_dir=False,
    min_size=208,
    max_size=2048,
    resize_mode='fix',
    edge_id=7,
)
data = dict(
    samples_per_gpu=16,
    workers_per_gpu=16,
    train=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='train/',
        ann_dir='train/',
        split='train.txt',
        process_cfg=process_cfg),
    val=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='val/',
        ann_dir='val/',
        split='val.txt',
        process_cfg=process_cfg),
    test=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='val/',
        ann_dir='val/',
        split='val.txt',
        process_cfg=process_cfg),
)
