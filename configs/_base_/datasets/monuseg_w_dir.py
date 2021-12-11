# dataset settings
dataset_type = 'NucleiMoNuSegDataset'
data_root = 'data/monuseg'
process_cfg = dict(if_flip=True, min_size=256, max_size=2048, resize_mode='fix', edge_id=2, with_dir=True)
data = dict(
    samples_per_gpu=16,
    workers_per_gpu=16,
    train=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='train/c300',
        ann_dir='train/c300',
        split='only-train_t16_train_c300.txt',
        process_cfg=process_cfg),
    val=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='train/c0',
        ann_dir='train/c0',
        split='only-train_t16_test_c0.txt',
        process_cfg=process_cfg),
    test=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='train/c0',
        ann_dir='train/c0',
        split='only-train_t16_test_c0.txt',
        process_cfg=process_cfg),
)
