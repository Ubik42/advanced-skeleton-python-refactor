"""Finish original Spline Inbetween Body Parts with full FK/IK matrices."""
from dataclasses import asdict,replace
from adv_py.core.character_registry import canonical,CharacterRegistryError
from adv_py.core.source_spline_part_matrix import plan_spline_part_matrix
from .maya_source_body_matrix import _reset_body
from .maya_source_graph_connections import SourceGraphConnections


def configure(host,body,splines,segments):
    host._require_transaction();c=host._cmds
    for spline in splines:
        if not spline.use_offset_parent_matrix:continue
        expanded=[];part_specs={}
        for index,start in enumerate(spline.body_joints):
            expanded.append(start)
            matches=[built for built in segments if hasattr(built,'ik') and built.ik.start_ik_driver==spline.ik_outputs[index]]
            if len(matches)>1:raise CharacterRegistryError('来源 Spline Part 起点重复')
            if not matches:continue
            built=matches[0]
            for part in built.body.parts:
                found=c.ls(part.body_part_name,long=True,type='joint') or []
                if len(found)!=1:raise CharacterRegistryError('来源 Spline Part Body 身份不唯一')
                target=found[0];expanded.append(target);part_specs[target]=(built,part)
        targets=tuple(control+'|'+spline.node_name(f'AdvPy_SplineIKLocalOrient{index}') for index,control in enumerate(spline.driver_targets))
        for index,target in enumerate(expanded):
            if target not in part_specs:continue
            built,part=part_specs[target];constraint=part.constraint_name
            if c.objExists(target+'.advPySourceBendyMatrix'):continue
            if not c.objExists(constraint):raise CharacterRegistryError('来源 Spline Part 原始朝向约束缺失')
            parent=(c.listRelatives(target,parent=True,fullPath=True) or [None])[0]
            offsets=tuple((axis,c.connectionInfo(constraint+'.offset'+axis,sourceFromDestination=True)) for axis in 'XYZ')
            values=tuple(float(c.getAttr(constraint+'.offset'+axis)) for axis in 'XYZ')
            stem='AdvPy_'+part.body_part_name+'_SourceSplinePart'
            plan=plan_spline_part_matrix(stem,target,parent,host._resolve_connected_node(part.fkx_name),
                host._resolve_connected_node(part.ikx_name),built.body.ik_weight_plug,spline.scale_reference,targets,index,len(expanded),
                spline.node_name('AdvPy_SplineVolumeDelta.output'),offset_sources=tuple((axis,source) for axis,source in offsets if source),offset_values=values)
            if any(host.find_name_collisions(node.name) for node in plan.nodes):raise CharacterRegistryError('来源 Spline Part 原生矩阵节点冲突')
            for axis,source in offsets:
                if source:c.disconnectAttr(source,constraint+'.offset'+axis)
            c.delete(constraint);_reset_body(c,target);c.setAttr(target+'.segmentScaleCompensate',False)
            graph=SourceGraphConnections(host,stem)
            for node in plan.nodes:
                c.createNode(node.kind,name=node.name,skipSelect=True)
                for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
            for node in plan.nodes:
                for source,attr in node.connections:graph.connect(source,node.name+'.'+attr)
            for source,destination in plan.outputs:graph.connect(source,destination)
            plan=replace(plan,nodes=graph.describe_nodes(plan.nodes),outputs=graph.describe_outputs(plan.outputs))
            c.addAttr(target,longName='advPySourceFkMatrix',dataType='string')
            c.setAttr(target+'.advPySourceFkMatrix',canonical(asdict(plan)),type='string',lock=True)
            c.addAttr(target,longName='advPySourceFkPoint',attributeType='bool');c.setAttr(target+'.advPySourceFkPoint',False,lock=True)
    host._transaction_changed=True
