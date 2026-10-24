"""Native source IK start frames and their locked parent-follow matrix graph."""
from dataclasses import asdict,replace
from .maya_original_transform_channels import align_original_transform
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_limb_root_frame import SourceIkRootFrameRecord,decode_record

MARKER='advPySourceIkRootFrame'


def create(host,spec):
    host._require_transaction();c=host._cmds
    for path in (spec.frame,spec.offset):
        name=path.rsplit('|',1)[-1]
        if host.find_name_collisions(name):
            raise CharacterRegistryError('来源 IK 起点层级名称冲突：'+name)
    frame=c.createNode('transform',name=spec.frame.rsplit('|',1)[-1],
                       parent=spec.parent,skipSelect=True)
    c.setAttr(frame+'.rotateOrder',spec.rotate_order)
    # MEL copies live parent translation/rotation, never parent scale/shear.
    target=spec.source_parent or spec.source_joint
    position=c.xform(target,query=True,worldSpace=True,translation=True)
    rotation=c.xform(target,query=True,worldSpace=True,rotation=True)
    c.xform(frame,worldSpace=True,translation=position,rotation=rotation)
    offset=c.createNode('transform',name=spec.offset.rsplit('|',1)[-1],
                        parent=frame,skipSelect=True)
    c.setAttr(offset+'.rotateOrder',spec.rotate_order)
    align_original_transform(c,offset,spec.source_joint,True,True)
    host._transaction_changed=True


def connect(host,spec,body_root,root_follow,*,use_offset_parent_matrix=True,saved_offset_matrix=None):
    host._require_transaction();c=host._cmds
    source=root_follow if spec.source_parent==body_root and root_follow else spec.source_parent
    if source is None:return
    from adv_py.core.source_limb_root_frame import plan_graph
    plan=plan_graph(spec.frame,spec.parent,source,spec.rotate_order,use_offset_parent_matrix)
    for node in plan.nodes:
        if host.find_name_collisions(node.name):raise CharacterRegistryError('来源 IK 起点矩阵名称冲突')
        c.createNode(node.kind,name=node.name,skipSelect=True)
        for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
    for node in plan.nodes:
        for upstream,attr in node.connections:c.connectAttr(upstream,node.name+'.'+attr)
    if use_offset_parent_matrix:
        for attr in ('translate','rotate'):c.setAttr(spec.frame+'.'+attr,0.,0.,0.,type='double3')
    for output in plan.outputs:c.connectAttr(*output)
    # MEL 80427–80452 connects the parent-follow matrix BEFORE aligning
    # IKXOffset, and 80802 creates the solver only after that bind frame.
    # Copying parent Euler values before connection is not the final frame
    # when parent/child rotation orders differ.
    if saved_offset_matrix is None:
        align_original_transform(c,spec.offset,spec.source_joint,True,True)
    else:
        c.xform(spec.offset,objectSpace=True,matrix=saved_offset_matrix)
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
        order = None
        if len(source)==1:
            order = c.getAttr(source[0]+'.rotateOrder')
        elif not source:
            from .maya_character_body_retirement import retired_message_source
            retired = retired_message_source(host,node.path+'.advPySourceJoint')
            if retired is not None:order = retired.rotate_order
        if (node.node_type!='joint' or order is None or not c.getAttr(marker)
                or not c.getAttr(marker,lock=True) or c.connectionInfo(marker,isDestination=True)
                or c.getAttr(node.path+'.rotateOrder')!=order):
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
        if plan.outputs[0][1].endswith('.offsetParentMatrix'):
            for attr in ('translate','rotate'):
                if c.listConnections(node.path+'.'+attr,source=True,destination=False) or any(
                        abs(value)>1e-8 for value in c.getAttr(node.path+'.'+attr)[0]):
                    raise CharacterRegistryError('来源 IK 起点矩阵本地变换变化')
        elif (c.connectionInfo(node.path+'.offsetParentMatrix',isDestination=True)
              or tuple(c.getAttr(node.path+'.offsetParentMatrix')) !=
              (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)):
            raise CharacterRegistryError('来源非 OPM IK 起点出现额外矩阵驱动')


def finalize(host,specs):
    host._require_transaction();c=host._cmds
    for spec in specs:
        if any(abs(value)>1e-5 for value in c.getAttr(spec.joint+'.jointOrient')[0]):
            raise CharacterRegistryError('来源 IK 起点 Offset 未接管绑定旋转')
        c.setAttr(spec.joint+'.jointOrient',0.,0.,0.,type='double3')
        c.setAttr(spec.joint+'.rotateOrder',spec.rotate_order)
    host._transaction_changed=True
