import argparse
import os

import mmcv
import torch
from mmcv.parallel import MMDataParallel, MMDistributedDataParallel
from mmcv.runner import get_dist_info, init_dist, load_checkpoint
from mmcv.utils import DictAction

from tiseg.apis import multi_gpu_test, single_gpu_test
from tiseg.datasets import build_dataloader, build_dataset
from tiseg.models import build_segmentor


def parse_args():
    parser = argparse.ArgumentParser(description='test (and eval) a model')
    parser.add_argument('config', help='test config file path')
    parser.add_argument('checkpoint', help='checkpoint file')
    parser.add_argument(
        '--eval',
        type=str,
        nargs='+',
        help='evaluation metrics, which depends on the dataset, e.g., "mIoU"'
        ' for generic datasets, and "cityscapes" for Cityscapes')
    parser.add_argument('--eval-options', nargs='+', action=DictAction, help='custom options for evaluation')
    parser.add_argument('--launcher', choices=['none', 'pytorch', 'slurm', 'mpi'], default='none', help='job launcher')
    parser.add_argument('--local_rank', type=int, default=0)
    args = parser.parse_args()
    if 'LOCAL_RANK' not in os.environ:
        os.environ['LOCAL_RANK'] = str(args.local_rank)
    return args


def main():
    args = parse_args()

    cfg = mmcv.Config.fromfile(args.config)

    # set cudnn_benchmark
    if cfg.get('cudnn_benchmark', False):
        torch.backends.cudnn.benchmark = True

    # init distributed env first, since logger depends on the dist info.
    if args.launcher == 'none':
        distributed = False
    else:
        distributed = True
        init_dist(args.launcher, **cfg.dist_params)

    # build the model and load checkpoint
    model = build_segmentor(cfg.model, train_cfg=cfg.get('train_cfg'), test_cfg=cfg.get('test_cfg'))
    _ = load_checkpoint(model, args.checkpoint, map_location='cpu')

    if not isinstance(cfg.data.test, list):
        cfg.data.test = [cfg.data.test]

    data_test_list = cfg.data.test
    for data_test in data_test_list:
        data_test.test_mode = True

        # build the dataloader
        # TODO: support multiple images per gpu (only minor changes are needed)
        dataset = build_dataset(data_test)
        data_loader = build_dataloader(
            dataset, samples_per_gpu=1, workers_per_gpu=cfg.data.workers_per_gpu, dist=distributed, shuffle=False)

        model.CLASSES = dataset.CLASSES
        model.PALETTE = dataset.PALETTE

        eval_kwargs = {} if args.eval_options is None else args.eval_options

        # clean gpu memory when starting a new evaluation.
        torch.cuda.empty_cache()

        if not distributed:
            model = MMDataParallel(model, device_ids=[0])
            results = single_gpu_test(model, data_loader, pre_eval=args.eval is not None)
        else:
            model = MMDistributedDataParallel(
                model.cuda(), device_ids=[torch.cuda.current_device()], broadcast_buffers=False)
            results = multi_gpu_test(model, data_loader, args.gpu_collect, pre_eval=args.eval is not None)

        rank, _ = get_dist_info()
        if rank == 0:
            if args.eval:
                dataset.evaluate(results, args.eval, **eval_kwargs)


if __name__ == '__main__':
    main()
