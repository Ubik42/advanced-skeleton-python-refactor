"""Original asAlignFKIK order on the registered source RP graph."""
from math import sqrt
from types import SimpleNamespace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_limb_animation import resolve_source_limb


def _plug(registration,binding):
    channel=next(ch for ch in registration.channels if ch.key==binding.blend_key)
    return channel.node+'.'+channel.attribute


def _ik_value(registration,binding):
    channel=next(ch for ch in registration.channels if ch.key==binding.blend_key)
    return 10. if channel.attribute=='FKIKBlend' else 1.


def _set(host,registration,node,attribute,value):
    c=host._cmds
    if not any(ch.node==node and ch.attribute==attribute for ch in registration.channels):
        if abs(float(c.getAttr(node+'.'+attribute))-value)<=1e-8:
            return
        raise CharacterRegistryError('来源 RP 匹配目标没有动画登记：'+node+'.'+attribute)
    if not c.getAttr(node+'.'+attribute,settable=True):
        raise CharacterRegistryError('来源 RP 匹配目标不可写：'+node+'.'+attribute)
    c.setAttr(node+'.'+attribute,value)


def _reset_control_attributes(host,registration,binding,role,control):
    from .maya_original_transform_channels import reset_original_custom_attributes
    reset_original_custom_attributes(host._cmds,control,
        set_value=lambda node,attribute,value:_set(host,registration,node,attribute,value),
        source_name=role+binding.label+'_'+binding.side)


def _reset_ik(host,registration,binding):
    """MEL 10822: only ControlSet descendants, leaving parent Extra intact."""
    c=host._cmds
    _reset_control_attributes(host,registration,binding,'IK',binding.ik_control)
    for control in c.listRelatives(binding.ik_control,allDescendents=True,
                                   type='transform',fullPath=True) or []:
        if not c.sets(control,isMember='ControlSet'):
            continue
        for kind in ('translate','rotate'):
            # The MEL compound reset tests tx/rx once, not each child lock.
            if c.getAttr(control+'.'+kind+'X',lock=True):
                continue
            for axis in 'XYZ':
                if not any(ch.node==control and ch.attribute==kind+axis
                           for ch in registration.channels):
                    raise CharacterRegistryError('来源 IK 子控制器没有动画登记：'+control)
            c.setAttr(control+'.'+kind,0.,0.,0.,type='float3')
    if c.objExists(binding.ik_control+'.legAim'):
        _set(host,registration,binding.ik_control,'legAim',0.)


def _position(host,registration,control,driver,target):
    """Translate the main control by the evaluated FKX displacement."""
    c=host._cmds
    actual=host._spine_world_frame(driver)[0][12:15]
    if max(abs(a-b) for a,b in zip(actual,target))<=1e-8:
        return
    for axis in 'XYZ':
        if not any(ch.node==control and ch.attribute=='translate'+axis
                   for ch in registration.channels):
            raise CharacterRegistryError('来源 FK 位移锁定，无法对齐骨段：'+control)
    origin=host._spine_world_frame(control)[0][12:15]
    c.xform(control,worldSpace=True,translation=tuple(o+t-a
            for o,t,a in zip(origin,target,actual)))


def _scale(host,registration,control,driver,target):
    c=host._cmds
    actual=tuple(c.getAttr(driver+'.scale')[0])
    values=tuple(c.getAttr(control+'.scale')[0])
    for axis,value,current,desired in zip('XYZ',values,actual,target):
        if abs(current-desired)<=1e-8:
            continue
        if abs(current)<=1e-8:
            raise CharacterRegistryError('来源 RP 匹配缩放退化：'+driver)
        _set(host,registration,control,'scale'+axis,value*desired/current)


def _pole_weights(host,binding):
    """MEL asGetAttrOPM chooses the largest-magnitude tx/OPM translation."""
    if binding.pole_offsets is None:
        return None
    result=[]
    c=host._cmds
    for path in binding.pole_offsets:
        value=float(c.getAttr(path+'.translateX'))
        if c.objExists(path+'.offsetParentMatrix'):
            matrix=c.getAttr(path+'.offsetParentMatrix')
            if len(matrix)==1 and isinstance(matrix[0],(tuple,list)):matrix=matrix[0]
            opm_value=float(matrix[12])
            if abs(opm_value)>abs(value):value=opm_value
        result.append(abs(value))
    return tuple(result)


def _qtoes(binding):
    """QToes are the existing Foot branch, including single-joint feet."""
    drivers={row.fk_driver for row in binding.hybrid_controls}
    if binding.reverse_roll and binding.toe_source:
        drivers.add(binding.toe_source)
    return tuple(row for row in binding.joints[binding.primary_count:]
                 if row.fk_driver in drivers)


def _align_ik_rotation(c, control, align):
    """Match AlignIKTo's Euler order before querying world rotation."""
    order=c.xform(control,query=True,rotateOrder=True)
    c.xform(align,preserve=True,rotateOrder=order)
    c.xform(control,worldSpace=True,rotation=tuple(c.xform(
        align,query=True,worldSpace=True,rotation=True)))


def _matching_scale(c, binding, maximum):
    if maximum==10.:
        # MEL divides by this actual graph output, not the magnitude of
        # Main's world X axis. Negative/nonuniform authored scale matters.
        return (float(c.getAttr('MainScaleMultiplyDivide.outputX'))
                if c.objExists('MainScaleMultiplyDivide') else 1.)
    world=c.xform(binding.global_control,query=True,worldSpace=True,matrix=True)
    return sqrt(sum(v*v for v in world[:3]))


def _align_fk_original(host, registration, binding):
    """asAlignFKIK IK2FK RP branch, MEL 11046–11107.

    Use Maya's world Euler operation and authored custom-orient correction.
    Do not solve around the user's Extra/Sub rotations: ADV does not do so.
    """
    c=host._cmds
    from .maya_source_spline_matching import _custom_orient
    primary=tuple(binding.joints[index] for index in dict.fromkeys(
        (0,binding.middle_index,binding.primary_count-1)))
    toe=next((row for row in binding.joints[binding.primary_count:]
              if binding.toe_control and row.fk_driver==binding.toe_source),None)
    qtoes=_qtoes(binding)
    targets={row.body:(tuple(c.xform(row.ik_driver,query=True,worldSpace=True,
                                   translation=True)),
                       tuple(c.xform(row.ik_driver,query=True,worldSpace=True,
                                   rotation=True)),
                       tuple(c.getAttr(row.body+'.scale')[0]))
             for row in (*primary,*((toe,) if toe else ()),*qtoes)}
    end_scale=tuple(c.xform(binding.ik_control,query=True,objectSpace=True,
                            relative=True,scale=True))
    def orient(row):
        if row.control==row.fk_driver:
            raise CharacterRegistryError('来源 RP 缺少原版 FK 控制器：'+row.body)
        c.xform(row.control,worldSpace=True,rotation=targets[row.body][1])
        _custom_orient(c,row.control)
    for row in primary:
        c.xform(row.control,objectSpace=True,translation=(0.,0.,0.))
        orient(row)
    for axis,value in zip('XYZ',end_scale):
        _set(host,registration,primary[-1].control,'scale'+axis,float(value))
    if toe:
        c.xform(toe.control,objectSpace=True,translation=(0.,0.,0.))
        orient(toe)
    for row in primary[:-1]:
        for axis,value in zip('XYZ',targets[row.body][2]):
            _set(host,registration,row.control,'scale'+axis,float(value))
    for row in primary[1:]:
        c.xform(row.control,worldSpace=True,translation=targets[row.body][0])
    if (qtoes and c.objExists(binding.ik_control+'.toesAim')
            and c.getAttr(binding.ik_control+'.toesAim')>0):
        orient(qtoes[0])
    for row in reversed(qtoes):
        c.xform(row.control,worldSpace=True,translation=targets[row.body][0])
        orient(row)


def apply(host,registration,binding,mode, *,baking_mocap=False,
          align_only=False,force=False,baking=False):
    host._require_transaction()
    if mode not in ('fk','ik'):
        raise CharacterRegistryError('来源 RP 对齐方向需要 fk / ik')
    c=host._cmds
    blend=_plug(registration,binding)
    value=float(c.getAttr(blend))
    maximum=_ik_value(registration,binding)
    target=maximum if mode=='ik' else 0.
    if value==target and not force:
        return
    if value not in (0.,maximum) and not force:
        raise CharacterRegistryError('来源 RP 对齐要求处于 FK 或 IK 端点')
    if mode=='ik' and any(abs(length.rest_length)<=1e-8 for length in binding.lengths):
        raise CharacterRegistryError('来源 RP Lenght 匹配的原版 tx 分母为零；该 FreeOrient 骨段无法执行长度匹配')
    host._transaction_changed=True
    auto=bool(c.autoKeyframe(query=True,state=True))
    selection=c.ls(selection=True,long=True) or []
    try:
        c.autoKeyframe(state=bool(baking))
        if mode=='ik':
            pole_weights=_pole_weights(host,binding)
            length_frames={path:host._spine_world_frame(path)[0][12:15]
                           for length in binding.lengths for path in (length.start_fk,length.end_fk)}
            end=binding.primary_count-1
            end_row=binding.joints[end]
            # Saved pre-correction bindings used the FK receiver for this
            # role. Resolve it to the primary FK control without changing
            # authored QToes, whose final FK control remains the target.
            qtoes=_qtoes(binding)
            position_source=qtoes[-1].control if qtoes else end_row.control
            position=host._spine_world_frame(position_source)[0][12:15]
            align=host._spine_world_frame(binding.align)[0]
            toe_frame=(host._spine_world_frame(binding.toe_align)[0]
                       if binding.toe_align else host._spine_world_frame(binding.toe_source)[0]
                       if binding.toe_source else None)
            hybrid_frames=tuple((row.control,host._spine_world_frame(row.fk_driver)[0])
                                for row in binding.hybrid_controls)
            scale=tuple(c.xform(end_row.control,query=True,objectSpace=True,
                               relative=True,scale=True))
            body_scale=tuple(c.getAttr(end_row.body+'.scale')[0])
            _reset_ik(host,registration,binding)
            # The original end control is positioned before orienting; Foot
            # roll controls are reset first so the aligned receiver is stable.
            c.xform(binding.ik_control,worldSpace=True,translation=position)
            if maximum==10.:
                _align_ik_rotation(c,binding.ik_control,binding.align)
            else:
                host._spine_set_world_rotation(binding.ik_control,align)
            _reset_control_attributes(host,registration,binding,'Pole',binding.pole_control)
            global_scale=_matching_scale(c,binding,maximum)
            from .maya_source_limb_pole import sample_original_matching_pole
            pole=sample_original_matching_pole(host,binding,pole_weights,baking_mocap=baking_mocap)
            c.xform(binding.pole_control,worldSpace=True,translation=pole)
            if binding.toe_control and toe_frame is not None:
                if c.objExists(binding.ik_control+'.roll'):
                    _set(host,registration,binding.ik_control,'roll',0.)
                if maximum==10. and binding.toe_align:
                    c.xform(binding.toe_control,worldSpace=True,rotation=tuple(c.xform(
                        binding.toe_align,query=True,worldSpace=True,rotation=True)))
                else:
                    host._spine_set_world_rotation(binding.toe_control,toe_frame)
            for axis,v in zip('XYZ',body_scale):
                _set(host,registration,binding.ik_control,'scale'+axis,float(v))
            if binding.lengths:
                _set(host,registration,binding.ik_control,'stretchy',10.)
                _set(host,registration,binding.ik_control,'volume',10.)
            # MEL 10924–10932: position again from FKX after the graph's
            # stretch/volume settings, then copy end FK local scale.
            final_source=qtoes[-1].control if qtoes else end_row.fk_driver
            c.xform(binding.ik_control,worldSpace=True,translation=
                    host._spine_world_frame(final_source)[0][12:15])
            for axis,v in zip('XYZ',scale):
                _set(host,registration,binding.ik_control,'scale'+axis,float(v))
            if binding.lengths:
                ratio=float(c.getAttr(binding.ratio_node))
                if abs(global_scale)<=1e-8 or abs(ratio)<=1e-8:
                    raise CharacterRegistryError('来源 RP 匹配长度比例退化')
                for length in binding.lengths:
                    a,b=length_frames[length.start_fk],length_frames[length.end_fk]
                    distance=sqrt(sum((x-y)**2 for x,y in zip(a,b)))
                    _set(host,registration,binding.ik_control,length.attribute,
                         distance*length.fraction/(length.rest_length*global_scale*ratio))
            if binding.reverse_roll:
                if maximum==10.:
                    from .maya_source_limb_reverse_roll import align_original_reverse_roll
                    align_original_reverse_roll(host,binding)
                else:
                    from adv_py.core.fit_symmetry import FitBuildSide
                    host._match_body_leg_hybrid_roll(SimpleNamespace(
                        reverse_roll_control_path=binding.reverse_roll,
                        reverse_roll_handle_name=binding.reverse_handle,
                        body_joint_paths=tuple(row.fk_driver for row in
                            (binding.joints[0],binding.joints[binding.middle_index],binding.joints[end])),
                        side=FitBuildSide(binding.side)))
            for control,frame in reversed(hybrid_frames):
                if maximum==10.:
                    driver=next(row.fk_driver for row in binding.hybrid_controls if row.control==control)
                    c.xform(control,worldSpace=True,rotation=tuple(c.xform(
                        driver,query=True,worldSpace=True,rotation=True)))
                else:
                    host._spine_set_world_rotation(control,frame)
            if not align_only:
                _set(host,registration,next(ch.node for ch in registration.channels
                     if ch.key==binding.blend_key),blend.rsplit('.',1)[1],maximum)
        else:
            if maximum==10.:
                leg_aim_rotation=(tuple(c.xform(binding.leg_aim_control,
                    query=True,worldSpace=True,rotation=True)) if binding.leg_aim_control else None)
                _align_fk_original(host,registration,binding)
                if not align_only:
                    _set(host,registration,next(ch.node for ch in registration.channels
                         if ch.key==binding.blend_key),blend.rsplit('.',1)[1],0.)
                if leg_aim_rotation is not None and not align_only:
                    c.xform(binding.leg_aim_control,worldSpace=True,rotation=leg_aim_rotation)
                return
            targets=tuple((host._spine_world_frame(row.ik_driver),
                           tuple(c.getAttr(row.body+'.scale')[0]))
                          for row in binding.joints)
            leg_aim_frame = (host._spine_world_frame(binding.leg_aim_control)[0]
                             if binding.leg_aim_control else None)
            if leg_aim_frame is not None:
                # Removing IK weight removes the LegAim layer. Preserve its
                # evaluated parent orientation before solving child FK axes.
                _set(host,registration,next(ch.node for ch in registration.channels
                     if ch.key==binding.blend_key),blend.rsplit('.',1)[1],0.)
                host._spine_set_world_rotation(binding.leg_aim_control,leg_aim_frame)
            # Parent first: every target is captured before writing controls.
            # FKX offset and Extra/Sub contributions remain intact.
            for row,((frame,axes),scale) in zip(binding.joints,targets):
                if row.control==row.fk_driver:
                    # MEL may omit a terminal FK control (control=off). Keep
                    # it in graph identity without treating the solver joint
                    # as an editable controller during conversion.
                    actual = host._spine_world_frame(row.fk_driver)[0]
                    if max(abs(a-b) for a,b in zip(actual,frame))>1e-4:
                        raise CharacterRegistryError('来源无 FK 控制的末端无法表示该 IK 姿态：'+row.body)
                    continue
                host._match_limb_fk_driver_axes(row.control,row.fk_driver,axes)
                _position(host,registration,row.control,row.fk_driver,frame[12:15])
                _scale(host,registration,row.control,row.fk_driver,scale)
            _set(host,registration,next(ch.node for ch in registration.channels
                 if ch.key==binding.blend_key),blend.rsplit('.',1)[1],0.)
    finally:
        c.autoKeyframe(state=auto)
        c.select(selection,replace=True) if selection else c.select(clear=True)


def _key_original_switch(c,registration,binding):
    """asSwitchFKIK RP key list, MEL 11320–11377."""
    c.setKeyframe(_plug(registration,binding))
    primary=tuple(binding.joints[index] for index in
                  (0,binding.middle_index,binding.primary_count-1))
    for index,row in enumerate(primary):
        kinds=('rotate','scale') if index==0 else ('translate','rotate','scale')
        for kind in kinds:
            c.setKeyframe(row.control,attribute=kind)
    toe=next((row for row in binding.joints[binding.primary_count:]
              if binding.toe_control and row.fk_driver==binding.toe_source),None)
    if toe:c.setKeyframe(toe.control,attribute='rotate')
    for kind in ('translate','rotate','scale'):
        c.setKeyframe(binding.ik_control,attribute=kind)
    c.setKeyframe(binding.pole_control,attribute='translate')
    for control in (binding.ik_control,binding.pole_control):
        for attribute in c.listAttr(control,userDefined=True) or []:
            from adv_py.core.character_generated_attributes import GENERATED_CHARACTER_ATTRIBUTES
            # Python's closed metadata list is not part of the source's
            # custom animation attributes. Unknown authored names survive.
            if attribute in GENERATED_CHARACTER_ATTRIBUTES:continue
            if c.getAttr(control+'.'+attribute,type=True) in ('string','message'):continue
            c.setKeyframe(control,attribute=attribute)
    from .maya_original_control_identity import control_roles, leaf
    roles=control_roles(registration)
    role_controls={role:name for name,role in roles.items()}
    for control in c.listRelatives(binding.ik_control,allDescendents=True,
                                   type='transform',fullPath=True) or []:
        if not c.sets(control,isMember='ControlSet'):continue
        for kind in ('translate','rotate'):c.setKeyframe(control,attribute=kind)
        # MEL derives each equivalent FK from the actual keyed child by
        # substituting the first Roll token. Do not key every QToes control
        # unconditionally or add LegAim to the original switch key list.
        source_role=roles.get(leaf(control),leaf(control))
        target_role=source_role.replace('Roll','FK',1)
        equivalent=role_controls.get(target_role,target_role)
        if c.objExists(equivalent):
            for kind in ('translate','rotate'):c.setKeyframe(equivalent,attribute=kind)


def switch(host,registration,binding,mode,*,time_range=None,baking_mocap=False):
    """Original two-pass RP switch and highlighted-range bake, 11216–11439."""
    from math import isfinite
    if mode not in ('fk','ik'):
        raise CharacterRegistryError('来源 RP 切换方向需要 fk / ik')
    host._require_transaction()
    c=host._cmds
    maximum=_ik_value(registration,binding)
    target=maximum if mode=='ik' else 0.
    inverse=maximum-target
    original_time=float(c.currentTime(query=True))
    start,end=(original_time,original_time+1.) if time_range is None else time_range
    if not isfinite(start) or not isfinite(end) or end<=start:
        raise CharacterRegistryError('来源 RP 切换区间需要有限且递增的时间')
    ranged=end-start>1.
    if ranged:c.currentTime(start,edit=True,update=True)
    frame=float(c.currentTime(query=True))
    plug=_plug(registration,binding)
    if float(c.getAttr(plug))!=inverse:
        c.warning('当前 FKIKBlend 不在源 FK / IK 端点，不能切换。')
        return False
    auto=bool(c.autoKeyframe(query=True,state=True))
    selected=c.ls(selection=True,long=True) or []
    leg_rotation=(tuple(c.xform(binding.leg_aim_control,query=True,
        worldSpace=True,rotation=True)) if binding.leg_aim_control else None)
    host._transaction_changed=True
    try:
        if ranged:c.autoKeyframe(state=True)
        keying=auto or ranged
        c.currentTime(frame-1.,edit=True,update=True)
        c.setAttr(plug,inverse)
        for pass_index in range(2):
            if not keying and pass_index==0:continue
            if keying:_key_original_switch(c,registration,binding)
            c.currentTime(float(c.currentTime(query=True))+1.,edit=True,update=True)
            apply(host,registration,binding,mode,align_only=True,force=True,
                  baking_mocap=baking_mocap)
            c.setAttr(plug,target)
            if leg_rotation is not None:
                c.xform(binding.leg_aim_control,worldSpace=True,rotation=leg_rotation)
        if ranged:
            bake_frame=start+1.
            while bake_frame<end:
                c.currentTime(bake_frame,edit=True,update=True)
                apply(host,registration,binding,mode,align_only=True,force=True,
                      baking=True,baking_mocap=baking_mocap)
                bake_frame+=1.
            c.setKeyframe(plug,time=end-1.,value=target)
            c.setKeyframe(plug,time=end,value=inverse)
            try:c.playbackOptions(selectionStartTime=start,
                selectionEndTime=end-1.,selectionVisible=True)
            except (TypeError,RuntimeError):pass
        return True
    finally:
        c.currentTime(frame,edit=True,update=True)
        c.autoKeyframe(state=auto or ranged)
        surviving=[node for node in selected if c.objExists(node)]
        c.select(surviving,replace=True) if surviving else c.select(clear=True)


def samples(host,registration,frames,label,side,mode,tolerance=1e-4, *,baking_mocap=False):
    binding=resolve_source_limb(registration,label,side.value)
    result=[]
    with host._character_sampling_time(preserve_modified=False) as seek:
        for frame in frames:
            seek(frame)
            before=host.capture_character_pose(registration)
            with host._character_static_controls(registration,before):
                apply(host,registration,binding,mode,baking_mocap=baking_mocap)
                after=host.capture_character_pose(registration)
                error=max(abs(a-b) for (_,left),(_,right) in
                    zip(before.body_frames,after.body_frames) for a,b in zip(left,right))
                if error>tolerance:
                    raise CharacterRegistryError('来源 RP 匹配改变身体姿态：'
                        +binding.label+' '+binding.side+' frame='+str(frame)+' error='+str(error))
                result.append((float(frame),after))
    return tuple(result)


def sample_helpers(host,registration,frames,label,side):
    binding=resolve_source_limb(registration,label,side)
    body_paths={row.body for row in binding.joints}
    # Part descendants belong to the same deformation span and must survive
    # matching too, rather than comparing only the three RP endpoints.
    paths=tuple(row.path for row in registration.body if row.path in body_paths
                or any(row.path.startswith(p+'|') and 'Part' in
                       row.path.rsplit('|',1)[-1] for p in body_paths))
    rows=[]
    with host._character_sampling_time() as seek:
        for frame in frames:
            seek(frame)
            rows.append((float(frame),tuple((p,host._spine_world_frame(p)[0]) for p in paths)))
    return tuple(rows)
