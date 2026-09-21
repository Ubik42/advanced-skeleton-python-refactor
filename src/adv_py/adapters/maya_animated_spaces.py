"""Owned dual-source constraints; stepped proxy offsets preserve switch poses."""
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError, REGISTRY_NAME
from adv_py.core.character_spaces import space_channels, space_mode_channel, space_proxy_path, has_animated_spaces

OWNER = 'adv_py.animated_space.v1'


def reverse_name(spec):
    return f'AdvPy_SpaceReverse_{spec.key}'


def enabled(host, spec):
    channel = space_mode_channel(spec)
    return host._cmds.objExists(channel.node + '.' + channel.attribute)


def _owner(c, node):
    c.addAttr(node, longName='advPySpaceOwner', dataType='string')
    c.setAttr(node+'.advPySpaceOwner', OWNER, type='string', lock=True)


def preflight(host, registration):
    if has_animated_spaces(registration):
        return
    c = host._cmds
    for spec in registration.spaces.spaces:
        if enabled(host, spec) or host.find_name_collisions(reverse_name(spec)):
            raise CharacterRegistryError('动画空间属性或节点名称已占用')
        for index, _ in enumerate(spec.targets):
            for mode in ('body', 'global'):
                if host.find_name_collisions(space_proxy_path(spec,index,mode).rsplit('|',1)[-1]):
                    raise CharacterRegistryError('动画空间偏移节点名称已占用')


def install(host, registration):
    c=host._cmds
    selection=c.ls(selection=True,long=True) or []
    try:
        return _install(host,registration)
    finally:
        c.select(selection,replace=True) if selection else c.select(clear=True)


def _install(host, registration):
    host._require_transaction()
    preflight(host, registration)
    c = host._cmds
    host._transaction_changed = True
    channels = list(registration.channels)
    nodes = list(registration.nodes)
    for spec in registration.spaces.spaces:
        mode = host.capture_control_space_mode(spec)
        matrices = tuple(host._spine_world_frame(p)[0] for p in spec.targets)
        channel = space_mode_channel(spec)
        c.addAttr(channel.node, longName=channel.attribute, attributeType='enum',
                  enumName='body:global', keyable=True)
        c.setAttr(channel.node+'.'+channel.attribute, 0 if mode=='body' else 1)
        reverse = c.createNode('reverse', name=reverse_name(spec), skipSelect=True)
        _owner(c, reverse)
        c.connectAttr(channel.node+'.'+channel.attribute, reverse+'.inputX')
        c.delete(spec.constraint_names)
        for index, (target, name, matrix) in enumerate(zip(spec.targets,spec.constraint_names,matrices)):
            proxies = []
            for source in ('body','global'):
                path = space_proxy_path(spec,index,source)
                c.createNode('transform', name=path.rsplit('|',1)[-1], parent=spec.source(source), skipSelect=True)
                _owner(c,path)
                if not spec.rotation_only:
                    c.xform(path,ws=True,translation=matrix[12:15])
                host._spine_set_world_rotation(path,matrix)
                for attr in ('scaleX','scaleY','scaleZ','shearXY','shearXZ','shearYZ','rotateOrder'):
                    c.setAttr(path+'.'+attr,lock=True)
                if spec.rotation_only:
                    for axis in 'XYZ':c.setAttr(path+'.translate'+axis,lock=True)
                proxies.append(path)
                nodes.append(host._registry_node(path))
            node = host._space_command(spec)(*proxies,target,maintainOffset=False,name=name)[0]
            _owner(c,node)
            weights = host._space_command(spec)(node,q=True,weightAliasList=True)
            c.connectAttr(reverse+'.outputX',node+'.'+weights[0])
            c.connectAttr(channel.node+'.'+channel.attribute,node+'.'+weights[1])
        channels.extend(space_channels(spec))
    result = replace(registration,channels=tuple(channels),nodes=tuple(nodes))
    host.write_character_registration_extension(registration,result)
    return result


def _edge(host, source, destination):
    c=host._cmds
    if not c.isConnected(source,destination):
        raise CharacterRegistryError('动画空间连接变化：'+destination)


def audit_mode(host, spec):
    c=host._cmds
    channel=space_mode_channel(spec)
    plug=channel.node+'.'+channel.attribute
    value=c.getAttr(plug)
    if value not in (0.,1.):
        raise CharacterRegistryError('动画空间只支持 body / global 离散状态')
    reverse=reverse_name(spec)
    if not c.objExists(reverse) or c.nodeType(reverse)!='reverse':
        raise CharacterRegistryError('动画空间权重节点缺失')
    for axis in 'YZ':
        if (c.getAttr(reverse+'.input'+axis)!=0 or c.connectionInfo(reverse+'.input'+axis,sourceFromDestination=True)
                or c.listConnections(reverse+'.output'+axis,s=False,d=True)):
            raise CharacterRegistryError('动画空间权重节点含外部连接')
    _edge(host,plug,reverse+'.inputX')
    command=host._space_command(spec)
    expected_mode_outputs={reverse+'.inputX'}
    expected_reverse_outputs=set()
    def canonical(plug):
        node,attr=plug.split('.',1)
        return host._resolve_connected_node(node)+'.'+attr
    for index,(target,name) in enumerate(zip(spec.targets,spec.constraint_names)):
        proxies=tuple(space_proxy_path(spec,index,m) for m in ('body','global'))
        for node in (reverse,name,*proxies):
            if (not c.objExists(node+'.advPySpaceOwner') or c.getAttr(node+'.advPySpaceOwner')!=OWNER
                    or not c.getAttr(node+'.advPySpaceOwner',lock=True)
                    or c.referenceQuery(node,isNodeReferenced=True) or any(c.lockNode(node,q=True,lock=True) or [])):
                raise CharacterRegistryError('动画空间节点归属或可写状态变化')
        if c.nodeType(name)!=('orientConstraint' if spec.rotation_only else 'parentConstraint'):
            raise CharacterRegistryError('动画空间约束类型变化')
        sources=tuple(host._resolve_connected_node(p) for p in command(name,q=True,targetList=True))
        if sources!=proxies:
            raise CharacterRegistryError('动画空间代理来源变化')
        allowed={*proxies,target,channel.node,host._resolve_connected_node(name),reverse}
        incoming={host._resolve_connected_node(n) for n in c.listConnections(name,s=True,d=False) or []}
        if incoming-allowed:
            raise CharacterRegistryError('动画空间约束含外部输入')
        for proxy,mode in zip(proxies,('body','global')):
            if c.nodeType(proxy)!='transform' or (c.listRelatives(proxy,parent=True,fullPath=True) or [])!=[spec.source(mode)]:
                raise CharacterRegistryError('动画空间代理父级变化')
            if c.listRelatives(proxy,children=True):
                raise CharacterRegistryError('动画空间代理存在外部子节点')
            consumers={host._resolve_connected_node(n) for n in c.listConnections(proxy,s=False,d=True) or []}
            if consumers-{host._resolve_connected_node(name),REGISTRY_NAME}:
                raise CharacterRegistryError('动画空间代理存在外部消费')
            for attr in ('scaleX','scaleY','scaleZ'):
                if c.getAttr(proxy+'.'+attr)!=1 or c.connectionInfo(proxy+'.'+attr,sourceFromDestination=True):
                    raise CharacterRegistryError('动画空间代理缩放变化')
            zero_attributes=('shearXY','shearXZ','shearYZ','rotateOrder')+tuple(
                kind+a for kind in ('rotateAxis','rotatePivot','scalePivot','rotatePivotTranslate','scalePivotTranslate') for a in 'XYZ')
            if spec.rotation_only:zero_attributes+=tuple('translate'+a for a in 'XYZ')
            for attr in zero_attributes:
                if c.getAttr(proxy+'.'+attr)!=0 or c.connectionInfo(proxy+'.'+attr,sourceFromDestination=True):
                    raise CharacterRegistryError('动画空间代理存在未登记变换')
            if (not c.getAttr(proxy+'.inheritsTransform') or c.connectionInfo(proxy+'.inheritsTransform',sourceFromDestination=True)
                    or tuple(c.getAttr(proxy+'.offsetParentMatrix'))!=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
                    or c.connectionInfo(proxy+'.offsetParentMatrix',sourceFromDestination=True)):
                raise CharacterRegistryError('动画空间代理继承矩阵变化')
        weights=command(name,q=True,weightAliasList=True)
        if len(weights)!=2:
            raise CharacterRegistryError('动画空间约束目标数量变化')
        _edge(host,reverse+'.outputX',name+'.'+weights[0]);_edge(host,plug,name+'.'+weights[1])
        expected_mode_outputs.add(name+'.'+weights[1]);expected_reverse_outputs.add(name+'.'+weights[0])
        expected={(target+'.'+a) for a in spec.attributes}
        actual={canonical(p) for p in c.listConnections(name,s=False,d=True,plugs=True) or []
                if host._resolve_connected_node(p.split('.',1)[0])!=host._resolve_connected_node(name)}
        if actual!=expected:
            raise CharacterRegistryError('动画空间约束输出被替换或共享')
        for attr in spec.attributes:
            _edge(host,name+'.constraint'+attr[0].upper()+attr[1:],target+'.'+attr)
        # Both targets use the proxy's exact world transform, without hidden offsets.
        offsets = [f'target[{i}].targetOffset{kind}{axis}' for i in range(2)
                   for kind in ('Translate','Rotate') for axis in 'XYZ'] if not spec.rotation_only else ['offset'+a for a in 'XYZ']
        for attr in offsets:
            if abs(c.getAttr(name+'.'+attr))>1e-9 or c.connectionInfo(name+'.'+attr,sourceFromDestination=True):
                raise CharacterRegistryError('动画空间约束含未登记偏移')
    for source,expected in ((plug,expected_mode_outputs),(reverse+'.outputX',expected_reverse_outputs)):
        actual={canonical(p) for p in c.listConnections(source,s=False,d=True,plugs=True) or []}
        if actual!={canonical(p) for p in expected}:
            raise CharacterRegistryError('动画空间权重存在外部消费')
    return 'body' if value==0 else 'global'


def audit(host, registration):
    expected=tuple(ch for spec in registration.spaces.spaces for ch in space_channels(spec))
    actual=tuple(ch for ch in registration.channels if ch.key.startswith('space.'))
    if not actual:
        if any(enabled(host,s) for s in registration.spaces.spaces):
            raise CharacterRegistryError('动画空间存在但没有登记')
        return
    if actual!=expected:
        raise CharacterRegistryError('动画空间登记通道不完整')
    c=host._cmds
    for ch in expected:
        plug=ch.node+'.'+ch.attribute
        source=c.connectionInfo(plug,sourceFromDestination=True)
        if source and (not host._character_direct_animation(source) or
                       any(t!='step' for t in c.keyTangent(plug,q=True,outTangentType=True) or [])):
            raise CharacterRegistryError('空间状态和偏移只允许原生阶梯动画曲线')


def switch(host, registration, key, mode, frame):
    host._require_transaction()
    spec=registration.spaces.space(key)
    spec.source(mode)
    c=host._cmds
    channels=space_channels(spec)
    selected=tuple(ch for ch in channels if ch.key.endswith('.mode') or f'.{mode}.' in ch.key)
    with host._character_sampling_time(preserve_modified=False) as seek:
        seek(frame-1)
        guard={ch.key:c.getAttr(ch.node+'.'+ch.attribute) for ch in selected}
        seek(frame)
        host.preflight_control_space_switch(spec)
        before=host.capture_character_pose(registration)
        if dict(before.spaces)[key]==mode:
            return before
        matrices=tuple(host._spine_world_frame(p)[0] for p in spec.targets)
        with host._character_static_controls(registration,before):
            for index,matrix in enumerate(matrices):
                path=space_proxy_path(spec,index,mode)
                if not spec.rotation_only:c.xform(path,ws=True,translation=matrix[12:15])
                host._spine_set_world_rotation(path,matrix)
            ch=space_mode_channel(spec)
            c.setAttr(ch.node+'.'+ch.attribute,0 if mode=='body' else 1)
            after=host.capture_character_pose(registration)
        host._transaction_changed=True
        for ch in selected:
            plug=ch.node+'.'+ch.attribute
            # A guard is needed only before the first authored event. Existing
            # step curves already preserve their entire previous interval.
            times=c.keyframe(plug,q=True,timeChange=True) or []
            if not any(t<frame for t in times):
                c.setKeyframe(plug,time=frame-1,value=guard[ch.key],inTangentType='linear',outTangentType='step')
            c.setKeyframe(plug,time=frame,value=dict(after.channels)[ch.key],inTangentType='linear',outTangentType='step')
        seek(frame)
        return after
