"""Recreate original Set Axis / customAxis layers before restored SDK systems."""
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from .maya_original_control_orient import (
    DETACH_HOLDER, _has, _address, set_original_control_orient, read_options,
)
from .maya_original_control_identity import source_control_name


@dataclass(frozen=True)
class OriginalOrientRebuildRow:
    role: str
    options: object
    custom_matrix: tuple | None = None


def capture(host, registration):
    c = host._cmds
    if c.objExists(DETACH_HOLDER):
        raise CharacterRegistryError('控制器方向仍在分离状态；先重新附着再重建')
    if not c.objExists('ControlSet'):
        return ()
    result = []
    for control in c.sets('ControlSet', query=True) or []:
        if not (_has(c, control, 'primaryAxis') or _has(c, control, 'customAxis')):
            continue
        role = source_control_name(host, control)
        if role == 'Main' or not c.objExists('AllSet') or not c.sets(control, isMember='AllSet'):
            continue
        custom = 'CustomOrient' + role
        if not c.objExists(custom):
            raise CharacterRegistryError('原朝向属性存在，但缺少原版 CustomOrient 层：' + role)
        matrix = (tuple(c.xform(custom, query=True, objectSpace=True, matrix=True))
                  if _has(c, control, 'customAxis') and c.getAttr(control + '.customAxis') else None)
        result.append(OriginalOrientRebuildRow(role, read_options(c, control), matrix))
    return tuple(result)


def restore(host, rows, registration, rig):
    host._require_transaction()
    before = registration
    for row in rows:
        control = _address(host, row.role)
        if not host._cmds.objExists(control):
            raise CharacterRegistryError('新 Body 缺少原朝向控制器：' + row.role)
        # Each native invocation may append the original mirror counterpart;
        # the saved ControlSet order is replayed, including later overrides.
        result = set_original_control_orient(host, (control,), row.options,
            custom_frames={row.role: row.custom_matrix} if row.custom_matrix is not None else None)
        if not result:
            raise CharacterRegistryError('原朝向控制器未在暂存 Body 中恢复：' + row.role)
        if row.custom_matrix is not None:
            control = _address(host, row.role)
            if not _has(host._cmds, control, 'customAxis'):
                host._cmds.addAttr(control, longName='customAxis', attributeType='bool')
            host._cmds.setAttr(control + '.customAxis', True)
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
