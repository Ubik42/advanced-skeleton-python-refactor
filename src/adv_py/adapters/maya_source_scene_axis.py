"""Shared asSceneUpAxisFlip implementation for Fit import and Body editing."""
from adv_py.core.fit_settings import FitSkeletonValidationError


def flip(host, transform, axis):
    host._require_transaction()
    c = host._cmds
    matches = c.ls(transform,long=True,type='transform') or ()
    if len(matches)!=1:
        raise FitSkeletonValidationError('场景上方向转换目标不存在或不唯一：'+transform)
    if axis not in ('y','z'):
        raise ValueError('场景上方向只能是 Y 或 Z')
    transform = matches[0]
    channels = tuple(transform+'.r'+suffix for suffix in ('x','y','z',''))
    locked = tuple(bool(c.getAttr(plug,lock=True)) for plug in channels)
    host._transaction_changed = True
    try:
        for plug,was_locked in zip(channels,locked):
            if was_locked:c.setAttr(plug,lock=False)
        c.setAttr(transform+'.r',90 if axis=='z' else 0,0,0,type='float3')
    finally:
        for plug,was_locked in zip(channels,locked):
            if was_locked:c.setAttr(plug,lock=True)
    c.upAxis(axis=axis)
