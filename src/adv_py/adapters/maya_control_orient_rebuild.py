"""Recreate original Set Axis / customAxis layers before restored SDK systems."""
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from .maya_original_control_orient import (
    DETACH_HOLDER, _has, _address, set_original_control_orient, read_options,_store_options,
)
from .maya_original_control_identity import source_control_name


@dataclass(frozen=True)
class OriginalOrientRebuildRow:
    role: str
    options: object
    custom_matrix: tuple | None = None
    custom_axis: bool | None = None
    reverse_matrix: tuple | None = None


def capture(host, registration):
    c = host._cmds
    if c.objExists(DETACH_HOLDER):
        raise CharacterRegistryError('控制器方向仍在分离状态；先重新附着再重建')
    if not c.objExists('ControlSet'):
        return ()
    result = []
    disabled=c.objExists('CustomOrientsDisabled')
    for control in c.sets('ControlSet', query=True) or []:
        if not (_has(c, control, 'primaryAxis') or _has(c, control, 'customAxis')):
            continue
        role = source_control_name(host, control)
        if role == 'Main' or not c.objExists('AllSet') or not c.sets(control, isMember='AllSet'):
            continue
        custom = 'CustomOrient' + role
        if not c.objExists(custom):
            raise CharacterRegistryError('原朝向属性存在，但缺少原版 CustomOrient 层：' + role)
        custom_axis=bool(_has(c,control,'customAxis') and c.getAttr(control+'.customAxis'))
        matrix = (tuple(c.xform(custom, query=True, objectSpace=True, matrix=True))
                  if custom_axis or disabled else None)
        reverse=None
        if matrix is not None:
            node='CustomOrientReverse'+role
            if not c.objExists(node):
                raise CharacterRegistryError('原朝向缺少实际反向抵消层：'+role)
            reverse=tuple(c.xform(node,query=True,objectSpace=True,matrix=True))
        result.append(OriginalOrientRebuildRow(role,read_options(c,control),matrix,custom_axis,reverse))
    return tuple(result)


def restore(host, rows, registration, rig):
    host._require_transaction()
    before = registration
    # A native mirrored call also visits the counterpart. Give every call the
    # complete saved custom/disabled frames so later mirror visits cannot
    # overwrite a frame already restored from the actual source scene.
    frames={row.role:row.custom_matrix for row in rows if row.custom_matrix is not None}
    for row in rows:
        control = _address(host, row.role)
        if not host._cmds.objExists(control):
            raise CharacterRegistryError('新 Body 缺少原朝向控制器：' + row.role)
        # Each native invocation may append the original mirror counterpart;
        # the saved ControlSet order is replayed, including later overrides.
        result = set_original_control_orient(host, (control,), row.options,
            custom_frames=frames or None)
        if not result:
            raise CharacterRegistryError('原朝向控制器未在暂存 Body 中恢复：' + row.role)
        if row.custom_matrix is not None and row.custom_axis is False:
            _store_options(host._cmds,_address(host,row.role),row.options)
        if row.custom_matrix is not None and row.custom_axis is not False:
            control = _address(host, row.role)
            if not _has(host._cmds, control, 'customAxis'):
                host._cmds.addAttr(control, longName='customAxis', attributeType='bool')
            host._cmds.setAttr(control + '.customAxis', True)
    for row in rows:
        if row.reverse_matrix is not None:
            host._cmds.xform('CustomOrientReverse'+row.role,objectSpace=True,matrix=row.reverse_matrix)
        if row.custom_axis is False:
            control=_address(host,row.role)
            if _has(host._cmds,control,'customAxis'):
                host._cmds.setAttr(control+'.customAxis',False)
    after = host.read_character_registration()
    by_uuid = {node.uuid: node for node in after.nodes}
    rewrites = []
    for node in before.nodes:
        current = by_uuid.get(node.uuid)
        if current is None or current.node_type != node.node_type:
            raise CharacterRegistryError('原朝向恢复改变了新 Body 的节点身份')
        if node.path != current.path:
            rewrites.append((node.path, current.path))
    paths = FitPartFinalPaths((), (), tuple(rewrites))
    return after, rebase_plan_paths_after_parts(rig, paths)


def retained_disabled_root(host,registration):
    """Retain the source holder and its actual values through normal handoff.

    The original disable operation leaves this object outside AllSet. Discover
    its native frame boundary rather than making another holder in the stage.
    """
    from math import isfinite
    from .maya_original_control_identity import control_roles
    c=host._cmds
    name='CustomOrientsDisabled'
    if not c.objExists(name):return ()
    paths=c.ls(name,long=True) or ()
    if len(paths)!=1 or c.nodeType(paths[0])!='transform':
        raise CharacterRegistryError('原版禁用朝向记录对象缺失或不唯一')
    if paths[0] in {row.path for row in registration.nodes}:
        raise CharacterRegistryError('原版禁用朝向记录不能替代生成 Body 身份')
    frames={'CustomOrient'+role for role in control_roles(registration).values()}
    frames.update('CustomOrientReverse'+role for role in control_roles(registration).values())
    for attribute in c.listAttr(name,userDefined=True) or ():
        parts=attribute.split('_')
        if len(parts)!=3 or parts[2] not in ('rx','ry','rz','sx','sy','sz'):
            raise CharacterRegistryError('原版禁用朝向记录的恢复属性无效：'+attribute)
        frame='_'.join(parts[:2])
        plug=name+'.'+attribute
        value=c.getAttr(plug)
        if (frame not in frames or not c.objExists(frame+'.'+parts[2])
                or type(value) not in (int,float) or not isfinite(value)
                or c.connectionInfo(plug,sourceFromDestination=True)):
            raise CharacterRegistryError('原版禁用朝向记录没有当前实际生成控制层对应：'+attribute)
    return (paths[0],)
