"""Closed spline payload decoder for version 2 character registrations."""
from dataclasses import fields

from .body_spline import BodySplinePlan
from .body_limb_mechanisms import BodyLimbMechanismJointSpec, BodyLimbMechanismRole
from .fit_symmetry import FitBuildSide


def decode_spline(raw, body):
    from .character_registry import exact, path, vector, CharacterRegistryError
    from .spline_names import spline_system_valid,remap_spline_value,scope_spline_plan
    system=raw.get('system_name','') if isinstance(raw,dict) else ''
    if not spline_system_valid(system):
        raise CharacterRegistryError('来源 Spline 系统名称无效')
    if system:
        raw={**remap_spline_value(raw,system,canonical=True),'system_name':''}

    if isinstance(raw, dict) and 'use_offset_parent_matrix' not in raw:
        raw = {**raw, 'use_offset_parent_matrix': False}
    if isinstance(raw, dict) and 'even_stretch_graph' not in raw:
        raw = {**raw, 'even_stretch_graph': False}
    if isinstance(raw, dict) and 'twist_ramp_graph' not in raw:
        raw = {**raw, 'twist_ramp_graph': False}
    if isinstance(raw, dict) and 'mid_follow_graph' not in raw:
        raw = {**raw, 'mid_follow_graph': False}
    if isinstance(raw, dict) and 'isolated_mid_follow_graph' not in raw:
        raw = {**raw, 'isolated_mid_follow_graph': False}
    if isinstance(raw, dict) and 'sub_targets' not in raw:
        raw = {**raw, 'sub_targets': [], 'extra_curve': False}
    if isinstance(raw, dict) and 'fk_root_point_from_receiver' not in raw:
        raw = {**raw, 'fk_root_point_from_receiver': False}
    if isinstance(raw, dict) and 'source_curve_points' not in raw:
        raw = {**raw, 'source_curve_points': [], 'fake_mid_control': False}
    if isinstance(raw, dict):
        for key, value in (('source_hybrid_graph',False),('source_control_axes',[]),('source_ik_local',False),('source_cv_axes',[]),('source_controller_layers',False),('source_follow_parent',None),('source_follow_targets',[]),('system_name',''),('source_body_matrix_indices',[]),('source_bendy_matrix_indices',[]),('source_fixed_orient_unique',False)):
            if key not in raw:
                raw = {**raw,key:value}
    if isinstance(raw,dict) and 'source_first_translate' not in raw:
        raw={**raw,'source_first_translate':False}
    if isinstance(raw,dict) and 'source_world_controls' not in raw:
        raw={**raw,'source_world_controls':False}
    if isinstance(raw,dict) and 'source_mode' not in raw:
        raw={**raw,'source_mode':None}
    if isinstance(raw,dict) and 'source_fit_control_count' not in raw:
        raw={**raw,'source_fit_control_count':None}
    if isinstance(raw,dict) and 'source_scale_indices' not in raw:
        raw={**raw,'source_scale_indices':[]}
    if isinstance(raw,dict) and 'source_ik_chain' not in raw:
        raw={**raw,'source_ik_chain':[]}
    if isinstance(raw,dict) and 'source_solver_tail' not in raw:
        raw={**raw,'source_solver_tail':None}
    if isinstance(raw,dict):
        for key in ('source_simple_twist','source_forward_axis'):
            if key not in raw:raw={**raw,key:None}
        if 'source_start_volume' not in raw:raw={**raw,'source_start_volume':False}
        if 'source_local_scale_indices' not in raw:raw={**raw,'source_local_scale_indices':[]}
    exact(raw, (field.name for field in fields(BodySplinePlan)))
    fit_count=raw['source_fit_control_count']
    if fit_count is not None and (type(fit_count) is not int or fit_count<2
                                 or not raw['source_curve_points']):
        raise CharacterRegistryError('来源 Spline Fit 标签控制数量无效')
    if type(raw['source_first_translate']) is not bool or raw['source_first_translate'] and not raw['source_curve_points']:
        raise CharacterRegistryError('来源 Spline 首控制器位移标记无效')
    if type(raw['source_world_controls']) is not bool or raw['source_world_controls'] and not raw['source_curve_points']:
        raise CharacterRegistryError('来源 Spline 世界控制朝向标记无效')
    source_mode=None
    if raw['source_mode'] is not None:
        from .source_spline_mode import SourceSplineModePlan
        mode=raw['source_mode']
        exact(mode,(field.name for field in fields(SourceSplineModePlan)))
        if not raw['source_curve_points']:
            raise CharacterRegistryError('只有来源 Spline 使用独立 FKIK 控制器')
        try:
            source_mode=SourceSplineModePlan(**{**mode,'parent_source':path(mode['parent_source'])})
        except (TypeError,ValueError,AttributeError) as exc:
            raise CharacterRegistryError('来源 Spline FKIK 控制器保存数据无效') from exc
    if type(raw['use_offset_parent_matrix']) is not bool:
        raise CharacterRegistryError('Spline OPM 开关无效')
    if type(raw['even_stretch_graph']) is not bool:
        raise CharacterRegistryError('Spline stretchEven 图标记无效')
    if (type(raw['twist_ramp_graph']) is not bool
            or (raw['twist_ramp_graph'] and not raw['even_stretch_graph'])):
        raise CharacterRegistryError('Spline 中间扭转图标记无效')
    if (type(raw['mid_follow_graph']) is not bool
            or (raw['mid_follow_graph'] and not raw['twist_ramp_graph']
                and not (raw['source_simple_twist'] is True and raw['source_curve_points']))):
        raise CharacterRegistryError('Spline 中间跟随图标记无效')
    if (type(raw['isolated_mid_follow_graph']) is not bool
            or (raw['isolated_mid_follow_graph'] and not raw['mid_follow_graph'])):
        raise CharacterRegistryError('Spline 独立跟随层标记无效')
    if type(raw['extra_curve']) is not bool:
        raise CharacterRegistryError('Spline IK Extra 曲线标记无效')
    if type(raw['fk_root_point_from_receiver']) is not bool:
        raise CharacterRegistryError('Spline FK 位置来源开关无效')
    if type(raw['source_fixed_orient_unique']) is not bool or raw['source_fixed_orient_unique'] and not raw['source_curve_points']:
        raise CharacterRegistryError('来源 Spline 固定朝向命名标记无效')
    body_paths = tuple(path(p) for p in raw['body_joints'])
    count = len(body_paths)
    scale_indices=raw['source_scale_indices']
    if (not isinstance(scale_indices,(list,tuple)) or scale_indices and (
            not raw['source_curve_points'] or len(scale_indices)!=count
            or any(type(index) is not int or index<0 for index in scale_indices)
            or scale_indices[0]!=0 or tuple(sorted(set(scale_indices)))!=tuple(scale_indices))):
        raise CharacterRegistryError('来源 Spline 扩展缩放索引无效')
    if count<2 or (not raw['source_curve_points'] and count>64) or len(set(body_paths)) != count:
        raise CharacterRegistryError('曲线脊柱关节数量或身份无效')
    if source_mode is not None:
        identities=tuple(p.rsplit('|',1)[-1] for p in body_paths)
        side=source_mode.name.rsplit('_',1)[-1]
        if (any(not name.endswith('_'+side) for name in identities)
                or identities[0]!=source_mode.start_joint+'_'+side
                or identities[-1]!=source_mode.end_joint+'_'+side
                or source_mode.middle_joint+'_'+side not in identities):
            raise CharacterRegistryError('来源 Spline FKIK 骨链标记与实际 Body 身份不一致')
    matrix_indices=raw['source_body_matrix_indices']
    local_indices=raw['source_local_scale_indices']
    if (not isinstance(local_indices,(list,tuple))
            or any(type(index) is not int or not 0<=index<count for index in local_indices)
            or tuple(sorted(set(local_indices)))!=tuple(local_indices)
            or local_indices and (raw['use_offset_parent_matrix'] or not raw['source_ik_chain']
                                  or not raw['source_curve_points'])):
        raise CharacterRegistryError('来源 Spline 局部缩放接收索引无效')
    if (not isinstance(matrix_indices,(list,tuple))
            or any(type(index) is not int or not 0<=index<count for index in matrix_indices)
            or tuple(sorted(set(matrix_indices)))!=tuple(matrix_indices)
            or matrix_indices and (not raw['use_offset_parent_matrix'] or not raw['source_curve_points'])):
        raise CharacterRegistryError('来源 Spline Body 矩阵接收索引无效')
    bendy_indices=raw['source_bendy_matrix_indices']
    if (not isinstance(bendy_indices,(list,tuple))
            or any(type(index) is not int or not 0<=index<count for index in bendy_indices)
            or tuple(sorted(set(bendy_indices)))!=tuple(bendy_indices)
            or set(bendy_indices)&set(matrix_indices)
            or bendy_indices and (not raw['use_offset_parent_matrix'] or not raw['source_curve_points'])):
        raise CharacterRegistryError('来源 Spline Bendy 矩阵交接索引无效')
    if raw['twist_ramp_graph'] and count<=2 and len(raw['source_ik_chain'])<=2:
        raise CharacterRegistryError('两关节 Spline 不使用中间扭转曲线')
    if raw['mid_follow_graph'] and count<=2 and not raw['source_curve_points']:
        raise CharacterRegistryError('两关节 Spline 不使用中间跟随图')
    by_path = {joint.path: joint for joint in body}
    from .body_limb_mechanisms import body_limb_parent_matches
    if any(p not in by_path for p in body_paths) or any(
        not body_limb_parent_matches(by_path[p].parent, parent,
                                    allow_part_parents=True)
        for parent, p in zip(body_paths, body_paths[1:])
    ):
        raise CharacterRegistryError('曲线脊柱必须对应实际 Body 父链')
    root = path(raw['root_path'])
    lengths = vector(raw['lengths'], count - 1)
    if min(lengths) <= 0:
        raise CharacterRegistryError('曲线脊柱骨段长度必须为正')
    axes = tuple(vector(axis, 3) for axis in raw['axes'])
    if len(axes) != 3 or any(abs(sum(a*b for a,b in zip(left,right)) - (i == j)) > 1e-5
                             for i,left in enumerate(axes) for j,right in enumerate(axes)):
        raise CharacterRegistryError('曲线脊柱朝向必须正交归一')
    positions = tuple(vector(position, 3) for position in raw['positions'])
    source_points = tuple(vector(position,3) for position in raw['source_curve_points'])
    control_axes = tuple(tuple(vector(axis,3) for axis in frame) for frame in raw['source_control_axes'])
    cv_axes = tuple(tuple(vector(axis,3) for axis in frame) for frame in raw['source_cv_axes'])
    if cv_axes and (not source_points or len(cv_axes)!=len(source_points) or any(
            len(frame)!=3 or any(abs(sum(a*b for a,b in zip(left,right))-(i==j))>1e-5
                for i,left in enumerate(frame) for j,right in enumerate(frame)) for frame in cv_axes)):
        raise CharacterRegistryError('来源 Spline CV 朝向声明无效')
    if (type(raw['fake_mid_control']) is not bool
            or source_points and len(source_points)!=(len(raw['source_ik_chain']) if raw['source_ik_chain'] else count)
            or raw['fake_mid_control'] and not source_points):
        raise CharacterRegistryError('来源 Spline 曲线点或补充中间控制标记无效')
    if (type(raw['source_hybrid_graph']) is not bool or type(raw['source_ik_local']) is not bool
            or type(raw['source_controller_layers']) is not bool
            or raw['source_controller_layers'] and not source_points
            or (raw['source_hybrid_graph'] or raw['source_ik_local'] or control_axes) and not source_points
            or control_axes and (len(control_axes)!=len(positions) or any(
                len(frame)!=3 or any(abs(sum(a*b for a,b in zip(left,right))-(i==j))>1e-5
                    for i,left in enumerate(frame) for j,right in enumerate(frame)) for frame in control_axes))):
        raise CharacterRegistryError('来源 Spline Hybrid 或控制朝向声明无效')
    targets = tuple(path(target) for target in raw['targets'])
    follow_parent = path(raw['source_follow_parent']) if raw['source_follow_parent'] is not None else None
    follow_targets = []
    for row in raw['source_follow_targets']:
        if (not isinstance(row,(tuple,list)) or len(row)!=3
                or not isinstance(row[0],str) or not row[0].isascii()
                or not row[0].replace('_','').isalnum()
                or type(row[2]) not in (float,int) or not 0<=row[2]<=10):
            raise CharacterRegistryError('来源 Spline Follow 层声明无效')
        follow_targets.append((row[0],path(row[1]),float(row[2])))
    follow_targets=tuple(follow_targets)
    if (bool(follow_parent)!=bool(follow_targets)
            or follow_parent and not raw['source_controller_layers']
            or len({row[0] for row in follow_targets})!=len(follow_targets)
            or follow_targets and not {'Main','Root'}.issubset({row[0] for row in follow_targets})):
        raise CharacterRegistryError('来源 Spline Follow 结构不完整')
    subs = tuple(path(target) for target in raw['sub_targets'])
    if subs and (len(subs) != len(targets) or any(
            sub != target+f'|AdvPy_SplineIK{index}Sub'
            for index, (target, sub) in enumerate(zip(targets, subs)))):
        raise CharacterRegistryError('Spline IK Sub 控制器层级无效')
    has_extras = all(target.rsplit('|', 1)[0].rsplit('|', 1)[-1]
                     == f'AdvPy_SplineIK{index}Extra'
                     for index, target in enumerate(targets))
    if raw['extra_curve'] and not has_extras:
        raise CharacterRegistryError('Spline IK Extra 曲线缺少父层')
    for index, target in enumerate(targets):
        offset = (target.rsplit('|', 2)[0] if has_extras
                  else target.rsplit('|', 1)[0])
        if offset.rsplit('|', 1)[-1] != f'AdvPy_SplineIK{index}Offset':
            raise CharacterRegistryError('Spline IK Offset 层级无效')
    if raw['isolated_mid_follow_graph']:
        for index, target in enumerate(targets):
            if raw['source_hybrid_graph'] and index in (0,len(targets)-1):
                continue
            parent = (raw['pelvis_control']+'|AdvPy_SplineIKFollowMain'
                      if 0<index<len(targets)-1 else raw['pelvis_control'])
            offset = parent+f'|AdvPy_SplineIK{index}Offset'
            expected = (offset+f'|AdvPy_SplineIK{index}Extra|AdvPy_SplineIK{index}'
                        if has_extras else offset+f'|AdvPy_SplineIK{index}')
            if target != expected:
                raise CharacterRegistryError('曲线脊柱 IK 控制器层级与跟随模式不一致')
    controls = tuple(path(control) for control in raw['fk_controls'])
    valid_count = (3 <= len(targets) if source_points
                   else len(targets) in (4,max(4,count+1)))
    if (not valid_count or len(positions)!=len(targets)
            or len(set(targets)) != len(targets) or len(controls) != count or len(set(controls)) != count):
        raise CharacterRegistryError('曲线脊柱控制器声明不完整')
    if raw['fake_mid_control'] and len(targets)!=3:
        raise CharacterRegistryError('来源 Spline 补充中间控制必须为三主控')
    native=[]
    for row in raw['source_ik_chain']:
        exact(row,(field.name for field in fields(BodyLimbMechanismJointSpec)))
        node=path(row['path']);source=path(row['source_joint'])
        frame=tuple(vector(axis,3) for axis in row['world_axes'])
        parent=root if not native else native[-1].path
        if (not source_points or row['role']!='ik' or row['parent_path']!=parent
                or node!=parent+'|'+row['name'] or len(frame)!=3
                or any(abs(sum(a*b for a,b in zip(left,right))-(i==j))>1e-5
                    for i,left in enumerate(frame) for j,right in enumerate(frame))):
            raise CharacterRegistryError('来源 Spline 完整 IK 父链无效')
        if source not in body_paths:
            # Only physical Inbetween Part ancestors may intervene between bases.
            if not any(end.startswith(source+'|') for end in body_paths):
                raise CharacterRegistryError('来源 Spline IK Part 不属于 Body 骨链')
            leaf=source.rsplit('|',1)[-1]
            if row['name']!='AdvPy_'+leaf+'_SplineNativeIK' or 'Part' not in leaf:
                raise CharacterRegistryError('来源 Spline IK Part 身份无效')
        native.append(BodyLimbMechanismJointSpec(BodyLimbMechanismRole.IK,
            FitBuildSide(row['side']),source,node,row['name'],parent,
            vector(row['world_position'],3),frame))
    if native and (tuple(j.source_joint for j in native if j.source_joint in body_paths)!=body_paths
                   or len({j.source_joint for j in native})!=len(native)
                   or tuple(i for i,j in enumerate(native) if j.source_joint in body_paths)!=tuple(scale_indices)):
        raise CharacterRegistryError('来源 Spline 完整 IK 链与缩放索引不一致')
    if native:
        for first,last in zip(native,native[1:]):
            if last.source_joint.rsplit('|',1)[0]!=first.source_joint or last.side!=first.side:
                raise CharacterRegistryError('来源 Spline IK 链没有严格继承物理 Fit Part 父链')
    native_by_source={joint.source_joint:joint for joint in native}
    joints = []
    for index, row in enumerate(raw['joints']):
        exact(row, (field.name for field in fields(BodyLimbMechanismJointSpec)))
        node = path(row['path'])
        joint_axes = tuple(vector(axis, 3) for axis in row['world_axes'])
        if len(joint_axes) != 3 or row['name'] != node.rsplit('|', 1)[-1]:
            raise CharacterRegistryError('曲线脊柱机制关节描述无效')
        joint = BodyLimbMechanismJointSpec(
            BodyLimbMechanismRole(row['role']), FitBuildSide(row['side']), path(row['source_joint']),
            node, row['name'], path(row['parent_path']), vector(row['world_position'], 3), joint_axes)
        expected_parent = (native_by_source[body_paths[index%count]].parent_path
                           if native and index>=count else root if index % count == 0 else joints[-1].path)
        if (index >= count * 2 or joint.source_joint != body_paths[index % count]
                or joint.role.value != ('fk' if index < count else 'ik')
                or joint.parent_path != expected_parent or node.rsplit('|', 1)[0] != expected_parent):
            raise CharacterRegistryError('曲线脊柱机制链顺序或父级无效')
        if native and index>=count and joint!=native_by_source[joint.source_joint]:
            raise CharacterRegistryError('来源 Spline 基础 IK 与完整 IK 链描述不一致')
        joints.append(joint)
    if len(joints) != count * 2:
        raise CharacterRegistryError('曲线脊柱机制链不完整')
    solver_tail=None
    if raw['source_solver_tail'] is not None:
        row=raw['source_solver_tail'];exact(row,(field.name for field in fields(BodyLimbMechanismJointSpec)))
        frame=tuple(vector(axis,3) for axis in row['world_axes'])
        if (not native or row['role']!='ik' or row['side']!=native[-1].side.value
                or row['source_joint']!=body_paths[-1] or row['name']!='AdvPy_SplineIKEndFake'
                or row['parent_path'] not in (native[-1].path,native[-2].path)
                or row['path']!=row['parent_path']+'|'+row['name']
                or len(frame)!=3 or frame!=native[-1].world_axes
                or vector(row['world_position'],3)!=native[-1].world_position):
            raise CharacterRegistryError('来源 Spline 原版辅助端点描述无效')
        solver_tail=BodyLimbMechanismJointSpec(BodyLimbMechanismRole.IK,native[-1].side,
            body_paths[-1],path(row['path']),row['name'],path(row['parent_path']),
            vector(row['world_position'],3),frame)
    simple=raw['source_simple_twist'];forward=raw['source_forward_axis']
    start_volume=raw['source_start_volume']
    if (type(start_volume) is not bool or start_volume and (not native or not raw['source_curve_points']
            or native[0].source_joint.rsplit('|',1)[-1].rsplit(':',1)[-1].rsplit('_',1)[0]=='Root')):
        raise CharacterRegistryError('来源 Spline 起点体积标记无效')
    if ((simple is None)!=(forward is None)
            or simple is not None and (type(simple) is not bool or not native
                or simple!=(len(native)==2) or type(forward) is not int or forward not in (0,1)
                or simple and forward!=0 or forward==1 and native[0].side is not FitBuildSide.LEFT)):
        raise CharacterRegistryError('来源 Spline 原版扭转模式或求解方向无效')
    result = BodySplinePlan(root, tuple(joints), body_paths, controls, path(raw['pelvis_control']),
                          path(raw['chest_space']), targets, positions, axes,
                          lengths, raw['use_offset_parent_matrix'],
                          raw['even_stretch_graph'], raw['twist_ramp_graph'],
                          raw['mid_follow_graph'], raw['isolated_mid_follow_graph'],
                          subs, raw['extra_curve'],
                          raw['fk_root_point_from_receiver'], source_points,
                          raw['fake_mid_control'],raw['source_hybrid_graph'],
                          control_axes,raw['source_ik_local'],cv_axes,
                          raw['source_controller_layers'],follow_parent,follow_targets,
                          source_body_matrix_indices=tuple(matrix_indices),
                          source_bendy_matrix_indices=tuple(bendy_indices),
                          source_fixed_orient_unique=raw['source_fixed_orient_unique'],
                          source_first_translate=raw['source_first_translate'],
                          source_world_controls=raw['source_world_controls'],source_mode=source_mode,
                          source_fit_control_count=fit_count,source_scale_indices=tuple(scale_indices),source_ik_chain=tuple(native),source_solver_tail=solver_tail,
                          source_simple_twist=simple,source_forward_axis=forward,source_start_volume=start_volume,
                          source_local_scale_indices=tuple(local_indices))
    if result.source_hybrid_graph and any(
            offset.rsplit('|',1)[0]!=result.target_parent(index)
            for index,offset in enumerate(result.offset_targets)):
        raise CharacterRegistryError('来源 Spline IKhybrid 主控父层无效')
    return scope_spline_plan(result,system)
