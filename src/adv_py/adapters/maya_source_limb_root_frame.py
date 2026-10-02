"""Native source IK start frames and their locked parent-follow matrix graph."""
from dataclasses import asdict,replace
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_body_matrix import SourceBodyMatrixPlan
from adv_py.core.source_rp_dynamics import SourceRpNode
from adv_py.core.source_limb_root_frame import SourceIkRootFrameRecord,decode_record

MARKER='advPySourceIkRootFrame'


def _matrix(axes,position):
    return tuple(value for axis in axes for value in (*axis,0.))+(*position,1.)


def create(host,spec):
    host._require_transaction();c=host._cmds
    for path,parent,axes,position in ((spec.frame,spec.parent,spec.parent_axes,spec.parent_position),
                                     (spec.offset,spec.frame,spec.axes,spec.position)):
        name=path.rsplit('|',1)[-1]
        if host.find_name_collisions(name):raise CharacterRegistryError('来源 IK 起点层级名称冲突：'+name)
        node=c.createNode('transform',name=name,parent=parent,skipSelect=True)
        c.setAttr(node+'.rotateOrder',spec.rotate_order)
        c.xform(node,worldSpace=True,matrix=_matrix(axes,position))
    host._transaction_changed=True


def connect(host,spec,body_root,root_follow):
    host._require_transaction();c=host._cmds
    source=root_follow if spec.source_parent==body_root and root_follow else spec.source_parent
    if source is None:return
    stem=spec.frame.rsplit('|',1)[-1];matrix=stem+'MM';pick=stem+'PM'
    nodes=(SourceRpNode(matrix,'multMatrix',connections=((source+'.worldMatrix[0]','matrixIn[0]'),
            (spec.parent+'.worldInverseMatrix[0]','matrixIn[1]'))),
           SourceRpNode(pick,'pickMatrix',(('useScale',0.),('useShear',0.)),((matrix+'.matrixSum','inputMatrix'),)))
    for node in nodes:
        if host.find_name_collisions(node.name):raise CharacterRegistryError('来源 IK 起点矩阵名称冲突')
        c.createNode(node.kind,name=node.name,skipSelect=True)
        for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
    for node in nodes:
        for upstream,attr in node.connections:c.connectAttr(upstream,node.name+'.'+attr)
    for attr in ('translate','rotate'):c.setAttr(spec.frame+'.'+attr,0.,0.,0.,type='double3')
    outputs=((pick+'.outputMatrix',spec.frame+'.offsetParentMatrix'),)
    c.connectAttr(*outputs[0]);plan=SourceBodyMatrixPlan(spec.frame,nodes,outputs)
    c.addAttr(spec.frame,longName=MARKER,dataType='string')
    record=SourceIkRootFrameRecord(plan,spec.offset,tuple(c.getAttr(spec.offset+'.matrix')),spec.joint,spec.rotate_order)
    c.setAttr(spec.frame+'.'+MARKER,canonical(asdict(record)),type='string',lock=True)
    host._transaction_changed=True


def attach_measurement(host,spec,measurement):
    host._require_transaction();c=host._cmds
    measurement=host._resolve_connected_node(measurement)
    plug=spec.frame+'.'+MARKER
    record=decode_record(c.getAttr(plug))
    if measurement.rsplit('|',1)[0]!=spec.frame or record.measurements:
        raise CharacterRegistryError('来源 IK 长度测量绑定重复或父级不一致')
    updated=replace(record,measurements=((measurement,tuple(c.getAttr(measurement+'.matrix'))),))
    c.setAttr(plug,lock=False)
    c.setAttr(plug,canonical(asdict(updated)),type='string',lock=True)
    host._transaction_changed=True


def audit_registered(host,registration):
    c=host._cmds
    # All native IKX joints retain Fit's rotation order, not just the root
    # offset or IK end. Their existing source message identifies the order.
    for node in registration.nodes:
        marker=node.path+'.advPySourceIkRotationOrder'
        if not c.objExists(marker):continue
        source=c.listConnections(node.path+'.advPySourceJoint',source=True,destination=False,type='joint') or []
        if (node.node_type!='joint' or len(source)!=1 or not c.getAttr(marker)
                or not c.getAttr(marker,lock=True) or c.connectionInfo(marker,isDestination=True)
                or c.getAttr(node.path+'.rotateOrder')!=c.getAttr(source[0]+'.rotateOrder')):
            raise CharacterRegistryError('来源 IK 机制关节旋转顺序或来源改变：'+node.path)
    for node in registration.nodes:
        plug=node.path+'.'+MARKER
        if not c.objExists(plug):continue
        if not c.getAttr(plug,lock=True):raise CharacterRegistryError('来源 IK 起点矩阵记录已解锁')
        saved=decode_record(c.getAttr(plug));plan=saved.graph
        if plan.body!=node.path:raise CharacterRegistryError('来源 IK 起点矩阵身份变化')
        if (not c.objExists(saved.offset) or not c.objExists(saved.joint)
                or c.nodeType(saved.offset)!='transform' or c.nodeType(saved.joint)!='joint'
                or c.getAttr(saved.offset+'.rotateOrder')!=saved.rotate_order
                or max(abs(a-b) for a,b in zip(c.getAttr(saved.offset+'.matrix'),saved.offset_matrix))>1e-8
                or any(abs(value)>1e-8 for value in c.getAttr(saved.joint+'.jointOrient')[0])):
            raise CharacterRegistryError('来源 IK 起点绑定 Offset 或零朝向变化')
        for measurement,matrix in saved.measurements:
            if (not c.objExists(measurement) or c.nodeType(measurement)!='transform'
                    or (c.listRelatives(measurement,parent=True,fullPath=True) or [])!=[node.path]
                    or max(abs(a-b) for a,b in zip(c.getAttr(measurement+'.matrix'),matrix))>1e-8
                    or any(c.listConnections(measurement+'.'+attr,s=True,d=False)
                           for attr in ('translate','rotate','scale','shear','offsetParentMatrix'))):
                raise CharacterRegistryError('来源 IK 长度测量绑定帧变化')
        for saved in plan.nodes:
            if not c.objExists(saved.name) or c.nodeType(saved.name)!=saved.kind:
                raise CharacterRegistryError('来源 IK 起点矩阵节点缺失')
            for attr,value in saved.values:
                if abs(float(c.getAttr(saved.name+'.'+attr))-value)>1e-8:
                    raise CharacterRegistryError('来源 IK 起点矩阵常量变化')
            for upstream,attr in saved.connections:
                if not c.isConnected(upstream,saved.name+'.'+attr):raise CharacterRegistryError('来源 IK 起点矩阵接线变化')
        for upstream,target in plan.outputs:
            if not c.isConnected(upstream,target):raise CharacterRegistryError('来源 IK 起点矩阵输出变化')
        for attr in ('translate','rotate'):
            if c.listConnections(node.path+'.'+attr,source=True,destination=False) or any(
                    abs(value)>1e-8 for value in c.getAttr(node.path+'.'+attr)[0]):
                raise CharacterRegistryError('来源 IK 起点矩阵本地变换变化')


def finalize(host,specs):
    host._require_transaction();c=host._cmds
    for spec in specs:
        if any(abs(value)>1e-5 for value in c.getAttr(spec.joint+'.jointOrient')[0]):
            raise CharacterRegistryError('来源 IK 起点 Offset 未接管绑定旋转')
        c.setAttr(spec.joint+'.jointOrient',0.,0.,0.,type='double3')
        c.setAttr(spec.joint+'.rotateOrder',spec.rotate_order)
    host._transaction_changed=True
