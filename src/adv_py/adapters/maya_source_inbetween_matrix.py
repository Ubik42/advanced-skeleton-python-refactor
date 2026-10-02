"""MEL 80240–80387: restore NoShear/Main order after Inbetween handoff."""
from dataclasses import asdict
from adv_py.core.source_rp_dynamics import SourceRpNode
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan
from adv_py.core.source_inbetween_matrix import SourceInbetweenMatrixRecord,decode
from adv_py.core.character_registry import canonical,CharacterRegistryError

MARKER='advPySourceInbetweenMatrix'


def _source(host,plug):
    value=host._cmds.connectionInfo(plug,sourceFromDestination=True)
    if not value:return None
    node,attr=value.split('.',1)
    return host._resolve_connected_node(node)+'.'+attr


def _save(host,target,names):
    c=host._cmds;nodes=[];matrices=[]
    for name in names:
        kind=c.nodeType(name);values=[];edges=[]
        attrs=(tuple('matrixIn['+str(i)+']' for i in c.getAttr(name+'.matrixIn',multiIndices=True) or ())
               if kind=='multMatrix' else ('inputMatrix','useTranslate','useRotate','useScale','useShear')
               if kind=='pickMatrix' else ('inputX',))
        for attr in attrs:
            plug=name+'.'+attr;source=_source(host,plug)
            if source:edges.append((source,attr))
            elif kind=='multMatrix':matrices.append((plug,tuple(c.getAttr(plug))))
            elif attr!='inputMatrix':values.append((attr,float(c.getAttr(plug))))
        nodes.append(SourceRpNode(name,kind,tuple(values),tuple(edges)))
    graph=SourceBodyMatrixPlan(target,tuple(nodes),((_source(host,target+'.offsetParentMatrix'),target+'.offsetParentMatrix'),))
    record=SourceInbetweenMatrixRecord(graph,tuple(matrices),bool(c.getAttr(target+'.inheritsTransform')))
    c.addAttr(target,longName=MARKER,dataType='string')
    c.setAttr(target+'.'+MARKER,canonical(asdict(record)),type='string',lock=True)
    audit_target(host,target)


def _main(host,stem,main,control):
    c=host._cmds;pick=stem+'MainPM';reverse=stem+'Reverse'
    c.createNode('pickMatrix',name=pick,skipSelect=True);c.createNode('reverse',name=reverse,skipSelect=True)
    c.connectAttr(main+'.worldMatrix[0]',pick+'.inputMatrix')
    for attr in ('useTranslate','useRotate','useShear'):c.setAttr(pick+'.'+attr,False)
    c.connectAttr(control+'.inheritScale',reverse+'.inputX');c.connectAttr(reverse+'.outputX',pick+'.useScale')
    return pick,reverse


def configure_fk(host,fk,segments,global_control,metadata,instances):
    host._require_transaction();c=host._cmds
    from maya.api import OpenMaya as om
    from adv_py.core.source_fit_identity import source_fit_metadata
    from adv_py.core.fit_scale_compensation import fit_segment_scale_compensate
    controls={control.offset_path:control for control in fk.controls}
    for built in segments:
        if not built.fk.use_offset_parent_matrix or built.fk.parts is None:continue
        for part in built.fk.parts.parts:
            stem='AdvPy_'+part.part_name+'_SourceInbetween';pick=stem+'NoShearPM'
            c.createNode('pickMatrix',name=pick,skipSelect=True)
            c.connectAttr(part.fkps_name+'.worldMatrix[0]',pick+'.inputMatrix')
            c.connectAttr(part.control_name+'.inheritScale',pick+'.useScale');c.setAttr(pick+'.useShear',False)
            matrix=part.fk_matrix_name
            incoming=[]
            for i in c.getAttr(matrix+'.matrixIn',multiIndices=True) or ():
                plug=matrix+'.matrixIn['+str(i)+']';source=_source(host,plug)
                if source and source.split('.',1)[0]==host._resolve_connected_node(part.fkps_name):incoming.append(plug)
            if len(incoming)!=1:raise CharacterRegistryError('来源 Inbetween FKPS 接收地址不唯一')
            c.disconnectAttr(c.connectionInfo(incoming[0],sourceFromDestination=True),incoming[0])
            c.connectAttr(pick+'.outputMatrix',incoming[0])
            target=host._resolve_connected_node(part.offset_name)
            _save(host,target,(matrix,part.pick_matrix_name,pick))
        target=built.rewire.downstream_fk_offset_path
        if target is None:continue
        control=controls[target];last=host._resolve_connected_node(built.rewire.last_part_fkx_name)
        before=om.MMatrix(c.xform(target,q=True,ws=True,m=True));source_world=om.MMatrix(c.getAttr(last+'.worldMatrix[0]'))
        local=tuple(before*source_world.inverse());translation=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,*local[12:15],1.)
        rotation=tuple(before*(om.MMatrix(translation)*source_world).inverse())
        body_name=control.driven_joint.rsplit('|',1)[-1]
        fit=source_fit_metadata(body_name,metadata,instances)
        if fit is None:
            fit=next((item for item in metadata if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1] in control.fit_joint_names),None)
        if fit is None:raise CharacterRegistryError('来源 Inbetween 下游缺少 Fit 身份')
        if not c.objExists(control.control_path+'.inheritScale'):
            c.addAttr(control.control_path,longName='inheritScale',attributeType='bool',defaultValue=not fit_segment_scale_compensate(
                fit,control.fit_joint_names[0],built.fk.anchor.start_body_name.rsplit('_',1)[0],use_offset_parent_matrix=True))
        stem='AdvPy_'+body_name+'_SourceInbetweenEnd';world=stem+'NoShearMM';pick=stem+'NoShearPM';matrix=stem+'MM'
        for name,kind in ((world,'multMatrix'),(pick,'pickMatrix'),(matrix,'multMatrix')):c.createNode(kind,name=name,skipSelect=True)
        c.setAttr(world+'.matrixIn[0]',*translation,type='matrix');c.connectAttr(last+'.worldMatrix[0]',world+'.matrixIn[1]')
        c.connectAttr(world+'.matrixSum',pick+'.inputMatrix');c.setAttr(pick+'.useShear',False)
        c.connectAttr(control.control_path+'.inheritScale',pick+'.useScale')
        main,reverse=_main(host,stem,global_control.control_path,control.control_path)
        c.setAttr(matrix+'.matrixIn[0]',*rotation,type='matrix');c.connectAttr(main+'.outputMatrix',matrix+'.matrixIn[1]')
        c.connectAttr(pick+'.outputMatrix',matrix+'.matrixIn[2]')
        old=c.connectionInfo(target+'.offsetParentMatrix',sourceFromDestination=True)
        c.disconnectAttr(old,target+'.offsetParentMatrix');c.setAttr(target+'.inheritsTransform',False)
        c.connectAttr(matrix+'.matrixSum',target+'.offsetParentMatrix')
        _save(host,target,(world,pick,main,reverse,matrix))
    host._transaction_changed=True


def audit_target(host,target):
    c=host._cmds;plug=target+'.'+MARKER
    if not c.getAttr(plug,lock=True):raise CharacterRegistryError('来源 Inbetween 矩阵记录已解锁')
    saved=decode(c.getAttr(plug));graph=saved.graph
    if graph.body!=target or bool(c.getAttr(target+'.inheritsTransform'))!=saved.inherits_transform:
        raise CharacterRegistryError('来源 Inbetween 矩阵接收身份或继承变化')
    for node in graph.nodes:
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:raise CharacterRegistryError('来源 Inbetween 矩阵节点缺失')
        for attr,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:raise CharacterRegistryError('来源 Inbetween 矩阵常量变化')
        for source,attr in node.connections:
            if not c.isConnected(source,node.name+'.'+attr):raise CharacterRegistryError('来源 Inbetween 矩阵接线变化')
    for plug,values in saved.matrices:
        if c.connectionInfo(plug,isDestination=True) or max(abs(a-b) for a,b in zip(c.getAttr(plug),values))>1e-8:
            raise CharacterRegistryError('来源 Inbetween 绑定矩阵变化')
    for source,target in graph.outputs:
        if not c.isConnected(source,target):raise CharacterRegistryError('来源 Inbetween 矩阵输出变化')


def audit_registered(host,registration):
    for node in registration.nodes:
        if host._cmds.objExists(node.path+'.'+MARKER):audit_target(host,node.path)
