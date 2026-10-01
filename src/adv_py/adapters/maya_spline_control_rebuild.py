"""Native surviving-control data mapping for an explicit Spline count edit."""
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError
from .maya_character_properties import plan as plan_property_transfer


def destination(staged,plug):
    change=staged.spline_change
    return change.destination(plug) if change is not None and change.systems else plug


def original_plug(change,plug):
    """Resolve a planned target property back to its still-live source."""
    exact=[source for source,target in change.plugs if target==plug]
    if len(exact)==1:return exact[0]
    node,separator,attribute=plug.partition('.')
    peers=[source for source,target in change.nodes if target==node]
    return peers[0]+separator+attribute if len(peers)==1 else plug


def authored_fit_count_changes(host,registration):
    """Original rebuild derives control count again from the current labels."""
    from adv_py.core.spline_control_rebuild import splines,control_count
    from adv_py.core.fit_ik import fit_joint_ik_info
    from adv_py.core.source_fit_identity import source_fit_build_name
    hierarchy=host.capture_fit_hierarchy(registration.container)
    labels={joint.path:host.read_joint_label(joint.path) for joint in hierarchy.joints}
    nodes={joint.path:joint for joint in hierarchy.joints}
    infos=[]
    for joint in hierarchy.joints:
        info=fit_joint_ik_info(hierarchy,labels,joint.path)
        if info is not None and info.start==joint.path and info.solver=='ikSplineSolver':
            infos.append(info)
    result=[]
    for plan in splines(registration):
        if not plan.source_curve_points:continue
        if plan.source_fit_control_count is None and plan.source_mode is None:
            # Older 0–1 graphs may predate label-driven counts. With no saved
            # label baseline, retain that layout and establish the baseline
            # during the ordinary rebuild instead of reinterpreting curves.
            continue
        start=plan.body_joints[0].rsplit('|',1)[-1].rsplit('_',1)[0]
        end=plan.body_joints[-1].rsplit('|',1)[-1].rsplit('_',1)[0]
        matches=[info for info in infos
                 if (nodes[info.start].short_name.rsplit(':',1)[-1]==plan.source_mode.fit_start_joint
                     if plan.source_mode is not None else
                     source_fit_build_name(nodes[info.start].short_name.rsplit(':',1)[-1])==start)
                 and source_fit_build_name(nodes[info.end].short_name.rsplit(':',1)[-1])==end]
        if len(matches)!=1:
            raise CharacterRegistryError('当前 Fit 标签不能唯一对应已保存 Spline：'+plan.system_name)
        authored=matches[0].control_count
        baseline=plan.source_fit_control_count
        if baseline is None:baseline=control_count(plan)
        if authored!=baseline:result.append((plan.system_name,authored))
    return tuple(result)


def control_states(staged):
    change=staged.spline_change
    if change is None or not change.systems:return staged.original.control_states
    return tuple(replace(row,node=change.node_destination(row.node))
                 for row in staged.original.control_states
                 if change.node_destination(row.node) is not None)


def plan_properties(host,stage,original,registration,change):
    rows=[]
    channels={row.node+'.'+row.attribute for row in original.registration.channels}
    generated_nodes={row.path for row in original.registration.nodes}
    if host._cmds.objExists('AllSet'):generated_nodes.update(host.capture_body_all_set_members())
    # Registered endpoint properties move to the regenerated endpoint, while
    # transforms keep their indexed control identity as in the MEL rebuild.
    for row in original.properties:
        grouped={}
        for attribute in row.attributes:
            plug=row.path+'.'+attribute[0]
            mapped=change.destination(plug)
            if mapped is None:continue
            node=mapped.rsplit('.',1)[0]
            if not stage._cmds.objExists(node):
                if plug in channels:continue
                raise CharacterRegistryError('删除的 Spline 控制器仍有用户属性：'+plug)
            if attribute[0]=='followEnd' and plug in channels:
                # The generated default is the new index/count fraction;
                # the old authored value/curve is still restored unchanged.
                metadata=dict(attribute[5])
                metadata['default']=tuple(stage._cmds.attributeQuery(
                    'followEnd',node=node,listDefault=True) or ())
                attribute=(*attribute[:5],tuple(metadata.items()))
            grouped.setdefault(node,[]).append(attribute)
        for node,attributes in grouped.items():
            owned={row.path+'.'+attribute[0] for attribute in attributes}
            links=[]
            for source,target in row.connections:
                if source not in owned and target not in owned:continue
                if (source in channels and target.split('.',1)[0] in generated_nodes
                        and change.affects(target.split('.',1)[0])):
                    # This consumer belongs to the newly generated solver,
                    # whose count-specific wiring is authoritative.
                    continue
                left,right=change.destination(source),change.destination(target)
                if left is not None and right is not None:links.append((left,right))
            rows.append(replace(row,path=node,attributes=tuple(attributes),
                                connections=tuple(sorted(links))))
    remapped=replace(original,properties=tuple(rows),registration=registration)
    return plan_property_transfer(host,remapped,stage.namespace)


def validate_removed_node(host,node,owned,original):
    """MEL drops obsolete generated receivers, never arbitrary user children."""
    c=host._cmds
    if c.referenceQuery(node,isNodeReferenced=True) or any(c.lockNode(node,q=True,lock=True) or []):
        raise CharacterRegistryError('删除的 Spline 接收节点被引用或锁定：'+node)
    if 'dagNode' in (c.nodeType(node,inherited=True) or []):
        children=set(c.listRelatives(node,children=True,fullPath=True) or [])
        if children-owned:
            raise CharacterRegistryError('删除的 Spline 控制器仍有用户子节点：'+node)
    from .maya_character_preservation import connections
    permitted={curve.node for curve in original.curves}
    permitted.update(row.node for row in original.selection_sets)
    for source,target in connections(host,node):
        peers={plug.split('.',1)[0] for plug in (source,target)}-{node}
        if not peers<=owned|permitted:
            raise CharacterRegistryError('删除的 Spline 接收节点仍有用户连接：'+node)
