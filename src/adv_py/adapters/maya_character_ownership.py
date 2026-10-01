"""Read-only deletion boundary audit against a freshly built replacement graph.

Namespace membership alone never establishes ownership. Automatic root-level
unit conversions are paired by their exclusive input/output boundary.
"""
from hashlib import sha256
from math import isclose

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_preservation import RebuildOwnership
from .maya_character_preservation import connections


def _driven_curve_state(commands,node):
    """Unitless SDK curves are rig logic, including their interpolation."""
    return (
        tuple(commands.keyframe(node,q=True,floatChange=True) or []),
        tuple(commands.keyframe(node,q=True,valueChange=True) or []),
        *(tuple(commands.keyTangent(node,q=True,**{flag:True}) or [])
          for flag in ('inTangentType','outTangentType','inAngle','outAngle',
                       'inWeight','outWeight','lock','weightLock')),
        tuple(commands.keyframe(node,q=True,breakdown=True) or []),
        *(commands.getAttr(node+'.'+attr)
          for attr in ('weightedTangents','preInfinity','postInfinity')),
    )


def _same_curve_state(left,right):
    if isinstance(left,tuple) and isinstance(right,tuple):
        return len(left)==len(right) and all(
            _same_curve_state(a,b) for a,b in zip(left,right))
    if isinstance(left,float) or isinstance(right,float):
        return isinstance(left,(int,float)) and isinstance(right,(int,float)) and isclose(
            left,right,rel_tol=1e-7,abs_tol=1e-8)
    return type(left) is type(right) and left==right


def _curve_topology(host,node):
    from maya.api import OpenMaya as om
    selection=om.MSelectionList();selection.add(host.scene_address(node))
    curve=om.MFnNurbsCurve(selection.getDagPath(0))
    return tuple(curve.knots())


def _curve_geometry(host,node):
    from maya.api import OpenMaya as om
    selection=om.MSelectionList();selection.add(host.scene_address(node))
    curve=om.MFnNurbsCurve(selection.getDagPath(0))
    return (int(curve.degree),int(curve.form),
            tuple((float(p.x),float(p.y),float(p.z),float(p.w))
                  for p in curve.cvPositions(om.MSpace.kObject)),
            tuple(curve.knots()))


def _editable_control_curve(host,node,registration):
    """Distinguish user-facing shapes from the IK solver's construction curve."""
    c=host._cmds
    parents=c.listRelatives(node,parent=True,fullPath=True) or []
    controls={channel.node for channel in registration.channels}
    if len(parents)!=1 or parents[0] not in controls:
        return False
    if bool(c.getAttr(node+'.intermediateObject')):
        return False
    return not any(c.listConnections(node+'.'+attribute,s=True,d=False)
                   for attribute in ('create','controlPoints'))


def _curve_display_settings(commands,node):
    settings=[]
    for attr in ('overrideEnabled','overrideDisplayType','overrideLevelOfDetail','overrideShading',
                 'overrideTexturing','overridePlayback','overrideVisibility','overrideColor',
                 'overrideRGBColors','overrideColorRGB','lineWidth'):
        if not commands.objExists(node+'.'+attr):continue
        value=commands.getAttr(node+'.'+attr)
        if isinstance(value,list):value=tuple(value[0])
        settings.append((attr,value,bool(commands.getAttr(node+'.'+attr,lock=True))))
    return tuple(settings)


def _control_shape_changes(host,target,names,original,replacement):
    """MEL's same-name control reuse also retains user-added curve shapes."""
    common={ch.node for ch in original.channels} & {ch.node for ch in replacement.channels}
    retained=[];created=[]
    for node in names:
        if host._cmds.objExists(node):continue
        parent=node.rsplit('|',1)[0]
        if (target._cmds.nodeType(node)!='nurbsCurve' or parent not in common
                or not _editable_control_curve(target,node,replacement)):
            raise CharacterRegistryError('原 Rig 缺少暂存结构节点：'+node)
        created.append((node,target._cmds.ls(node,uuid=True)[0]))
    for parent in sorted(common):
        if not host._cmds.objExists(parent) or not target._cmds.objExists(parent):continue
        for shape in host._cmds.listRelatives(parent,shapes=True,fullPath=True) or []:
            if shape in names:continue
            if (host._cmds.nodeType(shape)!='nurbsCurve'
                    or not _editable_control_curve(host,shape,original)):
                raise CharacterRegistryError('额外控制形状需要明确保留处理：'+shape)
            if (host._cmds.referenceQuery(shape,isNodeReferenced=True)
                    or any(host._cmds.lockNode(shape,q=True,lock=True) or [])):
                raise CharacterRegistryError('额外控制形状被引用或锁定：'+shape)
            retained.append((shape,host._cmds.ls(shape,uuid=True)[0],
                             target._cmds.ls(parent,uuid=True)[0],
                             connections(host,shape)))
    return tuple(retained),tuple(created)


def _graph(host,names,*,external_conversions=()):
    c=host._cmds
    nodes={name:name for name in names}
    edges=set()
    for name in names:edges.update(connections(host,name))
    outside={p.split('.',1)[0] for edge in edges for p in edge}-set(names)
    for node in sorted(outside):
        if node in external_conversions:continue
        if c.nodeType(node)!='unitConversion':continue
        links=connections(host,node)
        # Only a conversion entirely between known rig nodes is owned. A
        # conversion shared with an external consumer must block the audit.
        peers={p.split('.',1)[0] for edge in links for p in edge}-{node}
        if not peers or not peers<=set(names):continue
        incoming=tuple(sorted(a for a,b in links if b==node+'.input'))
        outgoing=tuple(sorted(b for a,b in links if a==node+'.output'))
        if len(incoming)!=1 or not outgoing:continue
        role='@conversion:'+sha256(repr((incoming,outgoing)).encode('utf8')).hexdigest()
        if role in nodes:raise CharacterRegistryError('单位转换归属存在歧义')
        nodes[role]=node
        edges.update(links)
    aliases={node:role for role,node in nodes.items()}
    def normalize(plug):
        node,attr=plug.split('.',1)
        if attr=='instObjGroups':
            attr='instObjGroups[0]'
        if (node in ('AllSet','ControlSet','DeformSet','Sets')
                and c.nodeType(node)=='objectSet'
                and attr.startswith(('dagSetMembers[','dnSetMembers['))
                and attr.endswith(']')):
            # Maya assigns sparse physical member indices in insertion order.
            # Compare the same member→set edge without that storage index;
            # changing the member or owning set still changes the graph.
            attr=attr.split('[',1)[0]+'[*]'
        return aliases.get(node,node)+'.'+attr
    return nodes,tuple(sorted((normalize(a),normalize(b)) for a,b in edges))


def audit(host,staged):
    """Reject unhandled connections or children before any deletion is possible."""
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    reg=target.read_character_registration()
    fit=reg.container
    names=tuple(n for n in target._cmds.ls(long=True)
                if not (n==fit or n.startswith(fit+'|')))
    # Audit applies to the pristine stage, before preserved curves move there.
    for node in names:
        kind=target._cmds.nodeType(node)
        if kind.startswith('animCurve') and kind not in (
                'animCurveUA','animCurveUL','animCurveUT','animCurveUU'):
            raise CharacterRegistryError('所有权审计需要尚未交接动画的暂存角色')
    retained_shapes,created_shapes=_control_shape_changes(
        host,target,names,staged.original.registration,reg)
    retained_names={row[0] for row in retained_shapes}
    created_names={row[0] for row in created_shapes}
    external_conversions={row[0] for row in (
        *staged.geometry_container_conversions,
        *staged.geometry_output_conversions,
        *staged.deformer_input_conversions,
        *staged.deformer_output_conversions)}
    if external_conversions & set(names):
        raise CharacterRegistryError('Geometry 保留单位转换与新 Rig 同名')
    old_nodes,old_edges=_graph(host,tuple(n for n in names if n not in created_names),
        external_conversions=external_conversions)
    new_nodes,new_edges=_graph(target,names)
    if set(old_nodes)!=set(new_nodes)-created_names:
        raise CharacterRegistryError('新旧 Rig 的独占单位转换边界不一致')
    rows=[];shapes=[];curve_geometry=[]
    original=staged.original
    extensions={row.path for row in original.extensions}
    geometry_roots={row[0] for row in (staged.authored_geometry or ())}
    retained_children = {fit, *extensions, *(
        shape.rsplit('|', 1)[0]
        for skin in original.skins for shape, _, _ in skin.meshes)}
    retained_children.update(geometry_roots)
    retained_children.update(retained_names)
    properties={row.path:{a[0] for a in row.attributes} for row in original.properties}
    for role in sorted(old_nodes):
        old,new=old_nodes[role],new_nodes[role]
        a,b=host._cmds,target._cmds
        kind=a.nodeType(old)
        if kind!=b.nodeType(new):raise CharacterRegistryError('新旧 Rig 节点类型不同：'+role)
        if a.referenceQuery(old,isNodeReferenced=True) or any(a.lockNode(old,q=True,lock=True) or []):
            raise CharacterRegistryError('旧 Rig 节点被引用或锁定：'+old)
        extra=set(a.listAttr(old,userDefined=True) or [])-set(b.listAttr(new,userDefined=True) or [])
        if extra-properties.get(old,set()):
            raise CharacterRegistryError('旧 Rig 节点有未采集的附加属性：'+old+' '+repr(sorted(extra-properties.get(old,set()))))
        if kind=='unitConversion' and a.getAttr(old+'.conversionFactor')!=b.getAttr(new+'.conversionFactor'):
            raise CharacterRegistryError('单位转换系数被修改：'+old)
        if kind in ('animCurveUA','animCurveUL','animCurveUT','animCurveUU'):
            if not _same_curve_state(_driven_curve_state(a,old),_driven_curve_state(b,new)):
                raise CharacterRegistryError('原 Rig 驱动曲线已修改，需要显式驱动曲线迁移：'+old)
        if kind=='nurbsCurve':
            shape_a=a.xform(old+'.cv[*]',q=True,objectSpace=True,t=True) or []
            shape_b=b.xform(new+'.cv[*]',q=True,objectSpace=True,t=True) or []
            editable=(_editable_control_curve(host,old,original.registration)
                      and _editable_control_curve(target,new,reg))
            if not editable and (len(shape_a)!=len(shape_b)
                    or _curve_topology(host,old)!=_curve_topology(target,new)
                    or any(a.getAttr(old+'.'+attr)!=b.getAttr(new+'.'+attr) for attr in ('degree','form','spans'))):
                raise CharacterRegistryError('控制形状拓扑不同，需要显式形状迁移：'+old)
            if editable:
                curve_geometry.append((role,*_curve_geometry(host,old)))
            settings=_curve_display_settings(a,old)
            # Solver curves receive their CVs from owned graph connections.
            # Their evaluated animation is not an editable control shape.
            driven = a.listConnections(old+'.controlPoints',source=True,destination=False) or []
            shapes.append((role,() if driven else tuple(shape_a),tuple(settings),_curve_topology(host,old)))
        if 'dagNode' in (a.nodeType(old,inherited=True) or []):
            children=set(a.listRelatives(old,children=True,fullPath=True) or [])
            if children-set(old_nodes.values())-retained_children:
                raise CharacterRegistryError('旧 Rig 存在未声明保留的子节点：'+old)
        rows.append((role,a.ls(old,uuid=True)[0],b.ls(new,uuid=True)[0],kind))
    old_owned=set(old_nodes.values())
    user_sets={row.node for row in original.selection_sets}
    new_owned=set(new_nodes.values())
    for shape,_,_,links in retained_shapes:
        for edge in links:
            peers={p.split('.',1)[0] for p in edge}-{shape}
            if not peers<=old_owned|user_sets:
                raise CharacterRegistryError('额外控制曲线有未声明的外部连接：'+shape)
            if peers & user_sets:
                from .maya_character_selection_preservation import membership_edge
                if not membership_edge(edge):
                    raise CharacterRegistryError('额外控制曲线与用户集有非成员连接：'+shape)
        points=tuple(host._cmds.xform(shape+'.cv[*]',q=True,objectSpace=True,t=True) or [])
        geometry=_curve_geometry(host,shape)
        shapes.append((shape,points,_curve_display_settings(host._cmds,shape),geometry[-1]))
        curve_geometry.append((shape,*geometry))
    permitted={pair for row in (*original.skins,*original.deformers,
        *original.extensions,*staged.custom_properties)
        for pair in row.connections}
    permitted.update(staged.geometry_container_drivers)
    permitted.update(staged.geometry_container_outputs)
    permitted.update(edge for row in original.selection_sets for edge in row.connections)
    permitted.update((converter+'.output',destination)
        for converter,destination in staged.geometry_output_conversions)
    permitted.update((upstream,converter+'.input')
        for converter,upstream in staged.geometry_container_conversions)
    permitted.update((upstream,converter+'.input')
        for converter,upstream,_ in staged.deformer_input_conversions)
    permitted.update((converter+'.output',destination)
        for converter,destinations in staged.deformer_output_conversions
        for destination in destinations)
    for curve in original.curves:
        permitted.update((curve.node+'.output',plug) for plug in curve.outputs)
    # Bind-pose records belong to retained skin, not to the rig being deleted.
    for skin in original.skins:
        for pose in host._cmds.listConnections(skin.node+'.bindPose',s=True,d=False) or []:
            if host._cmds.nodeType(pose)!='dagPose':raise CharacterRegistryError('蒙皮绑定姿态类型无效')
            permitted.update(connections(host,pose))
    # The replacement stage has no preserved mesh yet. A freshly built
    # AllSet may own a copied Geometry mesh, whose membership is restored
    # only when that mesh is handed over to the replacement character.
    retained_mesh_nodes = {
        node for skin in original.skins for shape, _, _ in skin.meshes
        for node in (shape, shape.rsplit('|', 1)[0])
    }
    retained_mesh_nodes.update(
        root+suffix for root, identities, _, _ in (staged.authored_geometry or ())
        for suffix, _, _ in identities)
    retained_mesh_nodes.update(external_conversions)
    retained_mesh_nodes.update(skin.node for skin in original.skins)
    retained_mesh_nodes.update(deformer.node for deformer in original.deformers)
    from adv_py.core.character_identity import SHARED_NODES
    retained_mesh_nodes.update(SHARED_NODES)
    for skin in original.skins:
        retained_mesh_nodes.update(host._cmds.listConnections(
            skin.node+'.bindPose',s=True,d=False) or [])
    permitted.update(
        edge for edge in old_edges
        if any(plug.split('.', 1)[0] == 'AllSet' for plug in edge)
        and any(plug.split('.', 1)[0] in retained_mesh_nodes
                for plug in edge)
    )
    extra=set(old_edges)-set(new_edges)-permitted
    missing=set(new_edges)-set(old_edges)
    retained_edges={edge for _,_,_,links in retained_shapes for edge in links}
    extra-=retained_edges
    for edge in tuple(missing):
        members={p.split('.',1)[0] for p in edge}
        if members & created_names and members<=new_owned:
            missing.remove(edge)
    if extra or missing:
        raise CharacterRegistryError('旧 Rig 连接不符合重建边界：'+repr((sorted(extra)[:3],sorted(missing)[:3])))
    result=RebuildOwnership(tuple(rows),old_edges,tuple(shapes),tuple(curve_geometry),
                            retained_shapes,created_shapes)
    if staged.ownership is not None and result!=staged.ownership:
        raise CharacterRegistryError('暂存后的节点归属、形状或连接发生变化')
    return result


def transfer_shapes(target,ownership,selection_sets=()):
    if ownership is None:return
    c=target._cmds
    if ownership.retained_shapes:
        from maya import cmds as native
        from .maya_character_transfer import _by_uuid,_writable_connection
        old_to_new={_by_uuid(native,old):_by_uuid(native,new)
                    for _,old,new,_ in ownership.nodes}
        user_sets={row.node:_by_uuid(native,row.uuid) for row in selection_sets}
        for role,uuid,parent_uuid,links in ownership.retained_shapes:
            source=_by_uuid(native,uuid)
            # Resolve endpoints before parenting changes the native DAG path.
            endpoints=[];sets=set()
            for a,b in links:
                left,attribute=a.split('.',1)
                right,target_attribute=b.split('.',1)
                # Original shape paths carry the original character namespace.
                # UUID mapping supplies the physical peer, independently of
                # which namespace the replacement host currently addresses.
                def physical(node):
                    if node==role:return source
                    if node in user_sets:return user_sets[node]
                    matched=[old for old in old_to_new
                             if target._cmds.identity.to_local(old)==node]
                    if len(matched)==1:return matched[0]
                    # to_local preserves foreign namespaces. Match the saved
                    # logical role through the audit's UUID pair as well.
                    for peer,old,_,_ in ownership.nodes:
                        if peer==node:return _by_uuid(native,old)
                    raise CharacterRegistryError('控制曲线保留连接无法定位：'+node)
                left,right=physical(left),physical(right)
                if native.nodeType(right)=='objectSet':
                    if right in user_sets.values():continue
                    if left!=source or right not in old_to_new:
                        raise CharacterRegistryError('控制曲线选择集连接超出重建范围：'+role)
                    sets.add((right,old_to_new[right]));continue
                endpoints.append((left,attribute,right,target_attribute))
            for old_set,new_set in sorted(sets):
                native.sets(source,remove=old_set)
                native.sets(source,add=new_set)
            for left,attribute,right,target_attribute in endpoints:
                a=left+'.'+attribute;b=right+'.'+target_attribute
                x=old_to_new.get(left,left)+'.'+attribute
                y=old_to_new.get(right,right)+'.'+target_attribute
                if (a,b)!=(x,y):
                    with _writable_connection(native,b,y):
                        native.disconnectAttr(a,b);native.connectAttr(x,y)
            native.parent(source,_by_uuid(native,parent_uuid),shape=True,relative=True)
            native.rename(_by_uuid(native,uuid),
                          ':'+target.scene_address(role).rsplit('|',1)[-1].lstrip(':'),
                          ignoreShape=True)
    if ownership.curve_geometry:
        from maya import cmds as native
        by_role={role:(old,new) for role,old,new,_ in ownership.nodes}
        for role,*_ in ownership.curve_geometry:
            if role not in by_role:
                continue  # User-added shapes already survive by native UUID.
            old=native.ls(by_role[role][0],long=True) or []
            if len(old)!=1:
                raise CharacterRegistryError('原控制曲线身份缺失：'+role)
            destination=target.scene_address(role)+'.create'
            locked=bool(native.getAttr(destination,lock=True))
            try:
                native.setAttr(destination,lock=False)
                # MEL retains geometry through this native temporary edge,
                # evaluates the result, then deletes the old shape with the
                # old rig. Maya retains the evaluated create datum. Commands
                # keep both the handoff and its rollback in the Undo chunk.
                native.connectAttr(old[0]+'.local',destination)
                _curve_geometry(target,role)
            finally:
                native.setAttr(destination,lock=locked)
    complete={row[0] for row in ownership.curve_geometry}
    for node,points,settings,knots in ownership.shapes:
        for index in range(0 if node in complete else len(points)//3):
            c.xform(node+f'.cv[{index}]',objectSpace=True,t=points[index*3:index*3+3])
        for attribute,value,locked in settings:
            plug=node+'.'+attribute
            c.setAttr(plug,lock=False)
            if isinstance(value,tuple):c.setAttr(plug,*value,type='double3')
            else:c.setAttr(plug,value)
            c.setAttr(plug,lock=locked)


def verify_shapes(target,ownership):
    if ownership is None:return
    c=target._cmds
    for node,uuid,parent_uuid,_ in ownership.retained_shapes:
        if (c.ls(node,uuid=True) or [])!=[uuid]:
            raise RuntimeError('额外控制曲线原生身份保留失败：'+node)
        parent=c.listRelatives(node,parent=True,fullPath=True) or []
        if len(parent)!=1 or (c.ls(parent[0],uuid=True) or [])!=[parent_uuid]:
            raise RuntimeError('额外控制曲线父级交接失败：'+node)
    for node,degree,form,points,knots in ownership.curve_geometry:
        if not _same_curve_state(_curve_geometry(target,node),
                                 (degree,form,points,knots)):
            raise RuntimeError('控制曲线完整几何保留复检失败：'+node)
    for node,points,settings,knots in ownership.shapes:
        current=tuple(c.xform(node+'.cv[*]',q=True,objectSpace=True,t=True) or [])
        if ((points and (len(current)!=len(points) or any(abs(a-b)>1e-8 for a,b in zip(current,points))))
                or _curve_topology(target,node)!=knots):
            raise RuntimeError('控制形状保留复检失败：'+node)
        for attr,value,locked in settings:
            actual=c.getAttr(node+'.'+attr)
            if isinstance(actual,list):actual=tuple(actual[0])
            if actual!=value or bool(c.getAttr(node+'.'+attr,lock=True))!=locked:
                raise RuntimeError('控制形状显示属性保留复检失败：'+node+'.'+attr)
