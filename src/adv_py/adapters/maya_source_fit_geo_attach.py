"""MEL 84863–84939 surface attachment, including native parent constraints."""
from .maya_body_fit_geo_attach import _matrix

def _align(c,node,target):
    parents=c.listRelatives(node,parent=True,fullPath=True) or []
    aligned=c.parent(node,target)[0]
    c.xform(aligned,objectSpace=True,translation=(0,0,0),rotation=(0,0,0))
    if parents:c.parent(aligned,parents[0])
    else:c.parent(aligned,world=True)

def create(host,spec,state):
    from maya import mel
    c=host._cmds;raw=getattr(c,'raw',c)
    plug=spec.fk_offset+'.offsetParentMatrix'
    if (c.connectionInfo(plug,sourceFromDestination=True) or None)!=state.opm_source:
        raise ValueError('GeoAttach 原矩阵来源变化')
    if bool(c.getAttr(spec.fk_offset+'.inheritsTransform'))!=state.inherits_transform:
        raise ValueError('GeoAttach 原变换继承状态变化')
    host._transaction_changed=True
    if c.objExists('closestSampler'):c.delete('closestSampler')
    sampler=c.createNode('closestPointOnMesh',name='closestSampler')
    try:
        raw.connectAttr(state.mesh_shape+'.outMesh',host.scene_address(sampler+'.inMesh'),force=True)
        position=state.source_position
        c.setAttr(sampler+'.inPosition',position[0]*spec.source_sign,position[1],position[2],type='double3')
        face=int(c.getAttr(sampler+'.closestFaceIndex'))
    finally:c.delete(sampler)
    attached=c.createNode('transform',name=spec.attached_matrix)
    surface=c.createNode('transform',name=spec.surface)
    detached=c.createNode('transform',name=spec.static_matrix)
    offset=c.createNode('transform',name=spec.blend_matrix)
    _align(c,offset,spec.fk_offset)
    mesh=raw.listRelatives(state.mesh_shape,parent=True,fullPath=True)[0]
    before=set(raw.ls(type='pointOnPolyConstraint') or [])
    raw.select(mesh+'.f['+str(face)+']',host.scene_address(surface),replace=True)
    mel.eval('doCreatePointOnPolyConstraintArgList 1 { "0","0","0","1","","1" };')
    created=set(raw.ls(type='pointOnPolyConstraint') or [])-before
    if len(created)!=1:raise RuntimeError('GeoAttach 原生面约束不唯一')
    poly=raw.rename(created.pop(),host.scene_address(spec.constraint))
    channels=('Rotate',) if spec.mode=='point' else ('Translate',) if spec.mode=='orient' else ()
    for channel in channels:
        for axis in 'XYZ':
            c.disconnectAttr(poly+'.constraint'+channel+axis,surface+'.'+channel.lower()+axis)
    _align(c,attached,surface);_align(c,detached,surface)
    c.parent(attached,surface,detached,spec.offset_parent)
    c.parent(offset,attached)
    moved=c.parent(spec.fk_offset,offset)[0]
    # Preserve the source absolute-parent local values and registered paths.
    c.parent(moved,spec.offset_parent,relative=True)
    constraint=spec.attached_matrix+'_parentConstraint1'
    c.parentConstraint(surface,detached,attached,name=constraint)
    aliases=c.parentConstraint(constraint,query=True,weightAliasList=True)
    c.addAttr(spec.fk_control,longName='attach',attributeType='double',minValue=0,maxValue=10,defaultValue=10,keyable=True)
    ramp=c.createNode('setRange',name=spec.weight_node)
    for axis,low,high in (('X',0,1),('Y',1,0)):
        for attr,value in (('min',low),('max',high),('oldMin',0),('oldMax',10)):c.setAttr(ramp+'.'+attr+axis,value)
        c.connectAttr(spec.fk_control+'.attach',ramp+'.value'+axis)
    for axis,alias in zip('XY',aliases):c.connectAttr(ramp+'.outValue'+axis,constraint+'.'+alias)
    bridge=c.createNode('multMatrix',name=spec.output_matrix)
    if state.opm_source:
        c.connectAttr(state.opm_source,bridge+'.matrixIn[0]');c.disconnectAttr(state.opm_source,plug)
    else:c.setAttr(bridge+'.matrixIn[0]',*state.opm_value,type='matrix')
    # A literal Maya parent has no effect when the receiver ignores its parent.
    if state.inherits_transform:
        c.connectAttr(offset+'.matrix',bridge+'.matrixIn[1]')
        c.connectAttr(attached+'.matrix',bridge+'.matrixIn[2]')
    c.connectAttr(bridge+'.matrixSum',plug)

def capture(host,spec,state):
    c=host._cmds
    constraint=spec.attached_matrix+'_parentConstraint1'
    types=((spec.surface,'transform'),(spec.static_matrix,'transform'),(spec.attached_matrix,'transform'),(spec.blend_matrix,'transform'),(spec.constraint,'pointOnPolyConstraint'),(constraint,'parentConstraint'),(spec.weight_node,'setRange'),(spec.output_matrix,'multMatrix'))
    if any(not c.objExists(n) or c.nodeType(n)!=t for n,t in types):return False
    aliases=c.parentConstraint(constraint,query=True,weightAliasList=True) or []
    if len(aliases)!=2:return False
    if bool(c.getAttr(spec.fk_offset+'.inheritsTransform'))!=state.inherits_transform:return False
    links=[(spec.output_matrix+'.matrixSum',spec.fk_offset+'.offsetParentMatrix')]
    if state.inherits_transform:
        links.extend(((spec.blend_matrix+'.matrix',spec.output_matrix+'.matrixIn[1]'),(spec.attached_matrix+'.matrix',spec.output_matrix+'.matrixIn[2]')))
    elif any(c.connectionInfo(spec.output_matrix+'.matrixIn['+str(i)+']',sourceFromDestination=True) for i in (1,2)):
        return False
    for axis,alias in zip('XY',aliases):
        links.extend(((spec.fk_control+'.attach',spec.weight_node+'.value'+axis),(spec.weight_node+'.outValue'+axis,constraint+'.'+alias)))
        low,high=(0,1) if axis=='X' else (1,0)
        for attr,value in (('min',low),('max',high),('oldMin',0),('oldMax',10)):
            if abs(c.getAttr(spec.weight_node+'.'+attr+axis)-value)>1e-8:return False
    if state.opm_source:links.append((state.opm_source,spec.output_matrix+'.matrixIn[0]'))
    elif _matrix(c.getAttr(spec.output_matrix+'.matrixIn[0]'))!=state.opm_value:return False
    for channel,enabled in (('Translate',spec.mode!='orient'),('Rotate',spec.mode!='point')):
        for axis in 'XYZ':
            if bool(c.isConnected(spec.constraint+'.constraint'+channel+axis,spec.surface+'.'+channel.lower()+axis,ignoreUnitConversion=True))!=enabled:return False
    return all(c.isConnected(a,b,ignoreUnitConversion=True) for a,b in links)
