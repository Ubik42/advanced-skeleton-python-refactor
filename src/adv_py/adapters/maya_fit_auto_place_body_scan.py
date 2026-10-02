"""Original crotch, trunk, ankle and foot detection inside the scan loop."""
from .maya_fit_auto_place_projection import save_projection,projected_curve,anchor,lock_trs


def body_scan(s):
    c=s.c;host=s.host;axis=s.axis
    def save(name,skin='CombinedSkin',find='center',keep=False):return save_projection(host,name,axis,skin,find,keep)
    def value(plug):return c.getAttr(plug)
    def set_y(value):c.setAttr('asFitScanCurve.translateY',value)
    if axis=='z' and not s.hit_crotch and abs(s.center_x)<.001*s.maximum_y and s.bound_max[0]>.001:
        save('Crotch')
        # Source re-reads the chosen center curve here. The overlap-expanded
        # width above is solely for armpit detection, not this root offset.
        s.crotch_width=(c.getAttr(s.center_curve+'.boundingBoxMaxX')-
                        c.getAttr(s.center_curve+'.boundingBoxMinX'))
        c.move(0,s.crotch_width/4.,0,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
        save('Root','CombinedSkinLower_M',keep=True)
        c.move(0,-s.crotch_width/8.,0,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
        save('Hip','CombinedSkinLower_M',keep=True)
        set_y(value('asFitScanCurveCrotch.translateY'));s.hit_crotch=True;s.crotch_index=s.index
        if not s.template.startswith('biped'):s.stop=True;return
    if axis=='z' and s.hit_crotch and s.index>s.crotch_index+5 and not s.hit_armpit and s.width>s.previous_width*1.5:
        c.move(0,-s.maximum_y/100.,0,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
        save('ArmPit');curve=projected_curve(host,'asFitProjectionArmPit','center')
        s.armpit_width=value(curve+'.boundingBoxMaxX')-value(curve+'.boundingBoxMinX')
        a=value('asFitScanCurveRoot.translateY');b=value('asFitScanCurveArmPit.translateY')
        set_y(b-(b-a)/4.);save('Chest','CombinedSkinLower_M',keep=True)
        b=value('asFitScanCurveChest.translateY')
        set_y(b-(b-a)/2.);save('Spine1','CombinedSkinLower_M',keep=True)
        set_y(value('asFitScanCurveArmPit.translateY'));s.hit_armpit=True
    if axis=='z' and not s.hit_armpit and s.index==99:
        for name,fraction,keep in (('ArmPit',75,False),('Neck',85,True),('Head',92,True)):
            set_y(s.minimum_y+s.step_y*fraction);save(name,keep=keep)
    if axis=='z' and not s.hit_neck and s.hit_armpit and s.width<s.armpit_width:
        save('Neck',keep=True);s.hit_neck=True
    if axis=='z' and s.hit_neck and not s.hit_head:
        a=value('asFitScanCurveNeck.translateY')
        if value('asFitScanCurve.translateY')>a+(s.maximum_y-a)/5.:
            save('Head',keep=True);s.hit_head=True
    ankle=(axis=='x' and not s.hit_ankle and s.index>2 and s.width<s.max_width/2.
           and s.width>s.previous_width*.9 and s.hits==2)
    fallback=axis=='x' and s.index==99 and not c.objExists('asFitHandleAnkle')
    if ankle or fallback:
        if fallback:set_y(s.minimum_y+s.step_y*5.)
        c.move(0,-s.maximum_y/100.,0,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
        save('Ankle','CombinedSkinLower_M','right',True)
        set_y((value('asFitScanCurveCrotch.translateY')+value('asFitScanCurveAnkle.translateY'))/2.)
        save('Knee','CombinedSkinLower_M','right',True)
        set_y(value('asFitScanCurveAnkle.translateY'))
        c.move(0,-s.maximum_y/100.,0,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
        set_y(s.y_at_max_z if s.y_at_max_z<=s.maximum_y/2. else s.minimum_y+s.step_y)
        save('Toes','CombinedSkinLower_M','right',True)
        set_y(value('asFitScanCurveAnkle.translateY'))
        curve=projected_curve(host,'asFitProjectionToes','right')
        sampler=c.duplicate(curve,name='AnkleRotSampler')[0]
        c.parent(sampler,'AutoPlacing',absolute=True);lock_trs(c,sampler,True,False,True,True)
        c.xform(sampler,centerPivots=True)
        for index in range(90):
            pivot=c.xform(sampler,query=True,worldSpace=True,pivots=True)[:3]
            c.rotate(0,1,0,sampler+'.cv[0:999]',relative=True,pivot=pivot,objectSpace=True,forceOrderXYZ=True)
            box=c.xform(sampler,query=True,worldSpace=True,boundingBox=True)
            s.previous_width=s.width;s.width=box[3]-box[0]
            if index>0 and s.width>s.previous_width:
                c.setAttr(sampler+'.rotateY',-(index+1));break
        # MEL reuses outer $i in this loop, so retain that index side effect.
        s.index=index;s.ankle_rotation=value(sampler+'.rotateY')
        c.setAttr(sampler+'.rotateY',0.)
        for index in range(1,7):c.createNode('transform',name='tempXform'+str(index),parent=sampler,skipSelect=True)
        minimum,maximum=c.getAttr(sampler+'.boundingBoxMin')[0],c.getAttr(sampler+'.boundingBoxMax')[0]
        center=tuple((a+b)/2. for a,b in zip(minimum,maximum))
        points={1:(center[0],center[1],minimum[2]),2:(center[0],center[1],maximum[2]),
                4:(minimum[0],center[1],center[2]),5:(maximum[0],center[1],center[2]),6:(center[0],center[1],maximum[2])}
        for index,point in points.items():c.xform('tempXform'+str(index),worldSpace=True,translation=point)
        c.pointConstraint('tempXform1','tempXform3',weight=.25)
        c.pointConstraint('tempXform2','tempXform3',weight=.75)
        c.parent('tempXform4','tempXform5','tempXform6','tempXform3',absolute=True)
        c.setAttr('tempXform4.translateZ',0.);c.setAttr('tempXform5.translateZ',0.)
        c.setAttr(sampler+'.rotateY',s.ankle_rotation)
        c.parent('tempXform3','asFitPivotToes',absolute=True)
        c.setAttr('asFitHandleToes.offsetZ',value('tempXform3.translateZ'))
        for joint,index in (('FootSideOuter',4),('FootSideInner',5),('ToesEnd',6),('Heel',1)):
            if c.objExists(joint):
                name=anchor(host,joint);point=c.xform('tempXform'+str(index),query=True,worldSpace=True,translation=True)
                c.xform(name,worldSpace=True,translation=(point[0],0,point[2]))
        # Child transforms are removed by deleting tempXform3, not twice.
        c.delete('tempXform1','tempXform2','tempXform3')
        c.setAttr('asFitPivotOrientToes.rotateY',s.ankle_rotation);s.hit_ankle=True
