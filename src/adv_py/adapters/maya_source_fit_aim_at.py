"""MEL 84987–85067: two target aimConstraint and complementary weights.

The source FKAimAt local matrix is inserted into the existing receiver OPM
instead of changing registered full DAG paths. This is the same parent-local
composition, including any existing receiver OPM, with no bind correction.
"""
from .maya_body_fit_aim_at import _axis, _matrix


def create(host, spec, state):
    c = host._cmds
    plug = spec.receiver + '.offsetParentMatrix'
    if (c.connectionInfo(plug, sourceFromDestination=True) or None) != state.receiver_opm_source:
        raise ValueError('AimAt 接收层来源已变化')
    if bool(c.getAttr(spec.receiver + '.inheritsTransform')) != state.receiver_inherits_transform:
        raise ValueError('AimAt 接收层变换继承状态变化')
    host._transaction_changed = True
    aimed = c.createNode('transform', name=spec.aim_matrix, parent=spec.fk_offset)
    target = c.createNode('transform', name=spec.corrected_matrix, parent=spec.fk_offset)
    static = c.createNode('transform', name=spec.blend_matrix, parent=spec.fk_offset)
    # asAlign 1 1 0 0: parent to target, zero local T/R, restore
    # original parent. World Euler copying loses the original shear/scale
    # decomposition when either parent has nonuniform scale.
    for node in (target, static):
        aligned = c.parent(node, spec.target_control)[0]
        c.xform(aligned, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
        c.parent(aligned, spec.fk_offset)
    # Execute the original absolute reparent before the constraint. Return
    # relatively to retain exactly those local values while preserving the
    # registered DAG address; the bridge below supplies the new parent matrix.
    moved = c.parent(spec.receiver, aimed)[0]
    c.parent(moved, spec.fk_offset, relative=True)
    target = c.parent(target, spec.target_control)[0]
    c.aimConstraint(target, static, aimed, offset=(0, 0, 0),
        aimVector=_axis(spec.aim_axis, spec.mirror_sign),
        upVector=_axis(spec.up_axis, spec.mirror_sign),
        worldUpType='object' if spec.up_object == 'self' else 'objectrotation',
        worldUpVector=(0, spec.mirror_sign, 0),
        worldUpObject=spec.fk_offset if spec.up_object == 'self' else target,
        name=spec.delta_matrix)
    aliases = c.aimConstraint(spec.delta_matrix, query=True, weightAliasList=True)
    if len(aliases) != 2:
        raise RuntimeError('AimAt 双目标权重缺失')
    c.addAttr(spec.fk_control, longName='aimAt', attributeType='double',
              minValue=0, maxValue=10, defaultValue=10, keyable=True)
    ramp = c.createNode('setRange', name=spec.weight_node)
    for axis, low, high in (('X', 0, 1), ('Y', 1, 0)):
        for attr, value in (('min', low), ('max', high), ('oldMin', 0), ('oldMax', 10)):
            c.setAttr(ramp + '.' + attr + axis, value)
        c.connectAttr(spec.fk_control + '.aimAt', ramp + '.value' + axis)
    for axis, alias in zip('XY', aliases):
        c.connectAttr(ramp + '.outValue' + axis, spec.delta_matrix + '.' + alias)
    bridge = c.createNode('multMatrix', name=spec.receiver_matrix)
    if state.receiver_opm_source:
        c.connectAttr(state.receiver_opm_source, bridge + '.matrixIn[0]')
        c.disconnectAttr(state.receiver_opm_source, plug)
    else:
        c.setAttr(bridge + '.matrixIn[0]', *state.receiver_opm_value, type='matrix')
    if state.receiver_inherits_transform:
        c.connectAttr(aimed + '.matrix', bridge + '.matrixIn[1]')
    c.connectAttr(bridge + '.matrixSum', plug)


def capture(host, spec, state):
    c = host._cmds
    kinds = ((spec.aim_matrix, 'transform'), (spec.corrected_matrix, 'transform'),
             (spec.blend_matrix, 'transform'), (spec.delta_matrix, 'aimConstraint'),
             (spec.weight_node, 'setRange'), (spec.receiver_matrix, 'multMatrix'))
    if any(not c.objExists(node) or c.nodeType(node) != kind for node, kind in kinds):
        return False
    def parent(node):
        return (c.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    if (parent(spec.aim_matrix) != spec.fk_offset
            or parent(spec.blend_matrix) != spec.fk_offset
            or parent(spec.corrected_matrix) != spec.target_control):
        return False
    aliases = c.aimConstraint(spec.delta_matrix, query=True, weightAliasList=True) or []
    targets = c.aimConstraint(spec.delta_matrix, query=True, targetList=True) or []
    if len(aliases) != 2 or [c.ls(t, long=True)[0] for t in targets] != [
            c.ls(spec.corrected_matrix, long=True)[0], c.ls(spec.blend_matrix, long=True)[0]]:
        return False
    if bool(c.getAttr(spec.receiver + '.inheritsTransform')) != state.receiver_inherits_transform:
        return False
    links = [(spec.receiver_matrix + '.matrixSum', spec.receiver + '.offsetParentMatrix')]
    if state.receiver_inherits_transform:
        links.append((spec.aim_matrix + '.matrix', spec.receiver_matrix + '.matrixIn[1]'))
    elif c.connectionInfo(spec.receiver_matrix + '.matrixIn[1]', sourceFromDestination=True):
        return False
    for axis, alias in zip('XY', aliases):
        links += [(spec.fk_control + '.aimAt', spec.weight_node + '.value' + axis),
                  (spec.weight_node + '.outValue' + axis, spec.delta_matrix + '.' + alias)]
    if state.receiver_opm_source:
        links.append((state.receiver_opm_source, spec.receiver_matrix + '.matrixIn[0]'))
    elif _matrix(c.getAttr(spec.receiver_matrix + '.matrixIn[0]')) != state.receiver_opm_value:
        return False
    for attr, values in (('aimVector', _axis(spec.aim_axis, spec.mirror_sign)),
                         ('upVector', _axis(spec.up_axis, spec.mirror_sign)),
                         ('worldUpVector', (0, spec.mirror_sign, 0)), ('offset', (0, 0, 0))):
        if any(abs(a-b) > 1e-8 for a, b in zip(_matrix(c.getAttr(spec.delta_matrix+'.'+attr)), values)):
            return False
    if c.getAttr(spec.delta_matrix + '.worldUpType') != (1 if spec.up_object == 'self' else 2):
        return False
    up = spec.fk_offset if spec.up_object == 'self' else spec.corrected_matrix
    links.append((up + '.worldMatrix[0]', spec.delta_matrix + '.worldUpMatrix'))
    for axis, low, high in (('X', 0, 1), ('Y', 1, 0)):
        for attr, value in (('min', low), ('max', high), ('oldMin', 0), ('oldMax', 10)):
            if abs(c.getAttr(spec.weight_node + '.' + attr + axis) - value) > 1e-8:
                return False
    return all(c.isConnected(a, b, ignoreUnitConversion=True) for a, b in links)
