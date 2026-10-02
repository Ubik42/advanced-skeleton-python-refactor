"""Source reverse wrist scan and angled thumb sampling, MEL 52845–52943."""
from .maya_fit_auto_place_fingers import project


def detect_thumb(s):
    c=s.c
    if not c.objExists('asFitPivotWrist') or s.hit_thumb or not s.has_ncloth:return
    current=c.getAttr('asFitScanCurve.translateX')
    c.setAttr('asFitScanCurve.translateX',c.getAttr('asFitScanCurveWrist.translateX'))
    project(s,'CombinedSkinUpper_M')
    for _ in range(199):
        c.move(0,0,-s.step_z/10.,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
        c.refresh()
        if len(c.listRelatives('asFitScanPolyProjectionCurves',children=True) or [])>1:break
    curves=c.listRelatives('asFitScanPolyProjectionCurves',children=True,type='transform') or []
    root=c.createNode('transform',name='angledSamplerOffset',parent='AutoPlacing',skipSelect=True)
    sampler=c.createNode('transform',name='angledSampler',parent=root,skipSelect=True)
    c.xform(root,worldSpace=True,translation=(0,s.maximum_y,s.minimum_z));c.setAttr(root+'.rotateX',35.)
    maximum_z=0.;point=(0,0,0);thumb_curve=''
    for curve in curves:
        for index in range(int(c.getAttr(curve+'.spans'))):
            p=c.xform(curve+'.cv['+str(index)+']',query=True,worldSpace=True,translation=True)
            c.xform(sampler,worldSpace=True,translation=p);local=c.getAttr(sampler+'.translate')[0]
            if local[2]>maximum_z:maximum_z,point,thumb_curve=local[2],p,curve
    c.setAttr('closestSampler.inPosition',*point,type='double3')
    c.select('CombinedSkinUpper_M.vtx['+str(c.getAttr('closestSampler.closestVertexIndex'))+']',replace=True)
    minimum_x=0.
    for _ in range(20):
        updated=False
        for vertex in c.ls(selection=True,flatten=True) or []:
            p=c.xform(vertex,query=True,worldSpace=True,translation=True)
            if p[0]<minimum_x:minimum_x,point,updated=p[0],p,True
        if not updated:break
        c.polySelectConstraint(pp=1,type=1)
    selected=c.ls(selection=True,flatten=True) or []
    tip=c.createNode('transform',name='asFitPivotThumbFinger4',parent='asFitPivotsFingers',skipSelect=True)
    c.xform(tip,worldSpace=True,translation=point)
    minimum=c.getAttr('asFitProjectionWrist_0.boundingBoxMin')[0];maximum=c.getAttr('asFitProjectionWrist_0.boundingBoxMax')[0]
    a=(minimum[0],(minimum[1]+maximum[1])/2.,maximum[2])
    minimum=c.getAttr(thumb_curve+'.boundingBoxMin')[0];maximum=c.getAttr(thumb_curve+'.boundingBoxMax')[0]
    b=(minimum[0],(minimum[1]+maximum[1])/2.,minimum[2])
    base=c.createNode('transform',name='asFitPivotThumbFinger1',parent='asFitPivotsFingers',skipSelect=True)
    point=tuple((x+y)/2. for x,y in zip(a,b))
    c.xform(base,worldSpace=True,translation=point);c.xform(root,worldSpace=True,translation=point)
    c.aimConstraint(tip,root,offset=(0,0,0),weight=1.,aimVector=(1,0,0),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
    maximum_x=0.
    for vertex in selected:
        p=c.xform(vertex,query=True,worldSpace=True,translation=True)
        c.xform(sampler,worldSpace=True,translation=p);local=c.getAttr(sampler+'.translate')[0]
        if local[0]>maximum_x:maximum_x,point=local[0],p
    c.xform(tip,worldSpace=True,translation=point);c.delete(root)
    c.setAttr('asFitScanCurve.translateX',current);s.hit_thumb=True
