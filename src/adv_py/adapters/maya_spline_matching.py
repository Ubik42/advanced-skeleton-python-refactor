"""Explicit FK position and cross-section channels for spline pose transfer."""
from dataclasses import replace
from math import sqrt

from adv_py.core.body_spline import BodySplinePlan, spline_owner_version
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.character_registry import CharacterChannel, CharacterRegistryError

PREFIX = 'spine.fkMatch.'


def _prefix(registration):
    name=getattr(registration.spine,'system_name','')
    return PREFIX+name+'.' if name else PREFIX


def channels(registration):
    plan = registration.spine
    if not isinstance(plan, BodySplinePlan):
        raise CharacterRegistryError('曲线脊柱匹配扩展要求 Spline 角色')
    result = []
    prefix=_prefix(registration)
    existing = {(channel.node, channel.attribute) for channel in registration.channels
                if not channel.key.startswith(prefix)}
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        if index:
            result.extend(CharacterChannel(f'{prefix}{index}.translate{axis}', control, 'translate'+axis) for axis in 'XYZ'
                          if (control, 'translate'+axis) not in existing)
        result.extend(CharacterChannel(f'{prefix}{index}.scale{axis}', control, 'matchScale'+axis, .001, None) for axis in 'XYZ')
    return tuple(result)


def enabled(registration):
    if registration.additional_spines:
        return all(enabled(replace(registration,spine=plan,additional_spines=()))
                   for plan in (registration.spine,)+registration.additional_spines)
    return any(ch.key.startswith(_prefix(registration)) for ch in registration.channels)


def install(host, registration,*,_persist=True,_scoped=False):
    if registration.additional_spines:
        result=registration
        for plan in (registration.spine,)+registration.additional_spines:
            view=replace(result,spine=plan,additional_spines=())
            built=install(host,view,_persist=False)
            result=replace(result,channels=built.channels,nodes=built.nodes)
        if _persist:
            host.write_character_registration_extension(registration,result)
        return result
    if getattr(registration.spine,'system_name','') and not _scoped:
        from .maya_spline_scope import spline_scope
        with spline_scope(host,registration.spine,localize=False):
            return install(host,registration,_persist=_persist,_scoped=True)
    host._require_transaction()
    extra = channels(registration)
    c = host._cmds
    plan = registration.spine
    try:
        version = spline_owner_version(c.getAttr(
            plan.root_path+'.advPySplineOwner'))
    except FitSkeletonValidationError as exc:
        raise CharacterRegistryError('曲线脊柱求解图所有权无效') from exc
    if (len(plan.body_joints)==2 and version<18
            and c.getAttr('AdvPy_SplineIKHandle.dTwistControlEnable')):
        before_twist=tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
        host._transaction_changed=True
        c.setAttr('AdvPy_SplineIKHandle.dTwistControlEnable',False)
        after_twist=tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
        if max(abs(a-b) for x,y in zip(before_twist,after_twist) for a,b in zip(x,y))>1e-4:
            raise CharacterRegistryError('单段脊柱扭转修正改变当前姿态')
    if enabled(registration):
        audit(host, registration)
        return registration
    if version < 2:
        raise CharacterRegistryError('曲线脊柱匹配要求受支持的求解图；旧实验角色需要显式迁移')
    count = len(plan.body_joints)
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        if index and c.objExists(f'AdvPy_SplineFKMatchPoint{index}'):
            raise CharacterRegistryError('曲线脊柱匹配节点名称被占用')
        for axis in 'XYZ':
            if c.objExists(control+'.matchScale'+axis):
                raise CharacterRegistryError('曲线脊柱匹配属性被占用')
    # Fresh generic source FK already owns position and local scale links.
    # Replace only those declared links, rather than adding a second point
    # constraint or force-overwriting a user-authored input.
    native_points = {}
    for index, control in enumerate(plan.fk_controls[1:], 1):
        joint = plan.joints[index].path
        source = c.connectionInfo(joint + '.scale', sourceFromDestination=True)
        if source and source != control + '.scale':
            raise CharacterRegistryError('曲线 FK 缩放输入不是声明的控制器：' + joint)
        if not source and any(c.connectionInfo(joint + '.scale' + axis,
                sourceFromDestination=True) for axis in 'XYZ'):
            raise CharacterRegistryError('曲线 FK 缩放输入存在额外轴连接：' + joint)
        point_name = control.rsplit('|', 1)[-1].removesuffix('FK') + 'FKPoint'
        points = c.ls(point_name, long=True, type='pointConstraint') or []
        incoming = tuple(c.connectionInfo(joint + '.translate' + axis,
                          sourceFromDestination=True) for axis in 'XYZ')
        if points:
            if len(points) != 1 or any(
                    not plug or host._resolve_connected_node(plug.split('.', 1)[0]) != points[0]
                    for plug in incoming):
                raise CharacterRegistryError('曲线 FK 位置输入不是声明的约束：' + joint)
            native_points[index] = points[0]
        elif any(incoming):
            raise CharacterRegistryError('曲线 FK 位置输入有外部连接：' + joint)
    before = tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
    host._transaction_changed = True
    for index, (control, joint) in enumerate(zip(plan.fk_controls, plan.joints[:count])):
        if not index:continue
        initial_scale = tuple(float(c.getAttr(joint.path + '.scale' + axis))
                              for axis in 'XYZ')
        if any(value < .001 for value in initial_scale):
            raise CharacterRegistryError('曲线 FK 匹配要求正的截面缩放：' + joint.path)
        source = c.connectionInfo(joint.path + '.scale', sourceFromDestination=True)
        if source:
            c.disconnectAttr(source, joint.path + '.scale')
        if index in native_points:
            c.delete(native_points[index])
        for axis, value in zip('XYZ', initial_scale):
            c.addAttr(control, longName='matchScale'+axis, niceName='匹配缩放 '+axis,
                      attributeType='double', minValue=.001, defaultValue=value, keyable=True)
            c.connectAttr(control+'.matchScale'+axis, joint.path+'.scale'+axis)
            if index:
                c.setAttr(control+'.translate'+axis, lock=False, keyable=True)
        if index:
            c.pointConstraint(control, joint.path, maintainOffset=False, name=f'AdvPy_SplineFKMatchPoint{index}')
            c.connectAttr(plan.joints[index-1].path+'.scale', joint.path+'.inverseScale', force=True)
        if index in plan.source_body_matrix_indices:
            from .maya_source_spline_body_matrix import install_match_scale
            install_match_scale(host,plan,index,control)
        elif index in plan.source_bendy_matrix_indices:
            from .maya_source_spline_body_matrix import install_bendy_match_scale
            install_bendy_match_scale(host,plan,index,control)
    # FK mechanism inputs changed, while all registered object identities remain.
    fk_paths = {joint.path for joint in plan.joints[:count]}
    result = replace(registration, channels=registration.channels+extra,
                     nodes=tuple(host._registry_node(node.path) if node.path in fk_paths else node for node in registration.nodes))
    if _persist:
        host.write_character_registration_extension(registration, result)
    after = tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
    if max(abs(a-b) for left,right in zip(before,after) for a,b in zip(left,right)) > 1e-4:
        raise RuntimeError('启用曲线脊柱匹配改变当前身体姿态')
    audit(host, result)
    return result


def audit(host, registration,*,_scoped=False):
    if registration.additional_spines:
        for plan in (registration.spine,)+registration.additional_spines:
            audit(host,replace(registration,spine=plan,additional_spines=()))
        return
    if getattr(registration.spine,'system_name','') and not _scoped:
        from .maya_spline_scope import spline_scope
        with spline_scope(host,registration.spine,localize=False):
            return audit(host,registration,_scoped=True)
    if not enabled(registration):
        return
    if tuple(ch for ch in registration.channels if ch.key.startswith(_prefix(registration))) != channels(registration):
        raise CharacterRegistryError('曲线脊柱匹配通道不完整')
    c = host._cmds
    plan = registration.spine
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        joint = plan.joints[index].path
        for axis in 'XYZ':
            if not c.isConnected(control+'.matchScale'+axis, joint+'.scale'+axis):
                raise CharacterRegistryError('曲线脊柱匹配截面连接被替换')
        if index:
            node = f'AdvPy_SplineFKMatchPoint{index}'
            if not c.objExists(node) or c.nodeType(node) != 'pointConstraint':
                raise CharacterRegistryError('曲线脊柱 FK 位置约束缺失')
            targets = tuple(host._resolve_connected_node(p) for p in c.pointConstraint(node, q=True, targetList=True))
            aliases=c.pointConstraint(node,q=True,weightAliasList=True)
            if (any(abs(c.getAttr(node+'.offset'+axis))>1e-9 or c.listConnections(node+'.offset'+axis,s=True,d=False) for axis in 'XYZ')
                    or len(aliases)!=1 or abs(c.getAttr(node+'.'+aliases[0])-1.)>1e-9 or c.listConnections(node+'.'+aliases[0],s=True,d=False)):
                raise CharacterRegistryError('曲线脊柱 FK 位置约束参数被修改')
            if targets != (control,):
                raise CharacterRegistryError('曲线脊柱 FK 位置来源被替换')
            if any(not c.isConnected(node+'.constraintTranslate'+a, joint+'.translate'+a) for a in 'XYZ'):
                raise CharacterRegistryError('曲线脊柱 FK 位置输出被替换')
            if not c.isConnected(plan.joints[index-1].path+'.scale', joint+'.inverseScale'):
                raise CharacterRegistryError('曲线脊柱 FK 缩放补偿被替换')
    if plan.source_body_matrix_indices or plan.source_bendy_matrix_indices:
        from .maya_source_spline_body_matrix import audit as audit_body_matrix
        audit_body_matrix(host,plan)


def match_fk(host, registration, before,*,_scoped=False):
    if registration.additional_spines:
        for plan in (registration.spine,)+registration.additional_spines:
            match_fk(host,replace(registration,spine=plan,additional_spines=()),before)
        return
    if getattr(registration.spine,'system_name','') and not _scoped:
        from .maya_spline_scope import spline_scope
        with spline_scope(host,registration.spine,localize=False):
            return match_fk(host,registration,before,_scoped=True)
    if not enabled(registration):
        raise CharacterRegistryError('先启用曲线脊柱动画匹配通道')
    c = host._cmds
    plan = registration.spine
    wanted = dict(before.body_frames)
    root_matrix = host._spine_world_frame(plan.root_path)[0]
    global_scale = sqrt(sum(v*v for v in root_matrix[:3]))
    if global_scale < 1e-8:
        raise CharacterRegistryError('曲线脊柱机制组缩放无效')
    # Preserve the actual local outputs, including the scale compensation of
    # mixed IK/FK poses. Decomposing a sheared world matrix loses this information.
    from .maya_source_spline_body_matrix import local_rotation_scale
    matrix_indices=(*plan.source_body_matrix_indices,*plan.source_bendy_matrix_indices)
    local = tuple(local_rotation_scale(host,j) if index in matrix_indices
                  else (tuple(c.getAttr(j+'.rotate')[0]),tuple(c.getAttr(j+'.scale')[0]))
                  for index,j in enumerate(plan.body_joints))
    c.setAttr(plan.settings+'.spineIkFk', 0.)
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        joint = plan.body_joints[index]
        matrix = wanted[joint.rsplit('|',1)[-1]]
        host._spine_set_world_rotation(control, matrix)
        c.xform(control, worldSpace=True, translation=matrix[12:15])
        for axis, start in zip('XYZ', (0,4,8)):
            c.setAttr(control+'.matchScale'+axis, sqrt(sum(v*v for v in matrix[start:start+3]))/global_scale)
        _solve_local_output(c, control, joint, *local[index],
            read_output=(lambda joint=joint:sum(local_rotation_scale(host,joint),()))
            if index in matrix_indices else None)
        c.xform(control, worldSpace=True, translation=matrix[12:15])


def _solve_linear(matrix, values):
    rows = [list(row)+[value] for row,value in zip(matrix,values)]
    for column in range(len(rows)):
        pivot = max(range(column,len(rows)),key=lambda i:abs(rows[i][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        if abs(rows[column][column]) < 1e-10:
            raise CharacterRegistryError('曲线脊柱匹配遇到不可逆的控制姿态')
        divisor = rows[column][column]
        rows[column] = [value/divisor for value in rows[column]]
        for index in range(len(rows)):
            if index == column:continue
            factor = rows[index][column]
            rows[index] = [a-factor*b for a,b in zip(rows[index],rows[column])]
    return tuple(row[-1] for row in rows)


def _solve_local_output(c, control, joint, rotation, scale,*,read_output=None):
    plugs = tuple(control+'.'+name+axis for name in ('rotate','matchScale') for axis in 'XYZ')
    wanted = rotation+scale
    def output():
        return read_output() if read_output is not None else tuple(c.getAttr(joint+'.rotate')[0])+tuple(c.getAttr(joint+'.scale')[0])
    def difference(a,b):
        return tuple((x-y+180.)%360.-180. if i<3 else x-y for i,(x,y) in enumerate(zip(a,b)))
    for iteration in range(12):
        actual = output()
        residual = difference(wanted,actual)
        # Maya constraint angle outputs settle at roughly 1e-7 degrees here.
        # The caller still verifies all world matrices at the unchanged 1e-4 gate.
        if max(abs(v) for v in residual[:3])<1e-6 and max(abs(v) for v in residual[3:])<1e-8:return
        original = tuple(c.getAttr(plug) for plug in plugs)
        columns = []
        for index,plug in enumerate(plugs):
            step = .01 if index<3 else max(1e-5,abs(original[index])*1e-3)
            c.setAttr(plug,original[index]+step)
            columns.append(tuple(v/step for v in difference(output(),actual)))
            c.setAttr(plug,original[index])
        delta = _solve_linear(tuple(zip(*columns)),residual)
        for index,(plug,value,change) in enumerate(zip(plugs,original,delta)):
            value += change
            if index>=3 and value<.001:
                raise CharacterRegistryError('曲线脊柱匹配截面超出正缩放范围')
            c.setAttr(plug,value)
    raise CharacterRegistryError('曲线脊柱 FK 匹配未收敛，已撤销转换：'+joint+' residual='+repr(residual))
