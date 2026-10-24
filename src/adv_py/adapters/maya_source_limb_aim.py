"""Native source Foot/LegAim graph; no MEL dispatch or alternative solver."""
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from adv_py.core.source_limb_aim import plan_source_foot_aim, plan_source_leg_aim


class _Graph:
    def __init__(self, host, stem):
        self.host, self.c, self.stem = host, host._cmds, stem
        self.nodes, self.edges, self.values = [], [], []

    def node(self, kind, suffix):
        if kind=='multDoubleLinear' and int(str(self.c.about(version=True)).split('.')[0])>=2026:
            kind='multDL'  # MEL asCreateMultDL's unitless Maya 2026 node.
        name = self.stem+'_'+suffix
        if self.host.find_name_collisions(name):
            raise CharacterRegistryError('来源瞄准节点名称已存在：'+name)
        node = self.c.createNode(kind, name=name, skipSelect=True)
        if node != name:
            raise CharacterRegistryError('来源瞄准节点名称漂移：'+name)
        self.nodes.append((name, kind))
        return name

    def set(self, plug, value, kind=None):
        if isinstance(value, (tuple, list)):
            self.c.setAttr(plug, *value, type=kind or 'double3')
        else:
            self.c.setAttr(plug, value)
        self.values.append((plug, value))

    def edge(self, source, target):
        self.c.connectAttr(source, target)
        actual = self.c.connectionInfo(target,sourceFromDestination=True)
        if actual:
            node,attribute = actual.split('.',1)
            node = self.host._resolve_connected_node(node)
            if self.c.nodeType(node)=='unitConversion' and actual!=source:
                incoming = self.c.connectionInfo(node+'.input',sourceFromDestination=True)
                if incoming:
                    incoming_node,incoming_attribute = incoming.split('.',1)
                    incoming = self.host._resolve_connected_node(incoming_node)+'.'+incoming_attribute
                if incoming==source:
                    # Maya inserts angle/distance conversions for some native
                    # math-node versions. Keep the actual converter contract.
                    name = self.stem+'_Units'+str(len(self.nodes))
                    if self.host.find_name_collisions(name):
                        raise CharacterRegistryError('来源瞄准单位转换名称已存在：'+name)
                    node = self.c.rename(node,name)
                    if node!=name:
                        raise CharacterRegistryError('来源瞄准单位转换名称漂移')
                    self.nodes.append((node,'unitConversion'))
                    self.values.append((node+'.conversionFactor',float(self.c.getAttr(node+'.conversionFactor'))))
                    self.edges.extend(((source,node+'.input'),(node+'.'+attribute,target)))
                    return
        self.edges.append((source, target))

    def matrix(self, source, target, suffix, use_opm):
        if use_opm:
            self.edge(source,target+'.offsetParentMatrix')
            return
        node = self.node('decomposeMatrix',suffix)
        self.set(node+'.inputRotateOrder',int(self.c.getAttr(target+'.rotateOrder')))
        self.edge(source,node+'.inputMatrix')
        for axis in 'XYZ':
            for kind in ('Translate','Rotate','Scale'):
                self.edge(node+'.output'+kind+axis,target+'.'+kind.lower()+axis)
        for axis,component in zip('XYZ',('XY','XZ','YZ')):
            self.edge(node+'.outputShear'+axis,target+'.shear'+component)

    def record(self, path, role, spec):
        from dataclasses import asdict
        self.c.addAttr(path, longName='advPySourceLimbAim', dataType='string')
        self.c.setAttr(path+'.advPySourceLimbAim', canonical(dict(
            version=1, role=role, spec=asdict(spec), nodes=self.nodes,
            edges=self.edges, values=self.values)), type='string', lock=True)


def _path(c, node):
    paths = c.ls(node, long=True) or ()
    if len(paths) != 1:
        raise CharacterRegistryError('来源瞄准 DAG 身份不唯一：'+node)
    return paths[0]


def _transform(c, path):
    node = c.createNode('transform', name=path.rsplit('|',1)[-1],
                        parent=path.rsplit('|',1)[0], skipSelect=True)
    if _path(c, node) != path:
        raise CharacterRegistryError('来源瞄准层路径漂移：'+path)
    return path


def _insert(c, parent, path):
    children = tuple(c.listRelatives(parent, children=True, fullPath=True,
                                    type='transform') or ())
    _transform(c, path)
    rewrites = []
    for child in children:
        moved = c.parent(child, path, relative=True)[0]
        rewrites.append((child, _path(c, moved)))
    return tuple(rewrites)


def _rebase(value, rewrites):
    return rebase_plan_paths_after_parts(value, FitPartFinalPaths((), (), rewrites))


def _foot(host, spec):
    from maya.api import OpenMaya as om
    c = host._cmds
    g = _Graph(host, spec.stem)
    for attribute, default, hard in (('toesAim',10.,True), ('liftRoll',10.,False)):
        if c.objExists(spec.control+'.'+attribute):
            raise CharacterRegistryError('来源 QToes 属性已存在：'+attribute)
        limits = dict(minValue=0.,maxValue=10.) if hard else dict(softMinValue=0.,softMaxValue=10.)
        c.addAttr(spec.control,longName=attribute,attributeType='double',
                  defaultValue=default,keyable=True,**limits)
    if spec.align_toes:
        c.xform(spec.align_toes,worldSpace=True,rotation=(0.,0.,0.))
    _transform(c,spec.start)
    # IKXOffset's position is before the solver rotations. Taking the start
    # joint worldMatrix would close a feedback loop through the foot aim.
    g.edge(spec.start_driver+'.translate',spec.start+'.translate')
    unit = g.node('unitConversion','ToesAimUnit')
    g.set(unit+'.conversionFactor',.1)
    g.edge(spec.control+'.toesAim',unit+'.input')
    aim = g.node('aimMatrix','ToesAimMatrix')
    g.set(aim+'.secondaryMode',1)
    g.set(aim+'.primaryInputAxis',(1.,0.,0.))
    g.set(aim+'.secondaryInputAxis',(0.,1.,0.))
    g.set(aim+'.secondaryTargetVector',(0.,1.,0.))
    g.edge(spec.roll_offset+'.worldMatrix[0]',aim+'.inputMatrix')
    _transform(c,spec.target_path)
    g.set(spec.target_path+'.inheritsTransform',False)
    g.edge(spec.target_path+'.worldMatrix[0]',aim+'.primaryTargetMatrix')
    target = g.node('multMatrix','AimAtMatrix')
    target_blend = g.node('blendMatrix','AimAtBlend')
    # The original detached sampler keeps world rotation identity at the
    # source start position, then multiplies IK translation and Main.
    position_matrix = tuple(om.MMatrix())[:12]+(*spec.start_position,1.)
    g.set(target+'.matrixIn[0]',position_matrix,'matrix')
    g.edge(spec.main+'.worldMatrix[0]',target+'.matrixIn[2]')
    ik_delta = g.node('multMatrix','IkDelta')
    g.edge(spec.control+'.worldMatrix[0]',ik_delta+'.matrixIn[0]')
    g.edge(spec.offset+'.worldInverseMatrix[0]',ik_delta+'.matrixIn[1]')
    ik_pick = g.node('pickMatrix','IkTranslation')
    g.set(ik_pick+'.useRotate',False)
    g.edge(ik_delta+'.matrixSum',ik_pick+'.inputMatrix')
    g.edge(ik_pick+'.outputMatrix',target+'.matrixIn[1]')
    g.edge(target+'.matrixSum',target_blend+'.inputMatrix')
    g.edge(spec.start+'.worldMatrix[0]',target_blend+'.target[0].targetMatrix')
    g.edge(unit+'.output',target_blend+'.target[0].weight')
    g.matrix(target_blend+'.outputMatrix',spec.target_path,'TargetDecompose',spec.use_offset_parent_matrix)
    g.edge(spec.pole+'.worldMatrix[0]',aim+'.secondaryTargetMatrix')
    local = g.node('multMatrix','AimLocal')
    g.edge(aim+'.outputMatrix',local+'.matrixIn[1]')
    g.edge(spec.roll_offset+'.worldInverseMatrix[0]',local+'.matrixIn[2]')
    rotation = g.node('pickMatrix','AimRotation')
    for attribute in ('useTranslate','useScale','useShear'):
        g.set(rotation+'.'+attribute,False)
    g.edge(local+'.matrixSum',rotation+'.inputMatrix')
    children = tuple(c.listRelatives(spec.roll_offset,children=True,fullPath=True,type='transform') or ())
    if not children:
        raise CharacterRegistryError('来源 QToes RollOffset 缺少控制层')
    _transform(c,spec.aim_path)
    # Follow MEL's create-under-child -> detach -> collect children sequence;
    # the unoffset frame compensates direct-connected Roll rotations.
    temp = c.createNode('transform',name=spec.unoffset_path.rsplit('|',1)[-1],
                        parent=children[0],skipSelect=True)
    temp = c.parent(temp,world=True)[0]
    original = tuple(children)
    for child in original:
        c.parent(child,temp)
    g.matrix(rotation+'.outputMatrix',spec.aim_path,'AimDecompose',spec.use_offset_parent_matrix)
    temp = c.parent(temp,spec.aim_path)[0]
    if _path(c,temp) != spec.unoffset_path:
        raise CharacterRegistryError('来源 QToes UnOffset 路径漂移')
    rewrites = tuple((child,spec.unoffset_path+'|'+child.rsplit('|',1)[-1]) for child in original)
    spec = _rebase(spec,rewrites)
    # If the first reverse-roll offset lives below the inserted toes layer,
    # use its final path before inserting the distance-driven LiftRoll.
    lift_rewrites = _insert(c,spec.lift_offset,spec.lift_path)
    rewrites += tuple((before,after) for before,after in lift_rewrites)
    spec = _rebase(spec,lift_rewrites)
    for batch in (rewrites[:len(original)],lift_rewrites):
        g.edges = _rebase(g.edges,batch)
        g.values = _rebase(g.values,batch)
    start = g.node('decomposeMatrix','LiftStart')
    end = g.node('decomposeMatrix','LiftEnd')
    distance = g.node('distanceBetween','LiftDistance')
    g.edge(spec.start+'.worldMatrix[0]',start+'.inputMatrix')
    g.edge(spec.control+'.worldMatrix[0]',end+'.inputMatrix')
    g.edge(start+'.outputTranslate',distance+'.point1')
    g.edge(end+'.outputTranslate',distance+'.point2')
    rest = float(c.getAttr(distance+'.distance'))
    if rest <= 1e-8:
        raise CharacterRegistryError('来源 LiftRoll 初始距离退化')
    divide = g.node('multiplyDivide','LiftMainScale')
    g.set(divide+'.operation',2)
    g.edge(distance+'.distance',divide+'.input1X')
    g.edge(spec.main_scale,divide+'.input2X')
    subtract = g.node('plusMinusAverage','LiftDelta')
    g.set(subtract+'.operation',2)
    g.edge(divide+'.outputX',subtract+'.input1D[0]')
    g.set(subtract+'.input1D[1]',rest)
    normalize = g.node('multDoubleLinear','LiftNormalize')
    g.edge(subtract+'.output1D',normalize+'.input1')
    sampler = c.createNode('transform',name=spec.stem+'_Sampler',parent=spec.end_fit,skipSelect=True)
    try:
        sampler = c.parent(sampler,world=True)[0]
        rotation_y = float(c.getAttr(sampler+'.rotateY'))
    finally:
        c.delete(sampler)
    sign = -1. if float(c.getAttr(spec.end_fit+'.jointOrientZ')) < 0 else 1.
    g.set(normalize+'.input2',(90.+rotation_y)/rest/10.*sign)
    amount = g.node('multDoubleLinear','LiftAmount')
    g.edge(spec.control+'.liftRoll',amount+'.input1')
    g.edge(normalize+'.output',amount+'.input2')
    clamp = g.node('clamp','LiftClamp')
    for attribute,value,component in (('liftRollMin',-999. if sign==1. else 0.,'minR'),
                                       ('liftRollMax',0. if sign==1. else 999.,'maxR')):
        c.addAttr(spec.control,longName=attribute,attributeType='double',keyable=False)
        c.setAttr(spec.control+'.'+attribute,value)
        g.edge(spec.control+'.'+attribute,clamp+'.'+component)
    g.edge(amount+'.output',clamp+'.inputR')
    g.edge(clamp+'.outputR',spec.lift_path+'.rotateX')
    g.record(spec.aim_path,'foot',spec)
    return spec, (rewrites[:len(original)],lift_rewrites)


def _leg(host, spec):
    from maya.api import OpenMaya as om
    c = host._cmds
    g = _Graph(host,spec.stem)
    c.addAttr(spec.control,longName='legAim',attributeType='double',
              minValue=0.,maxValue=10.,defaultValue=10.,keyable=True)
    unit = g.node('unitConversion','Unit')
    g.set(unit+'.conversionFactor',.1)
    g.edge(spec.control+'.legAim',unit+'.input')
    weight = g.node('multiplyDivide','BlendWeight')
    g.edge(unit+'.output',weight+'.input1X')
    g.edge(spec.blend,weight+'.input2X')
    rewrites = _insert(c,spec.offset,spec.aim_path)
    spec = _rebase(spec,rewrites)
    aim = g.node('aimMatrix','AimMatrix')
    g.set(aim+'.secondaryMode',2)
    g.set(aim+'.primaryInputAxis',(spec.sign,0.,0.))
    # MEL changes Y up to Z after creating asBlendedMatrixAim and recomputes MO.
    g.set(aim+'.secondaryInputAxis',(0.,0.,1.))
    g.set(aim+'.secondaryTargetVector',(0.,0.,1.))
    g.edge(spec.offset+'.worldMatrix[0]',aim+'.inputMatrix')
    g.edge(spec.target+'.worldMatrix[0]',aim+'.primaryTargetMatrix')
    g.edge(spec.offset+'.worldMatrix[0]',aim+'.secondaryTargetMatrix')
    local = g.node('multMatrix','AimLocal')
    g.edge(aim+'.outputMatrix',local+'.matrixIn[1]')
    g.edge(spec.offset+'.worldInverseMatrix[0]',local+'.matrixIn[2]')
    matrix = om.MMatrix(c.getAttr(local+'.matrixSum'))
    g.set(local+'.matrixIn[0]',tuple(matrix.inverse()),'matrix')
    rotation = g.node('pickMatrix','AimRotation')
    for attribute in ('useTranslate','useScale','useShear'):
        g.set(rotation+'.'+attribute,False)
    g.edge(local+'.matrixSum',rotation+'.inputMatrix')
    blend = g.node('blendMatrix','AimBlend')
    g.set(blend+'.inputMatrix',tuple(c.getAttr(rotation+'.outputMatrix')),'matrix')
    g.edge(rotation+'.outputMatrix',blend+'.target[0].targetMatrix')
    g.edge(weight+'.outputX',blend+'.target[0].weight')
    g.edge(blend+'.outputMatrix',spec.aim_path+'.offsetParentMatrix')
    # Original creates measurement locators/distance but does not connect its
    # sampled default angles or unstretched length to another driver.
    for path,source in ((spec.distance_start,spec.control),(spec.distance_end,spec.aim_path)):
        _transform(c,path)
        c.setAttr(path+'.visibility',False,lock=True)
        c.pointConstraint(source,path,name=path.rsplit('|',1)[-1]+'_Point')
    distance = g.node('distanceBetween','Distance')
    g.edge(spec.distance_start+'.translate',distance+'.point1')
    g.edge(spec.distance_end+'.translate',distance+'.point2')
    g.record(spec.aim_path,'leg',spec)
    return spec, rewrites


def _rewrite_records(host, paths, rewrites):
    from adv_py.core.character_registry import safe_json
    c = host._cmds
    result = []
    for path in paths:
        path = _rebase(path,rewrites)
        plug = path+'.advPySourceLimbAim'
        record = _rebase(safe_json(c.getAttr(plug)),rewrites)
        c.setAttr(plug,lock=False)
        c.setAttr(plug,canonical(record),type='string',lock=True)
        result.append(path)
    return result


def rebase_registered_records(host, registration, rewrites):
    """Reparented Body paths also live in the closed native-graph record."""
    paths = [node.path for node in registration.nodes
             if host._cmds.objExists(_rebase(node.path,rewrites)+'.advPySourceLimbAim')]
    _rewrite_records(host,paths,rewrites)


def rebase_plan_records(host, plan, rewrites):
    paths = [spec.aim_path for spec in plan.leg_aim]
    paths += [side.source_aim.aim_path for limb in plan.limbs if limb.foot
              for side in limb.foot.sides if side.source_aim]
    _rewrite_records(host,paths,rewrites)


def create(host,body,fk,limbs,root,splines,main,policy=None,instances=(),use_offset_parent_matrix=True):
    host._require_transaction()
    leg_specs = []
    record_paths = []
    for index in range(len(limbs)):
        for side_index in range(len(limbs[index].ik.limbs)):
            limb = limbs[index]
            ik = limb.ik.limbs[side_index]
            if limb.foot and (policy is None or policy.source_foot_aim is not False):
                foot = next(side for side in limb.foot.sides if side.side is ik.side)
                spec = plan_source_foot_aim(body,limb,ik,foot,main,
                                            use_offset_parent_matrix=use_offset_parent_matrix,instances=instances)
                if spec:
                    spec, batches = _foot(host,spec)
                    for rewrites in batches:
                        fk,limbs,root,splines,main,leg_specs = _rebase(
                            (fk,limbs,root,splines,main,leg_specs),rewrites)
                        record_paths = _rewrite_records(host,record_paths,rewrites)
                    record_paths.append(spec.aim_path)
                    limb = limbs[index]
                    limbs = list(limbs)
                    limbs[index] = replace(limb,foot=replace(limb.foot,sides=tuple(
                        replace(side,source_aim=spec,align_helpers=tuple(
                            replace(helper,world_axes=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)))
                            if helper.path == spec.align_toes else helper for helper in side.align_helpers))
                        if side.side is ik.side else side
                        for side in limb.foot.sides)))
            limb = limbs[index]
            ik = limb.ik.limbs[side_index]
            if policy is None or policy.source_leg_aim is not False:
                start = next(joint for joint in limb.mechanisms.joints if joint.path==ik.chain[0])
                source = next((item.source_joint for item in instances
                               if item.output_name==start.source_joint.rsplit('|',1)[-1]),'')
                spec = plan_source_leg_aim(body,fk,limb,ik,non_symmetry=any(
                    part.endswith('_NonSymmetry') for part in source.split('|')))
                if spec:
                    spec,rewrites = _leg(host,spec)
                    fk,limbs,root,splines,main,leg_specs = _rebase(
                        (fk,limbs,root,splines,main,leg_specs),rewrites)
                    leg_specs.append(spec)
                    record_paths = _rewrite_records(host,record_paths,rewrites)
                    record_paths.append(spec.aim_path)
                    if policy is not None:
                        # Frozen sets are not traversed by the shared Part
                        # rebaser; preserve the saved feature selection here.
                        from dataclasses import fields
                        policy = replace(policy,**{field.name:frozenset(
                            _rebase(value,rewrites) for value in getattr(policy,field.name))
                            for field in fields(policy) if isinstance(getattr(policy,field.name),frozenset)})
    if leg_specs or any(side.source_aim for limb in limbs if limb.foot for side in limb.foot.sides):
        host._transaction_changed = True
    return fk,list(limbs),root,tuple(splines),main,policy,tuple(leg_specs)


def records(host, registration):
    from adv_py.core.source_limb_aim import decode_source_limb_aim
    c = host._cmds
    for node in registration.nodes:
        plug = node.path+'.advPySourceLimbAim'
        if not c.objExists(plug):
            continue
        if not c.getAttr(plug,lock=True):
            raise CharacterRegistryError('来源瞄准图登记已解锁')
        record = decode_source_limb_aim(c.getAttr(plug))
        if record['spec'].get('aim_path') != node.path:
            raise CharacterRegistryError('来源瞄准层与图登记不一致')
        yield record


def audit(host, registration):
    from .maya_character_body_retirement import is_connected_or_retired
    c = host._cmds
    identities=set()
    for record in records(host,registration):
        identity=(record['spec']['control'],record['role'])
        if identity in identities:
            raise CharacterRegistryError('来源瞄准图身份重复')
        identities.add(identity)
        for node,kind in record['nodes']:
            if not c.objExists(node) or c.nodeType(node)!=kind:
                raise CharacterRegistryError('来源瞄准原生节点缺失：'+node)
        for source,target in record['edges']:
            if not is_connected_or_retired(host,source,target):
                raise CharacterRegistryError('来源瞄准驱动连接变化：'+target)
        for plug,wanted in record['values']:
            actual = c.getAttr(plug)
            if isinstance(wanted,list):
                if len(wanted)==3 and isinstance(actual,(tuple,list)) and len(actual)==1:
                    actual=actual[0]
                if len(actual)!=len(wanted) or any(abs(float(a)-float(b))>1e-8 for a,b in zip(actual,wanted)):
                    raise CharacterRegistryError('来源瞄准驱动常量变化：'+plug)
            elif abs(float(actual)-float(wanted))>1e-8:
                raise CharacterRegistryError('来源瞄准驱动常量变化：'+plug)
    for binding in registration.source_limbs:
        attributes={attribute for attribute,_ in binding.reset_attributes}
        for attribute,role in (('toesAim','foot'),('legAim','leg')):
            if attribute in attributes and (binding.ik_control,role) not in identities:
                raise CharacterRegistryError('来源 RP 动画属性缺少瞄准图登记：'+attribute)
        if ('legAim' in attributes)!=bool(binding.leg_aim_control):
            raise CharacterRegistryError('来源 LegAim 缺少父控制器动画身份')
