"""Connect individual Inbetween Fatness through the source Body scale graph."""
from adv_py.core.source_rp_part_scale import plan_source_rp_part_scale
from adv_py.core.character_registry import CharacterRegistryError


def configure(host,plan,limb,ik,inbetween_segments,connections):
    c=host._cmds
    stem='AdvPy_'+plan.label+'_RP_'+plan.side
    segment_index={segment.previous:index for index,segment in enumerate(plan.segments,1)}
    rows=[]
    for built in inbetween_segments:
        if not hasattr(built,'ik') or built.fk.parts is None:
            continue
        fk_parts={part.part_name:part for part in built.fk.parts.parts}
        for part in built.body.parts:
            solver=host._resolve_connected_node(part.ikx_name)
            index=segment_index.get(solver)
            if index is None:
                continue  # Spline/SC Parts are not in this RP handle.
            bodies=c.ls(part.body_part_name,long=True,type='joint') or ()
            if len(bodies)!=1:
                raise CharacterRegistryError('来源 RP Inbetween Body 身份不唯一')
            body=bodies[0]
            parent=(c.listRelatives(body,parent=True,fullPath=True) or [None])[0]
            if parent is None:
                raise CharacterRegistryError('来源 RP Inbetween 缺少 Body 父级')
            fk=fk_parts[part.body_part_name]
            control=(built.fk.parts.fk_system_path+'|'+fk.offset_name+'|'+fk.extra_name+'|'+fk.control_name)
            offset=part.constraint_name+'.offsetX'
            twist=c.connectionInfo(offset,sourceFromDestination=True) or None
            row=plan_source_rp_part_scale(stem,index,body,parent,
                host._resolve_connected_node(part.fkx_name),solver,control,
                built.body.ik_weight_plug,plan.volume,stem+'_Fatness'+str(index)+'.output1D',
                use_offset_parent_matrix=not fk.segment_scale_compensate,twist_source=twist)
            if row.constraint!=part.constraint_name:
                raise CharacterRegistryError('来源 RP Inbetween 约束身份改变')
            rows.append(row)
    for row in rows:
        if any(host.find_name_collisions(node.name) for node in row.nodes):
            raise CharacterRegistryError('来源 RP Inbetween 缩放节点名称被占用')
        if row.use_offset_parent_matrix:
            if c.connectionInfo(row.body+'.offsetParentMatrix',isDestination=True):
                raise CharacterRegistryError('来源 RP Inbetween OPM 已有输入')
            if not c.objExists(row.constraint) or c.nodeType(row.constraint)!='orientConstraint':
                raise CharacterRegistryError('来源 RP Inbetween 朝向来源缺失')
            # UnTwister has already created its weighted angle. The original
            # OPM branch inserts that angle's composeMatrix before Body BM.
            if row.twist_source:
                c.disconnectAttr(row.twist_source,row.constraint+'.offsetX')
            c.delete(row.constraint)
            for attribute in ('translate','rotate','scale','jointOrient'):
                compound=row.body+'.'+attribute
                source=c.connectionInfo(compound,sourceFromDestination=True)
                if source:c.disconnectAttr(source,compound)
                for axis in 'XYZ':
                    plug=compound+axis
                    source=c.connectionInfo(plug,sourceFromDestination=True)
                    if source:c.disconnectAttr(source,plug)
                value=1. if attribute=='scale' else 0.
                c.setAttr(compound,value,value,value,type='double3')
        else:
            if any(c.connectionInfo(row.body+'.scale'+axis,isDestination=True) for axis in 'XYZ'):
                raise CharacterRegistryError('来源 RP Inbetween 缩放已有输入')
        for node in row.nodes:
            c.createNode(node.kind,name=node.name,skipSelect=True)
            for attr,value in node.values:c.setAttr(node.name+'.'+attr,value)
        for node in row.nodes:
            for source,attribute in node.connections:connections.connect(source,node.name+'.'+attribute)
        for source,target in row.outputs:connections.connect(source,target)
    return (tuple(node for row in rows for node in row.nodes),
            tuple(output for row in rows for output in row.outputs))
