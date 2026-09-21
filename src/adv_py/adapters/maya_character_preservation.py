"""Capture original curves, sparse skin storage and explicit extension objects."""
from adv_py.core.character_registry import CharacterRegistryError
from dataclasses import replace
from adv_py.core.character_preservation import PreservedCurve, PreservedSkin, PreservedDeformer, PreservedExtension, CharacterPreservation, validate_preservation


def _plug(host,plug):
    if not plug:return ''
    node,attribute=plug.split('.',1)
    return host._resolve_connected_node(node)+'.'+attribute


def connections(host,node):
    c=host._cmds
    result=set()
    for incoming in (True,False):
        pairs=c.listConnections(node,source=incoming,destination=not incoming,plugs=True,connections=True) or []
        for local,other in zip(pairs[::2],pairs[1::2]):
            pair=(_plug(host,other),_plug(host,local)) if incoming else (_plug(host,local),_plug(host,other))
            result.add(pair)
    return tuple(sorted(result))


def capture_curve(host,node):
    c=host._cmds
    def tangent(flag):return tuple(c.keyTangent(node,q=True,**{flag:True}) or [])
    return PreservedCurve(node,c.ls(node,uuid=True)[0],c.nodeType(node),
        _plug(host,c.connectionInfo(node+'.input',sourceFromDestination=True)),
        tuple(sorted(_plug(host,p) for p in c.listConnections(node+'.output',s=False,d=True,plugs=True) or [])),
        tuple(c.keyframe(node,q=True,timeChange=True) or []),tuple(c.keyframe(node,q=True,valueChange=True) or []),
        tangent('inTangentType'),tangent('outTangentType'),tangent('inAngle'),tangent('outAngle'),
        tangent('inWeight'),tangent('outWeight'),tangent('lock'),tangent('weightLock'),
        tuple(c.keyframe(node,q=True,breakdown=True) or []),
        bool(c.getAttr(node+'.weightedTangents')),int(c.getAttr(node+'.preInfinity')),int(c.getAttr(node+'.postInfinity')))


def capture_skin(host,node):
    c=host._cmds
    geometries=[]
    for shape in c.skinCluster(node,q=True,geometry=True) or []:
        path=host._resolve_connected_node(shape)
        if c.nodeType(path)!='mesh':raise CharacterRegistryError('重建保留仅接受 mesh 蒙皮几何')
        geometries.append((path,c.ls(path,uuid=True)[0],int(c.polyEvaluate(path,vertex=True))))
    influences=[]
    for index in c.getAttr(node+'.matrix',multiIndices=True) or []:
        source=_plug(host,c.connectionInfo(node+f'.matrix[{index}]',sourceFromDestination=True))
        if not source:raise CharacterRegistryError('蒙皮影响矩阵缺少来源')
        pre=node+f'.bindPreMatrix[{index}]'
        influences.append((index,source,tuple(c.getAttr(pre)),_plug(host,c.connectionInfo(pre,sourceFromDestination=True))))
    weights=[]
    for vertex in c.getAttr(node+'.weightList',multiIndices=True) or []:
        plug=node+f'.weightList[{vertex}].weights'
        weights.append((vertex,tuple((index,float(c.getAttr(plug+f'[{index}]'))) for index in c.getAttr(plug,multiIndices=True) or [])))
    settings=tuple((attr,float(c.getAttr(node+'.'+attr))) for attr in (
        'envelope','skinningMethod','normalizeWeights','maxInfluences','maintainMaxInfluences',
        'weightDistribution','bindMethod','useComponents','deformUserNormals','dqsSupportNonRigid') if c.objExists(node+'.'+attr))
    blend=tuple((i,float(c.getAttr(node+f'.blendWeights[{i}]'))) for i in c.getAttr(node+'.blendWeights',multiIndices=True) or [])
    return PreservedSkin(node,c.ls(node,uuid=True)[0],tuple(geometries),settings,tuple(influences),tuple(weights),blend,connections(host,node))


def capture_deformer(host,node,mesh_stack):
    c=host._cmds
    kind=c.nodeType(node)
    if kind not in ('blendShape','deltaMush','wrap'):
        raise CharacterRegistryError('未声明的生产变形器类型：'+kind)
    names={'blendShape':('envelope','origin','supportNegativeWeights'),
           'deltaMush':('envelope','smoothingIterations','smoothingStep','pinBorderVertices',
                        'inwardConstraint','outwardConstraint','distanceWeight','displacement'),
           'wrap':('envelope','falloffMode','maxDistance','autoWeightThreshold','weightThreshold',
                   'exclusiveBind','smoothness')}
    settings=[]
    def numeric(value):
        if isinstance(value,list) and len(value)==1 and isinstance(value[0],tuple):
            value=value[0]
        if isinstance(value,(int,float)) and not isinstance(value,bool):return float(value)
        if isinstance(value,bool):return float(value)
        if isinstance(value,(tuple,list)) and all(isinstance(item,(int,float)) for item in value):
            return tuple(float(item) for item in value)
        raise CharacterRegistryError('生产变形器参数类型不受支持：'+node)
    for name in names[kind]:
        if c.objExists(node+'.'+name):
            settings.append((name,numeric(c.getAttr(node+'.'+name))))
    if kind=='blendShape':
        for index in c.getAttr(node+'.weight',multiIndices=True) or []:
            settings.append((f'weight[{index}]',float(c.getAttr(node+f'.weight[{index}]'))))
    aliases=tuple(c.aliasAttr(node,query=True) or [])
    return PreservedDeformer(host._resolve_connected_node(node),c.ls(node,uuid=True)[0],kind,
                             tuple(sorted(mesh_stack)),tuple(settings),aliases,connections(host,node))


def capture_deformers(host,skins):
    c=host._cmds
    stacks={}
    for skin in skins:
        for shape,_,_ in skin.meshes:
            history=c.listHistory(host.scene_address(shape),pruneDagObjects=True) or []
            for index,node in enumerate(history):
                if c.nodeType(node) in ('blendShape','deltaMush','wrap'):
                    path=host._resolve_connected_node(node)
                    stacks.setdefault(path,[]).append((shape,index))
    return tuple(capture_deformer(host,node,stacks[node]) for node in sorted(stacks))


def capture_extension(host,node):
    c=host._cmds
    resolved=c.ls(node,long=True) or []
    if len(resolved)!=1:raise CharacterRegistryError('用户扩展节点缺失或歧义：'+node)
    node=resolved[0]
    if c.referenceQuery(node,isNodeReferenced=True):raise CharacterRegistryError('用户扩展节点不能是引用')
    kind=c.nodeType(node)
    attributes=[]
    for attr in sorted(c.listAttr(node,userDefined=True) or []):
        if c.attributeQuery(attr,node=node,listChildren=True):continue
        plug=node+'.'+attr;datatype=c.getAttr(plug,type=True)
        if c.attributeQuery(attr,node=node,multi=True):
            raise CharacterRegistryError('用户扩展数组需要专用保留协议：'+plug)
        if datatype=='message':value=None
        elif datatype in ('string','bool','byte','short','long','float','double','doubleAngle','doubleLinear','enum','matrix'):
            # Request the explicit time context: after sampling other frames,
            # Maya can leave non-transform custom attributes with a stale cache.
            value=c.getAttr(plug,time=c.currentTime(q=True))
            if isinstance(value,list):value=tuple(value)
        else:raise CharacterRegistryError('用户扩展属性类型尚无保留协议：'+plug+' '+datatype)
        metadata=[]
        for exists,flag in (('minExists','minimum'),('maxExists','maximum'),('softMinExists','softMin'),('softMaxExists','softMax')):
            if c.attributeQuery(attr,node=node,**{exists:True}):
                metadata.append((flag,tuple(c.attributeQuery(attr,node=node,**{flag:True}))))
        if datatype=='enum':metadata.append(('enum',tuple(c.attributeQuery(attr,node=node,listEnum=True) or [])))
        if datatype not in ('string','matrix','message'):
            metadata.append(('default',tuple(c.attributeQuery(attr,node=node,listDefault=True) or [])))
        metadata.append(('parent',tuple(c.attributeQuery(attr,node=node,listParent=True) or [])))
        metadata.append(('niceName',c.attributeQuery(attr,node=node,niceName=True)))
        metadata.append(('channelBox',bool(c.getAttr(plug,channelBox=True))))
        attributes.append((attr,datatype,value,bool(c.getAttr(plug,lock=True)),bool(c.getAttr(plug,keyable=True)),tuple(metadata)))
    parent=(c.listRelatives(node,parent=True,fullPath=True) or [None])[0] if 'dagNode' in (c.nodeType(node,inherited=True) or []) else None
    matrix=tuple(c.xform(node,q=True,matrix=True,objectSpace=True)) if kind in ('transform','joint') else None
    return PreservedExtension(node,c.ls(node,uuid=True)[0],kind,parent,matrix,tuple(attributes),connections(host,node))


def capture(host,registration,extensions):
    c=host._cmds
    curves=set()
    for channel in registration.channels:
        source=c.connectionInfo(channel.node+'.'+channel.attribute,sourceFromDestination=True)
        if source:curves.add(source.rsplit('.',1)[0])
    members={row.path for row in registration.nodes}
    skins=[]
    for node in c.ls(type='skinCluster') or []:
        influences={host._resolve_connected_node(p) for p in c.skinCluster(node,q=True,influence=True) or []}
        if influences & members:
            skins.append(capture_skin(host,node))
    extension_paths=set()
    for node in extensions:
        resolved=c.ls(node,long=True) or []
        if len(resolved)!=1:raise CharacterRegistryError('用户扩展根缺失或歧义：'+node)
        node=resolved[0];extension_paths.add(node)
        if 'dagNode' in (c.nodeType(node,inherited=True) or []):
            extension_paths.update(c.listRelatives(node,allDescendents=True,fullPath=True) or [])
    extension_rows=tuple(capture_extension(host,node) for node in sorted(extension_paths))
    properties=[]
    for member in registration.nodes:
        if member.path==registration.container or member.path.startswith(registration.container+'|'):continue
        if not c.listAttr(member.path,userDefined=True):continue
        row=capture_extension(host,member.path)
        plugs={row.path+'.'+a[0] for a in row.attributes}
        properties.append(replace(row,parent=None,matrix=None,connections=tuple((a,b) for a,b in row.connections if a in plugs or b in plugs)))
    property_plugs={row.path+'.'+a[0] for row in properties for a in row.attributes}
    for row in (*extension_rows,*properties):
        for source,target in row.connections:
            node=source.rsplit('.',1)[0]
            if c.nodeType(node).startswith('animCurve'):
                if not host._character_direct_animation(source):
                    # Maya's ordinary setKeyframe may create a root-namespace
                    # curve for a namespaced user attachment. Adopt only a
                    # native time curve whose entire output boundary belongs
                    # to these explicitly retained extension objects.
                    physical=host.scene_address(node).lstrip(':')
                    driver=c.connectionInfo(node+'.input',sourceFromDestination=True)
                    outputs=c.listConnections(node+'.output',s=False,d=True,plugs=True) or []
                    native=c.nodeType(node) in ('animCurveTA','animCurveTL','animCurveTU')
                    timed=not driver or (driver.rsplit('.',1)[1]=='outTime' and c.nodeType(driver.rsplit('.',1)[0])=='time')
                    owned_outputs=outputs and all(host._resolve_connected_node(p.split('.',1)[0]) in extension_paths or _plug(host,p) in property_plugs for p in outputs)
                    if (':' in physical or not native or not timed or not owned_outputs or c.referenceQuery(node,isNodeReferenced=True)
                            or any(c.lockNode(node,q=True,lock=True) or [])):
                        raise CharacterRegistryError('用户扩展动画没有独占的原生时间曲线保留边界：'+source)
                curves.add(node)
    return validate_preservation(CharacterPreservation(registration,host.capture_character_pose(registration),
        float(c.currentTime(q=True)),host.character_time_unit(),host.namespace,tuple(capture_curve(host,node) for node in sorted(curves)),
        tuple(skins),extension_rows,tuple(properties),capture_deformers(host,skins)))
