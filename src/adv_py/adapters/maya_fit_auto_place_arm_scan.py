"""Original upper-body segmentation and Shoulder / Elbow straightening."""
from .maya_fit_auto_place_projection import save_projection,update_projection
from .maya_fit_auto_place_mesh import faces,invert,cast,grow_past_shell


def arm_scan(s):
    c=s.c;host=s.host;axis=s.axis
    def pos(node):return c.xform(node,query=True,worldSpace=True,translation=True)
    def save(name,skin='CombinedSkin',find='0',keep=False):return save_projection(host,name,axis,skin,find,keep)
    if axis=='yArmStraight' and not s.hit_arm_tip:
        save('ArmTip');s.hit_arm_tip=True
    if axis=='yArmStraight' and not s.hit_shoulder and c.getAttr('asFitScanCurve.translateX')>s.armpit_width*-.5 and c.objExists('asFitPivotArmPit'):
        save('Shoulder',find='closestToasFitPivotArmPit',keep=True)
        if not s.arm_straight and all(c.objExists('asFitPivot'+name) for name in ('ArmPit','Neck','Shoulder')):
            s.orbit_step*=-1.
            for node,visible in (('CombinedSkin',False),('CombinedSkinLower_M',False),('CombinedSkinUpper_M',True)):
                c.setAttr(node+'.visibility',visible)
            c.select('CombinedSkinUpper_M',replace=True)
            c.polySelectConstraint(mode=3,type=1,d=3,db=(0,s.maximum_y/10.),da=(0,1,0),dp=(0,0,0))
            c.polySelectConstraint(mode=0)
            for _ in range(999):
                before=len(c.ls(selection=True,flatten=True) or [])
                c.polySelectConstraint(pp=1,type=1)
                if len(c.ls(selection=True,flatten=True) or [])==before:break
                if c.xform(query=True,boundingBox=True)[4]>c.getAttr('asFitPivotArmPit.translateY'):break
            removed=faces(c);c.delete(removed)
            c.select(cast(removed,'CombinedSkinLower_M'),replace=True);invert(c);c.delete(c.ls(selection=True))
            c.duplicate('CombinedSkinUpper_M',name='CombinedSkinHead_M')
            c.connectAttr('CombinedSkinUpper_M.outMesh','closestSampler.inMesh',force=True)
            point=pos('asFitHandleNeck');c.select('CombinedSkinHead_M',replace=True)
            c.polySelectConstraint(mode=3,type=1,d=3,db=(0,point[1]),da=(0,1,0),dp=(0,0,0))
            c.polySelectConstraint(mode=0);removed=faces(c);c.delete(removed)
            c.select(cast(removed,'CombinedSkinUpper_M'),replace=True);invert(c);c.delete(c.ls(selection=True))
            c.setAttr('closestSampler.inPosition',*pos('asFitPivotOffsetArmTip'),type='double3')
            c.select('CombinedSkinUpper_M.vtx['+str(c.getAttr('closestSampler.closestVertexIndex'))+']',replace=True)
            for _ in range(999):
                before=len(c.ls(selection=True,flatten=True) or []);c.polySelectConstraint(pp=1,type=1)
                if len(c.ls(selection=True,flatten=True) or [])==before:
                    grow_past_shell(host)
                    if len(c.ls(selection=True,flatten=True) or [])==before:break
                box=c.xform(query=True,boundingBox=True)
                if box[4]>(c.getAttr('asFitPivotArmPit.translateY')+c.getAttr('asFitPivotNeck.translateY'))/2. and box[3]>c.getAttr('asFitPivotShoulder.translateX'):break
            vertices=c.ls(selection=True,flatten=True) or []
            c.select('asFitAutoPlaceJoints',replace=True)
            c.joint(name='asFitShoulderStraightBase');c.joint(name='asFitShoulderStraight')
            c.setAttr('asFitShoulderStraightBase.visibility',False)
            a,b,p=pos('asFitPivotArmPit'),pos('asFitPivotNeck'),pos('asFitPivotShoulder')
            c.xform('asFitShoulderStraight',worldSpace=True,translation=(p[0],(a[1]+b[1])/2.,(a[2]+b[2])/2.))
            cluster=c.skinCluster(('asFitShoulderStraight','asFitShoulderStraightBase'),'CombinedSkinUpper_M',
                name='CombinedSkinUpperSC_M',toSelectedBones=True,maximumInfluences=3,dropoffRate=4,removeUnusedInfluence=False)[0]
            c.skinPercent(cluster,'CombinedSkinUpper_M',transformValue=[('asFitShoulderStraightBase',1.)])
            c.skinPercent(cluster,vertices,transformValue=[('asFitShoulderStraight',1.)])
            c.deltaMush('CombinedSkinUpper_M',name='asFitDeltaMush',smoothingIterations=30,smoothingStep=.5,pinBorderVertices=True,envelope=1.)
            c.refresh()
            temp=c.createNode('transform',name='tempXform1',parent='AutoPlacing',skipSelect=True)
            c.pointConstraint('asFitShoulderStraight',temp)
            c.aimConstraint('asFitPivotArmTip',temp,offset=(0,0,0),weight=1.,aimVector=(-1,0,0),upVector=(0,1,0),worldUpType='scene')
            rotation=c.getAttr(temp+'.rotateZ')
            if rotation>10:c.setAttr('asFitShoulderStraight.rotateZ',-rotation)
            c.delete(temp)
            point=pos('asFitPivotArmTip');c.delete('asFitProjectionArmTip','asFitScanCurveArmTip')
            c.xform('asFitPivotArmTip',worldSpace=True,translation=point)
            s.hit_arm_tip=False;s.minimum_x=c.getAttr('CombinedSkinUpper_M.boundingBoxMinX')
            c.setAttr('AutoPlacing.bbMinX',s.minimum_x)
            for side in ('_R','_L'):
                for part in ('Upper','Lower'):
                    source='CombinedSkin'+part+'_M';target='CombinedSkin'+part+side
                    c.duplicate(source,name=target)
                    c.blendShape(source,target,name='CombinedSkin'+part+'BS'+side,frontOfChain=True,weight=(0,1.))
                    c.select(target,replace=True);c.refresh()
                    c.polySelectConstraint(mode=3,type=8,d=3,db=(0,-s.minimum_x),da=(1,0,0),dp=(s.minimum_x,0,0))
                    if side=='_R':invert(c)
                    c.delete(c.ls(selection=True));c.polySelectConstraint(mode=0);c.setAttr(target+'.visibility',False)
            update_projection(host,'Shoulder',axis,'CombinedSkinUpper_R','closestToasFitPivotArmPit',True)
            s.arm_straight=True
        s.hit_shoulder=True;s.break_axis=True;return
    if axis=='yElbowStraight' and s.previous_hits>1 and s.hits==1 and c.getAttr('asFitScanCurve.translateX')<s.minimum_x/2.:
        s.first_split_x=c.getAttr('asFitScanCurve.translateX')
    if axis=='y' and not c.objExists('asFitElbowStraight'):
        current=c.getAttr('asFitScanCurve.translateX')
        c.setAttr('asFitScanCurve.translateX',s.first_split_x);save('FirstNonFingerSplit','CombinedSkinUpper_M')
        c.setAttr('asFitScanCurve.translateX',s.first_split_x-(s.minimum_x-s.first_split_x)/2.5)
        save('Wrist','CombinedSkinUpper_M',keep=True)
        c.setAttr('asFitScanCurve.translateX',(c.getAttr('asFitHandleShoulder.translateX')+s.first_split_x)/2.)
        save('Elbow','CombinedSkinUpper_M',keep=True)
        c.setAttr('asFitScanCurve.translateX',s.first_split_x)
        point=pos('asFitPivotElbow');c.select('asFitShoulderStraight',replace=True)
        c.joint(name='asFitElbowStraight');c.xform('asFitElbowStraight',worldSpace=True,translation=point)
        rotation=c.getAttr('asFitShoulderStraight.rotateZ');c.setAttr('asFitShoulderStraight.rotateZ',0.)
        c.skinCluster('CombinedSkinUpperSC_M',edit=True,lockWeights=False,weight=0.,addInfluence='asFitElbowStraight')
        c.setAttr('asFitShoulderStraight.rotateZ',rotation);c.select('CombinedSkinUpper_M',replace=True)
        c.polySelectConstraint(mode=3,type=1,d=3,db=(0,999),da=(1,0,0),dp=(-999+point[0],0,0))
        c.skinPercent('CombinedSkinUpperSC_M',c.ls(selection=True),transformValue=[('asFitElbowStraight',1.)]);c.polySelectConstraint(mode=0)
        locator=c.spaceLocator(name='tempLoc1')[0];c.parent(locator,'AutoPlacing',absolute=True)
        a,b=pos('asFitPivotFirstNonFingerSplit'),pos('asFitElbowStraight')
        c.xform(locator,worldSpace=True,translation=a)
        c.parentConstraint('asFitElbowStraight','asFitPivotsFingers',maintainOffset=True)
        constraint=c.aimConstraint(locator,'asFitElbowStraight',maintainOffset=True,weight=1.,
            aimVector=(0,-1,0),upVector=(-1,0,0),worldUpType='scene')[0]
        c.refresh();c.xform(locator,worldSpace=True,translation=(a[0],a[1],b[2]));c.refresh()
        c.delete(constraint,locator);c.setAttr('asFitScanCurve.translateX',current)
