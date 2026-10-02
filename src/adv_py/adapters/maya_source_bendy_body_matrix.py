"""MEL 83745–83778/83920–83937: MicroX owns Bendy deformation OPM."""
from dataclasses import asdict

from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan,decode_source_body_matrix
from adv_py.core.source_rp_dynamics import SourceRpNode
from .maya_source_body_matrix import _reset_body
from .maya_source_graph_connections import SourceGraphConnections


def create(host,spec):
    host._require_transaction()
    c=host._cmds
    start=(c.ls(spec.deform_names[0],long=True,type='joint') or [None])[0]
    if start is None:
        raise CharacterRegistryError('来源 Bendy 起点不唯一')
    base_values=[]
    base_connections=[]
    shared_nodes=()
    compound=c.connectionInfo(start+'.scale',sourceFromDestination=True)
    if compound:
        node,attribute=compound.split('.',1)
        base_connections.append((host._resolve_connected_node(node)+'.'+attribute,'input1'))
    else:
        for axis in 'XYZ':
            incoming=c.connectionInfo(start+'.scale'+axis,sourceFromDestination=True)
            if incoming:
                node,attribute=incoming.split('.',1)
                base_connections.append((host._resolve_connected_node(node)+'.'+attribute,'input1'+axis))
            else:base_values.append(('input1'+axis,float(c.getAttr(start+'.scale'+axis))))
    if spec.source_scale_plugs:
        base_values=[]
        base_connections=[(plug,'input1'+axis) for axis,plug in zip('XYZ',spec.source_scale_plugs)]
        scale_node=spec.source_scale_plugs[0].split('.',1)[0]
        if c.nodeType(scale_node)!='blendColors':
            raise CharacterRegistryError('来源 Spline Bendy 独立缩放节点类型变化')
        shared_nodes=(SourceRpNode(scale_node,'blendColors',(),tuple(
            (host._resolve_connected_node(incoming.split('.',1)[0])+'.'+incoming.split('.',1)[1],attr)
            for attr in ('blender',*(color+axis for color in ('color1','color2') for axis in 'RGB'))
            for incoming in (c.connectionInfo(scale_node+'.'+attr,sourceFromDestination=True),)
            if incoming)),)
    for deform_index,(name,output,offset,matrix,scale,guide) in enumerate(zip(
            spec.deform_names,spec.micro_output_names,spec.micro_offset_names,
            spec.deform_matrix_names,spec.deform_scale_mult_names,spec.motion_transform_names)):
        joint=(c.ls(name,long=True,type='joint') or [None])[0]
        source=(c.ls(output,long=True,type='transform') or [None])[0]
        parent=(c.listRelatives(joint,parent=True,fullPath=True) or [None])[0] if joint else None
        if (not joint or not source or not parent or c.objExists(joint+'.advPySourceBendyMatrix')
                or any(host.find_name_collisions(node) for node in (matrix,scale))):
            raise CharacterRegistryError('来源 Bendy MicroX 矩阵接收图无效：'+name)
        values=[('operation',1.),('input2X',1.),*base_values]
        connections=list(base_connections)
        # Preserve the independent ScaleBlend or FK scale source before
        # disconnecting local Body scale. The source never reads Body output.
        connections.extend((guide+'.scale'+axis,'input2'+axis) for axis in 'YZ')
        nodes=(SourceRpNode(scale,'multiplyDivide',tuple(values),tuple(connections)),
               SourceRpNode(matrix,'multMatrix',connections=(
                   (source+'.worldMatrix[0]','matrixIn[0]'),
                   (parent+'.worldInverseMatrix[0]','matrixIn[1]'))))
        # Unlike the former scale-only OPM plus parentConstraint, this is
        # the original complete MicroX world transform receiver.
        old=c.connectionInfo(joint+'.offsetParentMatrix',sourceFromDestination=True)
        if old:c.disconnectAttr(old,joint+'.offsetParentMatrix')
        _reset_body(c,joint)
        c.setAttr(joint+'.segmentScaleCompensate',False)
        incoming=c.connectionInfo(offset+'.scale',sourceFromDestination=True)
        if incoming:c.disconnectAttr(incoming,offset+'.scale')
        for axis in 'XYZ':
            incoming=c.connectionInfo(offset+'.scale'+axis,sourceFromDestination=True)
            if incoming:c.disconnectAttr(incoming,offset+'.scale'+axis)
        graph=SourceGraphConnections(host,matrix)
        for node in nodes:
            c.createNode(node.kind,name=node.name,skipSelect=True)
            for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
        for node in nodes:
            for incoming,attr in node.connections:graph.connect(incoming,node.name+'.'+attr)
        outputs=((matrix+'.matrixSum',joint+'.offsetParentMatrix'),)
        graph.connect(*outputs[0])
        graph.connect(scale+'.output',offset+'.scale')
        # MEL 83936 uses the complete parent-relative matrix, drops scale
        # and preserves shear. A parentConstraint discards that shear.
        follow=guide+'MicroFollow'
        if not c.objExists(follow) or c.nodeType(follow)!='parentConstraint':
            raise CharacterRegistryError('来源 Bendy MicroOffset 原跟随缺失')
        c.delete(follow)
        receiver=host._resolve_connected_node(offset)
        micro_parent=(c.listRelatives(receiver,parent=True,fullPath=True) or [None])[0]
        micro_matrix=matrix+'MicroMM';micro_pick=matrix+'MicroPM'
        micro_nodes=(SourceRpNode(micro_matrix,'multMatrix',connections=((guide+'.worldMatrix[0]','matrixIn[0]'),
            (micro_parent+'.worldInverseMatrix[0]','matrixIn[1]'))),
            SourceRpNode(micro_pick,'pickMatrix',(('useScale',0.),('useShear',1.)),((micro_matrix+'.matrixSum','inputMatrix'),)))
        for node in micro_nodes:
            c.createNode(node.kind,name=node.name,skipSelect=True)
            for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
        for node in micro_nodes:
            for incoming,attr in node.connections:c.connectAttr(incoming,node.name+'.'+attr)
        for attr in ('translate','rotate'):c.setAttr(receiver+'.'+attr,0.,0.,0.,type='double3')
        micro_outputs=((micro_pick+'.outputMatrix',receiver+'.offsetParentMatrix'),)
        c.connectAttr(*micro_outputs[0])
        micro_plan=SourceBodyMatrixPlan(receiver,micro_nodes,micro_outputs)
        c.addAttr(receiver,longName='advPySourceBendyMicroMatrix',dataType='string')
        c.setAttr(receiver+'.advPySourceBendyMicroMatrix',canonical(asdict(micro_plan)),type='string',lock=True)
        # MEL retains ScaleBlend on Part local scale after replacing its OPM
        # with MicroX. Start Body local scale is reset. Both layers are needed.
        local_scale=()
        if deform_index and base_connections:
            inputs=dict((attr,source) for source,attr in base_connections)
            if 'input1' in inputs:
                node,attr=inputs['input1'].rsplit('.',1)
                components='RGB' if attr=='output' and c.nodeType(node)=='blendColors' else 'XYZ'
                inputs={
                    'input1'+axis:node+'.'+attr+component
                    for axis,component in zip('XYZ',components)}
            local_scale=tuple((inputs['input1'+axis],joint+'.scale'+axis) for axis in 'XYZ')
            for incoming,target in local_scale:graph.connect(incoming,target)
        # The Body record owns its matrix and scale-input graph. Offset scale
        # is checked separately because it is an upstream controller output.
        plan=SourceBodyMatrixPlan(joint,shared_nodes+graph.describe_nodes(nodes),graph.describe_outputs(outputs),graph.describe_outputs(local_scale))
        c.addAttr(joint,longName='advPySourceBendyMatrix',dataType='string')
        c.setAttr(joint+'.advPySourceBendyMatrix',canonical(asdict(plan)),type='string',lock=True)
    host._transaction_changed=True


def audit_joint(host,joint):
    c=host._cmds
    plug=joint+'.advPySourceBendyMatrix'
    marker='AdvPy_MicroSystem.advPyBendyGuideOwner'
    if (not c.objExists(plug) or not c.getAttr(plug,lock=True)
            or not c.objExists(marker) or not c.getAttr(marker,lock=True)
            or c.getAttr(marker)!='adv_py.fit_bendy_guides.v1'):
        raise CharacterRegistryError('来源 Bendy 变形矩阵归属无效：'+joint)
    plan=decode_source_body_matrix(c.getAttr(plug))
    if plan.body!=joint:
        raise CharacterRegistryError('来源 Bendy 变形矩阵登记身份变化')
    leaf=joint.rsplit('|',1)[-1].rsplit(':',1)[-1]
    matrix='AdvPy_BendyDeform'+leaf+'MM'
    source=(c.ls('MicroX'+leaf,long=True,type='transform') or [])
    parent=(c.listRelatives(joint,parent=True,fullPath=True) or [])
    if (len(source)!=1 or len(parent)!=1
            or not c.isConnected(source[0]+'.worldMatrix[0]',matrix+'.matrixIn[0]')
            or not c.isConnected(parent[0]+'.worldInverseMatrix[0]',matrix+'.matrixIn[1]')
            or not c.isConnected(matrix+'.matrixSum',joint+'.offsetParentMatrix')
            or c.getAttr(joint+'.segmentScaleCompensate')):
        raise CharacterRegistryError('来源 Bendy MicroX 完整矩阵输出变化：'+joint)
    for node in plan.nodes:
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:
            raise CharacterRegistryError('来源 Bendy 变形矩阵节点缺失：'+node.name)
        for attr,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:
                raise CharacterRegistryError('来源 Bendy 变形矩阵常量变化')
        for incoming,attr in node.connections:
            if not c.isConnected(incoming,node.name+'.'+attr):
                raise CharacterRegistryError('来源 Bendy 变形矩阵连接变化')
    for source,target in plan.local_scale:
        if not c.isConnected(source,target):
            raise CharacterRegistryError('来源 Bendy Part 本地 ScaleBlend 连接变化')
    for attr,expected in (('translate',0.),('rotate',0.),('jointOrient',0.),*((('scale',1.),) if not plan.local_scale else ())):
        if (c.listConnections(joint+'.'+attr,source=True,destination=False)
                or any(abs(float(value)-expected)>1e-8 for value in c.getAttr(joint+'.'+attr)[0])):
            raise CharacterRegistryError('来源 Bendy OPM 本地变换变化：'+joint)
    scale='AdvPy_BendyDeformScale'+leaf
    offset='MicroOffset'+leaf
    if not c.isConnected(scale+'.output',offset+'.scale'):
        raise CharacterRegistryError('来源 Bendy MicroOffset 缩放输出变化')


def audit(host,spec):
    c=host._cmds
    for name,scale,guide in zip(spec.deform_names,spec.deform_scale_mult_names,spec.motion_transform_names):
        joints=c.ls(name,long=True,type='joint') or []
        if len(joints)!=1:
            return False
        audit_joint(host,joints[0])
        if (c.connectionInfo(scale+'.input2X',isDestination=True)
                or abs(float(c.getAttr(scale+'.input2X'))-1.)>1e-8
                or any(not c.isConnected(guide+'.scale'+axis,scale+'.input2'+axis) for axis in 'YZ')):
            return False
    return True


def audit_registered(host,registration):
    for node in registration.nodes:
        if host._cmds.objExists(node.path+'.advPySourceBendyMicroMatrix') and not audit_micro(host,node.path):
            raise CharacterRegistryError('来源 Bendy MicroOffset 原生矩阵变化')
        if node.node_type=='joint' and host._cmds.objExists(node.path+'.advPySourceBendyMatrix'):
            audit_joint(host,node.path)


def audit_micro(host,offset):
    c=host._cmds;plug=offset+'.advPySourceBendyMicroMatrix'
    if not c.objExists(plug) or not c.getAttr(plug,lock=True):
        return False
    plan=decode_source_body_matrix(c.getAttr(plug))
    if plan.body!=host._resolve_connected_node(offset):return False
    for node in plan.nodes:
        if not c.objExists(node.name) or c.nodeType(node.name)!=node.kind:return False
        for attr,value in node.values:
            if abs(float(c.getAttr(node.name+'.'+attr))-value)>1e-8:return False
        for incoming,attr in node.connections:
            if not c.isConnected(incoming,node.name+'.'+attr):return False
    return all(c.isConnected(incoming,target) for incoming,target in plan.outputs)
