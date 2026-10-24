"""RP asFollowLevels, MEL 74359-74541 and PoleAim override 81764-81772."""


def _matrix(value):
    return tuple(value[0] if len(value) == 1 and isinstance(value[0], (tuple, list)) else value)


def create(host, spec, state):
    c = host._cmds
    host._transaction_changed = True
    blend = c.createNode('blendMatrix', name=spec.blend_node)
    c.setAttr(blend+'.inputMatrix', *state.offset_world, type='matrix')
    for index, (target, world) in enumerate(zip(spec.targets, state.target_worlds)):
        matrix = c.createNode('multMatrix', name=target.matrix_node)
        c.setAttr(matrix+'.matrixIn[0]', *state.offset_world, type='matrix')
        c.setAttr(matrix+'.matrixIn[1]', *_matrix(c.getAttr(target.source+'.worldInverseMatrix[0]')), type='matrix')
        c.connectAttr(target.source+'.worldMatrix[0]', matrix+'.matrixIn[2]')
        c.connectAttr(matrix+'.matrixSum', blend+f'.target[{index}].targetMatrix')
        c.addAttr(spec.fk_control, longName='follow'+target.label, attributeType='double',
                  minValue=0, maxValue=10, defaultValue=target.weight, keyable=True)
        weight = c.createNode('multDoubleLinear', name=target.weight_node)
        c.connectAttr(spec.fk_control+'.follow'+target.label, weight+'.input1')
        c.setAttr(weight+'.input2', .1)
        c.connectAttr(weight+'.output', blend+f'.target[{index}].weight')
    if spec.source_rp_pole_target:
        c.connectAttr(spec.source_rp_pole_target+'.worldMatrix[0]',
                      blend+f'.target[{len(spec.targets)-1}].targetMatrix', force=True)
    if spec.use_offset_parent_matrix:
        if state.opm_source:
            c.disconnectAttr(state.opm_source, spec.fk_offset+'.offsetParentMatrix')
        c.connectAttr(blend+'.outputMatrix', spec.fk_offset+'.offsetParentMatrix')
    else:
        dm = c.createNode('decomposeMatrix', name=spec.output_node)
        c.setAttr(dm+'.inputRotateOrder', c.getAttr(spec.fk_offset+'.rotateOrder'))
        c.connectAttr(blend+'.outputMatrix', dm+'.inputMatrix')
        for kind in ('Translate', 'Rotate', 'Scale'):
            for axis in 'XYZ':
                c.connectAttr(dm+'.output'+kind+axis, spec.fk_offset+'.'+kind.lower()+axis)
        for axis, component in zip('XYZ', ('XY', 'XZ', 'YZ')):
            c.connectAttr(dm+'.outputShear'+axis, spec.fk_offset+'.shear'+component)
    # The source invokes xform after asMatrixConnectAttr in both modes.
    c.xform(spec.fk_offset, objectSpace=True, translation=(0., 0., 0.), rotation=(0., 0., 0.))


def capture(host, spec, state, *, check_initial_pose=True):
    from maya.api import OpenMaya as om
    c = host._cmds
    def near(left, right):
        return len(left) == len(right) and all(abs(a-b) <= 1e-5 for a, b in zip(left, right))
    if c.nodeType(spec.blend_node) != 'blendMatrix' or not near(
            _matrix(c.getAttr(spec.blend_node+'.inputMatrix')), state.offset_world):
        return False
    links = []
    for index, (target, world) in enumerate(zip(spec.targets, state.target_worlds)):
        attr = spec.fk_control+'.follow'+target.label
        if (c.nodeType(target.matrix_node) != 'multMatrix'
                or c.nodeType(target.weight_node) != 'multDoubleLinear'
                or not near(_matrix(c.getAttr(target.matrix_node+'.matrixIn[0]')), state.offset_world)
                or not near(_matrix(c.getAttr(target.matrix_node+'.matrixIn[1]')), tuple(om.MMatrix(world).inverse()))
                or c.getAttr(target.weight_node+'.input2') != .1
                or c.attributeQuery('follow'+target.label, node=spec.fk_control, listDefault=True) != [target.weight]
                or check_initial_pose and c.getAttr(attr) != target.weight):
            return False
        matrix_source = (spec.source_rp_pole_target+'.worldMatrix[0]'
                         if spec.source_rp_pole_target and index == len(spec.targets)-1
                         else target.matrix_node+'.matrixSum')
        links.extend(((target.source+'.worldMatrix[0]', target.matrix_node+'.matrixIn[2]'),
                      (matrix_source, spec.blend_node+f'.target[{index}].targetMatrix'),
                      (attr, target.weight_node+'.input1'),
                      (target.weight_node+'.output', spec.blend_node+f'.target[{index}].weight')))
    if spec.use_offset_parent_matrix:
        links.append((spec.blend_node+'.outputMatrix', spec.fk_offset+'.offsetParentMatrix'))
        if any(abs(v) > 1e-8 for kind in ('translate', 'rotate') for v in c.getAttr(spec.fk_offset+'.'+kind)[0]):
            return False
    else:
        dm = spec.output_node
        if c.nodeType(dm) != 'decomposeMatrix' or c.getAttr(dm+'.inputRotateOrder') != c.getAttr(spec.fk_offset+'.rotateOrder'):
            return False
        links.append((spec.blend_node+'.outputMatrix', dm+'.inputMatrix'))
        for kind in ('Translate', 'Rotate', 'Scale'):
            for axis in 'XYZ':
                links.append((dm+'.output'+kind+axis, spec.fk_offset+'.'+kind.lower()+axis))
        for axis, component in zip('XYZ', ('XY', 'XZ', 'YZ')):
            links.append((dm+'.outputShear'+axis, spec.fk_offset+'.shear'+component))
    return (all(c.isConnected(a, b, ignoreUnitConversion=True) for a, b in links)
            and (not check_initial_pose or near(tuple(c.xform(spec.fk_offset, query=True, worldSpace=True, matrix=True)), state.offset_world)))
