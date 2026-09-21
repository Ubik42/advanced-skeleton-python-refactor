"""Explicit cross-namespace handoff; original curves and skin nodes survive."""
from dataclasses import replace,fields

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_preservation import validate_rebuild_layout
from .maya_character_preservation import capture_curve,capture_skin,capture_extension


def _by_uuid(c,uuid):
    paths=c.ls(uuid,long=True) or []
    if len(paths)!=1:raise CharacterRegistryError('保留对象 UUID 缺失或歧义：'+uuid)
    return paths[0]


def _curve_name(curve):
    return curve.node.rsplit(':',1)[-1]


def preflight(host,staged):
    from maya import cmds as c
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    actual=target.read_character_registration()
    if actual!=staged.registration:raise CharacterRegistryError('暂存登记已变化')
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
    if any(row.path in registered for row in staged.original.extensions):
        raise CharacterRegistryError('当前交接的附件应为独立用户节点，不得包含整个已登记 Rig')
    for row in staged.original.extensions:
        for source,destination in row.connections:
            for plug in (source,destination):
                node,attr=plug.split('.',1)
                if node in registered and not c.objExists(target.scene_address(plug)):
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
            meshes=tuple((uuid,tuple(c.xform(_by_uuid(c,uuid)+'.vtx[*]',q=True,ws=True,t=True)))
                for skin in staged.original.skins for _,uuid,_ in skin.meshes)
            attachments=tuple((row.uuid,tuple(c.xform(_by_uuid(c,row.uuid),q=True,ws=True,matrix=True)))
                for row in staged.original.extensions if row.matrix is not None)
            for row in staged.original.extensions:
                node=_by_uuid(c,row.uuid)
                for attribute,datatype,*_ in row.attributes:
                    if datatype in ('bool','byte','short','long','float','double','doubleAngle','doubleLinear','enum','matrix'):
                        value=c.getAttr(node+'.'+attribute,time=frame)
                        values=tuple(value) if isinstance(value,(tuple,list)) else (float(value),)
                        attachments+=((row.uuid+'.'+attribute,values),)
            result.append((frame,pose.body_frames,pose.space_frames,meshes,attachments))
        return tuple(result)


def transfer(host,staged):
    host._require_transaction()
    from maya import cmds as c
    target=preflight(host,staged)
    old=staged.original
    old_nodes={host.scene_address(n.path):target.scene_address(n.path) for n in old.registration.nodes}
    # Do not replace the original Fit tree: it remains the editable source.
    old_nodes={p:q for p,q in old_nodes.items() if not (p==host.scene_address(old.registration.container) or p.startswith(host.scene_address(old.registration.container)+'|'))}
    def redirect(plug):
        node,attr=plug.split('.',1)
        return old_nodes.get(node,node)+'.'+attr
    host._transaction_changed=True
    selection=[]
    for item in c.ls(sl=True,long=True) or []:
        node,separator,component=item.partition('.')
        selection.append((c.ls(node,uuid=True)[0],separator+component))
    try:
        # Match the original solver policy before any animation is moved.
        if host._cmds.ikHandle('AdvPy_SpineIKHandle',q=True,solver=True)=='AdvPy_SpineRPSolver':
            target._transaction_active=True
            try:target.ensure_precise_body_spine_solver(staged.registration.spine)
            finally:target._transaction_active=False;target._transaction_changed=False
        for ch,(_,value) in zip(staged.registration.channels,old.pose.channels):
            c.setAttr(target.scene_address(ch.node+'.'+ch.attribute),value)
        for source,target_node in old_nodes.items():
            plug=source+'.lockInfluenceWeights'
            if c.objExists(plug):
                destination=target_node+'.lockInfluenceWeights'
                if not c.objExists(destination):c.addAttr(target_node,longName='lockInfluenceWeights',attributeType='bool')
                c.setAttr(destination,bool(c.getAttr(plug)))
                c.setAttr(destination,lock=bool(c.getAttr(plug,lock=True)))
        for curve in old.curves:
            node=_by_uuid(c,curve.uuid)
            outputs=c.listConnections(node+'.output',s=False,d=True,plugs=True) or []
            for output in outputs:
                path,attr=output.split('.',1)
                destination=(c.ls(path,long=True) or [path])[0]+'.'+attr
                replacement=redirect(destination)
                if destination!=replacement:
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
                    c.disconnectAttr(a,b);c.connectAttr(x,y)
            bindposes=c.listConnections(host.scene_address(skin.node)+'.bindPose',s=True,d=False) or []
            for bindpose in bindposes:
                pairs=c.listConnections(bindpose,s=True,d=False,plugs=True,connections=True) or []
                for dest,source in zip(pairs[::2],pairs[1::2]):
                    node,attr=source.split('.',1);a=(c.ls(node,long=True) or [node])[0]+'.'+attr
                    replacement=redirect(a)
                    if a!=replacement:c.disconnectAttr(source,dest);c.connectAttr(replacement,dest)
        for source,destination in sorted({pair for row in old.extensions for pair in row.connections}):
            a,b=host.scene_address(source),host.scene_address(destination)
            x,y=redirect(a),redirect(b)
            if (a,b)!=(x,y) and not c.isConnected(x,y):
                if not c.isConnected(a,b):raise CharacterRegistryError('附件接线在交接前变化')
                c.disconnectAttr(a,b);c.connectAttr(x,y)
        # Retained DAG objects are reparented by UUID, with their local channels
        # intact; descendants follow their retained parent without renaming.
        for row in old.extensions:
            node=_by_uuid(c,row.uuid)
            if row.parent and host.scene_address(row.parent) in old_nodes:
                c.parent(node,old_nodes[host.scene_address(row.parent)],relative=True)
        c.currentTime(c.currentTime(q=True),edit=True,update=True)
        target.read_character_registration()
    finally:
        c.select([_by_uuid(c,uuid)+component for uuid,component in selection],replace=True) if selection else c.select(clear=True)
    return target


def verify_retained(host,staged):
    from maya import cmds as c
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    old=staged.original
    registered={n.path for n in old.registration.nodes if n.path!=old.registration.container and not n.path.startswith(old.registration.container+'|')}
    retained={row.path:row.uuid for row in old.extensions}
    retained.update({row.node:row.uuid for row in old.curves})
    def physical(plug):
        if not plug:return ''
        node,separator,attr=plug.partition('.')
        if node in registered:node=target.scene_address(node)
        elif node in retained:node=_by_uuid(c,retained[node])
        else:node=host.scene_address(node)
        return node+separator+attr
    def local(plug):return host._cmds.identity.to_local(physical(plug)) if plug else ''
    for curve in staged.original.curves:
        actual=capture_curve(target,_curve_name(curve))
        expected=replace(curve,node=_curve_name(curve),outputs=tuple(sorted(target._cmds.identity.to_local(physical(p)) for p in curve.outputs)))
        if actual!=expected:
            raise RuntimeError('交接改变了原生动画曲线数据')
    for skin in staged.original.skins:
        actual=capture_skin(host,skin.node)
        expected=replace(skin,influences=tuple((i,local(source),m,local(pre)) for i,source,m,pre in skin.influences),
            connections=tuple(sorted((local(a),local(b)) for a,b in skin.connections)))
        if actual!=expected:
            raise RuntimeError('交接改变了原蒙皮数据')
    for row in staged.original.extensions:
        actual=capture_extension(host,_by_uuid(c,row.uuid))
        expected=replace(row,path=local(row.path),parent=local(row.parent) if row.parent else None,
            connections=tuple(sorted((local(a),local(b)) for a,b in row.connections)))
        if actual!=expected:
            changed=[field.name for field in fields(row) if getattr(actual,field.name)!=getattr(expected,field.name)]
            changed_attrs=[a[0] for a,b in zip(actual.attributes,expected.attributes) if a!=b]
            raise RuntimeError('交接改变了用户附件属性或局部变换：'+row.path+'；'+str(changed)+'；'+str(changed_attrs))
