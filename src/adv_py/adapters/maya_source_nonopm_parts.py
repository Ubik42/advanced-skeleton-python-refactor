"""Original non-OPM Body Parts receive FKX/IKX position and local scale."""
from dataclasses import asdict
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan,decode_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from .maya_source_graph_connections import SourceGraphConnections

POINT='advPySourcePartPoint'
SCALE='advPySourceLocalScale'


def _source(host,plug):
    value=host._cmds.connectionInfo(plug,sourceFromDestination=True)
    if not value:return None
    name,attr=value.split('.',1)
    return host._resolve_connected_node(name)+'.'+attr


def _save(host,target,marker,record):
    c=host._cmds
    if c.objExists(target+'.'+marker):raise CharacterRegistryError('来源 Part 接收记录重复：'+target)
    c.addAttr(target,longName=marker,dataType='string')
    c.setAttr(target+'.'+marker,canonical(asdict(record)),type='string',lock=True)


def _point(host,target,drivers,weights,name):
    c=host._cmds
    if host.find_name_collisions(name):raise CharacterRegistryError('来源 Part 位置约束名称被占用')
    # Earlier generic length receivers are replaced by the source FKX/IKX
    # point constraint, exactly as MEL 80522–80530 does for Body joints.
    for attr in ('translate',*('translate'+axis for axis in 'XYZ')):
        plug=target+'.'+attr;source=c.connectionInfo(plug,sourceFromDestination=True)
        if source:c.disconnectAttr(source,plug)
    node=c.pointConstraint(*drivers,target,maintainOffset=False,name=name)[0]
    aliases=c.pointConstraint(node,q=True,weightAliasList=True)
    if len(aliases)!=len(drivers):raise CharacterRegistryError('来源 Part 位置约束权重数量变化')
    for source,alias in zip(weights,aliases):c.connectAttr(source,node+'.'+alias)
    values=tuple(('offset'+axis,0.) for axis in 'XYZ');edges=[]
    attrs=['constraintParentInverseMatrix']
    for index in range(len(drivers)):
        attrs.extend(f'target[{index}].'+attr for attr in
                     ('targetTranslate','targetRotatePivot','targetRotateTranslate','targetParentMatrix','targetWeight'))
    for attr in attrs:
        source=_source(host,node+'.'+attr)
        if source:edges.append((source,attr))
        elif attr.endswith('targetWeight'):values+=((attr,float(c.getAttr(node+'.'+attr))),)
    outputs=tuple((_source(host,target+'.translate'+axis),target+'.translate'+axis) for axis in 'XYZ')
    if any(source is None for source,_ in outputs):raise CharacterRegistryError('来源 Part 位置约束没有完整输出')
    _save(host,target,POINT,SourceBodyMatrixPlan(target,(SourceRpNode(node,'pointConstraint',values,tuple(edges)),),outputs))


def _fk_scale(host,target,control):
    c=host._cmds;graph=SourceGraphConnections(host,'AdvPy_'+target.rsplit('|',1)[-1]+'_SourceFkPartScale')
    outputs=[]
    for axis in 'XYZ':
        destination=target+'.scale'+axis
        for plug in (target+'.scale',destination):
            source=c.connectionInfo(plug,sourceFromDestination=True)
            if source:c.disconnectAttr(source,plug)
        source=control+'.scale'+axis;graph.connect(source,destination);outputs.append((source,destination))
    _save(host,target,SCALE,SourceBodyMatrixPlan(target,graph.describe_nodes(()),graph.describe_outputs(tuple(outputs))))


def configure(host,body,segments,fk,metadata,instances):
    host._require_transaction();c=host._cmds
    from adv_py.core.source_fit_identity import source_fit_metadata
    from adv_py.core.fit_scale_compensation import fit_segment_scale_compensate
    controls={control.driven_joint.rsplit('|',1)[-1]:control for control in fk.controls}
    # MEL 80186 visits every Fit joint, including ends without an FK control.
    # An uncompensated end also disables SSC on its parent's FKX. Iterating
    # controls alone missed the last Finger segment and shortened Main scale.
    for instance in instances:
        fit=source_fit_metadata(instance.output_name,metadata,instances)
        parent_name=(instance.parent_output_path or '').rsplit('|',1)[-1]
        if fit is None or fit_segment_scale_compensate(fit,
                instance.output_name.rsplit('_',1)[0],parent_name.rsplit('_',1)[0],
                use_offset_parent_matrix=False):continue
        parent_control=controls.get(parent_name)
        if parent_control is not None and parent_control.source_override_joint:
            c.setAttr(parent_control.source_override_path+'.segmentScaleCompensate',False)
    # Inbetween insertion changes the real parent. Generic Spline assembly
    # still links to its previous Body sample, bypassing the inserted Parts.
    # MEL's non-OPM joints compensate their immediate joint parent's scale.
    for joint in body.joints:
        parent=(c.listRelatives(joint.path,parent=True,fullPath=True) or [None])[0]
        if parent and c.nodeType(parent)=='joint' and c.getAttr(joint.path+'.segmentScaleCompensate'):
            c.connectAttr(parent+'.scale',joint.path+'.inverseScale',force=True)
    for built in segments:
        if built.fk.use_offset_parent_matrix:continue
        fk_parts={part.part_name:part for part in built.fk.parts.parts} if built.fk.parts else {}
        for part in built.body.parts:
            target=host._resolve_connected_node(part.body_part_name)
            if host.validate_body_bendy_handoff(target):continue
            drivers=(host._resolve_connected_node(part.fkx_name),)
            weights=()
            if hasattr(part,'ikx_name'):
                drivers+=(host._resolve_connected_node(part.ikx_name),)
                weights=(built.body.fk_weight_plug,built.body.ik_weight_plug)
            _point(host,target,drivers,weights,'AdvPy_'+part.body_part_name+'_SourcePoint')
            if len(drivers)==1:
                control=fk_parts.get(part.body_part_name)
                if control is None:raise CharacterRegistryError('来源 FK-only Part 缺少原控制器')
                _fk_scale(host,target,host._resolve_connected_node(control.control_name))
    host._transaction_changed=True


def audit_record(host,target,marker):
    c=host._cmds;plug=target+'.'+marker
    if not c.getAttr(plug,lock=True):raise CharacterRegistryError('来源 Part 接收登记已解锁')
    saved=decode_source_body_matrix(c.getAttr(plug))
    kind='translate' if marker==POINT else 'scale'
    if saved.body!=target or {destination for _,destination in saved.outputs}!={target+'.'+kind+axis for axis in 'XYZ'}:
        raise CharacterRegistryError('来源 Part 接收登记身份变化')
    for node in saved.nodes:
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:raise CharacterRegistryError('来源 Part 接收节点缺失')
        if marker==POINT and node.kind=='pointConstraint':
            targets=tuple(host._resolve_connected_node(name) for name in c.pointConstraint(node.name,q=True,targetList=True))
            expected=tuple(source.rsplit('.',1)[0] for source,attr in node.connections if attr.endswith('.targetTranslate'))
            if targets!=expected:raise CharacterRegistryError('来源 Part 位置接收目标变化')
        for attr,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:raise CharacterRegistryError('来源 Part 接收常量变化')
        for source,attr in node.connections:
            if not c.isConnected(source,node.name+'.'+attr):raise CharacterRegistryError('来源 Part 接收输入变化')
    for source,destination in saved.outputs:
        if not c.isConnected(source,destination):raise CharacterRegistryError('来源 Part 接收输出变化')


def audit_registered(host,registration):
    for joint in registration.body:
        for marker in (POINT,SCALE):
            if host._cmds.objExists(joint.path+'.'+marker):audit_record(host,joint.path,marker)
