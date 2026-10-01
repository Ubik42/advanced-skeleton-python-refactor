"""Explicit cross-namespace handoff; original curves and skin nodes survive."""
from dataclasses import replace,fields
from contextlib import contextmanager

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_preservation import validate_rebuild_layout
from .maya_character_preservation import capture_curve,capture_skin,capture_extension


def _by_uuid(c,uuid):
    paths=c.ls(uuid,long=True) or []
    if len(paths)!=1:raise CharacterRegistryError('保留对象 UUID 缺失或歧义：'+uuid)
    return paths[0]


def _curve_name(curve):
    return curve.node.rsplit(':',1)[-1]


def _move_set_member(c,source,destination,new_source,new_destination):
    """Let Maya allocate set storage rather than copying an occupied index."""
    member,attribute=source.split('.',1)
    owner,slot=destination.split('.',1)
    if (c.nodeType(owner)!='objectSet'
            or not slot.startswith(('dnSetMembers[','dagSetMembers['))
            or attribute not in ('message','instObjGroups','instObjGroups[0]')):
        return False
    replacement=new_source.split('.',1)[0]
    new_owner=new_destination.split('.',1)[0]
    if c.nodeType(new_owner)!='objectSet' or not c.sets(member,isMember=owner):
        raise CharacterRegistryError('保留选择集成员在交接前发生变化：'+source)
    c.sets(member,remove=owner)
    c.sets(replacement,addElement=new_owner)
    if not c.sets(replacement,isMember=new_owner):
        raise RuntimeError('选择集成员交接失败：'+new_source)
    return True


def _set_connection_identity(host,edges):
    """Retain each exact member/set relationship, independent of sparse slots."""
    c=host._cmds
    result=[]
    for source,destination in edges:
        node,attribute=destination.split('.',1)
        if (c.nodeType(node)=='objectSet'
                and attribute.startswith(('dnSetMembers[','dagSetMembers['))):
            destination=node+'.'+attribute.split('[',1)[0]+'[*]'
            member,output=source.split('.',1)
            if output=='instObjGroups':source=member+'.instObjGroups[0]'
        result.append((source,destination))
    return tuple(sorted(result))


def _sample_numeric_attribute(c,plug,datatype,frame):
    value=c.getAttr(plug,time=frame)
    if datatype=='matrix':
        if len(value)==1 and isinstance(value[0],(tuple,list)):
            value=value[0]
        if len(value)!=16:
            raise CharacterRegistryError('重建采样矩阵不完整：'+plug)
        return tuple(float(item) for item in value)
    if isinstance(value,(tuple,list)):
        if len(value)==1 and isinstance(value[0],(tuple,list)):
            value=value[0]
        return tuple(float(item) for item in value)
    return (float(value),)


def _refresh_skin_inputs(c,host,skins):
    for skin in skins:
        node=host.scene_address(skin.node)
        c.dgdirty(node+'.matrix')
        for index,*_ in skin.influences:c.getAttr(node+f'.matrix[{index}]')
        c.dgdirty(node)


@contextmanager
def _writable_connection(c,*plugs):
    """Temporarily unlock existing destinations without changing their contract."""
    locked=[plug for plug in dict.fromkeys(plugs) if c.getAttr(plug,lock=True)]
    try:
        for plug in locked:c.setAttr(plug,lock=False)
        yield
    finally:
        for plug in locked:c.setAttr(plug,lock=True)


def preflight(host,staged):
    from maya import cmds as c
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    actual=target.read_character_registration()
    if actual!=staged.registration:raise CharacterRegistryError('暂存登记已变化')
    change=staged.spline_change
    if change is not None and change.systems:
        from adv_py.core.spline_control_rebuild import plan_spline_control_rebuild
        if plan_spline_control_rebuild(staged.original.registration,actual,
                tuple((name,count) for name,_,count in change.systems))!=change:
            raise CharacterRegistryError('Spline 数量变更计划在交接前发生变化')
    else:
        validate_rebuild_layout(staged.original.registration,actual)
    for ch in actual.channels:
        plug=target.scene_address(ch.node+'.'+ch.attribute)
        if c.getAttr(plug,lock=True) or c.connectionInfo(plug,sourceFromDestination=True):
            raise CharacterRegistryError('暂存控制通道必须未连接且可写')
    for curve in staged.original.curves:
        name=target.scene_address(_curve_name(curve))
        if c.objExists(name):raise CharacterRegistryError('暂存动画曲线名称已占用：'+name)
    if len({_curve_name(row) for row in staged.original.curves})!=len(staged.original.curves):
        raise CharacterRegistryError('保留动画曲线迁移到同一命名空间后发生重名')
    registered={n.path for n in staged.original.registration.nodes}
    custom={row.path+'.'+a[0] for row in staged.custom_properties for a in row.attributes}
    animator={channel.node+'.'+channel.attribute for channel in actual.channels}
    if any(c.objExists(target.scene_address(plug)) for plug in custom-animator):
        raise CharacterRegistryError('暂存用户属性名称已被占用')
    if any(row.path in registered for row in staged.original.extensions):
        raise CharacterRegistryError('当前交接的附件应为独立用户节点，不得包含整个已登记 Rig')
    for row in staged.original.extensions:
        for source,destination in row.connections:
            for plug in (source,destination):
                node,attr=plug.split('.',1)
                if node in registered and plug not in custom and not c.objExists(target.scene_address(plug)):
                    raise CharacterRegistryError('附件连接需要尚未迁移的用户属性：'+plug)
    return target


def sample(host,staged,frames,target=False):
    from maya import cmds as c
    from .maya_body import MayaBodyBuildHost
    active=MayaBodyBuildHost(namespace=staged.namespace) if target else host
    reg=staged.registration if target else staged.original.registration
    with host._character_sampling_time() as seek:
        result=[]
        for frame in frames:
            seek(frame)
            pose=active.capture_character_pose(reg)
            _refresh_skin_inputs(c,host,staged.original.skins)
            meshes=tuple((uuid,tuple(c.xform(_by_uuid(c,uuid)+'.vtx[*]',q=True,ws=True,t=True)))
                for skin in staged.original.skins for _,uuid,_ in skin.meshes)
            attachments=tuple((row.uuid,tuple(c.xform(_by_uuid(c,row.uuid),q=True,ws=True,matrix=True)))
                for row in staged.original.extensions if row.matrix is not None)
            for row in staged.original.extensions:
                node=_by_uuid(c,row.uuid)
                for attribute,datatype,*_ in row.attributes:
                    if datatype in ('bool','byte','char','short','long',
                                    'float','double','doubleAngle',
                                    'doubleLinear','enum','time','matrix'):
                        values=_sample_numeric_attribute(c,
                            node+'.'+attribute,datatype,frame)
                        attachments+=((row.uuid+'.'+attribute,values),)
            for row in staged.custom_properties:
                node=active.scene_address(row.path)
                for attribute,datatype,*_ in row.attributes:
                    if datatype in ('bool','byte','char','short','long',
                                    'float','double','doubleAngle',
                                    'doubleLinear','enum','time','matrix'):
                        values=_sample_numeric_attribute(c,
                            node+'.'+attribute,datatype,frame)
                        attachments+=((row.uuid+'.'+attribute,values),)
            for attribute,*_ in staged.geometry_container_state or ():
                plug=active.scene_address('|Group|Geometry.'+attribute)
                values=_sample_numeric_attribute(c,plug,
                    'matrix' if attribute=='offsetParentMatrix' else
                    'double',frame)
                attachments+=(('Geometry.'+attribute,values),)
            result.append((frame,pose.body_frames,pose.space_frames,meshes,attachments))
        return tuple(result)


def transfer(host,staged):
    host._require_transaction()
    from maya import cmds as c
    target=preflight(host,staged)
    old=staged.original
    if staged.ownership is None:
        raise CharacterRegistryError('角色重建缺少完整生成图归属审计')
    change=staged.spline_change
    changing=change is not None and bool(change.systems)
    old_nodes={host.scene_address(n.path):target.scene_address(n.path) for n in old.registration.nodes
               if not changing or c.objExists(target.scene_address(n.path))}
    # The registry records animator-facing controls and Body ancestors. Skin
    # may also use generated Part or volume helpers without user channels.
    # The ownership audit pairs the entire replacement graph by UUID, so all
    # retained external edges must use that complete mapping before deletion.
    audited=set()
    for _role,old_id,new_id,_kind in staged.ownership.nodes:
        source=_by_uuid(c,old_id)
        replacement=_by_uuid(c,new_id)
        audited.add(source)
        known=old_nodes.get(source)
        if known is not None and (c.ls(known,long=True) or [known])[0] != replacement:
            raise CharacterRegistryError('登记节点与完整生成图的替换目标不一致：'+source)
        old_nodes[source]=replacement
    fit=host.scene_address(old.registration.container)
    for node in old.registration.nodes:
        source=host.scene_address(node.path)
        if source!=fit and not source.startswith(fit+'|'):
            paths=c.ls(source,long=True) or []
            removed_ids={uuid for _,uuid,_ in staged.ownership.removed_nodes}
            if len(paths)!=1 or (paths[0] not in audited
                    and not (changing and c.ls(paths[0],uuid=True)[0] in removed_ids)):
                raise CharacterRegistryError('登记节点没有进入完整生成图归属审计：'+source)
    geometry='|Group|Geometry'
    old_nodes[host.scene_address(geometry)]=target.scene_address(geometry)
    # Do not replace the original Fit tree: it remains the editable source.
    old_nodes={p:q for p,q in old_nodes.items() if not (p==host.scene_address(old.registration.container) or p.startswith(host.scene_address(old.registration.container)+'|'))}
    def redirect(plug):
        if changing:
            logical=host._cmds.identity.to_local(plug)
            mapped=change.destination(logical)
            if mapped is None:return None
            if mapped!=logical:return target.scene_address(mapped)
        node,attr=plug.split('.',1)
        return old_nodes.get(node,node)+'.'+attr
    host._transaction_changed=True
    selection=[]
    for item in c.ls(sl=True,long=True) or []:
        node,separator,component=item.partition('.')
        selection.append((c.ls(node,uuid=True)[0],separator+component))
    try:
        from .maya_character_properties import install,lock_and_verify
        install(target,staged.custom_properties,existing_plugs=frozenset(
            channel.node+'.'+channel.attribute for channel in staged.registration.channels))
        from .maya_character_ownership import transfer_shapes
        transfer_shapes(target,staged.ownership,old.selection_sets)
        from .maya_character_selection_preservation import install as install_selection_sets
        install_selection_sets(host,staged)
        # Match the original solver policy before any animation is moved.
        if host._cmds.objExists('AdvPy_SpineIKHandle') and host._cmds.ikHandle('AdvPy_SpineIKHandle',q=True,solver=True)=='AdvPy_SpineRPSolver':
            target._transaction_active=True
            try:target.ensure_precise_body_spine_solver(staged.registration.spine)
            finally:target._transaction_active=False;target._transaction_changed=False
        old_values=dict(old.pose.channels)
        for ch in staged.registration.channels:
            if ch.key in old_values:
                c.setAttr(target.scene_address(ch.node+'.'+ch.attribute),old_values[ch.key])
        for source,target_node in old_nodes.items():
            plug=source+'.lockInfluenceWeights'
            if c.objExists(plug):
                destination=target_node+'.lockInfluenceWeights'
                if not c.objExists(destination):c.addAttr(target_node,longName='lockInfluenceWeights',attributeType='bool')
                if c.connectionInfo(destination,sourceFromDestination=True):
                    raise CharacterRegistryError('替换影响关节锁定状态有外部驱动：'+destination)
                c.setAttr(destination,lock=False)
                c.setAttr(destination,bool(c.getAttr(plug)))
                c.setAttr(destination,lock=bool(c.getAttr(plug,lock=True)))
        for curve in old.curves:
            node=_by_uuid(c,curve.uuid)
            outputs=c.listConnections(node+'.output',s=False,d=True,plugs=True) or []
            for output in outputs:
                path,attr=output.split('.',1)
                destination=(c.ls(path,long=True) or [path])[0]+'.'+attr
                replacement=redirect(destination)
                if replacement is None:
                    c.disconnectAttr(node+'.output',destination)
                    continue
                if destination!=replacement:
                    with _writable_connection(c,destination,replacement):
                        c.disconnectAttr(node+'.output',destination)
                        c.connectAttr(node+'.output',replacement)
            c.rename(node,':'+target.scene_address(_curve_name(curve)).lstrip(':'))
        for skin in old.skins:
            # Rewire all recorded influence and lock-weight edges. Preserve
            # bindPreMatrix storage, weight indices and every deformer object.
            for source,destination in skin.connections:
                a=host.scene_address(source);b=host.scene_address(destination)
                x,y=redirect(a),redirect(b)
                if (a,b)!=(x,y):
                    if not c.isConnected(a,b):raise CharacterRegistryError('蒙皮接线在交接前变化')
                    if _move_set_member(c,a,b,x,y):continue
                    c.disconnectAttr(a,b);c.connectAttr(x,y)
            bindposes=c.listConnections(host.scene_address(skin.node)+'.bindPose',s=True,d=False) or []
            for bindpose in bindposes:
                pairs=c.listConnections(bindpose,s=True,d=False,plugs=True,connections=True) or []
                for dest,source in zip(pairs[::2],pairs[1::2]):
                    node,attr=source.split('.',1);a=(c.ls(node,long=True) or [node])[0]+'.'+attr
                    replacement=redirect(a)
                    if a!=replacement:c.disconnectAttr(source,dest);c.connectAttr(replacement,dest)
        curve_redirect={host.scene_address(row.node):_by_uuid(c,row.uuid) for row in old.curves}
        def live_redirect(plug):
            if changing:
                mapped=change.destination(host._cmds.identity.to_local(plug))
                if mapped is None:return None
                if mapped!=host._cmds.identity.to_local(plug):return target.scene_address(mapped)
            node,attr=plug.split('.',1)
            return curve_redirect.get(node,old_nodes.get(node,node))+'.'+attr
        owned_replacements={_by_uuid(c,old_id):_by_uuid(c,new_id)
            for _,old_id,new_id,_ in (staged.ownership.nodes
                                       if staged.ownership is not None else ())}
        def geometry_source(plug):
            node,attribute=plug.split('.',1)
            paths=c.ls(node,long=True) or []
            if len(paths)==1:
                node=owned_replacements.get(paths[0],paths[0])
            return live_redirect(node+'.'+attribute)
        for converter,upstream,_destinations in staged.deformer_input_conversions:
            a=host.scene_address(upstream)
            b=host.scene_address(converter+'.input')
            x=geometry_source(a)
            if x!=a:
                if not c.isConnected(a,b):
                    raise CharacterRegistryError(
                        '生产变形器单位转换输入在交接前变化：'+converter)
                with _writable_connection(c,b):
                    c.disconnectAttr(a,b)
                    c.connectAttr(x,b)
            if not c.isConnected(x,b):
                raise RuntimeError(
                    '生产变形器单位转换输入没有完整交接：'+converter)
        for deformer in old.deformers:
            for source,destination in deformer.connections:
                a=host.scene_address(source)
                b=host.scene_address(destination)
                x=geometry_source(a)
                y=geometry_source(b)
                if (a,b)==(x,y) or c.isConnected(x,y):
                    continue
                if not c.isConnected(a,b):
                    raise CharacterRegistryError(
                        '生产变形器接线在交接前变化：'+deformer.node)
                if _move_set_member(c,a,b,x,y):continue
                with _writable_connection(c,b,y):
                    c.disconnectAttr(a,b)
                    c.connectAttr(x,y)
        for converter,destinations in staged.deformer_output_conversions:
            a=host.scene_address(converter+'.output')
            for destination in destinations:
                b=host.scene_address(destination)
                y=geometry_source(b)
                if y!=b:
                    if not c.isConnected(a,b):
                        raise CharacterRegistryError(
                            '生产变形器输出单位转换在交接前变化：'+converter)
                    with _writable_connection(c,b,y):
                        c.disconnectAttr(a,b)
                        c.connectAttr(a,y)
                if not c.isConnected(a,y):
                    raise RuntimeError(
                        '生产变形器输出单位转换没有完整交接：'+converter)
        for converter,upstream in staged.geometry_container_conversions:
            a=host.scene_address(upstream)
            b=host.scene_address(converter+'.input')
            x=geometry_source(a)
            if x!=a:
                if not c.isConnected(a,b):
                    raise CharacterRegistryError(
                        'Geometry 单位转换输入在交接前变化：'+converter)
                with _writable_connection(c,b):
                    c.disconnectAttr(a,b)
                    c.connectAttr(x,b)
            if not c.isConnected(x,b):
                raise RuntimeError('Geometry 单位转换输入没有完整交接：'+converter)
        connected_geometry_drivers=[]
        for source,destination in staged.geometry_container_drivers:
            a=host.scene_address(source);b=host.scene_address(destination)
            x=geometry_source(a)
            y=target.scene_address(destination)
            if c.isConnected(x,y):
                connected_geometry_drivers.append((x,y))
                continue
            if not c.isConnected(a,b):
                raise CharacterRegistryError('Geometry 原生驱动在交接前变化：'+destination)
            with _writable_connection(c,b,y):
                c.disconnectAttr(a,b)
                c.connectAttr(x,y)
            connected_geometry_drivers.append((x,y))
        connected_geometry_outputs=[]
        for source,destination in staged.geometry_container_outputs:
            a=host.scene_address(source);b=host.scene_address(destination)
            x=target.scene_address(source)
            y=geometry_source(b)
            if c.isConnected(a,b):
                with _writable_connection(c,b,y):
                    c.disconnectAttr(a,b)
                    if not c.isConnected(x,y):
                        c.connectAttr(x,y)
            elif not c.isConnected(x,y):
                raise CharacterRegistryError(
                    'Geometry 原生输出在交接前变化：'+source)
            connected_geometry_outputs.append((x,y))
        connected_output_conversions=[]
        for converter,destination in staged.geometry_output_conversions:
            a=host.scene_address(converter+'.output')
            b=host.scene_address(destination)
            y=geometry_source(b)
            if y!=b:
                if not c.isConnected(a,b):
                    raise CharacterRegistryError(
                        'Geometry 输出单位转换在交接前变化：'+converter)
                with _writable_connection(c,b,y):
                    c.disconnectAttr(a,b)
                    c.connectAttr(a,y)
            connected_output_conversions.append((a,y))
        for source,destination in sorted({pair for row in (*old.extensions,*staged.custom_properties) for pair in row.connections}):
            if changing:
                from .maya_spline_control_rebuild import original_plug
                source=original_plug(change,source)
                destination=original_plug(change,destination)
            a,b=host.scene_address(source),host.scene_address(destination)
            x,y=live_redirect(a),live_redirect(b)
            if (a,b)!=(x,y) and not c.isConnected(x,y):
                if not c.isConnected(a,b):raise CharacterRegistryError('附件接线在交接前变化')
                if _move_set_member(c,a,b,x,y):continue
                with _writable_connection(c,b,y):
                    c.disconnectAttr(a,b);c.connectAttr(x,y)
        # Retained DAG objects are reparented by UUID, with their local channels
        # intact; descendants follow their retained parent without renaming.
        for row in old.extensions:
            node=_by_uuid(c,row.uuid)
            if row.path.startswith('|Group|Geometry|'):
                # Geometry branches remain on the original container until
                # promotion detaches them as one authored subtree.
                continue
            if row.parent and host.scene_address(row.parent) in old_nodes:
                c.parent(node,old_nodes[host.scene_address(row.parent)],relative=True)
        c.currentTime(c.currentTime(q=True),edit=True,update=True)
        # A static rig has no time-driven transform to invalidate Maya's skin
        # matrix cache after rewiring. Pull the new influence inputs before
        # dirtying the retained deformer; otherwise live geometry can differ
        # from the identical scene evaluated after reopening.
        _refresh_skin_inputs(c,host,old.skins)
        lock_and_verify(target,staged.custom_properties,apply_locks=True)
        from .maya_character_control_state import install as install_control_states
        from .maya_spline_control_rebuild import control_states
        install_control_states(target,control_states(staged))
        if (any(not c.isConnected(x,y) for x,y in connected_geometry_drivers)
                or any(not c.isConnected(x,y)
                       for x,y in connected_geometry_outputs)
                or any(not c.isConnected(x,y)
                       for x,y in connected_output_conversions)
                or {destination for _,destination in
                    target.capture_body_geometry_container_drivers()}
                    != {destination for _,destination in
                        staged.geometry_container_drivers}):
            raise RuntimeError('Geometry 原生驱动没有完整交接')
        target.read_character_registration()
    finally:
        c.select([_by_uuid(c,uuid)+component for uuid,component in selection],replace=True) if selection else c.select(clear=True)
    return target


def verify_retained(host,staged):
    from maya import cmds as c
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    if {destination for _,destination in target.capture_body_geometry_container_drivers()} != {
            destination for _,destination in staged.geometry_container_drivers}:
        raise RuntimeError('暂存 Geometry 原生驱动连接变化')
    old=staged.original
    from .maya_character_control_state import verify as verify_control_states
    from .maya_spline_control_rebuild import control_states
    verify_control_states(target,control_states(staged))
    from .maya_character_selection_preservation import verify as verify_selection_sets
    verify_selection_sets(staged)
    if host.capture_character_deformer_animation_state(
            old.deformers,old.skins)!=staged.deformer_animation_state:
        raise RuntimeError('交接改变了 Skin 或生产变形器的动画关键帧')
    from .maya_character_ownership import verify_shapes
    verify_shapes(target,staged.ownership)
    registered={n.path for n in old.registration.nodes if n.path!=old.registration.container and not n.path.startswith(old.registration.container+'|')}
    if staged.spline_change is not None and staged.spline_change.systems:
        registered.update(n.path for n in staged.registration.nodes)
    if any(row.path=='|Group|Geometry' for row in old.properties):
        registered.add('|Group|Geometry')
    retained={row.path:row.uuid for row in old.extensions}
    retained.update({row.node:row.uuid for row in old.curves})
    ownership_replacements={}
    for role,old_id,new_id,_ in (staged.ownership.nodes
                                  if staged.ownership is not None else ()):
        old_paths=c.ls(old_id,long=True) or []
        if not old_paths and not role.startswith('@'):
            old_paths=[host.scene_address(role)]
        if old_paths:
            ownership_replacements[old_paths[0]]=_by_uuid(c,new_id)
    def physical(plug):
        if not plug:return ''
        if staged.spline_change is not None and staged.spline_change.systems:
            mapped=staged.spline_change.destination(plug)
            if mapped is None:return ''
            if mapped!=plug:return target.scene_address(mapped)
        node,separator,attr=plug.partition('.')
        if node in registered:node=target.scene_address(node)
        elif node in retained:node=_by_uuid(c,retained[node])
        else:
            source=host.scene_address(node)
            node=ownership_replacements.get(source,source)
        return node+separator+attr
    def local(plug):return host._cmds.identity.to_local(physical(plug)) if plug else ''
    for curve in staged.original.curves:
        actual=capture_curve(target,_curve_name(curve))
        expected=replace(curve,node=_curve_name(curve),outputs=tuple(sorted(
            target._cmds.identity.to_local(physical(p)) for p in curve.outputs if physical(p))))
        if actual!=expected:
            raise RuntimeError('交接改变了原生动画曲线数据')
    for skin in staged.original.skins:
        actual=capture_skin(host,skin.node)
        expected=replace(skin,influences=tuple((i,local(source),m,local(pre)) for i,source,m,pre in skin.influences),
            connections=tuple(sorted((local(a),local(b)) for a,b in skin.connections)),
            influence_locks=tuple(sorted((i,local(path+'.lockInfluenceWeights').rsplit('.',1)[0],value,locked)
                for i,path,value,locked in skin.influence_locks)))
        actual=replace(actual,connections=_set_connection_identity(host,actual.connections))
        expected=replace(expected,connections=_set_connection_identity(host,expected.connections))
        if actual!=expected:
            raise RuntimeError('交接改变了原蒙皮数据')
    from .maya_character_preservation import capture_deformers
    captured_deformers=capture_deformers(host,staged.original.skins)
    expected_deformers=tuple(replace(row,
        connections=_set_connection_identity(host,tuple((local(a),local(b)) for a,b in row.connections)))
        for row in staged.original.deformers)
    captured_deformers=tuple(replace(row,connections=_set_connection_identity(host,row.connections))
                            for row in captured_deformers)
    if captured_deformers!=expected_deformers:
        raise RuntimeError('交接改变了生产变形器参数、连接或网格顺序')
    actual_conversions=host.capture_character_deformer_conversions(
        staged.original.deformers)
    expected_conversions=tuple(sorted((converter,local(upstream),
        tuple(sorted(local(destination) for destination in destinations)))
        for converter,upstream,destinations in
        staged.deformer_input_conversions))
    if actual_conversions!=expected_conversions:
        raise RuntimeError('交接改变了生产变形器单位转换输入')
    actual_outputs=host.capture_character_deformer_output_conversions(
        staged.original.deformers)
    expected_outputs=tuple(sorted((converter,
        tuple(sorted(local(destination) for destination in destinations)))
        for converter,destinations in staged.deformer_output_conversions))
    if actual_outputs!=expected_outputs:
        raise RuntimeError('交接改变了生产变形器单位转换输出')
    for row in staged.original.extensions:
        actual=capture_extension(host,_by_uuid(c,row.uuid))
        expected_parent=(row.parent if row.path.startswith('|Group|Geometry|')
                         else local(row.parent) if row.parent else None)
        expected=replace(row,path=local(row.path),parent=expected_parent,
            connections=tuple(sorted((local(a),local(b)) for a,b in row.connections)))
        actual=replace(actual,connections=_set_connection_identity(host,actual.connections))
        expected=replace(expected,connections=_set_connection_identity(host,expected.connections))
        if actual!=expected:
            changed=[field.name for field in fields(row) if getattr(actual,field.name)!=getattr(expected,field.name)]
            changed_attrs=[a[0] for a,b in zip(actual.attributes,expected.attributes) if a!=b]
            raise RuntimeError('交接改变了用户附件属性或局部变换：'+row.path+'；'+str(changed)+'；'+str(changed_attrs))
    from .maya_character_properties import lock_and_verify
    lock_and_verify(target,staged.custom_properties)
    for row in staged.custom_properties:
        actual=capture_extension(target,row.path)
        plugs={row.path+'.'+a[0] for a in row.attributes}
        actual_edges=tuple((a,b) for a,b in actual.connections if a in plugs or b in plugs)
        expected_edges=tuple(sorted((target._cmds.identity.to_local(physical(a)),target._cmds.identity.to_local(physical(b))) for a,b in row.connections))
        actual_edges=_set_connection_identity(target,actual_edges)
        expected_edges=_set_connection_identity(target,expected_edges)
        if staged.spline_change is not None and staged.spline_change.systems:
            animator={channel.node+'.'+channel.attribute for channel in staged.registration.channels}
            def retained_edge(edge):
                source,destination=edge
                return not (source in animator and staged.spline_change.affects(
                    destination.split('.',1)[0]))
            actual_edges=tuple(edge for edge in actual_edges if retained_edge(edge))
            expected_edges=tuple(edge for edge in expected_edges if retained_edge(edge))
        if actual_edges!=expected_edges:
            raise RuntimeError('控制器用户属性连接复检失败：'+row.path
                +' '+repr((set(actual_edges)-set(expected_edges),set(expected_edges)-set(actual_edges))))
