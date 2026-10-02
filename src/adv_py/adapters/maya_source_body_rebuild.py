"""Recover source FK features from their saved controls and actual drivers."""
from __future__ import annotations

from adv_py.core.body_generic_fk import GenericFkFeaturePolicy
from adv_py.core.character_registry import CharacterRegistryError


def capture_fk_policy(host, registration):
    from adv_py.core.body_spline import BodySplinePlan
    c = host._cmds
    controls = {}
    keys = {channel.key for channel in registration.channels}
    for node in registration.nodes:
        leaf = node.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if (node.node_type == "transform" and leaf.startswith("AdvPy_")
                and leaf.endswith("FK")
                and not leaf.endswith("_InbetweenFK")
                and "|AdvPy_GenericFKControls|" in node.path):
            controls[leaf.removeprefix("AdvPy_")] = node.path
    if "Root_MFK" not in controls:
        raise CharacterRegistryError("来源重建缺少 Root FK 控制身份")
    by_leaf = {}
    for node in registration.nodes:
        by_leaf.setdefault(node.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1], []).append(node)
    owned={node.path for node in registration.nodes}
    if c.objExists('AllSet'):
        owned.update(host.capture_body_all_set_members())
    scale, compensated, independent, global_controls = set(), set(), set(), set()
    fkx, points = set(), set()
    for stem, control in controls.items():
        leaf = control.rsplit("|", 1)[-1]
        short = leaf.rsplit(":", 1)[-1]
        namespace = leaf[:-len(short)]
        body_stem = stem.removesuffix("FK")
        prefix = "AdvPy_" + body_stem
        orient_name = ("AdvPy_SplineBaseFKOrient" if stem == "SplineBaseFK"
                       else prefix + "FKOrient")
        orients = c.ls(namespace + orient_name, long=True, type="orientConstraint") or []
        direct_bodies=[joint.path for joint in registration.body
                      if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]==body_stem
                      and c.objExists(joint.path+'.advPySourceFkMatrix')]
        direct_matrix=not orients and len(direct_bodies)==1
        if len(orients) != 1 and not direct_matrix:
            raise CharacterRegistryError("来源 FK 朝向驱动缺失或不唯一：" + short)
        outputs = (c.listConnections(orients[0] + ".constraintRotateX",
                                   source=False, destination=True, plugs=True) or []) if orients else []
        bendy_constraint = namespace + "AdvPy_BendyDeform" + body_stem
        if direct_matrix:
            from adv_py.core.source_body_matrix import decode_source_body_matrix
            graph=decode_source_body_matrix(c.getAttr(direct_bodies[0]+'.advPySourceFkMatrix'))
            if graph.body!=direct_bodies[0]:
                raise CharacterRegistryError('来源 FK OPM 保存身份变化：'+short)
            drivers=direct_bodies
            scale.add(control)
        elif not outputs and (c.objExists(bendy_constraint) or any(
                joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]==body_stem
                and c.objExists(joint.path+'.advPySourceBendyMatrix')
                for joint in registration.body)):
            if c.objExists(bendy_constraint) and c.nodeType(bendy_constraint) != "parentConstraint":
                raise CharacterRegistryError("来源 Bendy 变形驱动身份无效：" + short)
            drivers = [joint.path for joint in registration.body
                       if joint.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == body_stem]
        else:
            if len(outputs) != 1 or not outputs[0].endswith(".rotateX"):
                raise CharacterRegistryError("来源 FK 朝向驱动输出不完整：" + short)
            drivers = c.ls(outputs[0].rsplit(".", 1)[0], long=True) or []
        if len(drivers) != 1 or c.nodeType(drivers[0]) != "joint":
            raise CharacterRegistryError("来源 FK 输出不是唯一机制关节：" + short)
        driver = drivers[0]
        if not outputs and not direct_matrix:
            host.validate_body_bendy_handoff(driver)
        if (c.isConnected(control + '.scale',driver + '.scale')
                or all(c.isConnected(control + '.scale' + axis,
                                     driver + '.scale' + axis) for axis in 'XYZ')):
            scale.add(control)
        bendy_scale = namespace + "AdvPy_BendyDeformScale" + body_stem
        if c.objExists(bendy_scale) and c.isConnected(
                control + '.scale',bendy_scale + '.input1'):
            scale.add(control)
        point = c.ls(namespace + prefix + "FKPoint", long=True,
                     type="pointConstraint") or []
        if len(point) > 1:
            raise CharacterRegistryError("来源 FK 位置驱动名称重复：" + short)
        if point or direct_matrix and c.getAttr(driver+'.advPySourceFkPoint'):
            points.add(short)
        receivers = by_leaf.get("AdvPy_" + stem + "X", ())
        if len(receivers) > 1:
            raise CharacterRegistryError("来源 FKX 名称重复：" + short)
        if receivers and receivers[0].node_type == "joint":
            fkx.add(short)
        offsets = by_leaf.get("AdvPy_" + stem + "Offset", ())
        if len(offsets) != 1:
            raise CharacterRegistryError("来源 FK Offset 缺失或重复：" + short)
        if c.attributeQuery("inheritScale", node=control, exists=True):
            compensated.add(control)
            if not c.getAttr(offsets[0].path + ".inheritsTransform"):
                independent.add(control)
        elif by_leaf.get("AdvPy_" + driver.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                         + "_FkScaleCompWorldFKPS1"):
            compensated.add(control)
        else:
            parents = c.listRelatives(offsets[0].path, parent=True, fullPath=True) or []
            if (len(parents) == 1 and c.nodeType(parents[0]) == "joint"
                    and not c.getAttr(parents[0] + ".segmentScaleCompensate")
                    and not c.getAttr(driver + ".segmentScaleCompensate")):
                compensated.add(control)
        if "generic.global." + short + ".Global" in keys:
            global_controls.add(control)
    followers = frozenset(leaf.removeprefix("AdvPy_GenericFKFollow_")
                          for leaf in by_leaf if leaf.startswith("AdvPy_GenericFKFollow_"))
    # Generic Aim semantic stems contain the generated prefix; Fit selection
    # uses the original source name shared by both side controls.
    aim_sources = frozenset(channel.key.split(".")[2].removeprefix("AdvPy_")
                           .removesuffix("_FitAim")
                           for channel in registration.channels
                           if channel.key.startswith("generic.aim.")
                           and channel.key.endswith(".follow"))
    from adv_py.core.source_limb_root_frame import decode_record
    frames=tuple(decode_record(c.getAttr(node+'.advPySourceIkRootFrame'))
                 for node in owned if c.objExists(node+'.advPySourceIkRootFrame'))
    return GenericFkFeaturePolicy(
        source_ik_root_frames=bool(frames),
        source_rp_measurement_frame=any(record.measurements for record in frames),
        source_twist_reference_main_scale=any(
            node.rsplit('|',1)[-1].endswith('_FitPartTwistMainScaleCM') for node in owned),
        source_spline_layouts=tuple(plan for plan in
            (registration.spine,*registration.additional_spines) if isinstance(plan,BodySplinePlan)),
        source_spline_body_root=registration.body_root,
        source_rp_dynamics=any(key.startswith('source.rp.') for key in keys),
        source_foot_aim=any(key.startswith('source.foot.') and key.endswith('.toesAim') for key in keys),
        source_leg_aim=any(key.startswith('source.legAim.') for key in keys),
        source_rp_scale_axes=any(c.objExists(binding.ik_control+'.advPySourceRpScaleLayout')
                                 for binding in registration.source_limbs),
        source_rp_pole_sources=any(binding.dynamics_root and
            c.objExists(binding.dynamics_root+'.advPySourceRpPoleSources')
            for binding in registration.source_limbs),
        source_rp_x_translation=any(binding.dynamics_root and
            c.objExists(binding.dynamics_root+'.advPySourceRpXTranslation')
            for binding in registration.source_limbs),
        source_rp_part_scale=any(binding.dynamics_root and
            c.objExists(binding.dynamics_root+'.advPySourceRpPartScale')
            for binding in registration.source_limbs),
        source_rp_build_pole=any(c.objExists(binding.pole_control+'.advPySourceRpPolePlacement')
                               for binding in registration.source_limbs),
        source_untwister_receiver=any(
            c.objExists(node+'.advPySourceUnTwisterReceiver')
            for node in owned),
        source_body_matrix=any(c.objExists(joint.path+'.advPySourceFkMatrix')
            or c.objExists(joint.path+'.advPySourceEndMatrix')
            for joint in registration.body) or any(binding.dynamics_root and
            c.objExists(binding.dynamics_root+'.advPySourceBodyMatrix')
            for binding in registration.source_limbs),
        scale_controls=_pre_aim_controls(scale), compensated_controls=_pre_aim_controls(compensated),
        source_bendy_deform_matrix=any(c.objExists(joint.path+'.advPySourceBendyMatrix')
            for joint in registration.body),
        source_leg_lock_opm=any(c.objExists(node+'.advPySourceLegLockMatrix')
            for node in owned),
        source_root_body_matrix=c.objExists(registration.body_root+'.advPySourceFkMatrix'),
        global_controls=_pre_aim_controls(global_controls), aim_sources=aim_sources,
        follower_sources=followers, independent_controls=_pre_aim_controls(independent),
        fkx_joint_controls=frozenset(fkx), point_controls=frozenset(points))


def _pre_aim_controls(controls):
    from adv_py.core.source_limb_aim import pre_aim_control_path
    return frozenset(pre_aim_control_path(control) for control in controls)
