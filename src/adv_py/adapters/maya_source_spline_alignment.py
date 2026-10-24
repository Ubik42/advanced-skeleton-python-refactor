"""Source AlignIKTo scene creation, registration and endpoint rotation."""
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_spline_alignment import (
    ALIGNMENT_ATTRIBUTE,plan_source_spline_alignment_frames,
    encode_source_spline_alignment,decode_source_spline_alignment,
)

OWNER_ATTRIBUTE='advPySourceSplineAlignmentBody'
from .maya_source_fit_terminal import capture_non_terminal_fits


def _body_uuid(c,body,retired_body=()):
    identities=c.ls(body,uuid=True) or []
    if not identities:
        retired=tuple(row for row in retired_body if row.path==body)
        if len(retired)==1 and not c.ls(retired[0].uuid,long=True):
            return retired[0].uuid
    if len(identities)!=1:
        raise CharacterRegistryError('来源 AlignIKTo 的 Body 身份不唯一：'+body)
    return identities[0]


def _validate_owner(c,frame,retired_body=()):
    plug=frame.target+'.'+OWNER_ATTRIBUTE
    if (not c.objExists(plug) or not c.getAttr(plug,lock=True)
            or c.getAttr(plug,type=True)!='string'
            or c.getAttr(plug)!=_body_uuid(c,frame.body,retired_body)):
        raise CharacterRegistryError('来源 AlignIKTo 被同名节点占用或 Body 身份变化：'+frame.target)


def create(host,spline,fk,all_splines,hierarchy,instances):
    host._require_transaction()
    c=host._cmds
    frames=plan_source_spline_alignment_frames(spline,fk,all_splines,hierarchy,instances,
        non_terminal_fit=capture_non_terminal_fits(host,hierarchy))
    for frame in frames:
        name=frame.target.rsplit('|',1)[-1]
        if c.objExists(name):
            existing=c.ls(name,long=True,type='transform') or []
            if existing!=[frame.target]:
                raise CharacterRegistryError('来源 AlignIKTo 名称被占用：'+name)
            _validate_owner(c,frame)
            # Original creates each joint identity once when two IK systems
            # share a start. Never overwrite its authored reference frame.
            continue
        host._transaction_changed=True
        target=c.createNode('transform',name=name)
        c.setAttr(target+'.rotateOrder',c.getAttr(frame.body+'.rotateOrder'))
        position=c.xform(frame.body,query=True,worldSpace=True,translation=True)
        c.xform(target,worldSpace=True,translation=position)
        # Source asAlign(..., 1,0,0,0) leaves world rotation at zero.
        actual=c.parent(target,frame.parent,absolute=True)[0]
        if (c.ls(actual,long=True) or [])!=[frame.target]:
            raise CharacterRegistryError('来源 AlignIKTo 创建后路径变化：'+name)
        c.addAttr(frame.target,longName=OWNER_ATTRIBUTE,dataType='string')
        c.setAttr(frame.target+'.'+OWNER_ATTRIBUTE,_body_uuid(c,frame.body),type='string',lock=True)
    plug=spline.mode_control+'.'+ALIGNMENT_ATTRIBUTE
    if c.objExists(plug):
        raise CharacterRegistryError('来源 Spline AlignIKTo 记录已经存在')
    c.addAttr(spline.mode_control,longName=ALIGNMENT_ATTRIBUTE,dataType='string')
    c.setAttr(plug,encode_source_spline_alignment(frames),type='string',lock=True)
    return frames


def read(host,spline,*,retired_body=None):
    c=host._cmds
    if retired_body is None:
        from .maya_original_control_identity import registration
        saved=registration(host)
        retired_body=saved.retired_body if saved is not None else ()
    plug=spline.mode_control+'.'+ALIGNMENT_ATTRIBUTE
    if (not c.objExists(plug) or not c.getAttr(plug,lock=True)
            or c.getAttr(plug,type=True)!='string'):
        raise CharacterRegistryError('来源 Spline AlignIKTo 记录缺失或解锁')
    frames=decode_source_spline_alignment(c.getAttr(plug))
    if tuple(frame.body for frame in frames)!=(spline.body_joints[0],spline.body_joints[-1]):
        raise CharacterRegistryError('来源 Spline AlignIKTo 的首尾身份改变')
    for frame in frames:
        if ((c.ls(frame.target,long=True,type='transform') or [])!=[frame.target]
                or (c.listRelatives(frame.target,parent=True,fullPath=True) or [])!=[frame.parent]):
            raise CharacterRegistryError('来源 Spline AlignIKTo 节点缺失或父级变化：'+frame.target)
        _validate_owner(c,frame,retired_body)
    return frames


def endpoint_rotation(host,spline,index):
    c=host._cmds
    frame=read(host,spline)[0 if index==0 else 1]
    control=spline.targets[index]
    order=c.xform(control,query=True,rotateOrder=True)
    c.xform(frame.target,preserve=True,rotateOrder=order)
    return tuple(c.xform(frame.target,query=True,worldSpace=True,rotation=True))
