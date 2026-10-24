"""Recover source FK features from their saved controls and actual drivers."""
from __future__ import annotations

from adv_py.core.body_fit_aim import capture_body_fit_aim_layouts

from adv_py.core.body_generic_fk import GenericFkFeaturePolicy
from adv_py.core.character_registry import CharacterRegistryError


def derived_properties(host, registration):
    """MEL 79475–79495 regenerates locked Main.height from the live Fit."""
    from adv_py.core.body_character_global import fit_character_height
    c=host._cmds
    mains={channel.node for channel in registration.channels
           if channel.key=='global.translateX'}
    if len(mains)!=1:
        raise CharacterRegistryError('来源重建缺少唯一 Main 控制器')
    plug=next(iter(mains))+'.height'
    joints=host.capture_fit_hierarchy(registration.container).joints
    expected=fit_character_height(tuple(node.world_position for node in joints))
    if (not c.objExists(plug) or c.getAttr(plug,type=True)!='double'
            or not c.getAttr(plug,lock=True) or c.getAttr(plug)!=expected):
        raise CharacterRegistryError('来源重建 Main.height 未按原版 Fit 高度公式生成')
    return frozenset((plug,))


def capture_fk_policy(host, registration):
    from .maya_game_scaling_state import validation
    from .maya_character_body_retirement import validation as deletion_validation
    # Resolve the source detour once for the complete policy capture.
    with deletion_validation(host,registration),validation(host):
        return _capture_fk_policy(host, registration)


def _capture_fk_policy(host, registration):
    from .maya_game_scaling_state import original_scale_connection, original_segment_scale_compensate
    from adv_py.core.body_spline import BodySplinePlan
    c = host._cmds
    from .maya_character_body_retirement import source_record,source_property,removed_graph_node
    retired = {row.path:row for row in registration.retired_body}
    bodies = (*registration.body,*registration.retired_body)
    controls = {}
    from .maya_driving_registration import SDK_MARKER
    sdk_paths = frozenset(node.path for node in registration.nodes
                          if c.objExists(node.path + '.' + SDK_MARKER))
    keys = {channel.key for channel in registration.channels}
    for node in registration.nodes:
        leaf = node.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if (node.node_type == "transform" and leaf.startswith("AdvPy_")
                and leaf.endswith("FK")
                and not leaf.endswith("_InbetweenFK")
                and "|AdvPy_GenericFKControls|" in node.path):
            controls[leaf.removeprefix("AdvPy_")] = node.path
    if not controls and len(registration.body)==1:
        # A source terminal Root has no FK feature layout to retain. It uses
        # the same direct RootX branch on fresh build and staged replacement.
        return GenericFkFeaturePolicy(source_spline_layouts=(),
            source_spline_body_root=registration.body_root)
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
        direct_bodies=[joint.path for joint in bodies
                      if joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]==body_stem
                      and (c.objExists(joint.path+'.advPySourceFkMatrix')
                           or joint.path in retired and 'advPySourceFkMatrix' in dict(retired[joint.path].records))]
        removed_orient = removed_graph_node(host,namespace+orient_name,'orientConstraint') if not orients else None
        direct_matrix=not orients and len(direct_bodies)==1
        if len(orients) != 1 and not direct_matrix and removed_orient is None:
            raise CharacterRegistryError("来源 FK 朝向驱动缺失或不唯一：" + short)
        outputs = (c.listConnections(orients[0] + ".constraintRotateX",
                                   source=False, destination=True, plugs=True) or []) if orients else []
        if removed_orient is not None:
            outputs = [destination for row in registration.retired_body
                       for source,destination in row.incoming
                       if source==removed_orient.path+'.constraintRotateX']
        bendy_constraint = namespace + "AdvPy_BendyDeform" + body_stem
        if direct_matrix:
            from adv_py.core.source_body_matrix import decode_source_body_matrix
            graph=decode_source_body_matrix(source_record(host,direct_bodies[0],'advPySourceFkMatrix'))
            if graph.body!=direct_bodies[0]:
                raise CharacterRegistryError('来源 FK OPM 保存身份变化：'+short)
            drivers=direct_bodies
            scale.add(control)
        elif not outputs and (c.objExists(bendy_constraint) or any(
                joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]==body_stem
                and (c.objExists(joint.path+'.advPySourceBendyMatrix')
                     or joint.path in retired and 'advPySourceBendyMatrix' in dict(retired[joint.path].records))
                for joint in bodies)):
            if c.objExists(bendy_constraint) and c.nodeType(bendy_constraint) != "parentConstraint":
                raise CharacterRegistryError("来源 Bendy 变形驱动身份无效：" + short)
            drivers = [joint.path for joint in bodies
                       if joint.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == body_stem]
        else:
            if len(outputs) != 1 or not outputs[0].endswith(".rotateX"):
                raise CharacterRegistryError("来源 FK 朝向驱动输出不完整：" + short)
            output_node=outputs[0].rsplit(".",1)[0]
            drivers = [output_node] if output_node in retired else c.ls(output_node,long=True) or []
        if len(drivers) != 1 or drivers[0] not in retired and c.nodeType(drivers[0]) != "joint":
            raise CharacterRegistryError("来源 FK 输出不是唯一机制关节：" + short)
        driver = drivers[0]
        if not outputs and not direct_matrix:
            host.validate_body_bendy_handoff(driver)
        if (original_scale_connection(host, control + '.scale',driver + '.scale')
                or all(original_scale_connection(host, control + '.scale' + axis,
                                     driver + '.scale' + axis) for axis in 'XYZ')
                or _sdk_scale_drives(host,registration,control,driver)):
            scale.add(control)
        bendy_scale = namespace + "AdvPy_BendyDeformScale" + body_stem
        if c.objExists(bendy_scale) and c.isConnected(
                control + '.scale',bendy_scale + '.input1'):
            scale.add(control)
        point = c.ls(namespace + prefix + "FKPoint", long=True,
                     type="pointConstraint") or []
        if len(point) > 1:
            raise CharacterRegistryError("来源 FK 位置驱动名称重复：" + short)
        removed_point = removed_graph_node(host,namespace+prefix+'FKPoint','pointConstraint') if not point else None
        if point or removed_point or direct_matrix and source_property(host,driver,'advPySourceFkPoint'):
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
                    and not original_segment_scale_compensate(host, parents[0])
                    and not original_segment_scale_compensate(host, driver)):
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
    from .maya_source_rp_follow import decode as decode_follow, MARKER as FOLLOW_MARKER
    native_rp_controls=frozenset(binding.ik_control for binding in registration.source_limbs
        if c.objExists(binding.ik_control+'.'+FOLLOW_MARKER)
        and any(spec.source_rp for spec in decode_follow(c.getAttr(binding.ik_control+'.'+FOLLOW_MARKER))[0].spaces))
    return GenericFkFeaturePolicy(
        source_aim_layouts=capture_body_fit_aim_layouts(registration.channels),
        source_ik_root_frames=bool(frames),
        source_rp_follow_controls=_pre_aim_controls(native_rp_controls,sdk_paths),
        source_ik_root_modes=tuple(sorted((record.graph.body.rsplit('|',1)[-1],
            record.graph.outputs[0][1].endswith('.offsetParentMatrix')) for record in frames)),
        source_ik_root_offsets=tuple(sorted((record.graph.body.rsplit('|',1)[-1],
            record.offset_matrix) for record in frames)),
        source_rp_measurement_frame=any(record.measurements for record in frames),
        source_twist_reference_main_scale=any(
            node.rsplit('|',1)[-1].endswith('_FitPartTwistMainScaleCM') for node in owned),
        source_bendy_parent_frames=any(c.objExists(node+'.advPyBendySourceControlParent') for node in owned),
        source_bendy_child_aim=any(c.objExists(node+'.advPyBendySourceChildAim') for node in owned),
        source_bendy_micro_no_offset=any(c.objExists(node+'.advPyBendySourceMicroNoOffset') for node in owned),
        source_ik_rotation_orders=any(c.objExists(node+'.advPySourceIkRotationOrder') for node in owned),
        source_fk_follower_parent_scale=any(c.objExists(node+'.advPySourceFkFollowerParentScale') for node in owned),
        source_nonopm_fk_blend_targets=any(c.objExists(node+'.advPySourceNonOpmFkBlendTarget') for node in owned),
        source_nonopm_inverse_scale=any(c.objExists(node+'.advPySourceFkInverseScale') for node in owned),
        source_native_ik_effectors=any(c.objExists(node+'.advPySourceIkEffector') for node in owned),
        source_rp_mode_controls=any(c.objExists(channel.node+'.advPySourceRpMode')
            for channel in registration.channels if channel.attribute=='FKIKBlend'),
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
            for joint in registration.body) or any('advPySourceFkMatrix' in dict(row.records)
                or 'advPySourceEndMatrix' in dict(row.records) for row in registration.retired_body) or any(binding.dynamics_root and
            c.objExists(binding.dynamics_root+'.advPySourceBodyMatrix')
            for binding in registration.source_limbs),
        scale_controls=_pre_aim_controls(scale, sdk_paths), compensated_controls=_pre_aim_controls(compensated, sdk_paths),
        source_bendy_deform_matrix=any(c.objExists(joint.path+'.advPySourceBendyMatrix')
            for joint in registration.body) or any('advPySourceBendyMatrix' in dict(row.records)
                for row in registration.retired_body),
        source_leg_lock_opm=any(c.objExists(node+'.advPySourceLegLockMatrix')
            for node in owned),
        source_root_body_matrix=c.objExists(registration.body_root+'.advPySourceFkMatrix'),
        global_controls=_pre_aim_controls(global_controls, sdk_paths), aim_sources=aim_sources,
        follower_sources=followers, independent_controls=_pre_aim_controls(independent, sdk_paths),
        fkx_joint_controls=frozenset(fkx), point_controls=frozenset(points))


def _pre_aim_controls(controls, sdk_paths=()):
    from adv_py.core.source_limb_aim import pre_aim_control_path
    result = []
    for control in controls:
        original = ''
        parts = []
        for component in control.split('|')[1:]:
            original += '|' + component
            # The replacement's FK features are planned before source SDK
            # layers are restored. Remove only registered insertion objects,
            # including ancestor SDKs over a parent finger/Cup control.
            if original not in sdk_paths:
                parts.append(component)
        result.append(pre_aim_control_path('|' + '|'.join(parts)))
    return frozenset(result)


def _sdk_scale_drives(host,registration,control,driver):
    """SDK ScaleMPD preserves the original FK scale feature on rebuild.

    Match the saved source insertion's exact inputs and output, instead of
    considering any upstream multiplyDivide to be an authored FK feature.
    """
    from .maya_driving_registration import SDK_MARKER
    from adv_py.core.character_registry import safe_json,exact
    from .maya_game_scaling_state import original_scale_connection
    c=host._cmds
    for node in registration.nodes:
        marker=node.path+'.'+SDK_MARKER
        if not c.objExists(marker):continue
        record=exact(safe_json(c.getAttr(marker)),('child','scale'))
        scale=record['scale']
        if scale is None:continue
        exact(scale,('name','kind','values','connections'))
        if scale['kind']!='multiplyDivide':continue
        name=scale['name']
        edges={target:source for source,target in scale['connections']}
        if edges.get('input1')==control+'.scale':
            if (c.isConnected(control+'.scale',name+'.input1')
                    and original_scale_connection(host, name+'.output',driver+'.scale')):
                return True
        elif all(edges.get('input1'+axis)==control+'.scale'+axis for axis in 'XYZ'):
            if all(c.isConnected(control+'.scale'+axis,name+'.input1'+axis)
                   and original_scale_connection(host, name+'.output'+axis,driver+'.scale'+axis)
                   for axis in 'XYZ'):
                return True
    return False
