"""Original upper-body segmentation and Shoulder / Elbow straightening."""
from .maya_fit_auto_place_projection import save_projection,update_projection
from .maya_fit_auto_place_mesh import faces,invert,cast,grow_past_shell


def _position(c,node):
    return c.xform(node,query=True,worldSpace=True,translation=True)


def _vertex_count(c):
    return len(c.ls(selection=True,flatten=True) or [])


def _cut_body_and_head(s):
    """MEL 52383: cut lower geometry, then separate head from the upper mesh."""
    c=s.c
    for node,visible in (('CombinedSkin',False),('CombinedSkinLower_M',False),
                         ('CombinedSkinUpper_M',True)):
        c.setAttr(node+'.visibility',visible)
    c.select('CombinedSkinUpper_M',replace=True)
    c.polySelectConstraint(mode=3,type=1,d=3,db=(0,s.maximum_y/10.),
                          da=(0,1,0),dp=(0,0,0))
    c.polySelectConstraint(mode=0)
    for _ in range(999):
        before=_vertex_count(c)
        c.polySelectConstraint(pp=1,type=1)
        if _vertex_count(c)==before:
            break
        if c.xform(query=True,boundingBox=True)[4]>c.getAttr('asFitPivotArmPit.translateY'):
            break
    removed=faces(c)
    c.delete(removed)
    c.select(cast(removed,'CombinedSkinLower_M'),replace=True)
    invert(c)
    c.delete(c.ls(selection=True))

    c.duplicate('CombinedSkinUpper_M',name='CombinedSkinHead_M')
    c.connectAttr('CombinedSkinUpper_M.outMesh','closestSampler.inMesh',force=True)
    point=_position(c,'asFitHandleNeck')
    c.select('CombinedSkinHead_M',replace=True)
    c.polySelectConstraint(mode=3,type=1,d=3,db=(0,point[1]),
                          da=(0,1,0),dp=(0,0,0))
    c.polySelectConstraint(mode=0)
    removed=faces(c)
    c.delete(removed)
    c.select(cast(removed,'CombinedSkinUpper_M'),replace=True)
    invert(c)
    c.delete(c.ls(selection=True))


def _sample_arm_vertices(s):
    c=s.c
    point=_position(c,'asFitPivotOffsetArmTip')
    c.setAttr('closestSampler.inPosition',*point,type='double3')
    index=c.getAttr('closestSampler.closestVertexIndex')
    c.select('CombinedSkinUpper_M.vtx['+str(index)+']',replace=True)
    for _ in range(999):
        before=_vertex_count(c)
        c.polySelectConstraint(pp=1,type=1)
        if _vertex_count(c)==before:
            grow_past_shell(s.host)
            if _vertex_count(c)==before:
                break
        box=c.xform(query=True,boundingBox=True)
        shoulder_y=(c.getAttr('asFitPivotArmPit.translateY')+
                    c.getAttr('asFitPivotNeck.translateY'))/2.
        if box[4]>shoulder_y and box[3]>c.getAttr('asFitPivotShoulder.translateX'):
            break
    return c.ls(selection=True,flatten=True) or []


def _create_straight_shoulder(s,vertices):
    c=s.c
    c.select('asFitAutoPlaceJoints',replace=True)
    c.joint(name='asFitShoulderStraightBase')
    c.joint(name='asFitShoulderStraight')
    c.setAttr('asFitShoulderStraightBase.visibility',False)
    armpit=_position(c,'asFitPivotArmPit')
    neck=_position(c,'asFitPivotNeck')
    shoulder=_position(c,'asFitPivotShoulder')
    c.xform('asFitShoulderStraight',worldSpace=True,
            translation=(shoulder[0],(armpit[1]+neck[1])/2.,(armpit[2]+neck[2])/2.))
    cluster=c.skinCluster(('asFitShoulderStraight','asFitShoulderStraightBase'),
        'CombinedSkinUpper_M',name='CombinedSkinUpperSC_M',toSelectedBones=True,
        maximumInfluences=3,dropoffRate=4,removeUnusedInfluence=False)[0]
    c.skinPercent(cluster,'CombinedSkinUpper_M',transformValue=[('asFitShoulderStraightBase',1.)])
    c.skinPercent(cluster,vertices,transformValue=[('asFitShoulderStraight',1.)])
    c.deltaMush('CombinedSkinUpper_M',name='asFitDeltaMush',smoothingIterations=30,
                smoothingStep=.5,pinBorderVertices=True,envelope=1.)
    c.refresh()
    temp=c.createNode('transform',name='tempXform1',parent='AutoPlacing',skipSelect=True)
    c.pointConstraint('asFitShoulderStraight',temp)
    c.aimConstraint('asFitPivotArmTip',temp,offset=(0,0,0),weight=1.,
                    aimVector=(-1,0,0),upVector=(0,1,0),worldUpType='scene')
    rotation=c.getAttr(temp+'.rotateZ')
    if rotation>10:
        c.setAttr('asFitShoulderStraight.rotateZ',-rotation)
    c.delete(temp)
    point=_position(c,'asFitPivotArmTip')
    c.delete('asFitProjectionArmTip','asFitScanCurveArmTip')
    c.xform('asFitPivotArmTip',worldSpace=True,translation=point)
    s.hit_arm_tip=False
    s.minimum_x=c.getAttr('CombinedSkinUpper_M.boundingBoxMinX')
    c.setAttr('AutoPlacing.bbMinX',s.minimum_x)


def _split_limb_skins(s):
    c=s.c
    for side in ('_R','_L'):
        for part in ('Upper','Lower'):
            source='CombinedSkin'+part+'_M'
            target='CombinedSkin'+part+side
            c.duplicate(source,name=target)
            c.blendShape(source,target,name='CombinedSkin'+part+'BS'+side,
                          frontOfChain=True,weight=(0,1.))
            c.select(target,replace=True)
            c.refresh()
            c.polySelectConstraint(mode=3,type=8,d=3,db=(0,-s.minimum_x),
                                  da=(1,0,0),dp=(s.minimum_x,0,0))
            if side=='_R':
                invert(c)
            c.delete(c.ls(selection=True))
            c.polySelectConstraint(mode=0)
            c.setAttr(target+'.visibility',False)
    update_projection(s.host,'Shoulder',s.axis,'CombinedSkinUpper_R',
                      'closestToasFitPivotArmPit',True)


def _straighten_elbow(s):
    c=s.c
    current=c.getAttr('asFitScanCurve.translateX')
    def save(name,keep=False):
        save_projection(s.host,name,s.axis,'CombinedSkinUpper_M','0',keep)
    c.setAttr('asFitScanCurve.translateX',s.first_split_x)
    save('FirstNonFingerSplit')
    c.setAttr('asFitScanCurve.translateX',s.first_split_x-(s.minimum_x-s.first_split_x)/2.5)
    save('Wrist',True)
    c.setAttr('asFitScanCurve.translateX',(c.getAttr('asFitHandleShoulder.translateX')+s.first_split_x)/2.)
    save('Elbow',True)
    c.setAttr('asFitScanCurve.translateX',s.first_split_x)
    point=_position(c,'asFitPivotElbow')
    c.select('asFitShoulderStraight',replace=True)
    c.joint(name='asFitElbowStraight')
    c.xform('asFitElbowStraight',worldSpace=True,translation=point)
    rotation=c.getAttr('asFitShoulderStraight.rotateZ')
    c.setAttr('asFitShoulderStraight.rotateZ',0.)
    c.skinCluster('CombinedSkinUpperSC_M',edit=True,lockWeights=False,
                  weight=0.,addInfluence='asFitElbowStraight')
    c.setAttr('asFitShoulderStraight.rotateZ',rotation)
    c.select('CombinedSkinUpper_M',replace=True)
    c.polySelectConstraint(mode=3,type=1,d=3,db=(0,999),da=(1,0,0),dp=(-999+point[0],0,0))
    c.skinPercent('CombinedSkinUpperSC_M',c.ls(selection=True),
                  transformValue=[('asFitElbowStraight',1.)])
    c.polySelectConstraint(mode=0)
    locator=c.spaceLocator(name='tempLoc1')[0]
    c.parent(locator,'AutoPlacing',absolute=True)
    split=_position(c,'asFitPivotFirstNonFingerSplit')
    elbow=_position(c,'asFitElbowStraight')
    c.xform(locator,worldSpace=True,translation=split)
    c.parentConstraint('asFitElbowStraight','asFitPivotsFingers',maintainOffset=True)
    constraint=c.aimConstraint(locator,'asFitElbowStraight',maintainOffset=True,
        weight=1.,aimVector=(0,-1,0),upVector=(-1,0,0),worldUpType='scene')[0]
    c.refresh()
    c.xform(locator,worldSpace=True,translation=(split[0],split[1],elbow[2]))
    c.refresh()
    c.delete(constraint,locator)
    c.setAttr('asFitScanCurve.translateX',current)


def arm_scan(s):
    c=s.c
    if s.axis=='yArmStraight' and not s.hit_arm_tip:
        save_projection(s.host,'ArmTip',s.axis,'CombinedSkin','0',False)
        s.hit_arm_tip=True
    shoulder_hit=(s.axis=='yArmStraight' and not s.hit_shoulder and
        c.getAttr('asFitScanCurve.translateX')>s.armpit_width*-.5 and
        c.objExists('asFitPivotArmPit'))
    if shoulder_hit:
        save_projection(s.host,'Shoulder',s.axis,'CombinedSkin','closestToasFitPivotArmPit',True)
        if not s.arm_straight and all(c.objExists('asFitPivot'+name)
                                      for name in ('ArmPit','Neck','Shoulder')):
            s.orbit_step*=-1.
            _cut_body_and_head(s)
            vertices=_sample_arm_vertices(s)
            _create_straight_shoulder(s,vertices)
            _split_limb_skins(s)
            s.arm_straight=True
        s.hit_shoulder=True
        s.break_axis=True
        return
    if (s.axis=='yElbowStraight' and s.previous_hits>1 and s.hits==1 and
            c.getAttr('asFitScanCurve.translateX')<s.minimum_x/2.):
        s.first_split_x=c.getAttr('asFitScanCurve.translateX')
    if s.axis=='y' and not c.objExists('asFitElbowStraight'):
        _straighten_elbow(s)
