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


def _graph(host,names,*,external_conversions=(),roles=None,normalize_registry=False):
    c=host._cmds
    nodes={(roles or {}).get(name,name):name for name in names}
    edges=set()
    for name in names:edges.update(connections(host,name))
    outside={p.split('.',1)[0] for edge in edges for p in edge}-set(names)
    # Native converters can be in the registry too. Their generated suffix
    # depends on Maya connection order, so a Spline count edit can rename
    # unrelated Bendy converters without changing their actual boundaries.
    # Pair both registered and implicit converters by their complete edges.
    registered_conversions={name for name in names if c.nodeType(name)=='unitConversion'}
    for node in sorted(outside|registered_conversions):
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
        for existing in tuple(nodes):
            if nodes[existing]==node:del nodes[existing]
        nodes[role]=node
        edges.update(links)
    aliases={node:role for role,node in nodes.items()}
    def normalize(plug):
        node,attr=plug.split('.',1)
        if attr=='instObjGroups':
            attr='instObjGroups[0]'
        if normalize_registry and node=='AdvPy_CharacterRegistry' and attr.startswith('members['):
            # Registration independently verifies the exact ordered members;
            # count edits and appended extensions shift storage indices.
            attr='members[*]'
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


def _spline_conversion(host,node,change,owned):
    """An implicit conversion belongs to the exact generating Spline edge."""
    c=host._cmds
    if c.nodeType(node)!='unitConversion':return False
    links=connections(host,node)
    inputs=[source for source,target in links if target==node+'.input']
    peers={plug.split('.',1)[0] for edge in links for plug in edge}-{node}
    return (len(inputs)==1 and change.affects(inputs[0].split('.',1)[0])
            and peers<=owned)


def _missing_fit_fat_connection(host,edge,container):
    """Recover the six exact generated edges lost by older promotions."""
    source,destination=edge
    a,aa=source.split('.',1);b,ba=destination.split('.',1)
    fit_node=(a if a.startswith(container+'|') else
              b if b.startswith(container+'|') else None)
    if fit_node is None:return False
    fat=fit_node.rsplit('|',1)[-1]+'Fat'
    expected={(fit_node+'.fat',fat+'.input1Y'),(fit_node+'.fat',fat+'.input1Z'),
              (fit_node+'.fatFront',fat+'.input2Y'),(fit_node+'.fatWidth',fat+'.input2Z'),
              (fat+'.outputY',fit_node+'.fatFrontAbs'),(fat+'.outputZ',fit_node+'.fatWidthAbs')}
    c=host._cmds
    return (edge in expected and c.objExists(source) and c.objExists(destination)
            and c.nodeType(fat)=='multiplyDivide' and c.getAttr(fat+'.operation')==1
            and not c.connectionInfo(destination,sourceFromDestination=True))


def _source_fit_driving_edges(host, registration):
    """Exact Fit catalogue edges written by source asDsToFitSkeleton.

    Completed rigs can have removed their old Fit templates. Entering edit
    mode repopulates the bool catalogue from live driver outputs. Compute
    that source operation read-only while the original rig is retained.
    """
    planner = getattr(host, 'plan_body_driving_fit_sync', None)
    plan = planner(registration.container) if planner else None
    if plan is None:
        return frozenset()
    c = host._cmds
    edges = set()
    for control in plan.controls:
        index = 0
        for attribute in control.attributes:
            for curve in attribute.curves:
                if not c.nodeType(curve).startswith('animCurve'):
                    raise CharacterRegistryError('Fit SDK 目录来源不是原生动画曲线：' + curve)
                node = c.identity.to_local(curve) if hasattr(c, 'identity') else curve
                edges.add((registration.container + '.' + control.fit_attribute
                           + '[' + str(index) + ']', node + '.' + attribute.name))
                index += 1
    return frozenset(edges)


def _source_rp_reverse_ownership_edges(host, registration):
    """Declared bookkeeping upgrade for pre-owner-marker source RP rigs.

    This message link retains the same native reverse while transitional
    constraints are removed. Its numeric input/output boundary is still
    checked by source mode validation and the complete graph comparison.
    """
    from .maya_source_limb_mode import PLAN_MARKER, REVERSE_MARKER
    from adv_py.core.source_limb_mode import decode_source_limb_mode
    channels = {row.key: row for row in registration.channels}
    c = host._cmds
    edges = set()
    for binding in registration.source_limbs:
        channel = channels[binding.blend_key]
        if channel.attribute != 'FKIKBlend':
            continue
        plan = decode_source_limb_mode(c.getAttr(channel.node + '.' + PLAN_MARKER))
        if plan.source_mode.control != channel.node:
            raise CharacterRegistryError('RP 归属迁移的控制器身份不符')
        reverse = 'FKIKBlend' + plan.source_mode.token + 'Reverse'
        if c.nodeType(reverse) != 'reverse':
            raise CharacterRegistryError('RP 归属迁移的原版反向节点类型不符')
        edges.add((reverse + '.message', channel.node + '.' + REVERSE_MARKER))
    return frozenset(edges)


def _source_spline_alignment_additions(host,target,original,replacement,systems):
    """Only explicitly migrated native reference frames may be new nodes."""
    if not systems:return frozenset()
    from adv_py.core.source_spline_alignment_upgrade import audit_source_spline_alignment_upgrade
    from .maya_source_spline_alignment import read
    audit_source_spline_alignment_upgrade(original,replacement,systems)
    selected=set(systems)
    result=set()
    for plan in (replacement.spine,*replacement.additional_spines):
        if plan is None or plan.system_name not in selected:continue
        for frame in read(target,plan):
            if host._cmds.objExists(frame.target):continue
            if target._cmds.nodeType(frame.target)!='transform':
                raise CharacterRegistryError('AlignIKTo 迁移新增节点类型无效：'+frame.target)
            result.add(frame.target)
    return frozenset(result)


def _source_fk_follower_ownership_edges(host,target,original,replacement):
    """Retain old numeric followers while adding their exact Body role link."""
    from adv_py.core.character_body_retirement import complete_body_bindings
    bodies={row.path for row in complete_body_bindings(original)}
    owned={row.path for row in original.nodes}
    edges=set()
    for row in replacement.nodes:
        if (row.node_type!='transform' or row.path not in owned
                or not row.path.rsplit('|',1)[-1].startswith('AdvPy_GenericFKFollow_')):
            continue
        plug=row.path+'.advPySourceFkFollowerScaleBody'
        if host._cmds.objExists(plug) or not target._cmds.objExists(plug):continue
        peers=target._cmds.listConnections(plug,source=True,destination=False) or []
        paths=target._cmds.ls(peers,long=True,type='joint') or []
        if (target._cmds.getAttr(plug,type=True)!='message'
                or not target._cmds.getAttr(plug,lock=True)
                or len(paths)!=1 or paths[0] not in bodies
                or not target._cmds.isConnected(paths[0]+'.message',plug)):
            raise CharacterRegistryError('旧 FK 跟随层归属迁移的 Body 角色无效：'+row.path)
        edges.add((paths[0]+'.message',plug))
    return frozenset(edges)


def audit(host,staged):
    """Reject unhandled connections or children before any deletion is possible."""
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    reg=target.read_character_registration()
    fit=reg.container
    names=tuple(n for n in target._cmds.ls(long=True)
                if not (n==fit or n.startswith(fit+'|')))
    change=staged.spline_change
    changing=change is not None and bool(change.systems)
    alignment_added=_source_spline_alignment_additions(host,target,
        staged.original.registration,reg,getattr(staged,'spline_alignment_systems',()))
    old_role_nodes={}
    if changing:
        for name in names:
            if host._cmds.objExists(name):old_role_nodes[name]=name;continue
            if not change.affects(name):continue
            matches=host._cmds.ls(name.rsplit('|',1)[-1],long=True) or []
            if len(matches)>1:raise CharacterRegistryError('Spline 同名旧节点身份不唯一：'+name)
            if matches:old_role_nodes[name]=matches[0]
    common_names=tuple(name for name in names if
        (name in old_role_nodes if changing else host._cmds.objExists(name)))
    added_names=set(names)-set(common_names) if changing else set()
    removed_names=set()
    if changing:
        # AllSet supplies explicit old ownership; the selected Spline plan
        # supplies the finite set of receivers allowed to disappear.
        old_members=set(host.capture_body_all_set_members())
        removed_names={name for name in old_members
                       if (change.affects(name) or _spline_conversion(host,name,change,old_members))
                       and name not in old_role_nodes.values()}
    from .maya_body_face_rebuild import retired_body_helpers
    face_retired=retired_body_helpers(host,staged.original.registration,names)
    removed_names.update(face_retired)
    # Audit applies to the pristine stage, before preserved curves move there.
    for node in names:
        kind=target._cmds.nodeType(node)
        if kind.startswith('animCurve') and kind not in (
                'animCurveUA','animCurveUL','animCurveUT','animCurveUU'):
            raise CharacterRegistryError('所有权审计需要尚未交接动画的暂存角色')
    retained_shapes,created_shapes=_control_shape_changes(
        host,target,tuple(name for name in common_names if host._cmds.objExists(name))
        if changing else tuple(name for name in names if name not in alignment_added),
        staged.original.registration,reg)
    retained_names={row[0] for row in retained_shapes}
    created_names={row[0] for row in created_shapes}
    external_conversions={row[0] for row in (
        *staged.geometry_container_conversions,
        *staged.geometry_output_conversions,
        *staged.deformer_input_conversions,
        *staged.deformer_output_conversions)}
    if external_conversions & set(names):
        raise CharacterRegistryError('Geometry 保留单位转换与新 Rig 同名')
    old_names=tuple(old_role_nodes[name] for name in common_names) if changing else tuple(
        name for name in names if name not in created_names|alignment_added)
    old_nodes,old_edges=_graph(host,old_names+tuple(sorted(removed_names)),
        external_conversions=external_conversions,
        roles={node:role for role,node in old_role_nodes.items()} if changing else None,
        normalize_registry=True)
    # Extensions append members while fresh builds order the same identities
    # differently. read_character_registration already verifies every native
    # slot against its document; compare their message relationships here.
    new_nodes,new_edges=_graph(target,names,normalize_registry=True)
    added_roles=set(new_nodes)-set(old_nodes)-created_names
    removed_roles=set(old_nodes)-set(new_nodes)
    if changing:
        for role in added_roles:
            if (not change.affects(new_nodes[role]) and not role.startswith('@conversion:')
                    and not _spline_conversion(target,new_nodes[role],change,set(new_nodes.values()))):
                raise CharacterRegistryError('Spline 数量变更新增了非所属生成节点：'+role)
        for role in removed_roles:
            if (not change.affects(old_nodes[role]) and not role.startswith('@conversion:')
                    and not _spline_conversion(host,old_nodes[role],change,set(old_nodes.values()))):
                raise CharacterRegistryError('Spline 数量变更删除了非所属生成节点：'+role)
    elif set(old_nodes)-face_retired!=set(new_nodes)-created_names-alignment_added:
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
    from .maya_body_face_rebuild import retained_roots
    retained_children.update(retained_roots(host, original.registration))
    properties={row.path:{a[0] for a in row.attributes} for row in original.properties}
    for role in sorted(set(old_nodes)&set(new_nodes)):
        old,new=old_nodes[role],new_nodes[role]
        a,b=host._cmds,target._cmds
        kind=a.nodeType(old)
        affected=changing and change.affects(old)
        if kind!=b.nodeType(new):raise CharacterRegistryError('新旧 Rig 节点类型不同：'+role)
        if a.referenceQuery(old,isNodeReferenced=True) or any(a.lockNode(old,q=True,lock=True) or []):
            raise CharacterRegistryError('旧 Rig 节点被引用或锁定：'+old)
        extra=set(a.listAttr(old,userDefined=True) or [])-set(b.listAttr(new,userDefined=True) or [])
        if affected and kind in ('parentConstraint','orientConstraint','pointConstraint',
                                 'scaleConstraint','aimConstraint'):
            extra-=set(getattr(a,kind)(old,q=True,weightAliasList=True) or [])
        if extra-properties.get(old,set()):
            raise CharacterRegistryError('旧 Rig 节点有未采集的附加属性：'+old+' '+repr(sorted(extra-properties.get(old,set()))))
        if kind=='unitConversion' and not affected and a.getAttr(old+'.conversionFactor')!=b.getAttr(new+'.conversionFactor'):
            raise CharacterRegistryError('单位转换系数被修改：'+old)
        if kind in ('animCurveUA','animCurveUL','animCurveUT','animCurveUU') and not affected:
            if not _same_curve_state(_driven_curve_state(a,old),_driven_curve_state(b,new)):
                raise CharacterRegistryError('原 Rig 驱动曲线已修改，需要显式驱动曲线迁移：'+old)
        if kind=='nurbsCurve':
            shape_a=a.xform(old+'.cv[*]',q=True,objectSpace=True,t=True) or []
            shape_b=b.xform(new+'.cv[*]',q=True,objectSpace=True,t=True) or []
            editable=(_editable_control_curve(host,old,original.registration)
                      and _editable_control_curve(target,new,reg))
            if not editable and not affected and (len(shape_a)!=len(shape_b)
                    or _curve_topology(host,old)!=_curve_topology(target,new)
                    or any(a.getAttr(old+'.'+attr)!=b.getAttr(new+'.'+attr) for attr in ('degree','form','spans'))):
                raise CharacterRegistryError('控制形状拓扑不同，需要显式形状迁移：'+old)
            if editable:
                curve_geometry.append((role,*_curve_geometry(host,old)))
            settings=_curve_display_settings(a,old)
            # Solver curves receive their CVs from owned graph connections.
            # Their evaluated animation is not an editable control shape.
            driven = any(a.listConnections(old+'.'+attribute,
                                           source=True,destination=False)
                         for attribute in ('create', 'controlPoints'))
            if not affected or editable:
                shapes.append((role,() if driven else tuple(shape_a),tuple(settings),_curve_topology(host,old)))
        if 'dagNode' in (a.nodeType(old,inherited=True) or []):
            children=set(a.listRelatives(old,children=True,fullPath=True) or [])
            if children-set(old_nodes.values())-retained_children:
                raise CharacterRegistryError('旧 Rig 存在未声明保留的子节点：'+old)
        rows.append((role,a.ls(old,uuid=True)[0],b.ls(new,uuid=True)[0],kind))
    old_owned=set(old_nodes.values())
    if changing:
        from .maya_spline_control_rebuild import validate_removed_node
        for role in removed_roles:
            validate_removed_node(host,old_nodes[role],old_owned,original)
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
    from .maya_body_face_rebuild import boundary_edges
    permitted.update(boundary_edges(host,old_edges,original.registration))
    if (any(row.path.rsplit('|',1)[-1]=='AimSystem'
            for row in original.registration.nodes)
            and not any(row.path.rsplit('|',1)[-1]=='AimSystem'
                        for row in reg.nodes)
            and retained_roots(host,original.registration)):
        # EyeBall Fit removes the old Body Aim registration. A new empty
        # AimSystem may still be generated for other Body aim options.
        permitted.update(edge for edge in old_edges if
            edge[0].rsplit('.',1)[0].rsplit('|',1)[-1]=='AimSystem'
            and edge[0].endswith('.message')
            and edge[1].startswith('AdvPy_CharacterRegistry.members['))
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
    if changing:
        aliases={node:role for role,node in old_nodes.items()}
        def old_role_plug(plug):
            node,attribute=plug.split('.',1)
            return aliases.get(node,node)+'.'+attribute
        permitted={(old_role_plug(a),old_role_plug(b)) for a,b in permitted}
    # Bind-pose records belong to retained skin, not to the rig being deleted.
    for skin in original.skins:
        for pose in host._cmds.listConnections(skin.node+'.bindPose',s=True,d=False) or []:
            if host._cmds.nodeType(pose)!='dagPose':raise CharacterRegistryError('蒙皮绑定姿态类型无效')
            permitted.update(connections(host,pose))
    permitted={(source.rsplit('.',1)[0]+'.instObjGroups[0]'
                if source.endswith('.instObjGroups') else source,destination)
               for source,destination in permitted}
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
    # Absolute root-namespace markers are address syntax, not node identity.
    # Scoped reads retain |:Mesh to avoid writing into the replacement namespace;
    # root reads return |Mesh. Compare both spellings without dropping namespaces
    # or any attribute/index, and keep original addresses in the saved ownership.
    def canonical_edge(edge):
        result=[]
        for plug in edge:
            node,attribute=plug.split('.',1)
            node='|'.join(part.removeprefix(':') for part in node.split('|'))
            result.append(node+'.'+attribute)
        return tuple(result)
    old_comparison={canonical_edge(edge) for edge in old_edges}
    new_comparison={canonical_edge(edge) for edge in new_edges}
    extra=old_comparison-new_comparison-{canonical_edge(edge) for edge in permitted}
    missing=new_comparison-old_comparison
    # These declared native edit-mode catalogue links replace deleted Fit
    # templates. Every unrelated new edge still fails the ownership audit.
    missing -= _source_fit_driving_edges(host, original.registration)
    missing -= _source_rp_reverse_ownership_edges(host, original.registration)
    missing -= _source_fk_follower_ownership_edges(host,target,original.registration,reg)
    missing -= {(node+'.message','AdvPy_CharacterRegistry.members[*]')
                for node in alignment_added}
    missing -= {(node+'.instObjGroups[0]','AllSet.dagSetMembers[*]')
                for node in alignment_added}
    missing={edge for edge in missing if not _missing_fit_fat_connection(
        host,edge,original.registration.container)}
    if changing:
        # Only internal edges involving this explicitly regenerated Spline
        # may differ. External user/skin connections still require capture.
        from adv_py.core.character_identity import SHARED_NODES
        def regenerated(edge,owned):
            peers={plug.split('.',1)[0] for plug in edge}
            return (peers<=owned|set(SHARED_NODES)
                    and any(change.affects(node) or node.startswith('@conversion:')
                            for node in peers))
        extra={edge for edge in extra if not regenerated(edge,set(old_nodes))}
        missing={edge for edge in missing if not regenerated(edge,set(new_nodes))}
    extra={edge for edge in extra if not any(
        plug.split('.',1)[0] in face_retired for plug in edge)}
    retained_edges={edge for _,_,_,links in retained_shapes for edge in links}
    extra-=retained_edges
    for edge in tuple(missing):
        members={p.split('.',1)[0] for p in edge}
        if members & created_names and members<=new_owned:
            missing.remove(edge)
    if extra or missing:
        raise CharacterRegistryError('旧 Rig 连接不符合重建边界：'+repr((sorted(extra)[:24],sorted(missing)[:24])))
    result=RebuildOwnership(tuple(rows),old_edges,tuple(shapes),tuple(curve_geometry),
        retained_shapes,created_shapes,
        tuple((role,target._cmds.ls(new_nodes[role],uuid=True)[0],
               target._cmds.nodeType(new_nodes[role])) for role in sorted(added_roles)),
        tuple((role,host._cmds.ls(old_nodes[role],uuid=True)[0],
               host._cmds.nodeType(old_nodes[role])) for role in sorted(removed_roles)))
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
