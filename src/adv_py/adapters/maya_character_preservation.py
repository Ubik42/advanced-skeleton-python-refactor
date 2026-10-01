"""Capture original curves, sparse skin storage and explicit extension objects."""
from math import isfinite

from adv_py.core.character_registry import CharacterRegistryError
from dataclasses import replace
from adv_py.core.character_preservation import PreservedCurve, PreservedSkin, PreservedDeformer, PreservedExtension, PreservedControlState, CharacterPreservation, validate_preservation


def capture_control_states(host,registration):
    """Original Keep Lock/Hide and enabled transform limits (78208–78249)."""
    c=host._cmds
    controls={channel.node for channel in registration.channels}
    if c.objExists('ControlSet'):
        for member in c.sets('ControlSet',q=True) or []:
            if '.' in member:continue
            paths=c.ls(member,long=True) or []
            if len(paths)==1 and paths[0] in {n.path for n in registration.nodes}:
                controls.add(paths[0])
    joints={node.path for node in registration.nodes if node.node_type=='joint'
            and node.path!=registration.container
            and not node.path.startswith(registration.container+'|')}
    rows=[]
    for node in sorted(controls|joints):
        channels=()
        if node in controls:
            channels=tuple((attr,bool(c.getAttr(node+'.'+attr,lock=True)),
                            bool(c.getAttr(node+'.'+attr,keyable=True)),
                            bool(c.getAttr(node+'.'+attr,channelBox=True)))
                           for kind in ('translate','rotate','scale') for axis in 'XYZ'
                           for attr in (kind+axis,) if c.objExists(node+'.'+attr))
        limits=[]
        for kind in 'trs':
            for axis in 'xyz':
                flag=kind+axis
                enabled=tuple(bool(value) for value in c.transformLimits(node,q=True,**{'e'+flag:True}))
                if any(enabled):
                    values=tuple(float(value) for value in c.transformLimits(node,q=True,**{flag:True}))
                    limits.append((flag,values,enabled))
        if channels or limits:
            rows.append(PreservedControlState(node,c.ls(node,uuid=True)[0],channels,tuple(limits)))
    return tuple(rows)


def _added_control_roots(host,registration):
    """MEL keeps added ControlSet/DeformSet members outside AllSet."""
    c=host._cmds
    generated={row.path for row in registration.nodes}
    roots=set()
    members={member for name in ('ControlSet','DeformSet') if c.objExists(name)
             for member in c.sets(name,q=True) or []}
    for member in sorted(members):
        if '.' in member:continue
        paths=c.ls(member,long=True) or []
        if len(paths)!=1:
            raise CharacterRegistryError('新增控制器或变形关节身份不唯一：'+member)
        node=paths[0]
        if (node in generated or node==registration.container
                or node.startswith(registration.container+'|')):
            continue
        if c.objExists('AllSet') and c.sets(node,isMember='AllSet'):
            continue
        if c.nodeType(node) not in ('transform','joint'):
            raise CharacterRegistryError('新增控制器或变形关节需要独立的变换节点：'+node)
        roots.add(node)
    # A custom controller's complete subtree survives once; nested controls
    # keep their own membership without capturing the same native object twice.
    return tuple(sorted(node for node in roots
                        if not any(node.startswith(parent+'|')
                                   for parent in roots if parent!=node)))


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
    from maya.api import OpenMaya as om
    from maya.api import OpenMayaAnim as oma

    c=host._cmds
    geometries=[]
    for shape in c.skinCluster(node,q=True,geometry=True) or []:
        path=host._resolve_connected_node(shape)
        if c.nodeType(path)!='mesh':raise CharacterRegistryError('重建保留仅接受 mesh 蒙皮几何')
        geometries.append((path,c.ls(path,uuid=True)[0],int(c.polyEvaluate(path,vertex=True))))
    selection=om.MSelectionList()
    selection.add(host.scene_address(node))
    skin_fn=oma.MFnSkinCluster(selection.getDependNode(0))
    component_memberships=[]
    for shape,_,count in geometries:
        scene_shape=host.scene_address(shape)
        parents=c.listRelatives(scene_shape,parent=True,fullPath=True) or []
        if len(parents)!=1:
            raise CharacterRegistryError('蒙皮网格父级不唯一：'+shape)
        members=host._skin_vertex_members(skin_fn,scene_shape,parents[0],count)
        component_memberships.append((shape,None if len(members)==count else members))
    influences=[]
    for index in c.getAttr(node+'.matrix',multiIndices=True) or []:
        source=_plug(host,c.connectionInfo(node+f'.matrix[{index}]',sourceFromDestination=True))
        if not source:raise CharacterRegistryError('蒙皮影响矩阵缺少来源')
        pre=node+f'.bindPreMatrix[{index}]'
        matrix=c.getAttr(pre)
        if len(matrix)==1 and isinstance(matrix[0],(tuple,list)):
            matrix=matrix[0]
        matrix=tuple(float(value) for value in matrix)
        if len(matrix)!=16:
            raise CharacterRegistryError('蒙皮绑定逆矩阵不完整：'+pre)
        influences.append((index,source,matrix,
            _plug(host,c.connectionInfo(pre,sourceFromDestination=True))))
    influence_locks=[]
    for dag in skin_fn.influenceObjects():
        index=int(skin_fn.indexForInfluenceObject(dag))
        path=host._resolve_connected_node(dag.fullPathName())
        plug=path+'.lockInfluenceWeights'
        if c.objExists(plug):
            influence_locks.append((index,path,bool(c.getAttr(plug)),
                                    bool(c.getAttr(plug,lock=True))))
    weights=[]
    for vertex in c.getAttr(node+'.weightList',multiIndices=True) or []:
        plug=node+f'.weightList[{vertex}].weights'
        weights.append((vertex,tuple((index,float(c.getAttr(plug+f'[{index}]'))) for index in c.getAttr(plug,multiIndices=True) or [])))
    settings=tuple((attr,float(c.getAttr(node+'.'+attr))) for attr in (
        'envelope','skinningMethod','normalizeWeights','maxInfluences','maintainMaxInfluences',
        'weightDistribution','bindMethod','useComponents','deformUserNormals','dqsSupportNonRigid') if c.objExists(node+'.'+attr))
    blend=tuple((i,float(c.getAttr(node+f'.blendWeights[{i}]'))) for i in c.getAttr(node+'.blendWeights',multiIndices=True) or [])
    return PreservedSkin(node,c.ls(node,uuid=True)[0],tuple(geometries),settings,tuple(influences),tuple(weights),blend,connections(host,node),tuple(component_memberships),tuple(sorted(influence_locks)))


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
        children=tuple(c.attributeQuery(attr,node=node,listChildren=True) or ())
        plug=node+'.'+attr
        datatype=(c.attributeQuery(attr,node=node,attributeType=True)
                  if children else c.getAttr(plug,type=True))
        if children and datatype=='TdataCompound':
            datatype='compound'
        if c.attributeQuery(attr,node=node,multi=True):
            raise CharacterRegistryError('用户扩展数组需要专用保留协议：'+plug)
        if children:
            if datatype not in ('double2','double3','float2','float3',
                                'long2','long3','short2','short3',
                                'compound'):
                raise CharacterRegistryError(
                    '用户扩展复合属性类型尚无保留协议：'+plug+' '+datatype)
            value=None  # The child values are captured independently.
        elif datatype=='message':value=None
        elif datatype in ('string','bool','byte','char','short','long',
                          'float','double','doubleAngle','doubleLinear',
                          'enum','time','matrix'):
            # Request the explicit time context: after sampling other frames,
            # Maya can leave non-transform custom attributes with a stale cache.
            value=c.getAttr(plug,time=c.currentTime(q=True))
            if datatype=='matrix':
                if len(value)==1 and isinstance(value[0],(tuple,list)):
                    value=value[0]
                value=tuple(float(item) for item in value)
                if len(value)!=16 or not all(isfinite(item)
                                             for item in value):
                    raise CharacterRegistryError(
                        '用户扩展矩阵值不完整：'+plug)
            elif isinstance(value,list):value=tuple(value)
        else:raise CharacterRegistryError('用户扩展属性类型尚无保留协议：'+plug+' '+datatype)
        metadata=[]
        for exists,flag in (('minExists','minimum'),('maxExists','maximum'),('softMinExists','softMin'),('softMaxExists','softMax')):
            if c.attributeQuery(attr,node=node,**{exists:True}):
                metadata.append((flag,tuple(c.attributeQuery(attr,node=node,**{flag:True}))))
        if datatype=='enum':metadata.append(('enum',tuple(c.attributeQuery(attr,node=node,listEnum=True) or [])))
        if datatype not in ('string','matrix','message') and not children:
            metadata.append(('default',tuple(c.attributeQuery(attr,node=node,listDefault=True) or [])))
        metadata.append(('parent',tuple(c.attributeQuery(attr,node=node,listParent=True) or [])))
        if children:metadata.append(('children',children))
        metadata.append(('niceName',c.attributeQuery(attr,node=node,niceName=True)))
        metadata.append(('channelBox',bool(c.getAttr(plug,channelBox=True))))
        attributes.append((attr,datatype,value,bool(c.getAttr(plug,lock=True)),bool(c.getAttr(plug,keyable=True)),tuple(metadata)))
    captured={item[0] for item in attributes}
    for name,_,_,_,_,metadata in attributes:
        children=tuple(dict(metadata).get('children') or ())
        if children and not set(children)<=captured:
            raise CharacterRegistryError(
                '用户扩展复合属性子级未完整捕获：'+node+'.'+name)
    parent=(c.listRelatives(node,parent=True,fullPath=True) or [None])[0] if 'dagNode' in (c.nodeType(node,inherited=True) or []) else None
    matrix=tuple(c.xform(node,q=True,matrix=True,objectSpace=True)) if kind in ('transform','joint') else None
    return PreservedExtension(node,c.ls(node,uuid=True)[0],kind,parent,matrix,tuple(attributes),connections(host,node))


def capture(host,registration,extensions):
    from adv_py.core.character_generated_attributes import GENERATED_CHARACTER_ATTRIBUTES
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
    for node in (*extensions,*_added_control_roots(host,registration)):
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
        # Internal graph manifests contain evaluated bind constants and physical
        # namespace paths. They are not user properties to copy over a newly
        # built, independently audited rig.
        row=replace(row,attributes=tuple(attribute for attribute in row.attributes
            if attribute[0] not in GENERATED_CHARACTER_ATTRIBUTES))
        if not row.attributes:continue
        plugs={row.path+'.'+a[0] for a in row.attributes}
        properties.append(replace(row,parent=None,matrix=None,connections=tuple((a,b) for a,b in row.connections if a in plugs or b in plugs)))
    # MEL retains Geometry itself on rebuild. The Python replacement creates a
    # new container, so its authored attributes must join the property handoff.
    geometry='|Group|Geometry'
    if (geometry not in members and c.objExists(geometry)
            and c.listAttr(geometry,userDefined=True)):
        row=capture_extension(host,geometry)
        plugs={row.path+'.'+a[0] for a in row.attributes}
        properties.append(replace(row,parent=None,matrix=None,
            connections=tuple((a,b) for a,b in row.connections
                              if a in plugs or b in plugs)))
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
    from .maya_character_selection_preservation import capture as capture_selection_sets
    return validate_preservation(CharacterPreservation(registration,host.capture_character_pose(registration),
        float(c.currentTime(q=True)),host.character_time_unit(),host.namespace,tuple(capture_curve(host,node) for node in sorted(curves)),
        tuple(skins),extension_rows,tuple(properties),capture_deformers(host,skins),
        capture_control_states(host,registration),capture_selection_sets(host,registration)))
