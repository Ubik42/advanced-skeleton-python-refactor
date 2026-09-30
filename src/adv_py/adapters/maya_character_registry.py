from dataclasses import replace
import re

from adv_py.core.character_registry import (
    FORMAT, REGISTRY_NAME, CharacterRegistryError, CharacterNode, CharacterBindJoint,
    CharacterRegistration, encode_registration, decode_registration,
)
from adv_py.application.body_rig_validation import body_bind_pose_matches
from adv_py.core.body_skeleton import audit_body_provenance, oriented_body_provenance


class MayaCharacterRegistryMixin:
    def capture_body_generic_fk_feature_policy(self, registration):
        """Keep a rebuild's generic FK graph aligned with the saved rig."""
        from adv_py.core.body_generic_fk import GenericFkFeaturePolicy
        c = self._cmds
        stems = {
            channel.key[len('generic.fk.'):].split('.', 1)[0]
            for channel in registration.channels
            if channel.key.startswith('generic.fk.')}
        by_leaf = {}
        for node in registration.nodes:
            by_leaf.setdefault(node.path.rsplit('|', 1)[-1]
                               .rsplit(':', 1)[-1], []).append(node.path)
        standard_fkx_joints = set()
        hand_fkx_joints = set()
        torso_fkx_joints = set()
        for node in registration.nodes:
            leaf = node.path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            if (node.node_type != 'joint'
                    or not (leaf == 'AdvPy_RootFKX'
                            or (leaf.startswith('AdvPy_Torso')
                                and leaf.endswith('FKX')))):
                continue
            parent = node.parent
            if parent is None:
                raise CharacterRegistryError('Torso FKX 缺少控制器父级：' + leaf)
            control = parent.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            if control.endswith('FKSub'):
                parent = parent.rsplit('|', 1)[0]
                control = parent.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            if not control.endswith('FK') or parent not in by_leaf.get(
                    control, ()):
                raise CharacterRegistryError('Torso FKX 父级不是 FK 控制：' + leaf)
            torso_fkx_joints.add(control)
        standard_independent = set()
        for leaf, offsets in by_leaf.items():
            if not leaf.startswith('AdvPy_'):
                continue
            if 'FKOffset' in leaf:
                control_leaf = leaf.replace('FKOffset', 'FK')
            elif leaf.startswith('AdvPy_Torso') and leaf.endswith('Offset'):
                control_leaf = leaf[:-len('Offset')] + 'FK'
            else:
                continue
            controls = by_leaf.get(control_leaf, ())
            if len(offsets) == 1 and len(controls) == 1:
                if not bool(c.getAttr(offsets[0] + '.inheritsTransform')):
                    standard_independent.add(controls[0])
        for side in ('R', 'L'):
            for joint in ('Shoulder', 'Elbow', 'Wrist', 'Hip', 'Knee',
                          'Ankle', 'Toes', 'ToesEnd'):
                leaf = 'AdvPy_' + joint + 'FKX_' + side
                matches = by_leaf.get(leaf, ())
                if len(matches) > 1:
                    raise CharacterRegistryError(
                        '旧标准 FKX 节点名称不唯一：' + leaf)
                if matches and c.nodeType(matches[0]) == 'joint':
                    standard_fkx_joints.add('AdvPy_' + joint + 'FK_' + side)
            for digit in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
                for index in range(1, 5):
                    leaf = f'AdvPy_{digit}{index}FKX_{side}'
                    matches = by_leaf.get(leaf, ())
                    if len(matches) > 1:
                        raise CharacterRegistryError(
                            '旧 Hand FKX 节点名称不唯一：' + leaf)
                    if matches and c.nodeType(matches[0]) == 'joint':
                        hand_fkx_joints.add(
                            f'AdvPy_{digit}{index}FK_{side}')
        body_by_leaf = {joint.path.rsplit('|', 1)[-1]
                        .rsplit(':', 1)[-1]: joint.path
                        for joint in registration.body}
        hand_points = set()
        standard_points = set()
        torso_points = set()
        def point_matches_orient(point_name, orient_name,
                                 expected_joint=None):
            points = c.ls(point_name, long=True,
                          type='pointConstraint') or []
            if len(points) > 1:
                raise CharacterRegistryError(
                    'FK 位置约束名称不唯一：' + point_name)
            if not points:
                return False
            orients = c.ls(orient_name, long=True,
                           type='orientConstraint') or []
            if len(orients) != 1:
                raise CharacterRegistryError(
                    'FK 朝向约束缺失或不唯一：' + orient_name)
            point_targets = c.pointConstraint(
                points[0], query=True, targetList=True) or []
            orient_targets = c.orientConstraint(
                orients[0], query=True, targetList=True) or []
            point_outputs = c.listConnections(
                points[0] + '.constraintTranslateX',
                source=False, destination=True, plugs=True) or []
            orient_outputs = c.listConnections(
                orients[0] + '.constraintRotateX',
                source=False, destination=True, plugs=True) or []
            def resolved_target(targets):
                return (c.ls(targets[0], long=True) or []
                        if len(targets) == 1 else [])
            def resolved_output(outputs, suffix):
                if len(outputs) != 1 or not outputs[0].endswith(suffix):
                    return []
                return c.ls(outputs[0].rsplit('.', 1)[0], long=True) or []
            point_sources = resolved_target(point_targets)
            orient_sources = resolved_target(orient_targets)
            point_driven = resolved_output(point_outputs, '.translateX')
            orient_driven = resolved_output(orient_outputs, '.rotateX')
            if (len(point_sources) != 1
                    or point_sources != orient_sources
                    or len(point_driven) != 1
                    or point_driven != orient_driven
                    or c.nodeType(point_driven[0]) != 'joint'
                    or (expected_joint is not None
                        and point_driven != [expected_joint])):
                raise CharacterRegistryError(
                    'FK 位置约束与朝向约束驱动链不一致：' + point_name)
            for axis in 'YZ':
                point_axis_outputs = c.listConnections(
                    points[0] + '.constraintTranslate' + axis,
                    source=False, destination=True, plugs=True) or []
                orient_axis_outputs = c.listConnections(
                    orients[0] + '.constraintRotate' + axis,
                    source=False, destination=True, plugs=True) or []
                if (resolved_output(
                        point_axis_outputs, '.translate' + axis)
                        != point_driven
                        or resolved_output(
                            orient_axis_outputs, '.rotate' + axis)
                        != orient_driven):
                    raise CharacterRegistryError(
                        'FK 位置或朝向约束部分轴接线缺失：' + point_name)
            return True
        root_leaf = registration.body_root.rsplit('|', 1)[-1]
        root_namespace = (root_leaf.rsplit(':', 1)[0] + ':'
                          if ':' in root_leaf else '')
        pelvis_point = c.ls(root_namespace + 'AdvPy_TorsoPelvisPoint', long=True,
                            type='pointConstraint') or []
        if len(pelvis_point) != 1:
            raise CharacterRegistryError(
                'Torso Root 位置约束缺失或不唯一')
        pelvis_targets = c.pointConstraint(
            pelvis_point[0], query=True, targetList=True) or []
        if len(pelvis_targets) != 1:
            raise CharacterRegistryError('Torso Root 位置来源不唯一')
        pelvis_outputs = c.listConnections(
            pelvis_point[0] + '.constraintTranslateX',
            source=False, destination=True, plugs=True) or []
        if (len(pelvis_outputs) != 1
                or not pelvis_outputs[0].endswith('.translateX')
                or (c.ls(pelvis_outputs[0].rsplit('.', 1)[0],
                         long=True) or []) != [registration.body_root]):
            raise CharacterRegistryError('Torso Root 位置目标不是 Body 根')
        for axis in 'YZ':
            outputs = c.listConnections(
                pelvis_point[0] + '.constraintTranslate' + axis,
                source=False, destination=True, plugs=True) or []
            if (len(outputs) != 1
                    or not outputs[0].endswith('.translate' + axis)
                    or (c.ls(outputs[0].rsplit('.', 1)[0],
                             long=True) or []) != [registration.body_root]):
                raise CharacterRegistryError(
                    'Torso Root 位置约束部分轴接线缺失')
        pelvis_source = c.ls(pelvis_targets[0], long=True) or []
        root_fkx = by_leaf.get('AdvPy_RootFKX', ())
        root_control = by_leaf.get('AdvPy_TorsoRoot_MFK', ())
        if (len(pelvis_source) != 1
                or (pelvis_source != list(root_fkx)
                    and pelvis_source != list(root_control))):
            raise CharacterRegistryError(
                'Torso Root 位置来源不属于原控制链')
        root_point_from_fkx = pelvis_source == list(root_fkx)
        from adv_py.core.body_spline import BodySplinePlan
        spline_axis = isinstance(registration.spine, BodySplinePlan)
        axial_point_name = root_namespace + (
            'AdvPy_SplineFKRootPoint' if spline_axis
            else 'AdvPy_SpineFKRootPoint')
        axial_orient_name = root_namespace + (
            'AdvPy_SplineBaseFKOrient' if spline_axis
            else 'AdvPy_SpineBaseFKOrient')
        axial_points = c.ls(axial_point_name, long=True,
                            type='pointConstraint') or []
        axial_orients = c.ls(axial_orient_name, long=True,
                             type='orientConstraint') or []
        if len(axial_points) != 1 or len(axial_orients) != 1:
            raise CharacterRegistryError('轴向 FK 起点约束缺失或不唯一')
        axial_targets = c.pointConstraint(
            axial_points[0], query=True, targetList=True) or []
        axial_orient_targets = c.orientConstraint(
            axial_orients[0], query=True, targetList=True) or []
        if len(axial_targets) != 1 or len(axial_orient_targets) != 1:
            raise CharacterRegistryError('轴向 FK 起点来源不唯一')
        axial_source = c.ls(axial_targets[0], long=True) or []
        axial_receiver = c.ls(axial_orient_targets[0], long=True) or []
        axial_control = registration.spine.fk_controls[0]
        axial_proxy_name = root_namespace + 'AdvPy_Root_M_InbetweenFKX'
        axial_proxy = c.ls(axial_proxy_name, long=True,
                           type='joint') or []
        owned_axial_proxy = (
            axial_receiver == axial_proxy and len(axial_proxy) == 1
            and c.objExists(axial_proxy_name + '.advPyInbetweenFkOwner')
            and c.getAttr(axial_proxy_name + '.advPyInbetweenFkOwner')
            == 'adv_py.inbetween_fk.v1')
        if (len(axial_source) != 1 or len(axial_receiver) != 1
                or not (axial_receiver[0] == axial_control
                        or axial_receiver[0].startswith(axial_control + '|')
                        or owned_axial_proxy)
                or axial_source not in (
                    [registration.spine.pelvis_control],
                    axial_receiver)):
            raise CharacterRegistryError('轴向 FK 起点位置来源不属于原控制链')
        axial_point_from_receiver = axial_source == axial_receiver
        for axis in 'XYZ':
            outputs = c.listConnections(
                axial_points[0] + '.constraintTranslate' + axis,
                source=False, destination=True, plugs=True) or []
            if (len(outputs) != 1
                    or not outputs[0].endswith('.translate' + axis)
                    or (c.ls(outputs[0].rsplit('.', 1)[0],
                             long=True) or [])
                    != [registration.spine.joints[0].path]):
                raise CharacterRegistryError(
                    '轴向 FK 起点位置目标不是 FK 根关节')
        for node in registration.nodes:
            leaf = node.path.rsplit('|', 1)[-1]
            short = leaf.rsplit(':', 1)[-1]
            if (not short.startswith('AdvPy_Torso')
                    or not short.endswith('FK')
                    or short == 'AdvPy_TorsoRoot_MFK'):
                continue
            namespace = (leaf.rsplit(':', 1)[0] + ':'
                         if ':' in leaf else '')
            point_name = namespace + short.removesuffix('FK') + 'Point'
            orient_name = namespace + short.removesuffix('FK') + 'Orient'
            expected = body_by_leaf.get(
                short.removesuffix('FK').removeprefix('AdvPy_Torso'))
            if point_matches_orient(point_name, orient_name, expected):
                torso_points.add(short)
        for side in ('R', 'L'):
            for joint in ('Shoulder', 'Elbow', 'Wrist', 'Hip', 'Knee',
                          'Ankle', 'Toes', 'ToesEnd'):
                control_leaf = f'AdvPy_{joint}FK_{side}'
                controls = by_leaf.get(control_leaf, ())
                if len(controls) > 1:
                    raise CharacterRegistryError(
                        '标准 FK 控制器名称不唯一：' + control_leaf)
                if not controls:
                    continue
                control_name = controls[0].rsplit('|', 1)[-1]
                namespace = (control_name.rsplit(':', 1)[0] + ':'
                             if ':' in control_name else '')
                point_name = namespace + f'AdvPy_{joint}FKPoint_{side}'
                orient_name = (namespace + f'AdvPy_{joint}FKOrient_{side}')
                expected = body_by_leaf.get(f'{joint}_{side}')
                if point_matches_orient(point_name, orient_name, expected):
                    standard_points.add(control_leaf)
        for side in ('R', 'L'):
            for digit in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
                for index in range(1, 5):
                    control_leaf = f'AdvPy_{digit}{index}FK_{side}'
                    controls = by_leaf.get(control_leaf, ())
                    if len(controls) > 1:
                        raise CharacterRegistryError(
                            'Hand FK 控制器名称不唯一：' + control_leaf)
                    if not controls:
                        continue
                    control_name = controls[0].rsplit('|', 1)[-1]
                    namespace = (control_name.rsplit(':', 1)[0] + ':'
                                 if ':' in control_name else '')
                    point_name = (namespace + f'AdvPy_{digit}{index}'
                                  f'FKPoint_{side}')
                    orient_name = (namespace + f'AdvPy_{digit}{index}'
                                   f'FKOrient_{side}')
                    expected = body_by_leaf.get(
                        f'{digit}{index}_{side}')
                    if point_matches_orient(point_name, orient_name,
                                            expected):
                        hand_points.add(control_leaf)
        scale = set()
        compensated = set()
        independent = set()
        bendy_scales = set()
        fkx_joints = set()
        point_controls = set()
        twist_rewired = set()
        globally_driven = set()
        keys = {channel.key for channel in registration.channels}
        for stem in stems:
            controls = by_leaf.get('AdvPy_' + stem, ())
            body = body_by_leaf.get(stem.removesuffix('FK'))
            if len(controls) != 1 or body is None:
                raise CharacterRegistryError(
                    '旧通用 FK 控制器或 Body 关节无法唯一定位：' + stem)
            control = controls[0]
            control_leaf = control.rsplit('|', 1)[-1]
            namespace = (control_leaf.rsplit(':', 1)[0] + ':'
                         if ':' in control_leaf else '')
            point_name = (namespace + 'AdvPy_'
                          + stem.removesuffix('FK') + 'FKPoint')
            points = c.ls(point_name, long=True,
                          type='pointConstraint') or []
            if len(points) > 1:
                raise CharacterRegistryError(
                    '旧通用 FK 位置约束名称不唯一：' + stem)
            if points:
                orient_name = namespace + 'AdvPy_' + stem + 'Orient'
                point_matches_orient(point_name, orient_name, body)
                outputs = c.listConnections(
                    points[0] + '.constraintTranslateX',
                    source=False, destination=True, plugs=True) or []
                if (len(outputs) != 1
                        or not outputs[0].endswith('.translateX')
                        or (c.ls(outputs[0].rsplit('.', 1)[0],
                                 long=True) or []) != [body]):
                    raise CharacterRegistryError(
                        '旧通用 FK 位置约束接线无效：' + stem)
                point_controls.add(control_leaf.rsplit(':', 1)[-1])
            fkx = by_leaf.get('AdvPy_' + stem + 'X', ())
            if len(fkx) > 1:
                raise CharacterRegistryError(
                    '旧通用 FKX 节点名称不唯一：' + stem)
            if fkx and c.nodeType(fkx[0]) == 'joint':
                fkx_joints.add(control.rsplit('|', 1)[-1]
                               .rsplit(':', 1)[-1])
            sources = tuple(c.connectionInfo(
                body + '.scale' + axis, sourceFromDestination=True)
                for axis in 'XYZ')
            expected = tuple(control + '.scale' + axis for axis in 'XYZ')
            body_leaf = body.rsplit('|', 1)[-1]
            body_namespace = (body_leaf.rsplit(':', 1)[0] + ':'
                              if ':' in body_leaf else '')
            bendy_scale = (body_namespace + 'AdvPy_'
                           + body_leaf.rsplit(':', 1)[-1]
                           + 'BendyFKScale')
            if sources == expected:
                scale.add(control)
            elif c.objExists(bendy_scale):
                if (c.nodeType(bendy_scale) != 'multiplyDivide'
                        or int(c.getAttr(bendy_scale + '.operation')) != 1
                        or c.connectionInfo(body + '.scale',
                                            sourceFromDestination=True)
                        != bendy_scale + '.output'
                        or c.connectionInfo(bendy_scale + '.input2',
                                            sourceFromDestination=True)
                        != control + '.scale'
                        or not c.connectionInfo(
                            bendy_scale + '.input1',
                            sourceFromDestination=True)):
                    raise CharacterRegistryError(
                        '旧通用 Bendy FK 缩放图无效：' + stem)
                bendy_scales.add(control)
            elif any(sources):
                bendy_source = c.connectionInfo(
                    body + '.scale', sourceFromDestination=True)
                bendy_node = (bendy_source.split('.', 1)[0]
                              if bendy_source else '')
                if (not bendy_source.endswith('.output')
                        or not bendy_node.rsplit(':', 1)[-1].startswith(
                            'AdvPy_BendyDeformScale')
                        or not c.objExists(bendy_node)
                        or c.nodeType(bendy_node) != 'multiplyDivide'):
                    raise CharacterRegistryError(
                        '旧通用 FK 缩放连接不是完整的直驱图：' + stem)
            if c.attributeQuery('inheritScale', node=control, exists=True):
                compensated.add(control)
                offsets = by_leaf.get('AdvPy_' + stem + 'Offset', ())
                if len(offsets) != 1:
                    raise CharacterRegistryError(
                        '旧通用 FK 补偿层无法唯一定位：' + stem)
                if not bool(c.getAttr(offsets[0] + '.inheritsTransform')):
                    independent.add(control)
            else:
                # New non-OPM rigs use MEL's FKPS/SSC branch rather than an
                # inheritScale matrix graph. Retain it across rebuilds.
                prefix = ('AdvPy_' + stem.removesuffix('FK')
                          + '_FkScaleCompWorld')
                ps1 = by_leaf.get(prefix + 'FKPS1', ())
                if len(ps1) > 1:
                    raise CharacterRegistryError(
                        '旧通用 FKPS 节点名称不唯一：' + stem)
                if ps1:
                    if c.nodeType(ps1[0]) != 'transform':
                        raise CharacterRegistryError(
                            '旧通用 FKPS 节点类型无效：' + stem)
                    compensated.add(control)
                else:
                    offsets = by_leaf.get('AdvPy_' + stem + 'Offset', ())
                    if len(offsets) == 1:
                        parent = c.listRelatives(
                            offsets[0], parent=True, fullPath=True) or []
                        if (len(parent) == 1
                                and c.nodeType(parent[0]) == 'joint'
                                and not bool(c.getAttr(
                                    parent[0] + '.segmentScaleCompensate'))
                                and not bool(c.getAttr(
                                    body + '.segmentScaleCompensate'))):
                            compensated.add(control)
            body_leaf = stem.removesuffix('FK')
            control_leaf = control.rsplit('|', 1)[-1]
            namespace = (control_leaf.rsplit(':', 1)[0] + ':'
                         if ':' in control_leaf else '')
            compose = namespace + 'AdvPy_' + body_leaf + '_FitPartTwistCompose'
            if c.objExists(compose):
                offsets = by_leaf.get('AdvPy_' + stem + 'Offset', ())
                if len(offsets) != 1:
                    raise CharacterRegistryError(
                        '旧通用 Twist 缺少 FK Offset：' + body_leaf)
                source = c.connectionInfo(
                    compose + '.matrixIn[0]',
                    sourceFromDestination=True)
                source_node = source.split('.', 1)[0] if source else ''
                source_paths = c.ls(source_node, long=True) or []
                static = namespace + 'AdvPy_' + body_leaf \
                    + '_FitPartTwistStaticSource'
                static_paths = c.ls(static, long=True) or []
                if len(source_paths) == 1 and source_paths == static_paths:
                    pass
                elif (len(source_paths) == 1
                      and source.endswith('.worldMatrix[0]')
                      and source_paths[0].startswith(offsets[0] + '|')):
                    twist_rewired.add(body_leaf)
                else:
                    raise CharacterRegistryError(
                        '旧通用 Twist 来源无法识别：' + body_leaf)
            if 'fk.global.AdvPy_' + stem + '.Global' in keys:
                globally_driven.add(control)
        aim_sources = frozenset(match.group(1) for key in keys
            if (match := re.fullmatch(
                r'fit\.aim\.([A-Za-z_][A-Za-z_0-9]*)\.center\..+', key)))
        follower_sources = frozenset(
            leaf[len('AdvPy_GenericFKFollow_'):]
            for node in registration.nodes
            if (leaf := node.path.rsplit('|', 1)[-1]
                .rsplit(':', 1)[-1]).startswith(
                    'AdvPy_GenericFKFollow_')
            and node.path.rsplit('|', 1)[0].rsplit('|', 1)[-1]
                .rsplit(':', 1)[-1]
                == 'AdvPy_GenericFKControls')
        bendy_master_paths = {
            channel.key.split('.', 2)[1]: channel.node
            for channel in registration.channels
            if channel.key.startswith('bendy.')
            and channel.key.endswith('.microVis')}
        bendy_control_paths = {
            channel.key: channel.node
            for channel in registration.channels
            if channel.key.startswith('bendy.')
            and channel.key.endswith('.rotateX')}
        bendy_counts = []
        bendy_legacy_simple = set()
        bendy_legacy_twist_outputs = set()
        bendy_master_circular = set()
        bendy_legacy_start_icon = set()
        bendy_parented_end = set()
        bendy_legacy_circular = set()
        bendy_legacy_full_span = set()
        bendy_scaled_guides = set()
        bendy_additive_micro = set()
        bendy_opm_offset_scale = set()
        bendy_secondary_matrix = set()
        bendy_main_influence = set()
        for control in bendy_master_paths:
            stem, side = control.rsplit('_', 1)
            master_leaf = bendy_master_paths[control].rsplit('|', 1)[-1]
            namespace = (master_leaf.rsplit(':', 1)[0] + ':'
                         if ':' in master_leaf else '')
            guide_group = namespace + 'AdvPy_BendJoints'
            if (not c.objExists(guide_group)
                    or c.nodeType(guide_group) != 'transform'):
                raise CharacterRegistryError(
                    'Bendy 导向关节组缺失：' + control)
            guide_scale = c.connectionInfo(
                guide_group + '.scale', sourceFromDestination=True)
            if guide_scale:
                if (guide_scale.rsplit('|', 1)[-1]
                        .rsplit(':', 1)[-1]
                        != 'MainScaleMultiplyDivide.output'):
                    raise CharacterRegistryError(
                        'Bendy 导向关节组缩放来源错误：' + control)
                bendy_scaled_guides.add(control)
            old_output = namespace + 'AdvPy_' + control + 'TwistX'
            new_output = (namespace + 'BendX'
                          + stem.removeprefix('Bend') + '_' + side)
            circular = (namespace + 'BendCircular'
                        + stem.removeprefix('Bend') + '_' + side)
            start_icon_marker = (namespace + stem + '0_' + side
                                 + '.advPyBendyPartSpanIcon')
            falloff_marker = (bendy_master_paths[control]
                              + '.advPyBendyResidualFalloff')
            additive_marker = (bendy_master_paths[control]
                               + '.advPyBendyAdditiveMicroScale')
            opm_marker = (bendy_master_paths[control]
                          + '.advPyBendyOpmOffsetScale')
            secondary_marker = (bendy_master_paths[control]
                                + '.advPyBendySecondaryMatrixFollow')
            main_influence_marker = (bendy_master_paths[control]
                                     + '.advPyBendyMainInfluenceFollow')
            if c.objExists(main_influence_marker):
                if (not bool(c.getAttr(main_influence_marker))
                        or not c.getAttr(main_influence_marker,
                                         lock=True)):
                    raise CharacterRegistryError(
                        'Bendy 主导向关节标记已损坏：' + control)
                bendy_main_influence.add(control)
            if c.objExists(secondary_marker):
                if (not bool(c.getAttr(secondary_marker))
                        or not c.getAttr(secondary_marker, lock=True)):
                    raise CharacterRegistryError(
                        'Bendy 第二曲线矩阵标记已损坏：' + control)
                bendy_secondary_matrix.add(control)
            if c.objExists(opm_marker):
                if (not bool(c.getAttr(opm_marker))
                        or not c.getAttr(opm_marker, lock=True)):
                    raise CharacterRegistryError(
                        'Bendy OPM 缩放标记已损坏：' + control)
                bendy_opm_offset_scale.add(control)
            if c.objExists(additive_marker):
                if (not bool(c.getAttr(additive_marker))
                        or not c.getAttr(additive_marker, lock=True)):
                    raise CharacterRegistryError(
                        'Bendy Micro 加法缩放标记已损坏：' + control)
                bendy_additive_micro.add(control)
            if (control in bendy_opm_offset_scale
                    and control in bendy_additive_micro):
                raise CharacterRegistryError(
                    'Bendy OPM 与非 OPM 缩放标记同时存在：' + control)
            if not c.objExists(falloff_marker):
                bendy_legacy_full_span.add(control)
            elif (not bool(c.getAttr(falloff_marker))
                  or not c.getAttr(falloff_marker, lock=True)):
                raise CharacterRegistryError(
                    'Bendy 权重跨度标记已损坏：' + control)
            if not c.objExists(start_icon_marker):
                bendy_legacy_start_icon.add(control)
            elif (not bool(c.getAttr(start_icon_marker))
                  or not c.getAttr(start_icon_marker, lock=True)):
                raise CharacterRegistryError(
                    'Bendy 起点图标偏移标记已损坏：' + control)
            if c.objExists(circular):
                if c.nodeType(circular) != 'transform':
                    raise CharacterRegistryError(
                        'Bendy Circular 节点类型错误：' + control)
                bendy_master_circular.add(control)
            circular_length = (namespace + 'AdvPy_' + stem
                               + 'Circular_' + side + 'Length')
            if c.objExists(circular_length):
                marker = (circular_length
                          + '.advPyBendyLocalChildFactor')
                if not c.objExists(marker):
                    bendy_legacy_circular.add(control)
                elif (not bool(c.getAttr(marker))
                      or not c.getAttr(marker, lock=True)):
                    raise CharacterRegistryError(
                        'Bendy Circular 系数标记已损坏：' + control)
            if c.objExists(old_output):
                if c.objExists(new_output):
                    raise CharacterRegistryError(
                        'Bendy 扭转输出层新旧命名冲突：' + control)
                bendy_legacy_twist_outputs.add(control)
            elif not c.objExists(new_output):
                raise CharacterRegistryError(
                    'Bendy 主控缺少扭转输出层：' + control)
            pattern = re.compile(
                r'bendy\.' + re.escape(stem)
                + r'(\d+)_' + re.escape(side) + r'\.rotateX')
            indices = sorted(int(match.group(1))
                             for channel in registration.channels
                             if (match := pattern.fullmatch(channel.key)))
            if (not indices or indices != list(range(indices[-1] + 1))):
                raise CharacterRegistryError(
                    'Bendy 控制器编号不连续：' + control)
            proxy = ('BendX' + stem.removeprefix('Bend')
                     + '1_' + side)
            proxy_paths = [path for path in sorted(set(
                c.ls(proxy, '*:' + proxy, long=True,
                     type='transform') or []))
                if (c.listRelatives(path, parent=True,
                                    fullPath=True) or [])
                == [bendy_master_paths[control]]]
            if indices == [0]:
                if len(proxy_paths) != 1:
                    raise CharacterRegistryError(
                        'Bendy 单控制器缺少中点代理：' + control)
                bendy_counts.append((control, 1))
            else:
                bendy_counts.append((control, indices[-1]))
                if indices == [0, 1] and not proxy_paths:
                    bendy_legacy_simple.add(control)
            for index in indices:
                child = stem + str(index) + '_' + side
                output = (namespace + 'AdvPy_' + child + 'TwistX'
                          if control in bendy_legacy_twist_outputs else
                          namespace + 'BendX'
                          + stem.removeprefix('Bend')
                          + str(index) + '_' + side)
                if (not c.objExists(output)
                        or c.nodeType(output) != 'transform'):
                    raise CharacterRegistryError(
                        'Bendy 子控缺少扭转输出层：' + child)
                control_path = bendy_control_paths.get(
                    'bendy.' + child + '.rotateX')
                if (not control_path or
                        (c.listRelatives(output, parent=True,
                                         fullPath=True) or [])
                        != [control_path]):
                    raise CharacterRegistryError(
                        'Bendy 子控扭转输出层父级错误：' + child)
            end_proxy = (namespace + 'BendX'
                         + stem.removeprefix('Bend')
                         + str(bendy_counts[-1][1] + 1)
                         + '_' + side)
            end_parents = (c.listRelatives(
                end_proxy, parent=True, fullPath=True) or []
                if c.objExists(end_proxy) else [])
            if len(end_parents) == 1:
                parent_leaf = (end_parents[0].rsplit('|', 1)[-1]
                               .rsplit(':', 1)[-1])
                if parent_leaf in (
                        'AdvPy_' + stem + 'ParentUntwist_'
                        + side + 'Frame',
                        'AdvPy_' + stem + 'StartSource_' + side):
                    bendy_parented_end.add(control)
        def bendy_namespace(control):
            leaf = bendy_master_paths[control].rsplit('|', 1)[-1]
            return (leaf.rsplit(':', 1)[0] + ':'
                    if ':' in leaf else '')

        bendy_aim_follow = frozenset(
            control for control in bendy_master_paths
            if c.objExists(bendy_namespace(control) + 'AdvPy_'
                           + control.rsplit('_', 1)[0]
                           + 'MasterFollow_'
                           + control.rsplit('_', 1)[-1] + 'Aim'))
        bendy_start_names = frozenset(
            key.split('.', 2)[1] for key in keys
            if re.fullmatch(r'bendy\.Bend.+0_[RLM]\.rotateX', key))
        bendy_start_output_names = frozenset(
            name.replace('Bend', 'BendX', 1)
            for name in bendy_start_names)
        bendy_start_control = set()
        bendy_child_control = set()
        bendy_untwist = set()
        bendy_end_matrix = set()
        bendy_oriented = set()
        bendy_negative_right = set()
        bendy_micro_matrix = set()
        bendy_base_twist = set()
        bendy_micro_scale = set()
        bendy_yz_scale = set()
        bendy_up_twist = set()
        bendy_blended_up = set()
        for control in bendy_aim_follow:
            stem, side = control.rsplit('_', 1)
            namespace = bendy_namespace(control)
            offset_marker = (namespace + control
                             + 'Offset.advPyBendyOrientedBind')
            if c.objExists(offset_marker):
                if (not bool(c.getAttr(offset_marker))
                        or not c.getAttr(offset_marker, lock=True)):
                    raise CharacterRegistryError(
                        'Bendy 朝向绑定标记已损坏：' + control)
                bendy_oriented.add(control)
            frame = (namespace + 'AdvPy_' + stem
                     + 'ParentUntwist_' + side + 'Frame')
            if c.objExists(frame):
                bendy_untwist.add(control)
            end_matrix_pattern = (namespace + 'AdvPy_BendX'
                                  + stem.removeprefix('Bend')
                                  + '*_' + side + 'World')
            if c.ls(end_matrix_pattern, type='multMatrix'):
                bendy_end_matrix.add(control)
            blend = (namespace + 'AdvPy_' + stem + 'MasterFollow_'
                     + side + 'Blend')
            source = c.connectionInfo(blend + '.inputMatrix',
                                      sourceFromDestination=True)
            start = stem + '0_' + side
            start_output = ('BendX' + stem.removeprefix('Bend')
                            + '0_' + side)
            if (source and source.split('.', 1)[0].rsplit('|', 1)[-1]
                    .rsplit(':', 1)[-1] in (start, start_output)):
                bendy_start_control.add(control)
            end_world = (namespace + 'AdvPy_' + stem
                         + 'EndWorld_' + side)
            end_source = c.connectionInfo(end_world + '.matrixIn[0]',
                                          sourceFromDestination=True)
            end_leaf = (end_source.split('.', 1)[0].rsplit('|', 1)[-1]
                        .rsplit(':', 1)[-1]
                        if end_source else '')
            if end_leaf in bendy_start_names | bendy_start_output_names:
                bendy_child_control.add(control)
        for control in bendy_master_paths:
            stem, side = control.rsplit('_', 1)
            namespace = bendy_namespace(control)
            micro_aim = (namespace + 'AdvPy_'
                         + stem.removeprefix('Bend') + '_' + side
                         + 'AimMatrix')
            if c.objExists(micro_aim):
                if c.nodeType(micro_aim) != 'aimMatrix':
                    raise CharacterRegistryError(
                        'Bendy 微控制矩阵节点类型错误：' + control)
                bendy_micro_matrix.add(control)
                blend = (namespace + 'AdvPy_'
                         + stem.removeprefix('Bend') + '_' + side
                         + 'UpBlend')
                if c.objExists(blend):
                    if c.nodeType(blend) != 'blendMatrix':
                        raise CharacterRegistryError(
                            'Bendy 朝向兼容节点类型错误：' + control)
                    bendy_blended_up.add(control)
            base_twist = (namespace + 'AdvPy_'
                          + stem.removeprefix('Bend') + '_' + side
                          + 'BaseTwistOffset')
            if c.objExists(base_twist):
                if c.nodeType(base_twist) != 'plusMinusAverage':
                    raise CharacterRegistryError(
                        'Bendy 基础扭转节点类型错误：' + control)
                bendy_base_twist.add(control)
            micro_scale = (namespace + 'AdvPy_BendyMicroScaleCombine'
                           + stem.removeprefix('Bend') + '_' + side)
            if c.objExists(micro_scale):
                if c.nodeType(micro_scale) != 'multiplyDivide':
                    raise CharacterRegistryError(
                        'Bendy 微控制缩放节点类型错误：' + control)
                bendy_micro_scale.add(control)
            micro_offset = (namespace + 'MicroOffset'
                            + stem.removeprefix('Bend') + '_' + side)
            if c.objExists(micro_offset):
                x_source = c.connectionInfo(
                    micro_offset + '.scaleX',
                    sourceFromDestination=True)
                y_source = c.connectionInfo(
                    micro_offset + '.scaleY',
                    sourceFromDestination=True)
                z_source = c.connectionInfo(
                    micro_offset + '.scaleZ',
                    sourceFromDestination=True)
                expected = (namespace + 'AdvPy_'
                            + stem.removeprefix('Bend') + '_' + side
                            + 'BendScaleAdd.output3D')
                if (not x_source and y_source == expected + 'y'
                        and z_source == expected + 'z'):
                    bendy_yz_scale.add(control)
            up_twist = (namespace + 'AdvPy_'
                        + stem.removeprefix('Bend') + 'Part1_' + side
                        + 'UpTwistMultiply')
            if c.objExists(up_twist):
                if c.nodeType(up_twist) != 'multDoubleLinear':
                    raise CharacterRegistryError(
                        'Bendy 上行扭转节点类型错误：' + control)
                bendy_up_twist.add(control)
            if side != 'R':
                continue
            starts = c.ls(namespace + stem + '0_R', long=True,
                          type='transform') or []
            if len(starts) != 1:
                raise CharacterRegistryError(
                    'Bendy 起点控制器无法唯一定位：' + control)
            shapes = c.listRelatives(starts[0], shapes=True,
                                     fullPath=True) or []
            if len(shapes) != 1:
                raise CharacterRegistryError(
                    'Bendy 起点控制器曲线无法唯一定位：' + control)
            count = int(c.getAttr(shapes[0] + '.controlPoints', size=True))
            if count < 4:
                raise CharacterRegistryError(
                    'Bendy 起点控制器曲线无效：' + control)
            center_x = sum(float(c.getAttr(
                shapes[0] + f'.controlPoints[{index}].xValue'))
                for index in range(count)) / count
            if center_x < -1e-6:
                bendy_negative_right.add(control)
        return GenericFkFeaturePolicy(
            scale_controls=frozenset(scale),
            compensated_controls=frozenset(compensated),
            global_controls=frozenset(globally_driven),
            aim_sources=aim_sources,
            follower_sources=follower_sources,
            independent_controls=frozenset(independent),
            twist_rewired_sources=frozenset(twist_rewired),
            bendy_scale_controls=frozenset(bendy_scales),
            fkx_joint_controls=frozenset(fkx_joints),
            point_controls=frozenset(point_controls),
            hand_point_control_names=frozenset(hand_points),
            standard_point_control_names=frozenset(standard_points),
            torso_point_control_names=frozenset(torso_points),
            torso_root_point_from_fkx=root_point_from_fkx,
            axial_fk_root_point_from_receiver=axial_point_from_receiver,
            standard_fkx_joint_names=frozenset(standard_fkx_joints),
            hand_fkx_joint_names=frozenset(hand_fkx_joints),
            standard_fk_independent_controls=frozenset(
                standard_independent),
            torso_fkx_joint_names=frozenset(torso_fkx_joints),
            bendy_aim_follow_controls=bendy_aim_follow,
            bendy_start_control_sources=frozenset(bendy_start_control),
            bendy_child_control_sources=frozenset(bendy_child_control),
            bendy_untwist_controls=frozenset(bendy_untwist),
            bendy_end_matrix_controls=frozenset(bendy_end_matrix),
            bendy_oriented_controls=frozenset(bendy_oriented),
            bendy_negative_right_axes=frozenset(bendy_negative_right),
            bendy_micro_matrix_controls=frozenset(bendy_micro_matrix),
            bendy_base_twist_controls=frozenset(bendy_base_twist),
            bendy_micro_scale_controls=frozenset(bendy_micro_scale),
            bendy_control_counts=tuple(bendy_counts),
            bendy_yz_scale_controls=frozenset(bendy_yz_scale),
            bendy_up_twist_controls=frozenset(bendy_up_twist),
            bendy_blended_up_controls=frozenset(bendy_blended_up),
            bendy_legacy_simple_controls=frozenset(bendy_legacy_simple),
            bendy_legacy_twist_outputs=frozenset(
                bendy_legacy_twist_outputs),
            bendy_master_circular_controls=frozenset(
                bendy_master_circular),
            bendy_legacy_start_icon_controls=frozenset(
                bendy_legacy_start_icon),
            bendy_parented_end_controls=frozenset(bendy_parented_end),
            bendy_legacy_circular_controls=frozenset(
                bendy_legacy_circular),
            bendy_legacy_full_span_controls=frozenset(
                bendy_legacy_full_span),
            bendy_scaled_guide_controls=frozenset(
                bendy_scaled_guides),
            bendy_additive_micro_scale_controls=frozenset(
                bendy_additive_micro),
            bendy_opm_offset_scale_controls=frozenset(
                bendy_opm_offset_scale),
            bendy_secondary_matrix_controls=frozenset(
                bendy_secondary_matrix),
            bendy_main_influence_controls=frozenset(
                bendy_main_influence))

    def character_rebuild_transaction(self,label):
        from contextlib import nullcontext
        return nullcontext() if self._transaction_active else self.transaction(label)

    def promote_character_rebuild(self,staged):
        from .maya_character_promotion import promote
        return promote(self,staged)

    def match_character_rebuild_solver(self,stage,registration):
        if self._cmds.objExists('AdvPy_SpineIKHandle') and self._cmds.ikHandle('AdvPy_SpineIKHandle',q=True,solver=True)=='AdvPy_SpineRPSolver':
            with stage.transaction('Match replacement spine solver'):
                stage.ensure_precise_body_spine_solver(registration.spine)

    def preserve_character_rebuild_binding(self,stage,original,replacement):
        from adv_py.core.character_preservation import validate_rebuild_layout
        generated = replacement
        by_key = {channel.key:channel for channel in replacement.channels}
        old_keys = {channel.key for channel in original.channels}
        follow_key = 'head.aim.target.follow'
        if (follow_key in by_key and follow_key not in old_keys
                and set(by_key) - old_keys == {follow_key}):
            # Older registered rigs used the AimSystem/Main frame only.
            # Keep that motion when rebuilding their existing animation.
            with stage.transaction('Preserve legacy Head Aim follow mode'):
                stage._transaction_changed=True
                stage._cmds.setAttr(by_key[follow_key].node + '.follow', 0.0)
            replacement=replace(replacement,channels=tuple(
                channel for channel in replacement.channels
                if channel.key != follow_key))
            by_key = {channel.key:channel for channel in replacement.channels}
        legacy_generic = tuple(channel for channel in original.channels
                               if channel.key not in by_key
                               and channel.key.startswith('generic.fk.'))
        if legacy_generic:
            from adv_py.core.body_fk_channel_locks import FK_LOCK_ATTRIBUTES
            c=stage._cmds
            for channel in legacy_generic:
                plug=channel.node+'.'+channel.attribute
                if (channel.attribute not in FK_LOCK_ATTRIBUTES
                        or not c.objExists(plug)
                        or not c.getAttr(plug,lock=True)
                        or c.listConnections(plug,source=True,
                                             destination=False)):
                    raise CharacterRegistryError(
                        '旧通用 FK 通道无法安全恢复：'+channel.key)
            with stage.transaction('Preserve legacy generic FK channels'):
                stage._transaction_changed=True
                for channel in legacy_generic:
                    c.setAttr(channel.node+'.'+channel.attribute,
                              lock=False,keyable=True)
            replacement=replace(replacement,channels=(
                replacement.channels+legacy_generic))
            by_key={channel.key:channel for channel in replacement.channels}
        additions = set(by_key) - old_keys
        def additive_controller_channel(key):
            channel = by_key[key]
            return (key.startswith(("torso.", "arm.fk.", "leg.fk.",
                                    "hand.fk.", "arm.ik.", "leg.ik.",
                                    "arm.pole.extra.", "leg.pole.extra.",
                                    "foot.toe."))
                    and (channel.attribute in ("scaleX", "scaleY", "scaleZ")
                         or ".sub." in key or ".extra." in key))
        if old_keys <= set(by_key) and all(
                additive_controller_channel(key) for key in additions):
            replacement=replace(replacement,channels=tuple(by_key[channel.key] for channel in original.channels))
        validate_rebuild_layout(original,replacement)
        if (type(original.spine) is not type(replacement.spine)
                or len(original.spine.lengths)!=len(replacement.spine.lengths)
                or any(abs(a-b)>1e-6 for a,b in zip(original.spine.lengths,replacement.spine.lengths))):
            raise CharacterRegistryError('重建改变脊柱求解类型或绑定长度')
        # Same-layout rebuilding keeps the original binding definition exactly.
        # Re-evaluating matrices after Fit import can add sub-ulp noise, which
        # must not invalidate the character's previously saved animation files.
        retained=replace(replacement,body=original.body,
                         spine=replace(replacement.spine,lengths=original.spine.lengths))
        with stage.transaction('Preserve original binding identity'):
            stage.write_character_registration_extension(generated,retained)
        return retained

    def audit_character_rebuild_ownership(self,staged):
        from .maya_character_ownership import audit
        return audit(self,staged)

    def capture_character_deformer_conversions(self,deformers):
        """Retain converters whose entire output feeds preserved deformers."""
        from .maya_character_preservation import _plug
        c=self._cmds
        destinations={}
        for deformer in deformers:
            for source,destination in deformer.connections:
                node,attribute=source.split('.',1)
                if c.nodeType(node)!='unitConversion':
                    continue
                if attribute!='output':
                    raise CharacterRegistryError(
                        '生产变形器单位转换输出类型不受支持：'+source)
                destinations.setdefault(node,set()).add(destination)
        rows=[]
        for node,retained in destinations.items():
            upstream=c.connectionInfo(node+'.input',
                sourceFromDestination=True)
            outgoing=c.listConnections(node+'.output',source=False,
                destination=True,plugs=True) or []
            normalized=tuple(sorted(_plug(self,plug) for plug in outgoing))
            if (not upstream or len(normalized)!=len(retained)
                    or set(normalized)!=retained):
                raise CharacterRegistryError(
                    '生产变形器单位转换输出超出保留范围或缺少输入：'+node)
            rows.append((node,_plug(self,upstream),normalized))
        return tuple(sorted(rows))

    def capture_character_deformer_output_conversions(self,deformers):
        """Retain conversion fan-out carrying deformer outputs to Rig."""
        from .maya_character_preservation import _plug
        c=self._cmds
        rows=[]
        for deformer in deformers:
            for source,destination in deformer.connections:
                node=destination.split('.',1)[0]
                if c.nodeType(node)!='unitConversion':
                    continue
                if destination!=node+'.input':
                    raise CharacterRegistryError(
                        '生产变形器输出单位转换输入类型不受支持：'
                        + destination)
                incoming=c.connectionInfo(node+'.input',
                    sourceFromDestination=True)
                outputs=c.listConnections(node+'.output',source=False,
                    destination=True,plugs=True) or []
                normalized=tuple(sorted(_plug(self,plug) for plug in outputs))
                if (not incoming or _plug(self,incoming)!=source
                        or not normalized):
                    raise CharacterRegistryError(
                        '生产变形器输出单位转换缺少输入或输出：'+node)
                rows.append((node,normalized))
        return tuple(sorted(set(rows)))

    def capture_character_deformer_animation_state(self,deformers,skins=()):
        """Snapshot native Skin/deformer keys before replacing their drivers."""
        c=self._cmds
        rows=[]
        seen=set()
        for node in (row.node for row in (*skins,*deformers)):
            curves=c.listConnections(node,source=True,
                destination=False,type='animCurve',
                skipConversionNodes=True) or []
            for curve in curves:
                if curve in seen:
                    continue
                seen.add(curve)
                times=tuple(float(value) for value in (
                    c.keyframe(curve,query=True,timeChange=True) or ()))
                values=tuple(float(value) for value in (
                    c.keyframe(curve,query=True,valueChange=True) or ()))
                if len(times)!=len(values):
                    raise CharacterRegistryError(
                        '生产变形器动画曲线关键帧数据不完整：'+curve)
                tangent_types=(
                    tuple(c.keyTangent(curve,query=True,
                        inTangentType=True) or ()),
                    tuple(c.keyTangent(curve,query=True,
                        outTangentType=True) or ()))
                tangent_shape=tuple(tuple(float(value) for value in (
                    c.keyTangent(curve,query=True,**{flag:True}) or ()))
                    for flag in ('inAngle','outAngle','inWeight','outWeight'))
                if any(len(row)!=len(times) for row in
                       (*tangent_types,*tangent_shape)):
                    raise CharacterRegistryError(
                        '生产变形器动画曲线切线数据不完整：'+curve)
                infinity=(c.getAttr(curve+'.preInfinity'),
                          c.getAttr(curve+'.postInfinity'),
                          tuple(c.keyTangent(curve,query=True,
                              weightedTangents=True) or ()))
                rows.append((curve,times,values,tangent_types,
                             tangent_shape,infinity))
        return tuple(sorted(rows))

    def plan_character_property_transfer(self,original,namespace):
        from .maya_character_properties import plan
        return plan(self,original,namespace)

    def preflight_character_transfer(self,staged):
        from .maya_character_transfer import preflight
        preflight(self,staged)

    def sample_character_transfer(self,staged,frames,*,target=False):
        from .maya_character_transfer import sample
        return sample(self,staged,frames,target)

    def transfer_character_data(self,staged):
        from .maya_character_transfer import transfer
        transfer(self,staged)

    def verify_character_retained_data(self,staged):
        from .maya_character_transfer import verify_retained
        verify_retained(self,staged)

    def preflight_character_rebuild_namespace(self,namespace):
        from maya import cmds
        from adv_py.core.character_identity import CharacterIdentity
        if self.namespace is None:
            raise CharacterRegistryError('重建必须显式选择角色 namespace；根命名空间使用空字符串')
        identity=CharacterIdentity(namespace)
        if not identity.namespace:
            raise CharacterRegistryError('重建暂存需要非根命名空间')
        if cmds.namespace(exists=namespace) and (cmds.namespaceInfo(namespace,listOnlyDependencyNodes=True,recurse=True)
                or cmds.namespaceInfo(namespace,listOnlyNamespaces=True,recurse=True)):
            raise CharacterRegistryError('重建暂存命名空间已有内容')
        if ':' in namespace and not cmds.namespace(exists=namespace.rsplit(':',1)[0]):
            raise CharacterRegistryError('重建暂存的父命名空间不存在')

    def create_character_rebuild_host(self,namespace):
        self._require_transaction()
        self.preflight_character_rebuild_namespace(namespace)
        from maya import cmds
        from .maya_body import MayaBodyBuildHost
        from contextlib import contextmanager
        parent=self
        class RebuildStageHost(MayaBodyBuildHost):
            @contextmanager
            def transaction(stage,label):
                # The source host owns the one native Undo chunk. A stage
                # failure must propagate before that chunk is rolled back.
                parent._require_transaction()
                if stage._transaction_active:raise RuntimeError('重建暂存不允许嵌套应用事务')
                previous=set(stage._cmds.ls(type='transform',uuid=True) or [])
                stage._transaction_active=True;stage._transaction_changed=False
                try:
                    yield
                    if stage._transaction_changed:stage._checkpoint_new_transform_channels(previous)
                finally:
                    parent._transaction_changed|=stage._transaction_changed
                    stage._transaction_active=False;stage._transaction_changed=False
        self._transaction_changed=True
        if not cmds.namespace(exists=namespace):cmds.namespace(addNamespace=namespace)
        return RebuildStageHost(namespace=namespace)

    def capture_character_preservation(self,registration,extensions=()):
        from .maya_character_preservation import capture
        return capture(self,registration,extensions)

    @staticmethod
    def discover_scene_characters():
        """Physical identities for explicit host selection; never edits a scene."""
        from maya import cmds
        from adv_py.core.character_identity import CharacterIdentity, SceneCharacter
        rows=[]
        for node in cmds.ls(type='network') or []:
            if (node.rsplit(':',1)[-1]!=REGISTRY_NAME or not cmds.objExists(node+'.advPyRegistryOwner')
                    or cmds.getAttr(node+'.advPyRegistryOwner')!=FORMAT):
                continue
            namespace=node.rsplit(':',1)[0] if ':' in node else ''
            rows.append(SceneCharacter(CharacterIdentity(namespace),node,cmds.ls(node,uuid=True)[0],
                                       bool(cmds.referenceQuery(node,isNodeReferenced=True))))
        return tuple(sorted(rows,key=lambda row:row.identity.namespace))

    def preflight_character_space_animation(self, registration):
        from .maya_animated_spaces import preflight
        preflight(self, registration)

    def install_character_space_animation(self, registration):
        from .maya_animated_spaces import install
        return install(self, registration)

    def switch_character_space(self, registration, key, mode, frame):
        from .maya_animated_spaces import switch
        return switch(self, registration, key, mode, frame)

    def describe_character_stretch_matching(self,registration):
        from .maya_limb_shape import describe
        return describe(self,registration)

    def install_character_stretch_matching(self,before,after):
        from .maya_limb_shape import install,describe
        self._require_transaction()
        if self.read_character_registration()!=before or describe(self,before)!=after:
            raise CharacterRegistryError('拉伸匹配扩展计划失效')
        install(self,before,after)
        self.write_character_registration_extension(before,after)

    def sample_character_limb_helpers(self,registration,frames,limb,side):
        from .maya_limb_shape import sample_helpers
        return sample_helpers(self,registration,frames,limb,side)

    def capture_character_stretch_world(self,registration):
        from .maya_limb_shape import bindings
        lengths,volumes=bindings(self,registration)
        paths=[b.target.rsplit('.',1)[0] for b in lengths]+[p for b in volumes for p,_ in b.helpers]
        return tuple((p,self._spine_world_frame(p)[0]) for p in paths)

    def describe_character_limb_animation(self,registration):
        from adv_py.application.body_arm_ik_to_fk import MatchBodyArmIkToFk
        from adv_py.application.body_leg_ik_to_fk import MatchBodyLegIkToFk
        from adv_py.core.character_registry import CharacterChannel
        from adv_py.core.fit_symmetry import FitBuildSide
        self._validate_character_registration(registration)
        c=self._cmds
        from .maya_limb_orientation import preflight_orientation_install, orientation_channels
        preflight_orientation_install(self,registration)
        channels=list(registration.channels)
        existing={ch.key:ch for ch in channels}
        nodes=list(registration.nodes)
        known={n.path for n in nodes}
        for label,service in (("arm",MatchBodyArmIkToFk),("leg",MatchBodyLegIkToFk)):
            for side in (FitBuildSide.RIGHT,FitBuildSide.LEFT):
                # The read-only matching plan resolves actual driver paths and
                # the signed primary axis, including non-X leg constructions.
                plan=service(self).plan(side,registration.container,body_root_name=registration.body_root)
                if plan.provenance_issues or plan.blend_issues or plan.fk_issues:
                    raise CharacterRegistryError("四肢结构无法登记为动画骨段")
                for index,plug in enumerate(plan.match.fk_segment_plugs):
                    path,attribute=plug.rsplit('.',1)
                    channel=CharacterChannel(f"{label}.fkLength.{side.value}.{index}",path,attribute)
                    if channel.key in existing:
                        if existing[channel.key]!=channel:
                            raise CharacterRegistryError("已登记的四肢骨段通道被替换")
                        continue
                    if (c.nodeType(path)!="joint" or c.getAttr(plug,lock=True)
                            or not c.getAttr(plug,keyable=True) or c.listConnections(plug,s=True,d=False)):
                        raise CharacterRegistryError("新增骨段通道锁定、不可写键或已有输入")
                    if any(ch.node==path and ch.attribute==attribute for ch in channels):
                        raise CharacterRegistryError("四肢骨段通道已经以其他语义登记")
                    channels.append(channel)
                    while path:
                        if path not in known:
                            nodes.append(self._registry_node(path));known.add(path)
                        path=path.rsplit('|',1)[0]
        for ch in orientation_channels(registration):
            if ch.key not in existing:
                channels.append(ch)
        result=replace(registration,channels=tuple(channels),nodes=tuple(nodes))
        encode_registration(result)
        return result

    def extend_character_limb_registration(self,before,after):
        self._require_transaction()
        if self.read_character_registration()!=before or self.describe_character_limb_animation(before)!=after:
            raise CharacterRegistryError("角色骨段扩展计划已经失效")
        c=self._cmds
        self._transaction_changed=True
        from .maya_limb_orientation import install_orientation
        install_orientation(self,before)
        self.write_character_registration_extension(before,after)

    def write_character_registration_extension(self,before,after):
        self._require_transaction()
        self._validate_character_registration(after)
        c=self._cmds
        self._transaction_changed=True
        document=REGISTRY_NAME+".advPyRegistryDocument"
        c.setAttr(document,lock=False)
        c.setAttr(document,encode_registration(after),type="string")
        c.setAttr(document,lock=True)
        c.setAttr(REGISTRY_NAME+".members",lock=False)
        for index,member in enumerate(after.nodes[len(before.nodes):],start=len(before.nodes)):
            c.connectAttr(member.path+".message",REGISTRY_NAME+f".members[{index}]")
        c.setAttr(REGISTRY_NAME+".members",lock=True)

    def rebase_character_registration_bind_pose(self, registration):
        """Record final world bind frames after a Z-up Group rotation."""
        self._require_transaction()
        if self.read_character_registration() != registration:
            raise CharacterRegistryError("场景上方向转换前角色登记已变化")
        body = self.capture_body_skeleton(registration.body_root)
        current = {joint.path: joint for joint in body.joints}
        if set(current) != {joint.path for joint in registration.body}:
            raise CharacterRegistryError("场景上方向转换后 Body 关节集合变化")
        updated = replace(registration, body=tuple(
            CharacterBindJoint(joint.path, joint.parent,
                               self._spine_world_frame(joint.path)[0])
            for joint in registration.body))
        self.write_character_registration_extension(registration, updated)
        if self.read_character_registration() != updated:
            raise CharacterRegistryError("场景上方向转换后绑定矩阵登记失败")
        return updated

    def capture_character_registration_node(self, path: str):
        return self._registry_node(path)

    def _registry_node(self, path):
        c = self._cmds
        if (c.ls(path,long=True) or []) != [path] or c.nodeType(path) not in ("transform","joint"):
            raise CharacterRegistryError("登记节点缺失、歧义或类型无效："+path)
        if c.referenceQuery(path,isNodeReferenced=True) or any(c.lockNode(path,q=True,lock=True) or []):
            raise CharacterRegistryError("登记暂不支持引用或锁定节点："+path)
        inputs=[]
        for attribute in tuple(kind+axis for kind in ("translate","rotate","scale","jointOrient","rotateAxis") for axis in "XYZ")+("offsetParentMatrix",):
            plug=path+"."+attribute
            if not c.objExists(plug):
                continue
            source=c.connectionInfo(plug,sourceFromDestination=True)
            if source:
                node,attr=source.split(".",1)
                inputs.append((attribute,self._resolve_connected_node(node)+"."+attr))
        return CharacterNode(path,c.ls(path,uuid=True)[0],c.nodeType(path),
                             (c.listRelatives(path,parent=True,fullPath=True) or [None])[0],tuple(inputs))

    def _character_direct_animation(self, source):
        """Only native time-input curves may replace an editable user input."""
        c=self._cmds
        node,attribute=source.rsplit(".",1)
        if self.namespace is not None and not c.identity.owns(self.scene_address(node)):
            return False
        if attribute!="output" or c.nodeType(node) not in ("animCurveTA","animCurveTL","animCurveTU"):
            return False
        driver=c.connectionInfo(node+".input",sourceFromDestination=True)
        # Maya can use the implicit scene clock without a visible input edge,
        # including curves restored from its native scene format.
        if driver and (driver.rsplit(".",1)[1]!="outTime" or c.nodeType(driver.rsplit(".",1)[0])!="time"):
            return False
        return True

    def install_character_spline_animation(self, registration):
        from .maya_spline_matching import install
        return install(self, registration)

    def validate_character_spine(self, plan):
        from adv_py.core.body_spline import BodySplinePlan
        if isinstance(plan, BodySplinePlan):
            from .maya_spline import audit
            audit(self, plan)
        else:
            self.validate_body_spine(plan)

    def describe_character_registration(self, rig, channels):
        c = self._cmds
        body = self.capture_body_skeleton(rig.body.root)
        if not body_bind_pose_matches(rig.body,body):
            raise CharacterRegistryError("角色必须在构建后的绑定姿态登记")
        spine = rig.plan.torso.torso.spine or rig.plan.torso.torso.spline
        spaces = rig.plan.control_spaces
        self.validate_character_spine(spine)
        for spec in spaces.spaces:
            self.capture_control_space_mode(spec)
        container = rig.plan.arm.safety.symmetry.source.hierarchy.container
        paths = {body.root,container,*(j.path for j in body.joints),*(ch.node for ch in channels)}
        paths.update(
            control.source_override_path
            for module in (rig.plan.arm, rig.plan.leg)
            for control in module.fk_controls.controls
            if control.source_override_path is not None)
        if rig.plan.hand is not None:
            paths.update(
                control.source_override_path
                for control in rig.plan.hand.controls.controls
                if control.source_override_path is not None)
        if rig.plan.torso is not None:
            paths.update(
                control.source_override_path
                for control in rig.plan.torso.torso.controls.controls
                if control.source_override_path is not None)
        for scale in rig.plan.fk_scale_compensations:
            if scale.mel_non_opm_fkx and not scale.inherit_scale:
                ps1 = scale.parent_control_path + "|" + scale.fkps1_name
                paths.update((ps1, ps1 + "|" + scale.fkps2_name))
        paths.update((spine.root_path,spine.pelvis_control,*spine.fk_controls,*spine.body_joints,
                      spine.chest_space,*(j.path for j in spine.joints)))
        from adv_py.core.body_spline import BodySplinePlan
        if isinstance(spine, BodySplinePlan):
            paths.update((*spine.targets, spine.curve, *spine.ik_outputs[1:]))
        else:
            paths.update((spine.ik_offset,spine.ik_control,spine.pole_offset,spine.pole_control,spine.waist_output))
        paths.update(p for spec in spaces.spaces for p in (*spec.targets,*spec.sources))
        paths.update(p for spec in rig.plan.pole_aim
                     for p in (spec.frame_path, spec.aligned_path,
                               spec.aim_path, spec.target_path))
        if rig.plan.torso.torso.head_aim:
            aim=rig.plan.torso.torso.head_aim
            paths.update((aim.rest,aim.solved,aim.pivot,aim.target,aim.target_offset))
        for node in tuple(paths):
            parent = node.rsplit("|",1)[0]
            while parent:
                paths.add(parent)
                parent = parent.rsplit("|",1)[0]
        nodes = tuple(self._registry_node(p) for p in sorted(paths))
        resolved = []
        for ch in channels:
            plug = ch.node+"."+ch.attribute
            if not c.objExists(plug) or c.getAttr(plug,lock=True) or c.listConnections(plug,s=True,d=False):
                raise CharacterRegistryError("登记控制通道被占用："+plug)
            minimum = c.attributeQuery(ch.attribute,node=ch.node,minimum=True) if c.attributeQuery(ch.attribute,node=ch.node,minExists=True) else None
            maximum = c.attributeQuery(ch.attribute,node=ch.node,maximum=True) if c.attributeQuery(ch.attribute,node=ch.node,maxExists=True) else None
            resolved.append(replace(ch,minimum=minimum[0] if minimum else None,maximum=maximum[0] if maximum else None))
        plan = CharacterRegistration(body.root,container,tuple(resolved),tuple(
            CharacterBindJoint(j.path,j.parent_path,self._spine_world_frame(j.path)[0]) for j in body.joints),nodes,spine,spaces)
        encode_registration(plan)
        return plan

    def preflight_character_registration(self, plan):
        if self.find_name_collisions(REGISTRY_NAME) or self.discover_character_registrations():
            raise CharacterRegistryError("场景已有登记或登记名称被占用")
        self._validate_character_registration(plan)

    def _validate_character_registration(self, plan):
        c = self._cmds
        from .maya_head_aim import audit_registered
        audit_registered(self,plan)
        from .maya_spline_matching import audit as audit_spline_matching
        audit_spline_matching(self,plan)
        user_plugs={channel.node+"."+channel.attribute for channel in plan.channels}
        for node in plan.nodes:
            current=self._registry_node(node.path)
            retained=[]
            for attribute,source in current.inputs:
                if node.path+"."+attribute in user_plugs and self._character_direct_animation(source):
                    continue
                retained.append((attribute,source))
            if replace(current,inputs=tuple(retained)) != node:
                raise CharacterRegistryError("登记节点身份或父级变化："+node.path)
        body = self.capture_body_skeleton(plan.body_root)
        if {(j.path,j.parent_path) for j in body.joints} != {(j.path,j.parent) for j in plan.body}:
            raise CharacterRegistryError("登记 Body 拓扑变化")
        if audit_body_provenance(oriented_body_provenance(plan.container,len(plan.body)),body.provenance):
            raise CharacterRegistryError("Body 所有权无效")
        for channel in plan.channels:
            if not c.objExists(channel.node+"."+channel.attribute):
                raise CharacterRegistryError("登记控制通道缺失")
            source=c.connectionInfo(channel.node+"."+channel.attribute,sourceFromDestination=True)
            if source and not self._character_direct_animation(source):
                raise CharacterRegistryError("登记控制通道有非动画外部输入")
        from .maya_limb_orientation import audit_orientation
        audit_orientation(self,plan)
        from .maya_limb_shape import audit as audit_shape
        audit_shape(self,plan)
        from .maya_animated_spaces import audit as audit_spaces
        audit_spaces(self,plan)
        self.validate_character_spine(plan.spine)
        for spec in plan.spaces.spaces:
            self.capture_control_space_mode(spec)
        from .maya_body_pole_aim import audit_registered_pole_aim
        audit_registered_pole_aim(self, plan)

    def create_character_registration(self, plan):
        self._require_transaction()
        self.preflight_character_registration(plan)
        c = self._cmds
        self._transaction_changed = True
        node = c.createNode("network",name=REGISTRY_NAME,skipSelect=True)
        for attr,value in (("advPyRegistryOwner",FORMAT),("advPyRegistryDocument",encode_registration(plan))):
            c.addAttr(node,longName=attr,dataType="string")
            c.setAttr(node+"."+attr,value,type="string",lock=True)
        c.addAttr(node,longName="members",attributeType="message",multi=True)
        for index,member in enumerate(plan.nodes):
            c.connectAttr(member.path+".message",node+f".members[{index}]")
        c.setAttr(node+".members",lock=True)

    def discover_character_registrations(self):
        c = self._cmds
        return tuple(sorted(n for n in c.ls(type="network") or []
                            if (self.namespace is not None or ':' not in n)
                            if c.objExists(n+".advPyRegistryOwner") and c.getAttr(n+".advPyRegistryOwner")==FORMAT))

    def read_character_registration(self, name=REGISTRY_NAME):
        c = self._cmds
        if name != REGISTRY_NAME or (c.ls(name,long=True) or []) != [name] or c.nodeType(name)!="network":
            raise CharacterRegistryError("当前仅支持明确的标准单角色登记节点")
        if c.referenceQuery(name,isNodeReferenced=True) or self.discover_character_registrations() != (name,):
            raise CharacterRegistryError("角色登记归属、数量或引用状态无效")
        if not c.objExists(name+".advPyRegistryDocument"):
            raise CharacterRegistryError("角色登记文档缺失")
        plan = decode_registration(c.getAttr(name+".advPyRegistryDocument"))
        indices = c.getAttr(name+".members",multiIndices=True) or []
        # Undoing a Maya multi-message connection may leave an empty logical
        # array slot. Only trailing, unconnected capacity is permitted.
        if indices[:len(plan.nodes)] != list(range(len(plan.nodes))) or any(
                c.listConnections(name+f".members[{index}]",source=True,destination=False)
                for index in indices[len(plan.nodes):]):
            raise CharacterRegistryError("角色登记成员列表不完整")
        for index,member in enumerate(plan.nodes):
            inputs = c.listConnections(name+f".members[{index}]",source=True,destination=False,plugs=True) or []
            if len(inputs)!=1:
                raise CharacterRegistryError("登记成员连接缺失或歧义")
            node,attr = inputs[0].rsplit(".",1)
            if attr!="message" or self._resolve_connected_node(node)!=member.path:
                raise CharacterRegistryError("登记成员连接被替换")
        self._validate_character_registration(plan)
        return plan
