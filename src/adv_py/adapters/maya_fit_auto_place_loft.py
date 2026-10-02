"""MEL asFitAutoPlaceLoft: smooth contours and replace editable projections."""
from .maya_fit_auto_place_projection import save_projection


def build_loft(host,axis):
    host._require_transaction();host._transaction_changed=True
    c=host._cmds
    reps=('Wrist','Elbow','Shoulder') if axis=='yLoft' else ('Toes','Ankle','Knee','Hip','Root','Chest','Spine1','Neck','Head')
    prefix='asFitProjectionLoftCurve'+axis
    if axis=='yLoft':
        c.delete(prefix+'a')
        for i in range(51):
            name=prefix+str(i);x=c.getAttr(name+'.translateX')
            if x<c.getAttr('asFitHandleWrist.translateX') or x>c.getAttr('asFitHandleShoulder.translateX')*1.5:c.delete(name)
    curves=c.listRelatives('asFitLoftCurves'+axis,children=True) or []
    surface=c.loft(curves,name='asFitLoftSurface'+axis,constructionHistory=False,
                   uniform=True,close=False,autoReverse=True,degree=3,sectionSpans=2,
                   range=False,polygon=0,reverseSurfaceNormals=True)[0]
    if axis=='yLoft':
        last=int(c.getAttr(surface+'.spansV'))+2
        position=c.xform(surface+'.cv[0][0]',query=True,worldSpace=True,translation=True)
        c.move(c.getAttr('AutoPlacing.bbMinX')-position[0],0,0,surface+'.cv[0:7][0:1]',
               relative=True,objectSpace=True,worldSpaceDistance=True)
        position=c.xform(surface+'.cv[0]['+str(last)+']',query=True,worldSpace=True,translation=True)
        c.move(-position[0],0,0,surface+'.cv[0:7]['+str(last-1)+':'+str(last)+']',
               relative=True,objectSpace=True,worldSpaceDistance=True)
    c.parent(surface,'asFitCombinedLofts',absolute=True);c.delete('asFitLoftCurves'+axis)
    c.setAttr(surface+'.visibility',False)
    mesh=c.nurbsToPoly(surface,name='asFitLoft'+axis,mnd=1,ch=0,f=2,pt=1,pc=200,
        chr=.9,ft=.01,mel=.001,d=.1,ut=3,un=1,vt=3,vn=1,uch=0,ucr=0,cht=.2,es=0,ntr=0,mrt=0,uss=1)[0]
    c.parent(mesh,'asFitCombinedLofts',absolute=True);c.setAttr(mesh+'.visibility',False)
    c.duplicate(mesh,name=mesh+'_R');c.select(mesh+'_R',replace=True)
    c.polySelectConstraint(mode=3,type=1,d=3,db=(0,999),da=(1,0,0),dp=(999,0,0))
    vertices=c.ls(selection=True,flatten=True) or [];c.polySelectConstraint(mode=0)
    for vertex in vertices:
        position=c.xform(vertex,query=True,worldSpace=True,translation=True)
        c.xform(vertex,worldSpace=True,translation=(0,position[1],position[2]))
    for pattern in ('asFitProjectionLoft'+axis+'*','asFitScanCurveLoft'+axis+'*',
                    'asFitHandleLoft'+axis+'*','asFitPivotLoft'+axis+'*'):
        nodes=c.ls(pattern) or []
        if nodes:c.delete(nodes)
    c.delete(surface)
    for name in reps:
        if not c.objExists('asFitProjection'+name):continue
        skin=mesh+'_R' if name in ('Hip','Knee','Ankle','Toes') else mesh
        scan='asFitScanCurve'+name;handle='asFitHandle'+name;projection='asFitProjection'+name
        constraint=c.parentConstraint(scan,'asFitScanCurve')[0];c.delete(constraint)
        offsets=tuple(c.getAttr(handle+'.offset'+coord) for coord in 'XYZ') if c.objExists(handle+'.offsetX') else (0,0,0)
        rotation=c.getAttr('asFitPivotOrient'+name+'.rotate')[0]
        c.delete(handle,'asFitPivot'+name)
        c.rename(scan,scan+'Contour');c.rename(projection,projection+'Contour')
        for child in c.listRelatives(projection+'Contour',children=True) or []:
            stem,_,index=child.rpartition('_')
            c.rename(child,stem+'Contour_'+index)
        save_projection(host,name,axis,skin,'0',True)
        c.setAttr(projection+'.visibility',False)
        c.parentConstraint(handle,scan+'Contour',maintainOffset=True)
        for coord,value in zip('XYZ',offsets):c.setAttr(handle+'.offset'+coord,value)
        c.setAttr('asFitPivotOrient'+name+'.rotate',*rotation,type='double3')
    if axis=='zLoft' and c.objExists('asFitPivotNeck') and c.objExists('asFitPivotHead'):
        a=c.xform('asFitPivotNeck',query=True,worldSpace=True,translation=True)
        b=c.xform('asFitPivotHead',query=True,worldSpace=True,translation=True)
        c.setAttr('asFitHandleHead.offsetZ',a[2]-b[2])
