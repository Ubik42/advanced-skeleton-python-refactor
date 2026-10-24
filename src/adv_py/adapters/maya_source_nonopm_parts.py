"""Original non-OPM Body Parts receive FKX/IKX position and local scale."""
from dataclasses import asdict
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan,decode_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from .maya_source_graph_connections import SourceGraphConnections

POINT='advPySourcePartPoint'
SCALE='advPySourceLocalScale'
TWIST_POSITION='advPySourceTwistPosition'


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


def _fk_part_frame(host,built,part,controls):
    """MEL 79894/80151: local Inbetween rotation below the previous FKX."""
    from adv_py.core.source_inbetween_matrix import SourceInbetweenMatrixRecord
    from .maya_source_inbetween_matrix import MARKER,audit_target
    c=host._cmds;target=host._resolve_connected_node(part.offset_name)
    if c.objExists(target+'.'+MARKER):raise CharacterRegistryError('来源非 OPM FK Part 接收重复')
    matrix=part.fk_matrix_name;pick=part.pick_matrix_name
    incoming=_source(host,matrix+'.matrixIn[0]')
    if not incoming:raise CharacterRegistryError('来源非 OPM FK Part 缺少 Inbetween 旋转')
    stem='AdvPy_'+part.part_name+'_SourceNonOpmFk'
    dm=SourceRpNode(stem+'DM','decomposeMatrix',(('inputRotateOrder',0.),),((incoming,'inputMatrix'),))
    cm=SourceRpNode(stem+'CM','composeMatrix',(('inputRotateOrder',float(part.rotate_order)),),
        tuple((dm.name+'.outputRotate'+axis,'inputRotate'+axis) for axis in 'XYZ'))
    graph=SourceGraphConnections(host,stem);frame_nodes=[dm,cm]
    position=host._resolve_connected_node(part.fkps_name)+'.matrix'
    if part.segment_scale_compensate:
        # MEL's FKPS1 scale constraint affects FKPS2 position, while Part's
        # Offset still inherits the previous FKX's complete orientation/frame.
        parent=host._resolve_connected_node(part.parent_fkx_name)
        if host.find_name_collisions(stem+'FKPS1'):raise CharacterRegistryError('来源非 OPM FKPS 名称被占用')
        ps=c.createNode('transform',name=stem+'FKPS1',parent=parent,skipSelect=True)
        previous=next((item for item in built.fk.parts.parts if item.index==part.index-1),None)
        if previous is not None:source=host._resolve_connected_node(previous.driver_name)
        else:
            start=next(item for item in controls if item.control_path==built.fk.anchor.fk_control_path)
            source=start.sub_control_path or start.control_path
        _scale_parent(host,host._resolve_connected_node(ps),source,stem+'Scale')
        length=SourceRpNode(stem+'PositionMD','multiplyDivide',(('operation',1.),),
            ((host._resolve_connected_node(part.fkps_name)+'.translate','input1'),
             (host._resolve_connected_node(ps)+'.scale','input2')))
        translation=SourceRpNode(stem+'PositionCM','composeMatrix',connections=(
            (length.name+'.output','inputTranslate'),))
        frame_nodes.extend((length,translation));position=translation.name+'.outputMatrix'
    for node in frame_nodes:
        if host.find_name_collisions(node.name):raise CharacterRegistryError('来源非 OPM FK Part 节点被占用')
        c.createNode(node.kind,name=node.name,skipSelect=True)
        for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
        for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
    edges=((cm.name+'.outputMatrix','matrixIn[0]'),
           (position,'matrixIn[1]'),
           (host._resolve_connected_node(part.parent_fkx_name)+'.worldMatrix[0]','matrixIn[2]'),
           (built.fk.parts.fk_system_path+'.worldInverseMatrix[0]','matrixIn[3]'))
    for source,attr in edges:
        plug=matrix+'.'+attr;old=c.connectionInfo(plug,sourceFromDestination=True)
        if old:c.disconnectAttr(old,plug)
        graph.connect(source,plug)
    old=c.connectionInfo(pick+'.useScale',sourceFromDestination=True)
    if old:c.disconnectAttr(old,pick+'.useScale')
    for attr in ('useTranslate','useRotate','useScale','useShear'):c.setAttr(pick+'.'+attr,True)
    nodes=tuple(frame_nodes)+(SourceRpNode(matrix,'multMatrix',connections=edges),
           SourceRpNode(pick,'pickMatrix',tuple((attr,1.) for attr in
                         ('useTranslate','useRotate','useScale','useShear')),
                         ((matrix+'.matrixSum','inputMatrix'),)))
    record=SourceBodyMatrixPlan(target,graph.describe_nodes(nodes),
                               ((pick+'.outputMatrix',target+'.offsetParentMatrix'),))
    _save(host,target,MARKER,SourceInbetweenMatrixRecord(record,(),True))
    audit_target(host,target)


def _scale_parent(host,target,control,name):
    """Persist MEL's FKPS1 native scale constraint and its boundary."""
    c=host._cmds
    if host.find_name_collisions(name):raise CharacterRegistryError('来源 FKPS 缩放约束名称被占用')
    node=c.scaleConstraint(control,target,maintainOffset=False,name=name)[0]
    edges=[];values=[]
    for attr in ('constraintParentInverseMatrix','constraintScaleCompensate',
                 'target[0].targetScale','target[0].targetParentMatrix','target[0].targetWeight'):
        source=_source(host,node+'.'+attr)
        if source:edges.append((source,attr))
        elif attr in ('constraintScaleCompensate','target[0].targetWeight'):
            values.append((attr,float(c.getAttr(node+'.'+attr))))
    values+= [('offset'+axis,float(c.getAttr(node+'.offset'+axis))) for axis in 'XYZ']
    outputs=tuple((_source(host,target+'.scale'+axis),target+'.scale'+axis) for axis in 'XYZ')
    _save(host,target,SCALE,SourceBodyMatrixPlan(target,
        (SourceRpNode(node,'scaleConstraint',tuple(values),tuple(edges)),),outputs))


def configure_twist_positions(host,parts,steps,blended,independent):
    """MEL 83464–83483: one equal local interval from Body to child BM.

    The child BM is the independent FKX/IKX blend, before its Body's twist.
    Reading the reparented child Body here would create a dependency cycle.
    Bendy and Inbetween are deliberately supplied by their own receivers.
    """
    host._require_transaction();c=host._cmds
    by_step={step.part_name:step for step in steps};chains={}
    for part in parts:
        if part.start_body in blended:chains.setdefault(part.start_body,[]).append(part)
    for start,chain in chains.items():
        first=chain[0];end=first.end_body;stem='AdvPy_'+first.start_body_name+'_SourceTwistPosition'
        child=blended.get(end);nodes=[]
        if child:
            child_name=stem+'ChildBM'
            nodes.append(SourceRpNode(child_name,'blendMatrix',connections=(
                (child[0],'inputMatrix'),(child[1],'target[0].targetMatrix'),
                (child[2],'target[0].weight'))))
            child_world=child_name+'.outputMatrix'
        else:
            child_world=independent.get(end)
            if child_world is None:
                # Original Body BM consumes the undriven end's FKX frame.
                # Absence of that receiver is a source identity gap, not a
                # reason to silently keep a static Part length.
                raise CharacterRegistryError('来源 Twist Part 缺少末端独立矩阵：'+end)
        bm=stem+'BM';mm=stem+'MM';dm=stem+'DM'
        nodes.extend((SourceRpNode(bm,'blendMatrix',(('target[0].weight',1./(first.count+1)),),
            ((start+'.worldMatrix[0]','inputMatrix'),(child_world,'target[0].targetMatrix'))),
            SourceRpNode(mm,'multMatrix',connections=((bm+'.outputMatrix','matrixIn[0]'),
                (start+'.worldInverseMatrix[0]','matrixIn[1]'))),
            SourceRpNode(dm,'decomposeMatrix',connections=((mm+'.matrixSum','inputMatrix'),))))
        if any(host.find_name_collisions(node.name) for node in nodes):
            raise CharacterRegistryError('来源 Twist Part 位移节点名称被占用')
        graph=SourceGraphConnections(host,stem)
        for node in nodes:
            c.createNode(node.kind,name=node.name,skipSelect=True)
            for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
        for node in nodes:
            for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
        for part in chain:
            target=host._unique_fit_part_joint(part.name);step=by_step[part.name]
            destination=(step.matrix_name+'.inputTranslate' if step.use_offset_parent_matrix else target+'.translate')
            for plug in (destination,*(destination+axis for axis in 'XYZ')):
                old=c.connectionInfo(plug,sourceFromDestination=True)
                if old:c.disconnectAttr(old,plug)
            outputs=tuple((dm+'.outputTranslate'+axis,destination+axis) for axis in 'XYZ')
            for source,plug in outputs:graph.connect(source,plug)
            owned=graph.describe_nodes(nodes)
            if step.use_offset_parent_matrix:
                # An explicitly uncompensated Part keeps its existing twist
                # CM/OPM; persist that final receiver with the new translation.
                rotate=_source(host,step.matrix_name+'.inputRotateX')
                if rotate is None:raise CharacterRegistryError('来源 Twist Part 缺少旋转接收')
                owned+=(SourceRpNode(step.matrix_name,'composeMatrix',connections=(
                    (rotate,'inputRotateX'),*((source,'inputTranslate'+axis)
                        for axis,(source,_) in zip('XYZ',outputs)))),)
                outputs=((step.matrix_name+'.outputMatrix',target+'.offsetParentMatrix'),)
            _save(host,target,TWIST_POSITION,SourceBodyMatrixPlan(target,owned,graph.describe_outputs(outputs)))
    if chains:host._transaction_changed=True


def _fk_end_frame(host,built,controls,metadata,instances):
    """Retain the original FK Offset parent frame after the Part chain."""
    from maya.api import OpenMaya as om
    from adv_py.core.source_fit_identity import source_fit_metadata
    from adv_py.core.fit_scale_compensation import fit_segment_scale_compensate
    from adv_py.core.source_inbetween_matrix import SourceInbetweenMatrixRecord
    from .maya_source_inbetween_matrix import MARKER,audit_target
    c=host._cmds;target=built.rewire.downstream_fk_offset_path
    if target is None:return
    control=next((item for item in controls if item.offset_path==target),None)
    if control is None:raise CharacterRegistryError('来源非 OPM Part 下游缺少 FK 身份')
    parent=host._resolve_connected_node(built.rewire.last_part_fkx_name)
    bind=tuple(om.MMatrix(c.xform(target,q=True,ws=True,m=True))*
               om.MMatrix(c.getAttr(parent+'.worldMatrix[0]')).inverse())
    stem='AdvPy_'+target.rsplit('|',1)[-1]+'_SourceNonOpmParent';matrix=stem+'MM'
    if host.find_name_collisions(matrix):raise CharacterRegistryError('来源非 OPM 下游父帧名称被占用')
    c.delete(built.rewire.follow_constraint_name)
    for attr,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
        c.setAttr(target+'.'+attr,value,value,value,type='double3')
    c.createNode('multMatrix',name=matrix,skipSelect=True)
    c.setAttr(matrix+'.matrixIn[0]',*bind,type='matrix')
    edges=((parent+'.worldMatrix[0]','matrixIn[1]'),
           (target.rsplit('|',1)[0]+'.worldInverseMatrix[0]','matrixIn[2]'))
    for source,attr in edges:c.connectAttr(source,matrix+'.'+attr)
    c.connectAttr(matrix+'.matrixSum',target+'.offsetParentMatrix')
    record=SourceBodyMatrixPlan(target,(SourceRpNode(matrix,'multMatrix',connections=edges),),
                               ((matrix+'.matrixSum',target+'.offsetParentMatrix'),))
    _save(host,target,MARKER,SourceInbetweenMatrixRecord(record,
        ((matrix+'.matrixIn[0]',bind),),True))
    fit=next((item for item in metadata if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]
              in control.fit_joint_names),None)
    if fit is None:fit=source_fit_metadata(control.driven_joint.rsplit('|',1)[-1],metadata,instances)
    if fit is None:raise CharacterRegistryError('来源非 OPM 下游缺少 Fit 设置')
    enabled=fit_segment_scale_compensate(fit,control.fit_joint_names[0],
        built.fk.anchor.start_body_name.rsplit('_',1)[0],use_offset_parent_matrix=False)
    # Resolve end-joint eligibility by Fit provenance, since a Spline's
    # driven joint is a mechanism rather than the original Body identity.
    is_leaf=not any(instance.source_joint.rsplit('|',1)[0]==fit.joint for instance in instances)
    if not enabled:c.setAttr(parent+'.segmentScaleCompensate',False)
    elif not is_leaf:
        if any(host.find_name_collisions(stem+suffix) for suffix in ('FKPS1','FKPS2')):
            raise CharacterRegistryError('来源非 OPM 下游 FKPS 名称被占用')
        ps1=c.createNode('transform',name=stem+'FKPS1',parent=parent,skipSelect=True)
        ps2=c.createNode('transform',name=stem+'FKPS2',parent=ps1,skipSelect=True)
        c.setAttr(ps2+'.translate',*bind[12:15],type='double3')
        last=built.fk.parts.parts[-1]
        _scale_parent(host,host._resolve_connected_node(ps1),
                      host._resolve_connected_node(last.driver_name),stem+'Scale')
        _point(host,target,(host._resolve_connected_node(ps2),),(),stem+'Point')
    audit_target(host,target)


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
        for part in fk_parts.values():_fk_part_frame(host,built,part,fk.controls)
        _fk_end_frame(host,built,fk.controls,metadata,instances)
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
    from .maya_character_body_retirement import (
        source_record,removed_graph_node,is_connected_or_retired,retired_joint)
    c=host._cmds
    saved=decode_source_body_matrix(source_record(host,target,marker))
    kind='translate' if marker in (POINT,TWIST_POSITION) else 'scale'
    expected={target+'.'+kind+axis for axis in 'XYZ'}
    if marker==TWIST_POSITION and len(saved.outputs)==1:expected={target+'.offsetParentMatrix'}
    if saved.body!=target or {destination for _,destination in saved.outputs}!=expected:
        raise CharacterRegistryError('来源 Part 接收登记身份变化')
    for node in saved.nodes:
        removed=removed_graph_node(host,node.name,node.kind)
        if removed is not None:
            if not all(is_connected_or_retired(host,source,node.name+'.'+attr)
                       for source,attr in node.connections):
                raise CharacterRegistryError('来源 Part 已清理接收器的原输入变化')
            # Native export deletes a Body's child constraints as well. Their
            # constants were checked by the full character read before capture;
            # do not query a replacement node or fabricate live constraints.
            continue
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
            raise CharacterRegistryError('来源 Part 接收节点缺失：'+node.name+'；目标：'+target)
        if marker==POINT and node.kind=='pointConstraint':
            targets=tuple(host._resolve_connected_node(name) for name in (c.pointConstraint(node.name,q=True,targetList=True) or ()))
            expected=tuple(source.split('.',1)[0] for source,attr in node.connections
                if attr.endswith('.targetTranslate') and retired_joint(host,source.split('.',1)[0]) is None)
            if targets!=expected:raise CharacterRegistryError('来源 Part 位置接收目标变化')
        if marker==SCALE and node.kind=='scaleConstraint':
            targets=tuple(host._resolve_connected_node(name) for name in (c.scaleConstraint(node.name,q=True,targetList=True) or ()))
            expected=tuple(source.split('.',1)[0] for source,attr in node.connections
                if attr.endswith('.targetScale') and retired_joint(host,source.split('.',1)[0]) is None)
            if targets!=expected:raise CharacterRegistryError('来源 FKPS 缩放接收目标变化')
        for attr,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:raise CharacterRegistryError('来源 Part 接收常量变化')
        for source,attr in node.connections:
            if not is_connected_or_retired(host,source,node.name+'.'+attr):raise CharacterRegistryError('来源 Part 接收输入变化')
    for source,destination in saved.outputs:
        from .maya_game_scaling_state import original_scale_connection
        if not original_scale_connection(host,source,destination):raise CharacterRegistryError('来源 Part 接收输出变化')


def audit_registered(host,registration):
    for joint in registration.nodes:
        for marker in (POINT,SCALE,TWIST_POSITION):
            if host._cmds.objExists(joint.path+'.'+marker):audit_record(host,joint.path,marker)
    for joint in registration.retired_body:
        for marker in (POINT,SCALE,TWIST_POSITION):
            if marker in dict(joint.records):audit_record(host,joint.path,marker)
