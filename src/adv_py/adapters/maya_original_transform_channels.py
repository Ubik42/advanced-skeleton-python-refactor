"""Native asAlign and asLockAttr operations, ADV 6.925 MEL 10421–10558."""


def align_original_transform(commands, node, target, translation=True,
                             rotation=True, joint_orient=False, rotate_order=False):
    """Align through native parenting, including Maya's generated joint frame.

    Parent/reset/restore preserves the source's handling of scale and joint
    orientation. Copying a world matrix or Euler angles is not equivalent.
    Return the restored path because parenting can change a full DAG address.
    """
    previous = commands.listRelatives(node, parent=True, fullPath=True) or []
    target_path = (commands.ls(target, long=True) or [target])[0]
    node = commands.parent(node, target, absolute=True)[0]
    parent = (commands.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    generated = parent if parent != target_path else None
    if translation:
        commands.xform(node, objectSpace=True, translation=(0., 0., 0.))
        if generated:
            commands.xform(generated, objectSpace=True, translation=(0., 0., 0.))
    if rotate_order:
        commands.setAttr(node + '.rotateOrder', commands.getAttr(target + '.rotateOrder'))
    if rotation:
        commands.xform(node, objectSpace=True, rotation=(0., 0., 0.))
        if generated:
            commands.xform(generated, objectSpace=True, rotation=(0., 0., 0.))
    if joint_orient and rotation:
        commands.setAttr(node + '.jointOrient', 0., 0., 0., type='float3')
    if previous and commands.objExists(previous[0]):
        node = commands.parent(node, previous[0], absolute=True)[0]
    else:
        node = commands.parent(node, world=True, absolute=True)[0]
    if generated:
        commands.delete(generated)
    if joint_orient and not rotation:
        if commands.getAttr(target + '.rotateOrder') != 0:
            getattr(commands, 'raw', commands).warning(
                'Aligning jointOrient for objects without aligning rotation, '
                'and non-default rotationOrder, may cause problems.')
        constraint = commands.orientConstraint(target, node)
        angles = commands.xform(node, query=True, objectSpace=True, rotation=True)
        commands.delete(constraint[0])
        commands.setAttr(node + '.jointOrient', *angles, type='float3')
        commands.setAttr(node + '.rotate', 0., 0., 0., type='float3')
    return (commands.ls(node, long=True) or [node])[0]


def lock_original_transform_channels(commands, node, translation=False,
                                     rotation=False, scale=False, visibility=False):
    """Set child channel lock/keyability, then unlock compound parents.

    Source keeps translate/rotate/scale compounds non-keyable when unlocked;
    unlocking only their children leaves user-locked duplicated meshes unusable.
    """
    channels = (("translate", translation), ("rotate", rotation), ("scale", scale))
    for axis in "XYZ":
        for channel, locked in channels:
            commands.setAttr(node + "." + channel + axis,
                             lock=bool(locked), keyable=not locked)
    commands.setAttr(node + ".v", lock=bool(visibility), keyable=not visibility)
    for channel, locked in channels:
        if not locked:
            commands.setAttr(node + "." + channel, lock=False, keyable=False)


def reset_original_custom_attributes(commands, node, *, set_value=None, source_name=None):
    """asSetCustomAttrToDefault, MEL 11486–11505.

    Read each scene attribute's authored default, preserving edits and the
    source PoleLeg.follow compatibility case. Skip strings and unavailable
    animation channels exactly as MEL does.
    """
    for attribute in commands.listAttr(node,userDefined=True) or ():
        plug=node+'.'+attribute
        if (commands.getAttr(plug,type=True)=='string'
                or not commands.getAttr(plug,settable=True)
                or not commands.getAttr(plug,keyable=True)):
            continue
        value=commands.attributeQuery(attribute,node=node,listDefault=True)[0]
        if 'PoleLeg' in (source_name or node) and attribute=='follow':value=10.
        if set_value is None:commands.setAttr(plug,value)
        else:set_value(node,attribute,float(value))


def original_matrix_transform_values(commands, node, matrix_attribute, transform_attribute):
    """asTransformValuesFromMatrixPlug, MEL 26347–26363, native Euler order."""
    outputs = {'rotate':'outputRotate', 'translate':'outputTranslate', 'scale':'outputScale'}
    if transform_attribute not in outputs:
        raise ValueError('矩阵分解通道需要 rotate / translate / scale')
    selected = commands.ls(selection=True) or []
    temporary = 'tempDecomposeMatrix'
    if commands.objExists(temporary):
        commands.delete(temporary)
    temporary = commands.createNode('decomposeMatrix', name=temporary)
    try:
        commands.setAttr(temporary + '.inputRotateOrder', commands.getAttr(node + '.rotateOrder'))
        commands.connectAttr(node + '.' + matrix_attribute, temporary + '.inputMatrix')
        return tuple(commands.getAttr(temporary + '.' + outputs[transform_attribute])[0])
    finally:
        commands.delete(temporary)
        commands.select(selected, replace=True) if selected else commands.select(clear=True)


def original_transform_values(commands, node, transform_attribute):
    """asGetTransformValues, MEL 26365–26384, including per-joint OPM override.

    OPM rigs still have conventional lip/lid joint channels. Only decompose
    the offset matrix when the original Fit switch is on AND this particular
    node has an OPM connection. A static offset matrix alone is not enough.
    """
    if transform_attribute not in ('translate', 'rotate', 'scale'):
        raise ValueError('原版变换读取需要 translate / rotate / scale')
    opm = (commands.objExists('FitSkeleton.useOffsetParentMatrix')
           and commands.getAttr('FitSkeleton.useOffsetParentMatrix'))
    if opm and commands.listConnections(node + '.offsetParentMatrix'):
        return original_matrix_transform_values(commands, node, 'offsetParentMatrix', transform_attribute)
    result = commands.getAttr(node + '.' + transform_attribute)
    if len(result) == 1 and isinstance(result[0], (list, tuple)):
        result = result[0]
    return tuple(result)
