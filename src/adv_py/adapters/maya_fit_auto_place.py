"""ADV 6.925 AutoPlace phase orchestration, MEL 51771–52973."""
from types import SimpleNamespace
from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_AXES,FIT_AUTO_PLACE_GROUPS,FitAutoPlaceResult
from adv_py.core.fit_auto_scale import plan_fit_auto_scale
from .maya_fit_auto_scale import capture,apply
from .maya_fit_auto_place_projection import projected_curve,save_projection,lock_trs,straight_pole
from .maya_fit_auto_place_body_scan import body_scan
from .maya_fit_auto_place_arm_scan import arm_scan
from .maya_fit_auto_place_fingers import detect_fingers,straighten_fingers,project
from .maya_fit_auto_place_thumb import detect_thumb
from .maya_fit_auto_place_loft import build_loft
from .maya_fit_auto_place_positions import from_scan_curves,set_fat
from .maya_fit_auto_place_guides import finish


def run(host,container,skin,all_objects,right_eye):
    c=host._cmds
    display=c.jointDisplayScale(query=True)
    try:return _run(host,container,skin,all_objects,right_eye)
    except Exception:
        # Maya preferences are outside the scene's undo queue. A failed scan
        # must not leave the successful scale phase's global display setting.
        c.jointDisplayScale(display)
        raw=getattr(c,'raw',c)
        raw.polySelectConstraint(mode=0)
        raise


def _run(host,container,skin,all_objects,right_eye):
    host._require_transaction();c=host._cmds;raw=getattr(c,'raw',c)
    if c.objExists('AutoPlacing'):return finish(host,container,skin,all_objects)
    before=capture(host,container,skin,all_objects,right_eye);plan=plan_fit_auto_scale(before)
    host._transaction_changed=True
    c.createNode('transform',name='AutoPlacing',skipSelect=True)
    for name in FIT_AUTO_PLACE_GROUPS:c.createNode('transform',name=name,parent='AutoPlacing',skipSelect=True)
    c.createNode('transform',name='asFitPivotsFingers',parent='asFitPivots',skipSelect=True)
    c.createNode('transform',name='asFitAnchors',parent='asFitPivots',skipSelect=True)
    orbit=c.createNode('transform',name='asFitOrbitB',parent='asFitOrbitA',skipSelect=True)
    camera=raw.xform('persp',query=True,worldSpace=True,matrix=True)
    c.xform(orbit,worldSpace=True,matrix=camera)
    if c.objExists('closestSampler'):c.delete('closestSampler')
    c.createNode('closestPointOnMesh',name='closestSampler',skipSelect=True)
    for mesh in dict.fromkeys((*skin,*all_objects)):
        try:raw.setAttr(host.scene_address(mesh)+'.visibility',False)
        except RuntimeError:pass
    try:c.setAttr('Root.visibility',False)
    except RuntimeError:pass
    copies=[c.duplicate(mesh,name='CombinedSkin'+str(index),returnRootsOnly=True)[0] for index,mesh in enumerate(skin)]
    for node in copies:c.parent(node,'AutoPlacing',absolute=True)
    if len(copies)>1:
        mesh=c.polyUnite(copies,constructionHistory=False,mergeUVSets=0,name='TempCombinedSkin')[0]
        c.parent(mesh,'AutoPlacing',absolute=True);c.rename(mesh,'CombinedSkin')
        leftovers=[node for node in copies if c.objExists(node)]
        if leftovers:c.delete(leftovers)
    else:c.rename(copies[0],'CombinedSkin')
    c.parent('CombinedSkin','asFitCombinedSkins',absolute=True)
    c.setAttr('CombinedSkin.visibility',True);c.setAttr('CombinedSkin.overrideEnabled',True);c.setAttr('CombinedSkin.overrideDisplayType',2)
    minimum=c.getAttr('CombinedSkin.boundingBoxMin')[0];maximum=c.getAttr('CombinedSkin.boundingBoxMax')[0]
    for attr,value in (('bbMinZ',minimum[2]),('bbMaxZ',maximum[2]),('bbMaxY',maximum[1]),('bbMinX',minimum[0]),('fingerWidth',1.)):
        c.addAttr('AutoPlacing',longName=attr,attributeType='double',defaultValue=value,keyable=False)
    for part in ('Upper','Lower'):
        c.duplicate('CombinedSkin',name='CombinedSkin'+part+'_M');c.setAttr('CombinedSkin'+part+'_M.visibility',False)
    apply(host,plan,right_eye,skin,all_objects,keep_guides=True)
    template=c.getAttr(container+'.fitSkeletonTemplate') if c.objExists(container+'.fitSkeletonTemplate') else ''
    scan=c.curve(name='asFitScanCurve',degree=1,point=((minimum[0],0,0),(maximum[0],0,0)))
    shape=c.listRelatives(scan,shapes=True,type='nurbsCurve')[0]
    shape=c.rename(shape,'asFitScanCurveShape')
    c.setAttr(shape+'.overrideEnabled',True);c.setAttr(shape+'.overrideColor',14)
    c.parent(scan,'asFitScanCurves',absolute=True)
    s=SimpleNamespace(host=host,c=c,axis='',index=0,minimum_y=minimum[1],minimum_x=minimum[0],
        minimum_z=minimum[2],maximum_z=maximum[2],maximum_y=maximum[1],template=template,
        orbit_step=.2,hits=0,previous_hits=0,width=0.,previous_width=0.,max_width=0.,
        max_z_width=0.,y_at_max_z=0.,hit_crotch=False,crotch_index=0,crotch_width=0.,
        hit_armpit=False,armpit_width=0.,hit_neck=False,hit_head=False,hit_ankle=False,
        hit_arm_tip=False,hit_shoulder=False,arm_straight=False,first_split_x=0.,
        four_fingers=False,finger_grow_failed=False,max_finger_width=0.,has_ncloth=False,
        hit_thumb=False,nucleus='',stop=False,break_axis=False,step_y=0.,step_z=0.,direction=(0,0,1))
    def orbit_camera():
        if raw.getModifiers()!=4:return
        c.rotate(0,s.orbit_step,0,'asFitOrbitA',relative=True)
        raw.xform('persp',worldSpace=True,matrix=c.xform(orbit,query=True,worldSpace=True,matrix=True))
    s.orbit=orbit_camera;completed=[]
    # Maya's main progress bar belongs to the GUI. Standalone callers use the
    # same scanning loop without UI callbacks or synthetic reference results.
    progress=None
    if not raw.about(batch=True):
        from maya import mel
        progress=mel.eval('$advPyProgress=$gMainProgressBar;')
        raw.progressBar(progress,edit=True,status='Auto Place',beginProgress=True,isInterruptable=True,minValue=0,maxValue=300)
    try:
        for axis in FIT_AUTO_PLACE_AXES:
            s.axis=axis;s.break_axis=False;s.max_width=s.max_z_width=0.
            s.minimum_z=c.getAttr('AutoPlacing.bbMinZ');s.maximum_z=c.getAttr('AutoPlacing.bbMaxZ')
            s.maximum_y=c.getAttr('AutoPlacing.bbMaxY');s.minimum_x=c.getAttr('AutoPlacing.bbMinX')
            if axis.startswith('z'):
                translation=(0,0,s.maximum_z);rotation=(0,0,0);normal=(0,1,0)
            else:
                translation=(s.minimum_x,0 if axis=='x' else s.maximum_y,0);rotation=(0,-90,0)
                normal=(0,0,1) if axis=='x' else (1,0,0)
            c.setAttr(scan+'.translate',*translation,type='double3');c.setAttr(scan+'.rotate',*rotation,type='double3')
            s.index=0
            while s.index<100:
                if progress and raw.progressBar(progress,query=True,isCancelled=True):
                    finish(host,container,skin,all_objects);raise RuntimeError('AutoPlace 已中断')
                s.orbit()
                s.step_y=(s.maximum_y-s.minimum_y)/100. if not axis.startswith('y') else 0.
                s.step_z=s.minimum_x/50. if axis.startswith('y') else 0.
                s.direction=(0,0,1) if axis.startswith('z') else (1,0,0) if axis=='x' else (0,1,0)
                scale=.5 if s.index==99 else 1.
                c.move(0,s.step_y*scale,s.step_z*scale,scan,relative=True,objectSpace=True,worldSpaceDistance=True)
                s.project_on='CombinedSkinUpper_R' if axis in ('y','yElbowStraight') and c.objExists('CombinedSkinUpper_R') else 'CombinedSkin'
                s.previous_hits=s.hits;project(s,s.project_on);c.refresh()
                center=projected_curve(host,'asFitScanPolyProjectionCurves','center')
                s.previous_width=s.width
                s.bound_min=list(c.getAttr(center+'.boundingBoxMin')[0]);s.bound_max=list(c.getAttr(center+'.boundingBoxMax')[0])
                s.width=s.bound_max[0]-s.bound_min[0] if axis.startswith('z') else s.bound_max[2]-s.bound_min[2]
                if axis.startswith('z'):
                    for other in s.projected:
                        a=c.getAttr(other+'.boundingBoxMin')[0];b=c.getAttr(other+'.boundingBoxMax')[0]
                        if b[0]>s.bound_min[0] and a[0]<s.bound_max[0]:
                            s.bound_min[0]=min(s.bound_min[0],a[0]);s.bound_max[0]=max(s.bound_max[0],b[0]);s.width=s.bound_max[0]-s.bound_min[0]
                s.max_width=max(s.max_width,s.width);depth=s.bound_max[2]-s.bound_min[2]
                if depth>s.max_z_width:s.max_z_width=depth;s.y_at_max_z=c.getAttr(scan+'.translateY')
                s.center_x=(s.bound_min[0]+s.bound_max[0])/2.
                if axis=='zLoft' and not s.four_fingers:
                    finish(host,container,skin,all_objects)
                    return FitAutoPlaceResult(len(before.joints),tuple(completed),False,False)
                if axis.endswith('Loft'):
                    find,mesh=('right','CombinedSkinLower_R') if axis=='zLoft' and s.index<s.crotch_index else ('widest','CombinedSkinUpper_M') if axis=='yLoft' else ('widest','CombinedSkin')
                    if s.index==0:c.createNode('transform',name='asFitLoftCurves'+axis,parent='AutoPlacing',skipSelect=True)
                    name='Loft'+axis+str(s.index);save_projection(host,name,axis,mesh,find,False)
                    curve=projected_curve(host,'asFitProjection'+name,find)
                    others=[node for node in c.listRelatives('asFitProjection'+name,children=True) or [] if node!=curve]
                    if others:c.delete(others)
                    a=c.getAttr(curve+'.boundingBoxMin')[0];b=c.getAttr(curve+'.boundingBoxMax')[0]
                    name='asFitProjectionLoftCurve'+axis+str(s.index)
                    c.circle(name=name,center=(0,0,0),normal=normal,sweep=360,radius=1,degree=3,useTolerance=False,tolerance=.000393701,sections=8,constructionHistory=False)
                    c.parent(name,'asFitLoftCurves'+axis,absolute=True)
                    c.xform(name,worldSpace=True,translation=tuple((x+y)/2. for x,y in zip(a,b)))
                    c.setAttr(name+'.scale',*((y-x)/2. for x,y in zip(a,b)),type='double3')
                    if s.index==0:
                        first='asFitProjectionLoftCurve'+axis+'a';c.duplicate(name,name=first)
                        c.move(0,-s.step_y,0,first,relative=True);c.reorder(first,relative=-1)
                    if s.index==99 or axis=='yLoft' and s.index==50:build_loft(host,axis)
                    if axis=='yLoft' and s.index==50:break
                body_scan(s)
                if s.stop:break
                arm_scan(s)
                if s.break_axis:break
                detect_fingers(s);straighten_fingers(s);s.index+=1
            completed.append(axis)
            if s.stop:break
        if c.objExists('asFitPivotMiddleFinger1') and c.objExists('asFitPivotMiddleFinger4'):
            a=c.xform('asFitPivotMiddleFinger1',query=True,worldSpace=True,translation=True)
            b=c.xform('asFitPivotMiddleFinger4',query=True,worldSpace=True,translation=True)
            c.setAttr('asFitHandleWrist.translateX',a[0]-(b[0]-a[0]))
        detect_thumb(s);c.setAttr('CombinedSkinLower_M.visibility',True)
        for handle in c.listRelatives('asFitHandles',allDescendents=True,type='transform') or []:
            if not c.objExists(handle+'.xyz'):continue
            lock_trs(c,handle,True,True,True,True)
            channels=('translateY','rotateX') if c.getAttr(handle+'.xyz')==0 else ('translateX','rotateY') if c.getAttr(handle+'.xyz')==1 else ()
            for channel in channels:c.setAttr(handle+'.'+channel,lock=False,keyable=True)
        c.delete([node for node in (scan,'asFitScanPolyProjectionCurves','closestSampler') if c.objExists(node)])
        from_scan_curves(host,container);set_fat(host,container)
        constraints=c.listRelatives('asFitConstraints',children=True) or []
        if constraints:c.delete(constraints)
        from adv_py.application.registered_body_build import _refresh_fit_orientations_before_body
        with host.fit_manual_update_channels(container):
            host.normalize_fit_joint_names(container)
            host.normalize_fit_ik_labels(container)
            host.bake_fit_container_scale(container)
            _refresh_fit_orientations_before_body(host,container)
        from_scan_curves(host,container)
        c.setAttr('Root.visibility',True);straight_pole(host,'Leg');straight_pole(host,'Arm')
        c.select(clear=True)
        return FitAutoPlaceResult(len(before.joints),tuple(completed),s.four_fingers,True)
    finally:
        if progress:raw.progressBar(progress,edit=True,endProgress=True)
        raw.xform('persp',worldSpace=True,matrix=camera)
