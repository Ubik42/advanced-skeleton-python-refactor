"""Original asAlignFKIK order on the registered source RP graph."""
from math import sqrt
from types import SimpleNamespace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_limb_animation import resolve_source_limb,source_pole_position


def _plug(registration,binding):
    channel=next(ch for ch in registration.channels if ch.key==binding.blend_key)
    return channel.node+'.'+channel.attribute


def _set(host,registration,node,attribute,value):
    c=host._cmds
    if not any(ch.node==node and ch.attribute==attribute for ch in registration.channels):
        if abs(float(c.getAttr(node+'.'+attribute))-value)<=1e-8:
            return
        raise CharacterRegistryError('来源 RP 匹配目标没有动画登记：'+node+'.'+attribute)
    if not c.getAttr(node+'.'+attribute,settable=True):
        raise CharacterRegistryError('来源 RP 匹配目标不可写：'+node+'.'+attribute)
    c.setAttr(node+'.'+attribute,value)


def _reset(host,registration,binding):
    for attr,value in binding.reset_attributes:
        _set(host,registration,binding.ik_control,attr,value)
    for control in binding.reset_controls:
        for kind in ('translate','rotate'):
            for axis in 'XYZ':
                attribute=kind+axis
                if host._cmds.getAttr(control+'.'+attribute,lock=True):
                    continue
                _set(host,registration,control,attribute,0.)


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


def apply(host,registration,binding,mode):
    host._require_transaction()
    c=host._cmds
    blend=_plug(registration,binding)
    value=float(c.getAttr(blend))
    target=1. if mode=='ik' else 0.
    if value==target:
        return
    if value not in (0.,1.):
        raise CharacterRegistryError('来源 RP 对齐要求处于 FK 或 IK 端点')
    if mode=='ik' and any(abs(length.rest_length)<=1e-8 for length in binding.lengths):
        raise CharacterRegistryError('来源 RP Lenght 匹配的原版 tx 分母为零；该 FreeOrient 骨段无法执行长度匹配')
    host._transaction_changed=True
    auto=bool(c.autoKeyframe(query=True,state=True))
    selection=c.ls(selection=True,long=True) or []
    try:
        c.autoKeyframe(state=False)
        if mode=='ik':
            pole_weights=_pole_weights(host,binding)
            sources=[host._spine_world_frame(row.fk_driver) for row in binding.joints]
            length_frames={path:host._spine_world_frame(path)[0][12:15]
                           for length in binding.lengths for path in (length.start_fk,length.end_fk)}
            end=binding.primary_count-1
            position=host._spine_world_frame(binding.ik_position_source)[0][12:15]
            align=host._spine_world_frame(binding.align)[0]
            toe_frame=(host._spine_world_frame(binding.toe_align)[0]
                       if binding.toe_align else host._spine_world_frame(binding.toe_source)[0]
                       if binding.toe_source else None)
            hybrid_frames=tuple((row.control,host._spine_world_frame(row.fk_driver)[0])
                                for row in binding.hybrid_controls)
            scale=tuple(c.getAttr(binding.joints[end].control+'.scale')[0])
            _reset(host,registration,binding)
            # The original end control is positioned before orienting; Foot
            # roll controls are reset first so the aligned receiver is stable.
            c.xform(binding.ik_control,worldSpace=True,translation=position)
            host._spine_set_world_rotation(binding.ik_control,align)
            world=host._spine_world_frame(binding.global_control)[0]
            global_scale=sqrt(sum(v*v for v in world[:3]))
            line=tuple(a-b for a,b in zip(sources[end][0][12:15],sources[0][0][12:15]))
            fallback=min(sources[binding.middle_index][1],
                         key=lambda axis:abs(sum(a*b for a,b in zip(axis,line))))
            if binding.middle_index==0:
                pole_weights=(0.,1.)
                fallback=(0.,0.,1.)
            pole=source_pole_position(sources[0][0][12:15],
                sources[binding.middle_index][0][12:15],sources[end][0][12:15],
                binding.height*global_scale,fallback,weights=pole_weights)
            c.xform(binding.pole_control,worldSpace=True,translation=pole)
            for axis,v in zip('XYZ',scale):
                _set(host,registration,binding.ik_control,'scale'+axis,float(v))
            if binding.lengths:
                _set(host,registration,binding.ik_control,'stretchy',10.)
                _set(host,registration,binding.ik_control,'antiPop',0.)
                _set(host,registration,binding.ik_control,'volume',10.)
                _set(host,registration,binding.pole_control,'lock',0.)
                ratio=float(c.getAttr(binding.ratio_node))
                if global_scale<=1e-8 or ratio<=1e-8:
                    raise CharacterRegistryError('来源 RP 匹配长度比例退化')
                for length in binding.lengths:
                    a,b=length_frames[length.start_fk],length_frames[length.end_fk]
                    distance=sqrt(sum((x-y)**2 for x,y in zip(a,b)))
                    _set(host,registration,binding.ik_control,length.attribute,
                         distance*length.fraction/(length.rest_length*global_scale*ratio))
            if binding.toe_control:
                if toe_frame is not None:
                    host._spine_set_world_rotation(binding.toe_control,toe_frame)
            if binding.reverse_roll:
                from adv_py.core.fit_symmetry import FitBuildSide
                host._match_body_leg_hybrid_roll(SimpleNamespace(
                    reverse_roll_control_path=binding.reverse_roll,
                    reverse_roll_handle_name=binding.reverse_handle,
                    body_joint_paths=tuple(row.fk_driver for row in
                        (binding.joints[0],binding.joints[binding.middle_index],binding.joints[end])),
                    side=FitBuildSide(binding.side)))
            for control,frame in reversed(hybrid_frames):
                host._spine_set_world_rotation(control,frame)
            _set(host,registration,next(ch.node for ch in registration.channels
                 if ch.key==binding.blend_key),blend.rsplit('.',1)[1],1.)
        else:
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


def samples(host,registration,frames,label,side,mode,tolerance=1e-4):
    binding=resolve_source_limb(registration,label,side.value)
    result=[]
    with host._character_sampling_time(preserve_modified=False) as seek:
        for frame in frames:
            seek(frame)
            before=host.capture_character_pose(registration)
            with host._character_static_controls(registration,before):
                apply(host,registration,binding,mode)
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
