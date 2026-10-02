"""MEL 83313–83348: twist reference follows FKX/parent BM, never Bendy Body."""
from dataclasses import asdict, replace
from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan, decode_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from .maya_source_graph_connections import SourceGraphConnections
from .maya_source_parent_inverse import parent_world_inverse

MARKER = 'advPySourceTwistReference'
GROUP = '|Group|MotionSystem|TwistSystem'


def create(host, inputs, independent, blended, *, main_scale_plug=None):
    host._require_transaction()
    c=host._cmds
    resolved=[]
    for item in inputs:
        parent=item.reference_parent_body
        world=independent.get(parent)
        blend=blended.get(parent)
        if item.reference_inverse_plug or not parent or not (world or blend):
            resolved.append(item)
            continue
        if not c.objExists(GROUP):
            c.createNode('transform',name='TwistSystem',parent='|Group|MotionSystem',skipSelect=True)
        stem='AdvPy_'+item.start_body.rsplit('|',1)[-1]+'_FitPartTwist'
        frame=stem+'ParentFrame'
        reference=stem+'IndependentReference'
        matrix=stem+'ParentMM'
        blend_name=stem+'ParentBM'
        scale_name=stem+'MainScaleCM'
        names=(frame,reference,matrix)+((blend_name,) if blend else ())+((scale_name,) if main_scale_plug else ())
        if any(host.find_name_collisions(name) for name in names):
            raise CharacterRegistryError('来源 Twist 独立父参考名称冲突：'+stem)
        for plug in ((blend[:3]) if blend else (world,)):
            if not c.objExists(plug):
                raise CharacterRegistryError('来源 Twist 独立父输入缺失：'+plug)
        if any(plug.split('.',1)[0] in (parent,item.start_body)
               for plug in ((blend[:2]) if blend else (world,))):
            raise CharacterRegistryError('来源 Twist 参考不能回读受驱动 Body')
        frame=c.createNode('transform',name=frame,parent=GROUP,skipSelect=True)
        frame=(c.ls(frame,long=True) or [frame])[0]
        nodes=[]
        if blend:
            nodes.append(SourceRpNode(blend_name,'blendMatrix',connections=(
                (blend[0],'inputMatrix'),(blend[1],'target[0].targetMatrix'),
                (blend[2],'target[0].weight'))))
            world=blend_name+'.outputMatrix'
        sources=[world]
        # MEL 84453–84466 inserts the same Root inbetween inverse rotation
        # before RootBM when it supplies children's twist reference frames.
        if parent.rsplit('|',1)[-1]=='Root_M' and c.objExists('AdvPy_SourceRootRemoveRotIM.outputMatrix'):
            sources.insert(0,'AdvPy_SourceRootRemoveRotIM.outputMatrix')
        # MEL 78897 scales TwistSystem only in non-OPM mode. The original
        # asMatrixConnectAttr decomposes the parent world matrix into that
        # scaled hierarchy; cancelling its parent inverse loses this factor.
        # Encode it per owned frame so legacy scene rebuilds retain their graph.
        if main_scale_plug:
            if not c.objExists(main_scale_plug):
                raise CharacterRegistryError('来源 Twist Main 缩放输入缺失')
            nodes.append(SourceRpNode(scale_name,'composeMatrix',connections=(
                (main_scale_plug,'inputScale'),)))
            sources.append(scale_name+'.outputMatrix')
        sources.append(parent_world_inverse(host,frame))
        nodes.append(SourceRpNode(matrix,'multMatrix',connections=tuple(
            (source,f'matrixIn[{index}]') for index,source in enumerate(sources))))
        graph=SourceGraphConnections(host,stem+'Parent')
        for node in nodes:
            c.createNode(node.kind,name=node.name,skipSelect=True)
        for node in nodes:
            for upstream,attribute in node.connections:
                graph.connect(upstream,node.name+'.'+attribute)
        outputs=((matrix+'.matrixSum',frame+'.offsetParentMatrix'),)
        graph.connect(*outputs[0])
        reference=c.createNode('transform',name=reference,parent=frame,skipSelect=True)
        reference=(c.ls(reference,long=True) or [reference])[0]
        c.xform(reference,worldSpace=True,matrix=c.xform(item.start_body,
                 query=True,worldSpace=True,matrix=True))
        c.setAttr(frame+'.visibility',False)
        plan=SourceBodyMatrixPlan(frame,graph.describe_nodes(tuple(nodes)),
                                 graph.describe_outputs(outputs))
        c.addAttr(reference,longName=MARKER,dataType='string')
        c.setAttr(reference+'.'+MARKER,canonical(asdict(plan)),type='string',lock=True)
        resolved.append(replace(item,reference_inverse_plug=reference+'.worldInverseMatrix[0]'))
    host._transaction_changed=True
    return tuple(resolved)


def audit(host, reference):
    c=host._cmds
    plug=reference+'.'+MARKER
    if not c.objExists(plug):return
    if not c.getAttr(plug,lock=True):
        raise CharacterRegistryError('来源 Twist 独立父参考登记未锁定')
    plan=decode_source_body_matrix(c.getAttr(plug))
    frame=(c.listRelatives(reference,parent=True,fullPath=True) or [])
    if frame!=[plan.body]:
        raise CharacterRegistryError('来源 Twist 独立父参考身份变化')
    if len(frame)!=1 or (c.listRelatives(frame[0],parent=True,fullPath=True) or [])!=[GROUP]:
        raise CharacterRegistryError('来源 Twist 独立父参考层级变化')
    if c.getAttr(frame[0]+'.visibility'):
        raise CharacterRegistryError('来源 Twist 内部父参考显示变化')
    for node in plan.nodes:
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
            raise CharacterRegistryError('来源 Twist 独立父参考节点缺失')
        for attribute,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attribute))-value)>1e-8:
                raise CharacterRegistryError('来源 Twist 独立父参考常量变化')
        for upstream,attribute in node.connections:
            if not c.isConnected(upstream,node.name+'.'+attribute):
                raise CharacterRegistryError('来源 Twist 独立父参考接线变化')
    for upstream,destination in plan.outputs:
        if not c.isConnected(upstream,destination):
            raise CharacterRegistryError('来源 Twist 独立父参考输出变化')


def audit_registered(host,registration):
    c = host._cmds
    paths = {node.path for node in registration.nodes}
    # Internal reference transforms are owned through the source TwistSystem,
    # rather than individually listed as character control members.
    if c.objExists(GROUP):
        paths.update(c.listRelatives(GROUP,allDescendents=True,fullPath=True,type='transform') or ())
    for path in sorted(paths):
        if c.objExists(path+'.'+MARKER):audit(host,path)
