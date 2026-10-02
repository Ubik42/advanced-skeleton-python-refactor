"""asFitAutoPlaceFromScanCurves, MEL 52987–53222."""
from .maya_fit_auto_place_projection import projected_curve


def from_scan_curves(host,container='FitSkeleton'):
    c=host._cmds
    selection=c.ls(selection=True,long=True) or []
    maximum=c.getAttr('AutoPlacing.bbMaxY')
    def exists(*nodes):return all(c.objExists(node) for node in nodes)
    def position(node):return c.xform(node,query=True,worldSpace=True,translation=True)
    def move(node,point):c.xform(node,worldSpace=True,translation=point)
    def constrain(source,target,**flags):return c.pointConstraint(source,target,**flags)[0]
    if c.objExists(container+'.lockCenterJoints'):c.setAttr(container+'.lockCenterJoints',False)
    if exists('asFitPivotRoot','Root'):
        a,b=position('asFitPivotRoot'),position('Root')
        factor=a[1]/b[1] if b[1] else 1.
        joints=list(reversed(c.listRelatives(container,allDescendents=True,type='joint',fullPath=True) or []))
        points=[position(joint) for joint in joints]
        for joint,point in zip(joints,points):
            move(joint,tuple(value*factor for value in point))
            if c.objExists(joint+'.fat'):c.setAttr(joint+'.fat',c.getAttr(joint+'.fat')*factor)
        constrain('asFitPivotOffsetRoot','Root',skip='x')
    if exists('asFitPivotHip','Hip','asFitPivotAnkle'):
        # Preserve the native center-curve evaluation before applying its pivot.
        projected_curve(host,'asFitProjectionHip','center')
        move('Hip',position('asFitPivotHip'));constrain('asFitPivotOffsetHip','Hip')
    for joint in ('Knee','Ankle','Toes','Toes'):
        if exists('asFitPivot'+joint,joint):constrain('asFitPivotOffset'+joint,joint)
    for joint in ('Heel','FootSideOuter','FootSideInner','ToesEnd'):
        if exists('asFitAnchor'+joint,joint):constrain('asFitAnchor'+joint,joint)
    for joint in ('Spine1','Chest'):
        if exists('asFitPivotRoot','asFitPivot'+joint,joint):constrain('asFitPivotOffset'+joint,joint,skip='z')
    if exists('asFitPivotNeck','Neck'):constrain('asFitPivotOffsetNeck','Neck',skip='z',weight=1.)
    if exists('asFitPivotHead','Head'):
        c.delete(constrain('asFitPivotOffsetHead','Head',skip='z',weight=1.))
        a,b=position('asFitPivotOffsetHead'),position('asFitPivotOffsetNeck')
        move('Head',(0,a[1],b[2]));constrain('asFitPivotOffsetHead','Head',skip='z',weight=1.)
        if exists('HeadEnd'):move('HeadEnd',(0,maximum,a[2]))
        if exists('Jaw'):move('Jaw',(0,a[1]+(maximum-a[1])/5.,a[2]+maximum/50.))
        if exists('JawEnd'):c.setAttr('JawEnd.translateX',(maximum-a[1])/3.)
    if exists('asFitPivotHead','Eye'):
        if exists('asFitPivotEye'):
            constrain('asFitPivotEye','Eye',weight=1.)
            if exists('EyeEnd'):c.setAttr('EyeEnd.translateX',c.getAttr('asFitPivotEye.radius'))
        else:
            a=position('asFitPivotHead')
            move('Eye',((maximum-a[1])/-5.,a[1]+(maximum-a[1])/2.,a[2]+maximum/15.))
            if exists('EyeEnd'):c.setAttr('EyeEnd.translateX',(maximum-a[1])/10.)
    if exists('asFitPivotOffsetShoulder','Scapula'):
        if exists('asFitPivotOffsetScapula1'):c.delete('asFitPivotOffsetScapula1')
        c.duplicate('asFitPivotOffsetShoulder',name='asFitPivotOffsetScapula1')
        c.duplicate('asFitPivotOffsetShoulder',name='asFitPivotOffsetScapula2')
        c.parent('asFitPivotOffsetScapula2','asFitPivotOffsetScapula1',absolute=True)
        constrain('asFitPivotOffsetShoulder','asFitPivotOffsetScapula1',skip='x')
        constrain('asFitPivotOffsetShoulder','asFitPivotOffsetScapula2',skip=('y','z'),weight=.33)
        constrain('asFitPivots','asFitPivotOffsetScapula2',skip=('y','z'),weight=.67)
        constrain('asFitPivotOffsetScapula2','Scapula',weight=1.)
    for joint in ('Shoulder','Wrist','Elbow'):
        if exists('asFitPivot'+joint,joint):constrain('asFitPivotOffset'+joint,joint,weight=1.)
    offset=0.
    if exists('asFitPivotIndexFinger1','asFitPivotMiddleFinger1'):
        a,b=position('asFitPivotIndexFinger1'),position('asFitPivotMiddleFinger1')
        offset=sum((x-y)**2 for x,y in zip(a,b))**.5/2.
    for finger in ('Index','Middle','Ring','Pinky','Thumb'):
        first=finger+'Finger1';tip='asFitPivot'+finger+'Finger4'
        if not exists('asFitPivot'+first,first):continue
        a='asFitPivot'+first+'OffsetA';b='asFitPivot'+first+'OffsetB'
        if exists(a):c.delete(a)
        c.createNode('transform',name=a,parent='asFitPivot'+first,skipSelect=True)
        c.delete(c.aimConstraint('Elbow',a,offset=(0,0,0),weight=1.,aimVector=(1,0,0),
                                upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0)))
        c.createNode('transform',name=b,parent=a,skipSelect=True)
        if finger!='Thumb':c.setAttr(b+'.translateX',offset)
        constrain(b,first,weight=1.)
        for segment,weight in ((2,.6),(3,.3)):
            node=finger+'Finger'+str(segment)
            constrain(first,node,weight=weight);constrain(tip,node,weight=1.-weight)
        constrain(tip,finger+'Finger4',weight=1.)
        curve='FingerCurve'+finger
        if exists(curve):
            for segment in range(2,5):
                node=finger+'Finger'+str(segment)
                c.delete(node+'_pointConstraint1')
                c.delete(c.geometryConstraint(curve,node))
        c.setAttr(finger+'Finger3.jointOrient',0,0,0,type='double3')
    if exists('asFitPivotPinkyFinger1','asFitPivotWrist','Cup'):
        constrain('asFitPivotPinkyFinger1','Cup',weight=.1)
        constrain('asFitPivotWrist','Cup',weight=.9)
    constraints=c.listRelatives(container,allDescendents=True,type='constraint') or []
    if constraints:c.parent(constraints,'asFitConstraints',absolute=True)
    c.select(selection,replace=True) if selection else c.select(clear=True)


def set_fat(host,container='FitSkeleton'):
    """Source 53222: its unpopulated local fitJoints loop performs no writes.

    Preserve that behavior rather than silently applying guessed torso radii.
    The five explicit finger chains do receive the source fingerWidth values.
    """
    c=host._cmds;width=c.getAttr('AutoPlacing.fingerWidth')/2.
    joints=tuple(c.listRelatives(container,allDescendents=True,type='joint',fullPath=True) or [])
    host.write_missing_fit_deform_profiles(container,joints)
    for finger in ('Index','Middle','Ring','Pinky','Thumb'):
        for index in range(1,5):
            joint=finger+'Finger'+str(index)
            if not c.objExists(joint):continue
            for attr,value in (('fat',1.),('fatFront',width),('fatWidth',width)):
                if not c.objExists(joint+'.'+attr):c.addAttr(joint,longName=attr,attributeType='double',keyable=True,defaultValue=1.)
                c.setAttr(joint+'.'+attr,value)
