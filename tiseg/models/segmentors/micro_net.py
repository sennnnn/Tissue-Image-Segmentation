import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from skimage import morphology, measure
from skimage.morphology import remove_small_objects
from scipy.ndimage import binary_fill_holes
from mmcv.cnn import ConvModule

from ..builder import SEGMENTORS
from ..losses import BatchMultiClassDiceLoss, mdice, tdice
from .base import BaseSegmentor


def conv(in_dims, out_dims, kernel, pad=False, norm_cfg=dict(type='BN'), act_cfg=dict(type='ReLU')):
    if pad:
        padding = (kernel - 1) // 2
    else:
        padding = 0
    return ConvModule(in_dims, out_dims, kernel, 1, padding, norm_cfg=norm_cfg, act_cfg=act_cfg)


def transconv(in_dims, out_dims, kernel):
    return nn.ConvTranspose2d(in_dims, out_dims, kernel, 1)


class DownBlock(nn.Module):

    def __init__(self, in_dims, out_dims):
        super().__init__()
        self.convs = nn.Sequential(
            conv(in_dims, out_dims, 3), conv(out_dims, out_dims, 3, norm_cfg=None), nn.MaxPool2d(2, 2))
        self.img_convs = nn.Sequential(conv(3, out_dims, 3), conv(out_dims, out_dims, 3, norm_cfg=None))

    def forward(self, x, img):
        x = self.convs(x)
        B, C, H, W = x.shape
        ix = F.interpolate(img, (H + 4, W + 4), mode='bilinear', align_corners=False)
        ix = self.img_convs(ix)

        out = torch.cat([x, ix], dim=1)

        return out


class UpBlock(nn.Module):

    def __init__(self, in_dims, skip_dims, feed_dims):
        super().__init__()
        self.upsample = nn.Sequential(
            nn.Upsample(scale_factor=2, mode='bilinear'),
            conv(in_dims, feed_dims, 3, pad=True, norm_cfg=None, act_cfg=None))
        self.convs = nn.Sequential(
            conv(feed_dims, feed_dims, 3, norm_cfg=None), conv(feed_dims, feed_dims, 3, norm_cfg=None))
        self.in_trans_conv = transconv(feed_dims, feed_dims, 5)
        self.skip_trans_conv = transconv(skip_dims, feed_dims, 5)
        self.bottle_neck = conv(feed_dims * 2, feed_dims, 1, pad=True, norm_cfg=None)

    def forward(self, x, skip):
        x = self.upsample(x)
        x = self.convs(x)
        x = self.in_trans_conv(x)

        skip = self.skip_trans_conv(skip)

        out = torch.cat([x, skip], dim=1)
        out = self.bottle_neck(out)

        return out


class DecodeBlock(nn.Module):

    def __init__(self, in_dims, feed_dims, num_classes, up_factor):
        self.in_dims = in_dims
        self.up_factor = up_factor

        self.upsample = nn.Sequential(
            nn.Upsample(scale_factor=up_factor, mode='bilinear'),
            conv(in_dims, feed_dims, 3, pad=True, norm_cfg=None, act_cfg=None))

        self.feed_conv = conv(feed_dims, feed_dims, 3, norm_cfg=None)
        self.dropout = nn.Dropout(0.5)
        self.sem_conv = conv(feed_dims, num_classes)

    def forward(self, x):
        x = self.upsample(x)
        feats = self.feed_conv(x)
        out = self.dropout(feats)
        out = self.sem_conv(out)

        return out, feats


@SEGMENTORS.register_module()
class MicroNet(BaseSegmentor):
    """Implementation of `Micro-Net: A unified model for segmentation of various objects in microscopy images`.
    """

    def __init__(self, num_classes, train_cfg, test_cfg):
        super(MicroNet, self).__init__()
        self.train_cfg = train_cfg
        self.test_cfg = test_cfg
        self.num_classes = num_classes

        self.db1 = DownBlock(3, 64)
        self.db2 = DownBlock(64, 128)
        self.db3 = DownBlock(128, 256)
        self.db4 = DownBlock(256, 512)

        self.db5 = nn.Sequential(conv(512, 2048, 3, norm_cfg=None), conv(512, 2048, 3, norm_cfg=None))

        self.ub4 = UpBlock(2048, 512, 1024)
        self.ub3 = UpBlock(1024, 256, 512)
        self.ub2 = UpBlock(512, 128, 256)
        self.ub1 = UpBlock(256, 64, 128)

        self.out_branch1 = DecodeBlock(128, 64, num_classes + 1, 2)
        self.out_branch2 = DecodeBlock(256, 128, num_classes + 1, 4)
        self.out_branch3 = DecodeBlock(512, 256, num_classes + 1, 8)

        self.dropout = nn.Dropout(0.5)
        self.final_sem_conv = nn.Conv2d(64 + 128 + 256, num_classes + 1, 1)

    def calculate(self, img, test_mode=True):
        b1 = self.db1(img)
        b2 = self.db2(b1)
        b3 = self.db3(b2)
        b4 = self.db4(b3)
        b5 = self.db5(b4)
        b6 = self.ub4(b5, b4)
        b7 = self.ub3(b6, b3)
        b8 = self.ub2(b7, b2)
        b9 = self.ub1(b8, b1)

        p_a1, feats1 = self.out_branch1(b9)
        p_a2, feats2 = self.out_branch2(b8)
        p_a3, feats3 = self.out_branch3(b7)

        feats = torch.cat([feats1, feats2, feats3], dim=1)
        feats = self.dropout(feats)
        p_o = self.final_sem_conv(feats)

        if test_mode:
            return p_o
        else:
            return p_o, p_a1, p_a2, p_a3

    def forward(self, data, label=None, metas=None, **kwargs):
        """detectron2 style forward functions. Segmentor can be see as meta_arch of detectron2.
        """
        if self.training:
            sem_logit, aux_logit_1, aux_logit_2, aux_logit_3 = self.calculate(data['img'], test_mode=False)
            sem_gt = label['sem_gt_w_bound']
            loss = dict()
            sem_gt = sem_gt.squeeze(1)
            sem_loss = self._sem_loss(sem_logit, sem_gt)
            loss.update(sem_loss)
            aux_loss_1 = self._aux_loss(aux_logit_1, sem_gt, idx=1)
            loss.update(aux_loss_1)
            aux_loss_2 = self._aux_loss(aux_logit_2, sem_gt, idx=2)
            loss.update(aux_loss_2)
            aux_loss_3 = self._aux_loss(aux_logit_3, sem_gt, idx=3)
            loss.update(aux_loss_3)
            # calculate training metric
            training_metric_dict = self._training_metric(sem_logit, sem_gt)
            loss.update(training_metric_dict)
            return loss
        else:
            assert metas is not None
            # NOTE: only support batch size = 1 now.
            sem_logit = self.inference(data['img'], metas[0], True)
            sem_pred = sem_logit.argmax(dim=1)
            # Extract inside class
            sem_pred = sem_pred.cpu().numpy()[0]
            sem_pred, inst_pred = self.postprocess(sem_pred)
            # unravel batch dim
            ret_list = []
            ret_list.append({'sem_pred': sem_pred, 'inst_pred': inst_pred})
            return ret_list

    def postprocess(self, pred):
        """model free post-process for both instance-level & semantic-level."""
        pred[pred == self.num_classes] = 0
        sem_id_list = list(np.unique(pred))
        inst_pred = np.zeros_like(pred).astype(np.int32)
        sem_pred = np.zeros_like(pred).astype(np.uint8)
        cur = 0
        for sem_id in sem_id_list:
            # 0 is background semantic class.
            if sem_id == 0:
                continue
            sem_id_mask = pred == sem_id
            # fill instance holes
            sem_id_mask = binary_fill_holes(sem_id_mask)
            sem_id_mask = remove_small_objects(sem_id_mask, 5)
            inst_sem_mask = measure.label(sem_id_mask)
            inst_sem_mask = morphology.dilation(inst_sem_mask, selem=morphology.disk(self.test_cfg.get('radius', 3)))
            inst_sem_mask[inst_sem_mask > 0] += cur
            inst_pred[inst_sem_mask > 0] = 0
            inst_pred += inst_sem_mask
            cur += len(np.unique(inst_sem_mask))
            sem_pred[inst_sem_mask > 0] = sem_id

        return sem_pred, inst_pred

    def _sem_loss(self, sem_logit, sem_gt):
        """calculate mask branch loss."""
        sem_loss = {}
        sem_ce_loss_calculator = nn.CrossEntropyLoss(reduction='none')
        sem_dice_loss_calculator = BatchMultiClassDiceLoss(num_classes=self.num_classes)
        # Assign weight map for each pixel position
        # sem_loss *= weight_map
        sem_ce_loss = torch.mean(sem_ce_loss_calculator(sem_logit, sem_gt))
        sem_dice_loss = sem_dice_loss_calculator(sem_logit, sem_gt)
        # loss weight
        alpha = 5
        beta = 0.5
        sem_loss['sem_ce_loss'] = alpha * sem_ce_loss
        sem_loss['sem_dice_loss'] = beta * sem_dice_loss

        return sem_loss

    def _aux_loss(self, sem_logit, sem_gt, idx):
        sem_loss = {}
        sem_ce_loss_calculator = nn.CrossEntropyLoss(reduction='none')
        sem_dice_loss_calculator = BatchMultiClassDiceLoss(num_classes=self.num_classes)
        # Assign weight map for each pixel position
        # sem_loss *= weight_map
        sem_ce_loss = torch.mean(sem_ce_loss_calculator(sem_logit, sem_gt))
        sem_dice_loss = sem_dice_loss_calculator(sem_logit, sem_gt)
        # loss weight
        alpha = 5
        beta = 0.5
        sem_loss[f'sem_ce_loss_aux{idx}'] = alpha * sem_ce_loss
        sem_loss[f'sem_dice_loss_aux{idx}'] = beta * sem_dice_loss

        return sem_loss

    def _training_metric(self, sem_logit, sem_gt):
        """metric calculation when training."""
        wrap_dict = {}

        # loss
        clean_sem_logit = sem_logit.clone().detach()
        clean_sem_gt = sem_gt.clone().detach()

        wrap_dict['sem_tdice'] = tdice(clean_sem_logit, clean_sem_gt, self.num_classes)
        wrap_dict['sem_mdice'] = mdice(clean_sem_logit, clean_sem_gt, self.num_classes)

        return wrap_dict
