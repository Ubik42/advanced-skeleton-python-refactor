"""Read native ADV RP correspondence from its authored FKIK attributes.

This is a read-only adapter for original scenes without Python registration.
Every address refers to an existing source node; no rig, channel, or pose is
created to make the scene look like a registered Python character.
"""
from types import SimpleNamespace

from adv_py.core.source_limb_animation import SourceLimbJointBinding, SourceLimbHybridBinding


def _fit_toes(c, end, side):
    """asGetToesJoint / asGetQToesJoints, MEL 11506–11569."""
    if not c.objExists(end):
        return None, ()
    full = c.listRelatives(end, fullPath=True, type='joint', allDescendents=True) or ()
    short = c.listRelatives(end, type='joint', allDescendents=True) or ()
    toes = None
    qtoes = []
    for path, joint in zip(full, short):
        if not c.getAttr(path + '.drawLabel'):
            continue
        label = c.getAttr(path + '.otherType')
        if not c.objExists('FK' + joint + side):
            continue
        if 'Toes' in label and 'QToes' not in label and 'ToesEnd' not in label:
            toes = joint
        if 'QToes' in label:
            chain = tuple(part for part in c.ls(joint, long=True)[0].split('|') if part)
            for name in reversed(chain):
                if name == end:
                    break
                qtoes.append(name)
    return toes, tuple(qtoes)


def read(host, label, side):
    """Native asAlignFKIK RP setup, including source Fit-derived toe ordering."""
    c = host._cmds
    suffix = '_' + side
    mode = 'FKIK' + label + suffix
    if not c.objExists(mode):
        raise ValueError('Object:"' + mode + '" does not exists !')
    if not c.objExists('Pole' + label + suffix):
        raise ValueError('该原版系统属于 Spline，需要来源 Spline 对应记录：' + mode)
    start, middle, end = (c.getAttr(mode + '.' + attribute)
                          for attribute in ('startJoint', 'middleJoint', 'endJoint'))
    required = ('Main', 'FKX' + start + suffix, 'IKX' + start + suffix,
                'IKX' + middle + suffix, 'Pole' + label + suffix, 'FKX' + end + suffix)
    for node in required:
        if not c.objExists(node):
            raise ValueError('Object:"' + node + '" does not exists !')
    if c.objExists('Main.version'):
        version = float(c.getAttr('Main.version'))
        if 6.240 < version < 6.261:
            raise ValueError('Detected Rig version:"' + str(version) + '" which has issues with Switch FK2Ik, Update to the latest version, and run "ReBuild AdvancedSkeleton" to fix this.')
    toes, qtoes = _fit_toes(c, end, suffix)
    primary = (start, middle, end)
    joints = tuple(SourceLimbJointBinding(name + suffix, 'FKX' + name + suffix,
                    'IKX' + name + suffix, 'FK' + name + suffix, 'FK' + name + suffix)
                   for name in (*primary, *qtoes, *((toes,) if toes else ())))
    ik = 'IK' + label + suffix
    pole = 'Pole' + label + suffix
    align = 'AlignIKTo' + end + suffix
    override = 'AlignIKTo' + qtoes[0] + suffix if qtoes else align
    if not c.objExists(override):
        override = align
    reset = tuple(node for node in c.listRelatives(ik, allDescendents=True, type='transform', fullPath=True) or ()
                  if c.sets(node, isMember='ControlSet'))
    lengths = []
    inputs = []
    sign = -1. if side == 'L' else 1.
    middle_length = 'IKX' + middle + suffix + '_IKLenght' + suffix
    measurement = 'IKX' + middle + suffix + '_IKmessureDiv' + suffix
    if c.objExists(middle_length) and c.objExists(measurement):
        for index, (a, b) in enumerate(((start, middle), (middle, end)), 1):
            length = 'IKX' + b + suffix + '_IKLenght' + suffix
            lengths.append(SimpleNamespace(attribute='Lenght' + str(index),
                start_fk='FK' + a + suffix, end_fk='FK' + b + suffix,
                rest_length=float(c.getAttr(length + '.input2X')) * sign, fraction=1.))
            inputs.append((length + '.input2X', measurement + '.input1X', sign))
    hybrids = tuple(SourceLimbHybridBinding('IKhybrid' + name + suffix, 'FKX' + name + suffix)
                    for name in qtoes) if len(qtoes) > 1 else ()
    reverse = 'Roll' + qtoes[-1] + suffix if qtoes and c.objExists(ik + '.toesAim') else None
    binding = SimpleNamespace(label=label, side=side, blend_key=mode + '.FKIKBlend',
        ik_control=ik, pole_control=pole, align=override, primary_align=align,
        middle_index=1, primary_count=3, joints=joints, reset_controls=reset, reset_attributes=(),
        toe_control='IKToes' + suffix if toes else None,
        toe_align='AlignIKToToes' + suffix if toes and c.objExists('AlignIKToToes' + suffix) else None,
        toe_source='FKX' + (toes if toes else qtoes[0]) + suffix if qtoes or toes else None,
        native_qtoes=tuple('FKX' + name + suffix for name in qtoes),
        ik_position_source='FK' + (qtoes[-1] if qtoes else end) + suffix,
        hybrid_controls=hybrids, reverse_roll=reverse, reverse_handle=None,
        lengths=tuple(lengths), native_length_inputs=tuple(inputs),
        ratio_node=measurement + '.input1X' if lengths else None, dynamics_root=None,
        global_control='Main', height=float(c.getAttr('Main.height')),
        leg_aim_control='FKLegAim' + suffix if c.objExists('FKLegAim' + suffix) else None,
        ik_scale_axes=None, pole_offsets=('FKOffset' + middle + suffix, 'FKOffset' + end + suffix))
    controls = tuple(dict.fromkeys((*[node for node in c.sets('ControlSet', query=True) or ()],
                                   ik, pole, *reset, *(row.control for row in joints))))
    channels = []
    for control in controls:
        for attribute in c.listAttr(control, keyable=True) or ():
            channels.append(SimpleNamespace(key=control + '.' + attribute, node=control, attribute=attribute))
    if not any(row.key == binding.blend_key for row in channels):
        channels.append(SimpleNamespace(key=binding.blend_key, node=mode, attribute='FKIKBlend'))
    return SimpleNamespace(channels=tuple(channels), source_limbs=(binding,), spine=None,
                           additional_spines=(), nodes=()), binding
