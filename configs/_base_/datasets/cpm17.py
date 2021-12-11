# dataset settings
dataset_type = 'NucleiCPM17Dataset'
data_root = 'data/cpm17'
process_cfg = dict(if_flip=True, min_size=256, max_size=2048, resize_mode='fix', edge_id=2, with_dir=False)
data = dict(
    samples_per_gpu=16,
    workers_per_gpu=16,
    train=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='train/c300',
        ann_dir='train/c300',
        split='train_c300.txt',
        process_cfg=process_cfg),
    val=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='test/c0',
        ann_dir='test/c0',
        split='test_c0.txt',
        process_cfg=process_cfg),
    test=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='test/c0',
        ann_dir='test/c0',
        split='test_c0.txt',
        process_cfg=process_cfg),
)
