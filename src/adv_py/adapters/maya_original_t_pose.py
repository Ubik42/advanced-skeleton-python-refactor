"""Original asGoToBuildPose T-pose branch, MEL 12728–12779."""
from .maya_original_control_identity import registration, source_control_from_role
from adv_py.core.source_limb_animation import resolve_source_limb


def apply(host):
    """Move the original Extra layers; leave the FKIK blend value unchanged.

    The body build-pose caller executes this between saved pose channels and
    the GUI/expression/Fit.run overrides, exactly as the original procedure.
    """
    host._require_transaction()
    c = host._cmds
    saved = registration(host)
    required = ('FKExtraHip', 'FKExtraKnee', 'FKExtraAnkle',
                'FKExtraShoulder', 'FKExtraElbow', 'FKExtraWrist',
                'IKExtraLeg', 'PoleExtraLeg')
    completed = []
    for sign, side in ((1, 'R'), (-1, 'L')):
        suffix = '_' + side
        nodes = {role: source_control_from_role(host, role + suffix)
                 for role in required}
        for role in required:
            if not c.objExists(nodes[role]):
                c.warning('Required node: "' + role + suffix
                          + '" Not Found, Unable to go to Tpose')
                return tuple(completed)
        if saved is None:
            leg_scene = arm_scene = None
        else:
            leg_scene = arm_scene = saved
            leg = resolve_source_limb(saved, 'Leg', side)
            arm = resolve_source_limb(saved, 'Arm', side)
        host._transaction_changed = True
        for role, rotation in (
                ('FKExtraHip', (0, -90, -90 * sign + 2)),
                ('FKExtraKnee', (0, -90, -90 * sign - 2)),
                ('FKExtraAnkle', (90 * sign, 0, -90 * sign)),
                ('FKExtraShoulder', (-90 * sign, 0, 180)),
                ('FKExtraElbow', (-90 * sign, 0, 180)),
                ('FKExtraWrist', (-90 * sign, 0, 180))):
            c.xform(nodes[role], worldSpace=True, rotation=rotation)
        if saved is None:
            from .maya_original_rp_scene import read
            leg_scene, leg = read(host, 'Leg', side)
        host.align_source_character_limb(leg_scene, leg, 'ik')
        position = c.xform(leg.ik_control, query=True, objectSpace=True, translation=True)
        rotation = c.xform(leg.ik_control, query=True, objectSpace=True, rotation=True)
        c.xform(nodes['IKExtraLeg'], objectSpace=True,
                translation=position, rotation=rotation)
        c.xform(leg.ik_control, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
        position = c.xform(leg.pole_control, query=True, objectSpace=True, translation=True)
        c.xform(nodes['PoleExtraLeg'], objectSpace=True, translation=position)
        c.xform(nodes['PoleExtraLeg'], worldSpace=True, rotation=(0, 0, 0))
        c.xform(leg.pole_control, objectSpace=True, translation=(0, 0, 0))
        if saved is None:
            arm_scene, arm = read(host, 'Arm', side)
        host.align_source_character_limb(arm_scene, arm, 'ik')
        c.xform(arm.pole_control, objectSpace=True, translation=(0, 0, 0))
        position = c.xform(arm.ik_control, query=True, worldSpace=True, translation=True)
        extra = source_control_from_role(host, 'PoleExtraArm' + suffix)
        c.xform(extra, worldSpace=True, translation=position)
        c.setAttr(extra + '.tx', 0)
        c.setAttr(extra + '.tz', 0)
        c.xform(extra, worldSpace=True, rotation=(0, 0, 0))
        completed.append(side)
    return tuple(completed)
