"""ADV 6.925 AutoPlace phase orchestration, MEL 51771–52973."""
from contextlib import nullcontext
from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_AXES,FIT_AUTO_PLACE_GROUPS,FitAutoPlaceResult
from adv_py.core.fit_auto_scale import plan_fit_auto_scale
from .maya_fit_auto_scale import capture_combined,apply_scale_and_eye
from .maya_fit_auto_place_projection import projected_curve,save_projection,lock_trs,straight_pole,auto_orbit,defer_camera_restore
from .maya_fit_auto_place_body_scan import body_scan
from .maya_fit_auto_place_arm_scan import arm_scan
from .maya_fit_auto_place_fingers import detect_fingers,straighten_fingers,project
from .maya_fit_auto_place_thumb import detect_thumb
from .maya_fit_auto_place_loft import build_loft
from .maya_fit_auto_place_positions import from_scan_curves,set_fat
from .maya_fit_auto_place_guides import finish
from .maya_fit_auto_place_state import FitAutoPlaceScanState


def run(host,container,skin,all_objects,right_eye,*,return_scale=False):
    c=host._cmds
    display=c.jointDisplayScale(query=True)
    try:return _run(host,container,skin,all_objects,right_eye,return_scale=return_scale)
    except Exception:
        # Maya preferences are outside the scene's undo queue. A failed scan
        # must not leave the successful scale phase's global display setting.
        c.jointDisplayScale(display)
        raw=getattr(c,'raw',c)
        raw.polySelectConstraint(mode=0)
        raise


def _run(host,container,skin,all_objects,right_eye,*,return_scale=False):
    host._require_transaction();c=host._cmds;raw=getattr(c,'raw',c)
    if c.objExists('AutoPlacing'):return finish(host,container,skin,all_objects)
    selected=tuple(c.ls(selection=True,long=True) or ())
    scale_only=c.objExists('asFitAutoScale')
    if scale_only:
        host._transaction_changed=True
        c.delete('asFitAutoScale')
    if not c.objExists(container):
        raise ValueError('FitSkeleton does not exists, you must first import a FitSkeleton.')
    if not skin:
        raise ValueError('To use AutoPlace, you must first choose Skin geometry in the "Body>Pre" section.')
    from adv_py.application.model_check import CheckModel,ReviewModelCheck
    from .maya_model_checker import MayaModelCheckHost
    for geometry in skin:
        if not c.objExists(geometry):
            raise ValueError('Choosen Skin object"'+geometry+'" does not exist.')
        raw.select(host.scene_address(geometry),replace=True)
        game_engine=bool(raw.checkBox('asFaceGameEngineCheckBox',query=True,value=True)) \
            if raw.checkBox('asFaceGameEngineCheckBox',query=True,exists=True) else False
        checker=ReviewModelCheck if getattr(host,'_fit_auto_place_interactive',True) else CheckModel
        checker(MayaModelCheckHost()).execute(skip_symmetry=True,game_engine=game_engine)
    joints=c.listRelatives(container,allDescendents=True,type='joint') or ()
    if not joints:
        c.warning('No FitJoints found, Import a FitSkeleton first.')
        c.select(selected,replace=True) if selected else c.select(clear=True)
        if return_scale:
            from adv_py.application.fit_auto_scale import FitAutoScaleResult
            return FitAutoScaleResult(None,False)
        return FitAutoPlaceResult(0,(),False,False)
    host._transaction_changed=True
    c.createNode('transform',name='AutoPlacing',skipSelect=True)
    c.currentTime(1)
    try:c.setAttr('Root.visibility',False)
    except RuntimeError:pass
    c.createNode('transform',name='asFitOrbitA',parent='AutoPlacing',skipSelect=True)
    # Source creates under the global camera, then reparents absolutely.
    # The creation namespace still belongs to the selected character.
    with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
        raw.createNode('transform',name='asFitOrbitB',parent='persp',skipSelect=True)
    c.parent('asFitOrbitB','asFitOrbitA',absolute=True)
    for name in FIT_AUTO_PLACE_GROUPS[1:]:
        c.createNode('transform',name=name,parent='AutoPlacing',skipSelect=True)
        if name=='asFitPivots':
            c.createNode('transform',name='asFitPivotsFingers',parent=name,skipSelect=True)
            c.createNode('transform',name='asFitAnchors',parent='AutoPlacing',skipSelect=True)
    defer_camera_restore(host)
    if c.objExists('closestSampler'):c.delete('closestSampler')
    c.createNode('closestPointOnMesh',name='closestSampler',skipSelect=True)
    for mesh in dict.fromkeys((*skin,*all_objects)):
        try:raw.setAttr(host.scene_address(mesh)+'.visibility',False)
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
    before=capture_combined(host,container,'CombinedSkin')
    plan=plan_fit_auto_scale(before)
    eye_placed=apply_scale_and_eye(host,plan,right_eye)
    if scale_only:
        finish(host,container,skin,all_objects)
        c.select(selected,replace=True) if selected else c.select(clear=True)
        if return_scale:
            from adv_py.application.fit_auto_scale import FitAutoScaleResult
            return FitAutoScaleResult(plan,eye_placed)
        return FitAutoPlaceResult(len(before.joints),(),False,False)
    template=c.getAttr(container+'.fitSkeletonTemplate') if c.objExists(container+'.fitSkeletonTemplate') else ''
    scan=c.curve(name='asFitScanCurve',degree=1,point=((minimum[0],0,0),(maximum[0],0,0)))
    shape=c.listRelatives(scan,shapes=True,type='nurbsCurve')[0]
    shape=c.rename(shape,'asFitScanCurveShape')
    c.setAttr(shape+'.overrideEnabled',True);c.setAttr(shape+'.overrideColor',14)
    c.parent(scan,'asFitScanCurves',absolute=True)
    s=FitAutoPlaceScanState(host=host,c=c,minimum_y=minimum[1],minimum_x=minimum[0],
        minimum_z=minimum[2],maximum_z=maximum[2],maximum_y=maximum[1],template=template)
    def orbit_camera():
        auto_orbit(host,s.orbit_step)
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
            c.setAttr(scan+'.translate',*translation,type='float3');c.setAttr(scan+'.rotate',*rotation,type='float3')
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
                s.previous_hits=s.hits;project(s,s.project_on,refresh=True)
                center=projected_curve(host,'asFitScanPolyProjectionCurves','center')
                s.center_curve=center
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
                    c.setAttr(name+'.scale',*((y-x)/2. for x,y in zip(a,b)),type='float3')
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
        host.manual_update_fit(container)
        from_scan_curves(host,container)
        c.setAttr('Root.visibility',True);straight_pole(host,'Leg');straight_pole(host,'Arm')
        c.select(clear=True)
        return FitAutoPlaceResult(len(before.joints),tuple(completed),s.four_fingers,True)
    finally:
        if progress:raw.progressBar(progress,edit=True,endProgress=True)
