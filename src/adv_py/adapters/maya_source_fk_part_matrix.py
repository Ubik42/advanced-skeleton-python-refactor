"""Original OPM FK-only Inbetween Parts receive the complete FKX matrix."""
from dataclasses import asdict,replace
from adv_py.core.source_body_matrix import plan_source_fk_body_matrix
from adv_py.core.character_registry import canonical,CharacterRegistryError
from .maya_source_body_matrix import _reset_body
from .maya_source_graph_connections import SourceGraphConnections


def configure(host,segments):
    host._require_transaction();c=host._cmds
    for built in segments:
        if hasattr(built,'ik') or not built.fk.use_offset_parent_matrix:continue
        for part in built.body.parts:
            found=c.ls(part.body_part_name,long=True,type='joint') or []
            if len(found)!=1:raise CharacterRegistryError('来源 FK Part Body 身份不唯一')
            target=found[0];constraint=part.constraint_name
            if c.objExists(target+'.advPySourceBendyMatrix'):continue
            parent=(c.listRelatives(target,parent=True,fullPath=True) or [None])[0]
            if parent is None or not c.objExists(constraint) or c.nodeType(constraint)!='orientConstraint':
                raise CharacterRegistryError('来源 FK Part 原朝向接收缺失')
            offsets=tuple((axis,c.connectionInfo(constraint+'.offset'+axis,sourceFromDestination=True)) for axis in 'XYZ')
            values=tuple(float(c.getAttr(constraint+'.offset'+axis)) for axis in 'XYZ')
            plan=plan_source_fk_body_matrix('AdvPy_'+part.body_part_name+'_SourceFkPart',target,parent,
                host._resolve_connected_node(part.fkx_name)+'.worldMatrix[0]',
                offset_sources=tuple((axis,source) for axis,source in offsets if source),offset_values=values)
            if any(host.find_name_collisions(node.name) for node in plan.nodes):
                raise CharacterRegistryError('来源 FK Part 矩阵节点冲突')
            for axis,source in offsets:
                if source:c.disconnectAttr(source,constraint+'.offset'+axis)
            c.delete(constraint);_reset_body(c,target);c.setAttr(target+'.segmentScaleCompensate',False)
            graph=SourceGraphConnections(host,'AdvPy_'+part.body_part_name+'_SourceFkPart')
            for node in plan.nodes:
                c.createNode(node.kind,name=node.name,skipSelect=True)
                for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
            for node in plan.nodes:
                for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
            for source,destination in plan.outputs:graph.connect(source,destination)
            plan=replace(plan,nodes=graph.describe_nodes(plan.nodes),outputs=graph.describe_outputs(plan.outputs))
            c.addAttr(target,longName='advPySourceFkMatrix',dataType='string')
            c.setAttr(target+'.advPySourceFkMatrix',canonical(asdict(plan)),type='string',lock=True)
            c.addAttr(target,longName='advPySourceFkPoint',attributeType='bool')
            c.setAttr(target+'.advPySourceFkPoint',False,lock=True)
    host._transaction_changed=True
