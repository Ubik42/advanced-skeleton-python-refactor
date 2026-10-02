"""Native projected scan curves, handles and pivots; MEL 53534–53784."""
from adv_py.core.fit_auto_place import FitProjectionBounds,choose_fit_projected_curve


def _box(c,node):
    return tuple(c.getAttr(node+'.boundingBoxMin')[0]),tuple(c.getAttr(node+'.boundingBoxMax')[0])


def projected_curve(host,group,find):
    c=host._cmds
    hidden=not c.getAttr(group+'.visibility')
    if hidden:c.setAttr(group+'.visibility',True)
    try:minimum,maximum=_box(c,group)
    finally:
        if hidden:c.setAttr(group+'.visibility',False)
    rows=tuple(FitProjectionBounds(node,*_box(c,node),int(c.getAttr(node+'.spans')))
               for node in c.listRelatives(group,children=True,type='transform') or [])
    position=tuple(c.xform(find[len('closestTo'):],query=True,worldSpace=True,translation=True)) if find.startswith('closestTo') else None
    return choose_fit_projected_curve(rows,minimum,maximum,find,closest_position=position)


def width_min(host,curve):
    c=host._cmds
    if c.objExists('tempWidthMessure'):c.delete('tempWidthMessure')
    root=c.createNode('transform',name='tempWidthMessure',skipSelect=True)
    child=c.createNode('transform',name='tempWidthMessure2',parent=root,skipSelect=True)
    try:
        minimum,maximum=_box(c,curve)
        c.xform(root,worldSpace=True,translation=tuple((a+b)/2. for a,b in zip(minimum,maximum)))
        c.geometryConstraint(curve,child,weight=1.)
        return sum(value*value for value in c.getAttr(child+'.translate')[0])**.5*2.
    finally:c.delete(root)


def lock_trs(c,node,translate=True,rotate=True,scale=True,visibility=False):
    for channel,locked in (('translate',translate),('rotate',rotate),('scale',scale)):
        for axis in 'XYZ':c.setAttr(node+'.'+channel+axis,lock=locked,keyable=not locked)
    c.setAttr(node+'.visibility',lock=visibility,keyable=not visibility)


def save_projection(host,name,axis,skin,find,keep_history):
    host._require_transaction();host._transaction_changed=True;c=host._cmds
    direction=(0,0,1) if axis.startswith('z') else (1,0,0) if axis=='x' else (0,1,0)
    scan='asFitScanCurve'+name;handle='asFitHandle'+name;projection='asFitProjection'+name
    c.duplicate('asFitScanCurve',name=scan)
    if axis.startswith('z'):
        direction=(1,0,0)
        position=c.xform('asFitScanCurve',query=True,worldSpace=True,translation=True)
        c.setAttr(scan+'.translate',c.getAttr('AutoPlacing.bbMinX'),position[1],
                  (c.getAttr('AutoPlacing.bbMinZ')+c.getAttr('AutoPlacing.bbMaxZ'))/2.,type='double3')
        c.setAttr(scan+'.rotateY',-90.)
        axis='x'
    c.setAttr(scan+'.visibility',False)
    shape=(c.listRelatives(scan,shapes=True,type='nurbsCurve') or [None])[0]
    c.setAttr(shape+'.dispGeometry',True)
    result=c.polyProjectCurve(scan,skin,constructionHistory=True,direction=direction,
                              pointsOnEdges=False,curveSamples=50,automatic=False)
    c.rename(result[0],projection);c.rename(result[1],'polyProjectCurve'+name)
    c.parent(projection,'asFitProjections',absolute=True)
    position=c.xform(scan,query=True,worldSpace=True,translation=True)
    c.curve(name=handle,degree=1,point=((0,0,0),(0,0,0)),knot=(0,1))
    c.parent(handle,'asFitHandles',absolute=True)
    c.setAttr(handle+'.overrideEnabled',True);c.setAttr(handle+'.overrideColor',14)
    c.addAttr(handle,longName='xyz',attributeType='enum',enumName='x:y:z:',keyable=False)
    for coord in 'XYZ':c.addAttr(handle,longName='offset'+coord,attributeType='double',keyable=True)
    if axis.startswith('z'):
        c.xform(handle,worldSpace=True,translation=(position[0],position[1],0))
        c.xform(handle,worldSpace=True,pivots=position);c.setAttr(handle+'.xyz',2)
    elif axis=='x':
        c.xform(handle,worldSpace=True,translation=(0,position[1],position[2]))
        c.setAttr(handle+'.controlPoints[1].xValue',c.getAttr(scan+'.translateX'))
        c.xform(handle,pivots=(c.getAttr(scan+'.translateX'),0,0));c.setAttr(handle+'.xyz',0)
    else:
        c.xform(handle,worldSpace=True,translation=(position[0],0,0))
        c.setAttr(handle+'.controlPoints[1].yValue',c.getAttr(scan+'.translateY'))
        c.xform(handle,worldSpace=True,pivots=(position[0],position[1],0))
        c.setAttr(handle+'.overrideColor',13);c.setAttr(handle+'.xyz',1)
    c.parentConstraint(handle,scan,maintainOffset=True)
    c.setAttr(projection+'.overrideEnabled',True);c.setAttr(projection+'.overrideColor',17)
    for i,node in enumerate(c.listRelatives(projection,children=True,type='transform') or []):
        node=c.rename(node,projection+'_'+str(i));lock_trs(c,node)
    curve=projected_curve(host,projection,find)
    pivot='asFitPivot'+name;orient='asFitPivotOrient'+name;offset='asFitPivotOffset'+name
    c.createNode('transform',name=pivot,parent='asFitPivots',skipSelect=True)
    c.createNode('transform',name=orient,parent=pivot,skipSelect=True)
    c.createNode('transform',name=offset,parent=orient,skipSelect=True)
    c.connectAttr(handle+'.rotate',pivot+'.rotate')
    for coord in 'XYZ':c.connectAttr(handle+'.offset'+coord,offset+'.translate'+coord)
    average=c.createNode('plusMinusAverage',name=pivot+'PMA1',skipSelect=True)
    c.setAttr(average+'.operation',3)
    c.connectAttr(curve+'.boundingBoxMin',average+'.input3D[0]')
    c.connectAttr(curve+'.boundingBoxMax',average+'.input3D[1]')
    c.connectAttr(average+'.output3D',pivot+'.translate')
    if axis=='x' or axis.startswith('z'):c.connectAttr(scan+'.translateY',pivot+'.translateY',force=True)
    coord='x' if axis=='x' else 'z' if axis.startswith('z') else 'y'
    bound='Min' if coord=='x' else 'Max'
    c.connectAttr(curve+'.boundingBox'+bound+coord.upper(),handle+'.controlPoints[0].'+coord+'Value')
    if not keep_history:
        c.setAttr(projection+'.visibility',False);c.setAttr(handle+'.visibility',False)
    return projection


def update_projection(host,name,axis,skin,find,keep_history):
    c=host._cmds
    position=c.getAttr('asFitScanCurve.translate')[0];rotation=c.getAttr('asFitScanCurve.rotate')[0]
    try:
        c.setAttr('asFitScanCurve.translate',*c.getAttr('asFitScanCurve'+name+'.translate')[0],type='double3')
        c.setAttr('asFitScanCurve.rotate',*c.getAttr('asFitScanCurve'+name+'.rotate')[0],type='double3')
        c.delete('asFitScanCurve'+name,'asFitHandle'+name,'asFitProjection'+name,'asFitPivot'+name)
        return save_projection(host,name,axis,skin,find,keep_history)
    finally:
        c.setAttr('asFitScanCurve.translate',*position,type='double3')
        c.setAttr('asFitScanCurve.rotate',*rotation,type='double3')


def anchor(host,joint):
    c=host._cmds;name='asFitAnchor'+joint
    c.spaceLocator(name=name);c.parent(name,'asFitAnchors',absolute=True)
    shape=c.listRelatives(name,shapes=True)[0]
    c.setAttr(shape+'.overrideEnabled',True);c.setAttr(shape+'.overrideColor',14)
    size=c.getAttr('AutoPlacing.bbMaxY')/100.
    c.setAttr(shape+'.localScale',size,size,size,type='double3')
    return name


def straight_pole(host,limb):
    c=host._cmds
    start,middle,end=('Shoulder','Elbow','Wrist') if limb=='Arm' else ('Hip','Knee','Ankle')
    if any(not c.objExists(node) for node in (start,middle,end)):return False
    handles=c.objExists('asFitHandleHip')
    if handles:
        for coord in 'XYZ':c.setAttr('asFitHandle'+middle+'.offset'+coord,0.)
    for node in ('tempXform1','tempXform2'):
        if c.objExists(node):c.delete(node)
    root=c.createNode('transform',name='tempXform1',skipSelect=True)
    child=c.createNode('transform',name='tempXform2',parent=root,skipSelect=True)
    try:
        c.pointConstraint(start,root,weight=c.getAttr(end+'.translateX'))
        c.pointConstraint(end,root,weight=c.getAttr(middle+'.translateX'))
        position=c.xform(root,query=True,worldSpace=True,translation=True)
        middle_position=c.xform(middle,query=True,worldSpace=True,translation=True)
        distance=sum((a-b)**2 for a,b in zip(position,middle_position))**.5
        c.setAttr(child+'.translateZ',-distance if limb=='Arm' else distance)
        target=c.xform(child,query=True,worldSpace=True,translation=True)
        if handles:
            for coord,a,b in zip('XYZ',target,middle_position):c.setAttr('asFitHandle'+middle+'.offset'+coord,a-b)
        else:c.move(*target,middle,absolute=True,preserveChildPosition=True)
    finally:c.delete(root)
    return True
