"""Explicit FK position and cross-section channels for spline pose transfer."""
from dataclasses import replace
from math import sqrt

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterChannel, CharacterRegistryError

PREFIX = 'spine.fkMatch.'


def channels(registration):
    plan = registration.spine
    if not isinstance(plan, BodySplinePlan):
        raise CharacterRegistryError('曲线脊柱匹配扩展要求 Spline 角色')
    result = []
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        if index:
            result.extend(CharacterChannel(f'{PREFIX}{index}.translate{axis}', control, 'translate'+axis) for axis in 'XYZ')
        result.extend(CharacterChannel(f'{PREFIX}{index}.scale{axis}', control, 'matchScale'+axis, .001, None) for axis in 'XYZ')
    return tuple(result)


def enabled(registration):
    return any(ch.key.startswith(PREFIX) for ch in registration.channels)


def install(host, registration):
    host._require_transaction()
    extra = channels(registration)
    if len(registration.spine.body_joints)==2 and host._cmds.getAttr('AdvPy_SplineIKHandle.dTwistControlEnable'):
        before_twist=tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
        host._transaction_changed=True
        host._cmds.setAttr('AdvPy_SplineIKHandle.dTwistControlEnable',False)
        after_twist=tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
        if max(abs(a-b) for x,y in zip(before_twist,after_twist) for a,b in zip(x,y))>1e-4:
            raise CharacterRegistryError('单段脊柱扭转修正改变当前姿态')
    if enabled(registration):
        audit(host, registration)
        return registration
    c = host._cmds
    plan = registration.spine
    if c.getAttr(plan.root_path+'.advPySplineOwner')!='adv_py.spline.v2':
        raise CharacterRegistryError('曲线脊柱匹配要求修正缩放传递后的 v2 求解图；旧实验角色需要显式迁移')
    count = len(plan.body_joints)
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        if index and c.objExists(f'AdvPy_SplineFKMatchPoint{index}'):
            raise CharacterRegistryError('曲线脊柱匹配节点名称被占用')
        for axis in 'XYZ':
            if c.objExists(control+'.matchScale'+axis):
                raise CharacterRegistryError('曲线脊柱匹配属性被占用')
    before = tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
    host._transaction_changed = True
    for index, (control, joint) in enumerate(zip(plan.fk_controls, plan.joints[:count])):
        if not index:continue
        for axis in 'XYZ':
            c.addAttr(control, longName='matchScale'+axis, niceName='匹配缩放 '+axis,
                      attributeType='double', minValue=.001, defaultValue=1., keyable=True)
            c.connectAttr(control+'.matchScale'+axis, joint.path+'.scale'+axis)
            if index:
                c.setAttr(control+'.translate'+axis, lock=False, keyable=True)
        if index:
            c.pointConstraint(control, joint.path, maintainOffset=False, name=f'AdvPy_SplineFKMatchPoint{index}')
            c.connectAttr(plan.joints[index-1].path+'.scale', joint.path+'.inverseScale', force=True)
    # FK mechanism inputs changed, while all registered object identities remain.
    fk_paths = {joint.path for joint in plan.joints[:count]}
    result = replace(registration, channels=registration.channels+extra,
                     nodes=tuple(host._registry_node(node.path) if node.path in fk_paths else node for node in registration.nodes))
    host.write_character_registration_extension(registration, result)
    after = tuple(host._spine_world_frame(j.path)[0] for j in registration.body)
    if max(abs(a-b) for left,right in zip(before,after) for a,b in zip(left,right)) > 1e-4:
        raise RuntimeError('启用曲线脊柱匹配改变当前身体姿态')
    audit(host, result)
    return result


def audit(host, registration):
    if not enabled(registration):
        return
    if tuple(ch for ch in registration.channels if ch.key.startswith(PREFIX)) != channels(registration):
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


def match_fk(host, registration, before):
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
    local = tuple((tuple(c.getAttr(j+'.rotate')[0]), tuple(c.getAttr(j+'.scale')[0])) for j in plan.body_joints)
    c.setAttr(plan.settings+'.spineIkFk', 0.)
    for index, control in enumerate(plan.fk_controls):
        if not index:continue
        joint = plan.body_joints[index]
        matrix = wanted[joint.rsplit('|',1)[-1]]
        host._spine_set_world_rotation(control, matrix)
        c.xform(control, worldSpace=True, translation=matrix[12:15])
        for axis, start in zip('XYZ', (0,4,8)):
            c.setAttr(control+'.matchScale'+axis, sqrt(sum(v*v for v in matrix[start:start+3]))/global_scale)
        _solve_local_output(c, control, joint, *local[index])
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


def _solve_local_output(c, control, joint, rotation, scale):
    plugs = tuple(control+'.'+name+axis for name in ('rotate','matchScale') for axis in 'XYZ')
    wanted = rotation+scale
    def output():return tuple(c.getAttr(joint+'.rotate')[0])+tuple(c.getAttr(joint+'.scale')[0])
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
