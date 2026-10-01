"""Repair the finite historical Source Root/Spline OPM self-inverse edges."""
from adv_py.core.character_registry import CharacterRegistryError


def repair(host, registration):
    from adv_py.core.spline_control_rebuild import splines
    c = host._cmds
    names = {'AdvPy_SourceRootFollowMM': 2, 'AdvPy_SourceLegLockOutputMM': 1}
    names.update({node.path.rsplit('|', 1)[-1] + 'LegLockMM': 2
                  for node in registration.nodes})
    names.update({plan.node_name('AdvPy_SplineFirstFixedMM'): 1
                  for plan in splines(registration) if plan.source_curve_points})
    owned = {row.path for row in registration.nodes}
    edits = []
    for matrix, index in names.items():
        if not c.objExists(matrix):
            continue
        outputs = c.connectionInfo(matrix + '.matrixSum', destinationFromSource=True) or ()
        for output in outputs:
            if not output.endswith('.offsetParentMatrix'):
                continue
            node = host._resolve_connected_node(output.split('.', 1)[0])
            if node not in owned:
                raise CharacterRegistryError('来源 OPM 修复目标不属于角色登记：' + node)
            destination = matrix + f'.matrixIn[{index}]'
            old = node + '.parentInverseMatrix[0]'
            if not c.isConnected(old, destination):
                continue
            parent = (c.listRelatives(node, parent=True, fullPath=True) or [None])[0]
            if parent is None or c.nodeType(matrix) != 'multMatrix':
                raise CharacterRegistryError('来源 OPM 的历史父矩阵接收图不完整：' + matrix)
            if (c.referenceQuery(matrix, isNodeReferenced=True)
                    or any(c.lockNode(matrix, query=True, lock=True) or [])
                    or c.getAttr(destination, lock=True)):
                raise CharacterRegistryError('来源 OPM 历史矩阵被引用或锁定：' + matrix)
            edits.append((old, parent + '.worldInverseMatrix[0]', destination))
    if edits:
        host._require_transaction()
        host._transaction_changed = True
        for old, new, destination in edits:
            c.disconnectAttr(old, destination)
            c.connectAttr(new, destination)
    return tuple(edits)
