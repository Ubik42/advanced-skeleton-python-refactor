"""asAlignFKIK/asSwitchFKIK Spline branch, MEL 10978–11439.

Curve-based FK→IK intentionally has the same approximate result as ADV. It
does not require the optional least-squares pose-transfer extension.
"""
from contextlib import contextmanager
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_spline_animation import source_spline_align_order,source_spline_nearest_deform


def enable_first_translation(host,registration):
    """Upgrade the old Python-only first-control lock without replacing its graph."""
    from adv_py.core.body_spline import BodySplinePlan
    from adv_py.core.character_registry import CharacterChannel
    host._require_transaction()
    plans=(registration.spine,*registration.additional_spines)
    if not any(isinstance(plan,BodySplinePlan) and plan.source_curve_points
               and not plan.source_first_translate for plan in plans):return registration
    c=host._cmds
    channels=list(registration.channels)
    known={(ch.node,ch.attribute) for ch in channels}
    updated=[]
    for plan in plans:
        if not isinstance(plan,BodySplinePlan) or not plan.source_curve_points or plan.source_first_translate:
            updated.append(plan);continue
        prefix='source.spline'+('.'+plan.system_name if plan.system_name else '')
        for index,control in enumerate(plan.targets):
            kinds=('translate','rotate') if index==0 else ('rotate',)
            for kind in kinds:
                for axis in 'XYZ':
                    attribute=kind+axis
                    plug=control+'.'+attribute
                    if (control,attribute) in known:continue
                    if c.connectionInfo(plug,sourceFromDestination=True):
                        raise CharacterRegistryError('来源 Spline 待升级通道已有外部输入：'+plug)
                    c.setAttr(plug,lock=False,keyable=True)
                    channels.append(CharacterChannel(prefix+'.'+str(index)+'.'+attribute,control,attribute))
                    known.add((control,attribute))
        updated.append(replace(plan,source_first_translate=True))
    host._transaction_changed=True
    result=replace(registration,spine=updated[0],additional_spines=tuple(updated[1:]),channels=tuple(channels))
    host.write_character_registration_extension(registration,result)
    return result


@contextmanager
def _restore_selection(c):
    selected=c.ls(selection=True,long=True) or []
    try:yield
    finally:
        surviving=[node for node in selected if c.objExists(node)]
        c.select(surviving,replace=True) if surviving else c.select(clear=True)


def _custom_orient(c,control):
    """Original correction, using the actual custom-orient parent if present."""
    leaf=control.rsplit('|',1)[-1]
    namespace,separator,name=leaf.rpartition(':')
    prefix=namespace+':' if separator else ''
    from .maya_original_control_identity import command_registration, control_roles
    actual=name if separator else leaf
    role=control_roles(command_registration(c,namespace)).get(actual,actual)
    candidates=tuple(dict.fromkeys((prefix+'CustomOrient'+actual,prefix+'CustomOrient'+role)))
    matches=list(dict.fromkeys(path for candidate in candidates
                              for path in c.ls(candidate,long=True) or []))
    if not matches:return
    if len(matches)!=1:raise CharacterRegistryError('自定义朝向节点不唯一：'+control)
    custom=matches[0]
    parent=(c.listRelatives(custom,parent=True,fullPath=True) or [None])[0]
    temporary=c.createNode('transform',name='AdvPy_CustomOrientWithRotateOrder',parent=parent,skipSelect=True)
    try:
        c.setAttr(temporary+'.rotateOrder',c.getAttr(control+'.rotateOrder'))
        c.orientConstraint(custom,temporary,maintainOffset=False)
        rotation=c.xform(temporary,query=True,objectSpace=True,rotation=True)
    finally:c.delete(temporary)
    c.xform(control,relative=True,objectSpace=True,rotation=rotation)
    if c.getAttr(custom+'.scaleX')<0:
        rotation=c.xform(control,query=True,worldSpace=True,rotation=True)
        try:
            c.setAttr(custom+'.scale',1.,1.,1.,type='float3')
            c.xform(control,worldSpace=True,rotation=rotation)
        finally:c.setAttr(custom+'.scale',-1.,-1.,-1.,type='float3')
        if c.attributeQuery('worldorient',node=control,exists=True) and c.getAttr(control+'.worldorient'):
            c.rotate(*c.xform(custom,query=True,objectSpace=True,rotation=True),control,
                     relative=True,objectSpace=True)


def _endpoint_rotation(host,registration,binding,index):
    """Evaluate the original AlignIKTo rest offset in the current FKX frame."""
    import maya.api.OpenMaya as om
    c=host._cmds
    plan=binding.plan
    body_index=0 if index==0 else len(plan.body_joints)-1
    control=plan.targets[index]
    driver=binding.fk_drivers[body_index]
    rest=next(joint.matrix for joint in registration.body if joint.path==plan.body_joints[body_index])
    # Strip scale from the bind frame: AlignIKTo inherits FKX orientation;
    # controller axes are a constant rest offset, not an Euler copy.
    axes=(plan.source_control_axes[index] if plan.source_control_axes and plan.source_ik_local
          else ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)) if plan.source_world_controls else plan.axes)
    target=om.MMatrix((*axes[0],0.,*axes[1],0.,*axes[2],0.,0.,0.,0.,1.))
    rest_matrix=om.MTransformationMatrix(om.MMatrix(rest))
    rest_matrix.setTranslation(om.MVector(),om.MSpace.kTransform)
    rest_matrix.setScale((1.,1.,1.),om.MSpace.kTransform)
    temporary=c.createNode('transform',name='AdvPy_SplineAlignIKTo',parent=driver,skipSelect=True)
    try:
        c.xform(temporary,objectSpace=True,matrix=tuple(target*rest_matrix.asMatrix().inverse()))
        c.xform(temporary,preserve=True,rotateOrder=('xyz','yzx','zxy','xzy','yxz','zyx')[int(c.getAttr(control+'.rotateOrder'))])
        return tuple(c.xform(temporary,query=True,worldSpace=True,rotation=True))
    finally:c.delete(temporary)


def align(host,registration,binding,mode,*,baking=False):
    host._require_transaction()
    if mode not in ('fk','ik'):raise CharacterRegistryError('来源 Spline 对齐方向需要 fk / ik')
    c=host._cmds
    plan=binding.plan
    auto=bool(c.autoKeyframe(query=True,state=True))
    host._transaction_changed=True
    with _restore_selection(c):
        c.autoKeyframe(state=bool(baking))
        try:
            if mode=='fk':
                # Capture every IKX before moving its parent FK controller.
                frames=tuple((tuple(c.xform(driver,query=True,worldSpace=True,translation=True)),
                              tuple(c.xform(driver,query=True,worldSpace=True,rotation=True)))
                             for driver in binding.ik_drivers)
                for control,(position,rotation) in zip(binding.fk_controls,frames):
                    if not any(ch.node==control for ch in registration.channels):continue
                    for _ in range(2):
                        c.xform(control,worldSpace=True,translation=position,rotation=rotation)
                    _custom_orient(c,control)
                return
            positions=tuple(tuple(c.xform(joint,query=True,worldSpace=True,translation=True))
                            for joint in binding.physical_chain)
            deform=(c.listRelatives('DeformationSystem',allDescendents=True,type='joint',fullPath=True)
                    if c.objExists('DeformationSystem') else [joint.path for joint in registration.body]) or []
            deform_positions=tuple((joint,tuple(c.xform(joint,query=True,worldSpace=True,translation=True)))
                                   for joint in deform)
            deform_rotations={joint:tuple(c.xform(joint,query=True,worldSpace=True,rotation=True))
                              for joint in deform}
            # End orientation must be read before Hybrid parenting changes FKX.
            endpoint={len(plan.targets)-1:_endpoint_rotation(host,registration,binding,len(plan.targets)-1)}
            if plan.body_joints[0].rsplit('|',1)[-1].rsplit(':',1)[-1]=='Root_M':
                endpoint[0]=_endpoint_rotation(host,registration,binding,0)
            curve=c.curve(name='AdvPy_FK2IKCurve',degree=1,point=positions)
            info=None
            try:
                curve=c.rebuildCurve(curve,constructionHistory=False,replaceOriginal=True,
                    rebuildType=0,endKnots=1,keepRange=0,keepControlPoints=False,
                    keepEndPoints=True,keepTangents=False,spans=0,degree=3,tolerance=.01)[0]
                shape=(c.listRelatives(curve,shapes=True,fullPath=True) or [None])[0]
                info=c.createNode('pointOnCurveInfo',name='AdvPy_FK2IKCurveInfo',skipSelect=True)
                c.setAttr(info+'.turnOnPercentage',True)
                c.connectAttr(shape+'.worldSpace[0]',info+'.inputCurve')
                def sample(index):
                    c.setAttr(info+'.parameter',index/(len(plan.targets)-1.))
                    return tuple(c.getAttr(info+'.position')[0])
                for index,control in enumerate(plan.hybrid_controls):
                    position=sample(index)
                    nearest=source_spline_nearest_deform(position,deform_positions)
                    c.xform(control,worldSpace=True,translation=position,rotation=deform_rotations[nearest])
                    _custom_orient(c,control)
                for index in source_spline_align_order(len(plan.targets)):
                    control=plan.targets[index]
                    c.xform(control,worldSpace=True,translation=sample(index))
                    c.setAttr(control+'.rotate',0.,0.,0.)
                    if index in endpoint:c.xform(control,worldSpace=True,rotation=endpoint[index])
                    if index==0:_custom_orient(c,control)
            finally:
                if info is not None and c.objExists(info):c.delete(info)
                if c.objExists(curve):c.delete(curve)
            c.warning('与原版 ADV 一致：FK 转曲线 IK 时，目标可能无法完全对齐。')
        finally:c.autoKeyframe(state=auto)


def _key(c,binding):
    c.setKeyframe(binding.blend_plug)
    for control in binding.controls:
        for attr in ('translate','rotate'):
            c.setKeyframe(control,attribute=attr)


def switch(host,registration,binding,mode,*,time_range=None):
    """Original preceding-frame keys, two align passes and optional range bake."""
    host._require_transaction()
    c=host._cmds
    if mode not in ('fk','ik'):raise CharacterRegistryError('来源 Spline 切换方向需要 fk / ik')
    target=binding.plan.mode_maximum if mode=='ik' else 0.
    inverse=binding.plan.mode_maximum-target
    current=float(c.currentTime(query=True))
    start,end=(current,current+1.) if time_range is None else time_range
    from math import isfinite
    if (not isfinite(start) or not isfinite(end) or end<=start):
        raise CharacterRegistryError('Spline 切换区间需要有限且递增的时间')
    ranged=end-start>1.
    if ranged:c.currentTime(start,edit=True,update=True)
    frame=float(c.currentTime(query=True))
    if abs(float(c.getAttr(binding.blend_plug))-inverse)>1e-8:
        c.warning('当前 Spline 混合值不在源 FK / IK 端点，不能切换。')
        c.currentTime(current,edit=True,update=True)
        return False
    auto=bool(c.autoKeyframe(query=True,state=True))
    host._transaction_changed=True
    with _restore_selection(c):
        try:
            if ranged:c.autoKeyframe(state=True)
            keying=auto or ranged
            c.currentTime(frame-1.,edit=True,update=True)
            c.setAttr(binding.blend_plug,inverse)
            for pass_index in range(2):
                if not keying and pass_index==0:continue
                if keying:_key(c,binding)
                c.currentTime(float(c.currentTime(query=True))+1.,edit=True,update=True)
                align(host,registration,binding,mode)
                c.setAttr(binding.blend_plug,target)
            if ranged:
                bake_frame=start+1.
                while bake_frame<end:
                    c.currentTime(bake_frame,edit=True,update=True)
                    align(host,registration,binding,mode,baking=True)
                    bake_frame+=1.
                c.setKeyframe(binding.blend_plug,time=end-1.,value=target)
                c.setKeyframe(binding.blend_plug,time=end,value=inverse)
                # Maya versions without highlighted-range setters still bake.
                try:c.playbackOptions(selectionStartTime=start,selectionEndTime=end-1.,selectionVisible=True)
                except (TypeError,RuntimeError):pass
            return True
        finally:
            c.currentTime(frame,edit=True,update=True)
            # asSwitchFKIK enables Auto Key for a highlighted range and
            # retains it (the source updates its local autoKey flag to 1).
            c.autoKeyframe(state=auto or ranged)
