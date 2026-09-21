"""Audited IK segment overrides and shared helper-volume compensation."""
from dataclasses import dataclass, replace
from adv_py.core.character_registry import CharacterChannel, CharacterRegistryError
from adv_py.core.limb_shape_matching import matched_local_length, matched_volume_factor


@dataclass(frozen=True)
class LengthBinding:
    limb: str
    side: str
    index: int
    target: str
    source_joint: str
    settings: str
    node: str

    @property
    def value_attribute(self): return f'ikMatchLength{self.index}_{self.side}'
    @property
    def weight_attribute(self): return f'ikMatchLengthWeight_{self.side}'


@dataclass(frozen=True)
class VolumeBinding:
    limb: str
    side: str
    settings: str
    node: str
    source: str
    helpers: tuple

    @property
    def attribute(self): return f'matchVolumeFactor_{self.side}'


def bindings(host,registration):
    from adv_py.core.body_arm_mechanisms import plan_body_arm_mechanisms
    from adv_py.core.body_leg_mechanisms import plan_body_leg_mechanisms
    from adv_py.core.body_arm_twist import plan_body_arm_twist
    from adv_py.core.body_leg_twist import plan_body_leg_twist
    body=host.capture_body_skeleton(registration.body_root)
    # Binding topology and helper axes come from the recorded rest frames,
    # never from a transient, partially blended animation pose.
    rest={j.path:j.matrix for j in registration.body}
    body=replace(body,joints=tuple(replace(j,world_position=rest[j.path][12:15],
        world_axes=tuple(host._normalized_vector(rest[j.path][i:i+3]) for i in (0,4,8))) for j in body.joints))
    channels={ch.key:ch for ch in registration.channels}
    lengths=[];volumes=[]
    for limb,planner,twist_planner,parts in (
            ('arm',plan_body_arm_mechanisms,plan_body_arm_twist,('Elbow','Wrist')),
            ('leg',plan_body_leg_mechanisms,plan_body_leg_twist,('Knee','Ankle'))):
        mechanism=planner(body);twist=twist_planner(body)
        for side in ('R','L'):
            settings=channels[f'{limb}.settings.{limb}IkFk_{side}'].node
            for index,part in enumerate(parts):
                candidates=[j for j in mechanism.joints if j.role.value=='ik' and j.source_joint.rsplit('|',1)[-1]==f'{part}_{side}']
                if len(candidates)!=1: raise CharacterRegistryError('IK 骨段来源不唯一')
                axis=channels[f'{limb}.fkLength.{side}.{index}'].attribute
                joint=candidates[0]
                lengths.append(LengthBinding(limb,side,index,joint.path+'.'+axis,joint.source_joint,settings,
                    f'AdvPy_{limb.title()}IKMatchLength{index}_{side}'))
            helpers=tuple((j.path,tuple(a for a in 'XYZ' if a!=j.axis)) for j in twist.joints if j.side.value==side)
            volumes.append(VolumeBinding(limb,side,settings,f'AdvPy_{limb.title()}MatchVolume_{side}',
                f'AdvPy_{limb.title()}VolumeBlend_{side}.outputR',helpers))
    return tuple(lengths),tuple(volumes)


def channels_for(lengths,volumes):
    rows=[]
    for b in lengths:
        if b.index==0:
            rows.append(CharacterChannel(f'{b.limb}.ikLengthWeight.{b.side}',b.settings,b.weight_attribute,0.,1.))
        rows.append(CharacterChannel(f'{b.limb}.ikLength.{b.side}.{b.index}',b.settings,b.value_attribute))
    rows.extend(CharacterChannel(f'{b.limb}.volumeMatch.{b.side}',b.settings,b.attribute,1e-6,None) for b in volumes)
    return tuple(rows)


def enabled(registration):
    return any('.ikLengthWeight.' in ch.key for ch in registration.channels)


def preflight(host,registration,lengths,volumes):
    if enabled(registration):
        audit(host,registration,lengths,volumes);return
    c=host._cmds
    for ch in channels_for(lengths,volumes):
        if c.objExists(ch.node+'.'+ch.attribute): raise CharacterRegistryError('拉伸匹配属性已占用')
    for b in lengths:
        if any(c.objExists(b.node+suffix) for suffix in ('','In','Out')):
            raise CharacterRegistryError('IK 骨段匹配节点名称已占用')
        if c.getAttr(b.target,lock=True) or not c.connectionInfo(b.target,sourceFromDestination=True):
            raise CharacterRegistryError('IK 骨段必须连接既有拉伸网络且未锁定')
        if abs(c.getAttr(b.target))<=1e-8:raise CharacterRegistryError('IK 骨段长度退化')
    for b in volumes:
        if c.objExists(b.node):raise CharacterRegistryError('体积匹配节点名称已占用')
        for path,axes in b.helpers:
            for axis in axes:
                if not c.isConnected(b.source,path+'.scale'+axis) or c.getAttr(path+'.scale'+axis,lock=True):
                    raise CharacterRegistryError('体积 helper 接线或锁定状态无效')


def describe(host,registration):
    host._validate_character_registration(registration)
    lengths,volumes=bindings(host,registration)
    preflight(host,registration,lengths,volumes)
    if enabled(registration):return registration
    nodes=list(registration.nodes);indices={n.path:i for i,n in enumerate(nodes)}
    replacements={}
    for b in lengths:
        node,attribute=b.target.rsplit('.',1)
        replacements.setdefault(node,{})[attribute]=b.node+'Out.output'
    for b in volumes:
        for node,axes in b.helpers:
            replacements.setdefault(node,{}).update({'scale'+a:b.node+'.outputX' for a in axes})
    for path,updates in replacements.items():
        state=host._registry_node(path)
        inputs=dict(state.inputs);inputs.update(updates)
        state=replace(state,inputs=tuple((a,inputs[a]) for a in (kind+axis for kind in ('translate','rotate','scale','jointOrient','rotateAxis') for axis in 'XYZ') if a in inputs)
                      +tuple((a,v) for a,v in inputs.items() if a=='offsetParentMatrix'))
        if path in indices:nodes[indices[path]]=state
        else:indices[path]=len(nodes);nodes.append(state)
        parent=path.rsplit('|',1)[0]
        while parent:
            if parent not in indices:
                indices[parent]=len(nodes);nodes.append(host._registry_node(parent))
            parent=parent.rsplit('|',1)[0]
    return replace(registration,channels=registration.channels+channels_for(lengths,volumes),nodes=tuple(nodes))


def install(host,before,after):
    host._require_transaction()
    lengths,volumes=bindings(host,before);preflight(host,before,lengths,volumes)
    if enabled(before):return
    c=host._cmds;host._transaction_changed=True
    for ch in channels_for(lengths,volumes):
        kwargs={'longName':ch.attribute,'attributeType':'double','keyable':True}
        if ch.minimum is not None:kwargs['minValue']=ch.minimum
        if ch.maximum is not None:kwargs['maxValue']=ch.maximum
        kwargs['defaultValue']=1. if '.volumeMatch.' in ch.key else 0.
        c.addAttr(ch.node,**kwargs)
    for b in lengths:
        original=c.connectionInfo(b.target,sourceFromDestination=True)
        c.setAttr(b.settings+'.'+b.value_attribute,c.getAttr(b.target))
        c.createNode('blendTwoAttr',name=b.node,skipSelect=True)
        c.addAttr(b.node,longName='advPyShapeOwner',dataType='string')
        c.setAttr(b.node+'.advPyShapeOwner','adv_py.limb_shape.v1',type='string',lock=True)
        c.addAttr(b.node,longName='originalSource',dataType='string')
        c.setAttr(b.node+'.originalSource',host._canonical_plug(original),type='string',lock=True)
        for suffix in ('In','Out'):
            c.createNode('unitConversion',name=b.node+suffix,skipSelect=True)
            c.setAttr(b.node+suffix+'.conversionFactor',1.,lock=True)
        c.disconnectAttr(original,b.target)
        c.connectAttr(original,b.node+'In.input')
        c.connectAttr(b.node+'In.output',b.node+'.input[0]')
        c.connectAttr(b.settings+'.'+b.value_attribute,b.node+'.input[1]')
        c.connectAttr(b.settings+'.'+b.weight_attribute,b.node+'.attributesBlender')
        c.connectAttr(b.node+'.output',b.node+'Out.input')
        c.connectAttr(b.node+'Out.output',b.target)
    for b in volumes:
        c.setAttr(b.settings+'.'+b.attribute,1.)
        c.createNode('multiplyDivide',name=b.node,skipSelect=True)
        c.setAttr(b.node+'.operation',1,lock=True)
        c.addAttr(b.node,longName='advPyShapeOwner',dataType='string')
        c.setAttr(b.node+'.advPyShapeOwner','adv_py.limb_shape.v1',type='string',lock=True)
        c.connectAttr(b.source,b.node+'.input1X')
        c.connectAttr(b.settings+'.'+b.attribute,b.node+'.input2X')
        for path,axes in b.helpers:
            for axis in axes:
                c.disconnectAttr(b.source,path+'.scale'+axis)
                c.connectAttr(b.node+'.outputX',path+'.scale'+axis)


def audit(host,registration,lengths=None,volumes=None):
    if not enabled(registration):return
    if lengths is None:lengths,volumes=bindings(host,registration)
    c=host._cmds
    expected=channels_for(lengths,volumes)
    if tuple(ch for ch in registration.channels if '.ikLength.' in ch.key or '.ikLengthWeight.' in ch.key or '.volumeMatch.' in ch.key)!=expected:
        raise CharacterRegistryError('拉伸匹配通道集合不完整')
    def node(name,kind):
        if not c.objExists(name) or c.nodeType(name)!=kind or c.referenceQuery(name,isNodeReferenced=True):
            raise CharacterRegistryError('拉伸匹配节点缺失或类型无效')
    def edge(source,target):
        if not c.isConnected(source,target):raise CharacterRegistryError('拉伸匹配接线被替换')
    def outputs(source,wanted):
        if {host._canonical_plug(p) for p in c.listConnections(source,s=False,d=True,plugs=True) or []}!={host._canonical_plug(p) for p in wanted}:
            raise CharacterRegistryError('拉伸匹配存在外部输出')
    for b in lengths:
        node(b.node,'blendTwoAttr')
        if not c.objExists(b.node+'.advPyShapeOwner') or c.getAttr(b.node+'.advPyShapeOwner')!='adv_py.limb_shape.v1':
            raise CharacterRegistryError('IK 骨段匹配归属无效')
        if c.getAttr(b.node+'.input',multiIndices=True)!=[0,1]:
            raise CharacterRegistryError('IK 骨段覆盖输入集合变化')
        for suffix in ('In','Out'):
            node(b.node+suffix,'unitConversion')
            if c.getAttr(b.node+suffix+'.conversionFactor')!=1. or c.listConnections(b.node+suffix+'.conversionFactor',s=True,d=False):
                raise CharacterRegistryError('IK 骨段单位转换被修改')
        edge(c.getAttr(b.node+'.originalSource'),b.node+'In.input')
        edge(b.node+'In.output',b.node+'.input[0]');outputs(b.node+'In.output',[b.node+'.input[0]'])
        edge(b.settings+'.'+b.value_attribute,b.node+'.input[1]')
        outputs(b.settings+'.'+b.value_attribute,[b.node+'.input[1]'])
        edge(b.settings+'.'+b.weight_attribute,b.node+'.attributesBlender')
        outputs(b.settings+'.'+b.weight_attribute,[other.node+'.attributesBlender' for other in lengths if (other.limb,other.side)==(b.limb,b.side)])
        edge(b.node+'.output',b.node+'Out.input');outputs(b.node+'.output',[b.node+'Out.input'])
        edge(b.node+'Out.output',b.target);outputs(b.node+'Out.output',[b.target])
    for b in volumes:
        node(b.node,'multiplyDivide')
        if c.getAttr(b.node+'.operation')!=1 or c.listConnections(b.node+'.operation',s=True,d=False):
            raise CharacterRegistryError('体积补偿运算被修改')
        if not c.objExists(b.node+'.advPyShapeOwner') or c.getAttr(b.node+'.advPyShapeOwner')!='adv_py.limb_shape.v1':
            raise CharacterRegistryError('体积匹配归属无效')
        edge(b.source,b.node+'.input1X');edge(b.settings+'.'+b.attribute,b.node+'.input2X')
        outputs(b.settings+'.'+b.attribute,[b.node+'.input2X'])
        targets=[p+'.scale'+axis for p,axes in b.helpers for axis in axes]
        for target in targets:edge(b.node+'.outputX',target)
        outputs(b.node+'.outputX',targets)


def begin_match(host,registration,limb,side,mode):
    if not enabled(registration):return None
    lengths,volumes=bindings(host,registration)
    lengths=tuple(b for b in lengths if (b.limb,b.side)==(limb,side))
    volume=next(b for b in volumes if (b.limb,b.side)==(limb,side))
    c=host._cmds
    before=host.capture_character_pose(registration)
    wanted=dict(before.body_frames)
    width=c.getAttr(volume.helpers[0][0]+'.scale'+volume.helpers[0][1][0])
    if mode=='ik':
        for b in lengths:
            body=next(j for j in registration.body if j.path==b.source_joint)
            child=wanted[body.path.rsplit('|',1)[-1]][12:15]
            parent=wanted[body.parent.rsplit('|',1)[-1]][12:15]
            driver,attribute=b.target.rsplit('.',1)
            driver_parent=c.listRelatives(driver,parent=True,fullPath=True)[0]
            matrix=host._spine_world_frame(driver_parent)[0]
            value=matched_local_length(parent,child,matrix,attribute[-1],c.getAttr(b.target))
            c.setAttr(b.settings+'.'+b.value_attribute,value)
        c.setAttr(lengths[0].settings+'.'+lengths[0].weight_attribute,1.)
    return volume,width


def finish_match(host,state):
    if state is None:return
    b,width=state;c=host._cmds
    base=c.getAttr(b.source)
    c.setAttr(b.settings+'.'+b.attribute,matched_volume_factor(width,base))


def sample_helpers(host,registration,frames,limb,side):
    if not enabled(registration):return ()
    _,volumes=bindings(host,registration)
    b=next(b for b in volumes if (b.limb,b.side)==(limb,side))
    with host._character_sampling_time() as seek:
        rows=[]
        for frame in frames:
            seek(frame)
            rows.append((float(frame),tuple((p,host._spine_world_frame(p)[0]) for p,_ in b.helpers)))
        return tuple(rows)


def begin_optional_match(host,limb,side,mode):
    if not host._cmds.objExists(f'AdvPy_{limb.title()}Settings.ikMatchLengthWeight_{side}'):return None
    registration=host.read_character_registration()
    channels=tuple(ch for ch in registration.channels if ch.key.startswith((f'{limb}.ikLength.{side}.',f'{limb}.ikLengthWeight.{side}',f'{limb}.volumeMatch.{side}')))
    if any(not host._cmds.getAttr(ch.node+'.'+ch.attribute,settable=True) for ch in channels):
        raise CharacterRegistryError('拉伸匹配通道不可静态写入')
    host._transaction_changed=True
    return begin_match(host,registration,limb,side,mode)
