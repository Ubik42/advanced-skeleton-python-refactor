"""Read the original end-joint ikLocal enum without changing RP defaults."""
from dataclasses import dataclass,replace
from .body_controller_appearance import body_fk_curve_radius


@dataclass(frozen=True,slots=True)
class SourceInternalIkLocalSpec:
    control_name: str
    offset_path: str
    extra_path: str
    control_path: str
    world_position: tuple
    world_axes: tuple
    rotate_order: int
    radius: float
    target: str
    old_follow_constraint: str
    constraint_name: str
    visibility_source: str


def plan_source_internal_ik_local(body,fk,limbs,metadata, *,instances=()):
    by_path={joint.path:joint for joint in body.joints}
    from .source_fit_identity import source_fit_metadata
    rows=[]
    for limb in limbs:
        for ik in limb.ik.limbs:
            start=next(joint for joint in limb.mechanisms.joints if joint.path==ik.chain[0])
            chain=tuple(joint.path for joint in limb.mechanisms.joints
                        if joint.side is ik.side and joint.role.value=='ik'
                        and joint.source_joint.rsplit('|',1)[-1].rsplit('_',1)[0] in limb.joint_names)
            for joint in limb.mechanisms.joints:
                if joint.side is not ik.side or joint.path not in chain[:-1]:
                    continue
                body_joint=by_path[joint.source_joint]
                item=source_fit_metadata(body_joint.name,metadata,instances)
                if item is None or item.ik_local_mode is None:
                    continue
                control=next((control for control in fk.controls if control.driven_joint in
                    (joint.source_joint,next((driver.path for driver in limb.mechanisms.joints
                        if driver.role.value=='fk' and driver.source_joint==joint.source_joint),''))),None)
                if control is None:
                    continue
                follower=next((follower for follower in fk.followers
                               if follower.path==control.parent_path),None)
                # MEL requires FKParentConstraintTo<parent> to exist; an
                # ordinary internal FK parent does not introduce this control.
                if follower is None:
                    continue
                name='AdvPy_IKLocal'+limb.label+body_joint.name
                offset=follower.path+'|'+name+'Offset'
                extra=offset+'|'+name+'Extra'
                side=next(side for side in limb.blend.sides if side.side is ik.side)
                rows.append(SourceInternalIkLocalSpec(name,offset,extra,extra+'|'+name,
                    body_joint.world_position,start.world_axes if item.ik_local_mode=='localOrient'
                    else body_joint.world_axes,body_joint.rotation_order,
                    control.radius,start.path,start.name+'ParentPoint',name+'Constraint',
                    limb.blend.settings_path+'.'+side.attribute))
    return tuple(rows)


def configure_source_limb_ik(ik,mechanisms,body,metadata,end_name, *,instances=(),source_pole_placement=True):
    by_name={joint.name:joint for joint in body.joints}
    from .source_fit_identity import source_fit_metadata
    specs=[]
    for spec in ik.limbs:
        end=by_name[end_name+'_'+spec.side.value]
        item=source_fit_metadata(end.name,metadata,instances)
        middle=next(joint for joint in mechanisms.joints if joint.path==spec.chain[1])
        start=next(joint for joint in mechanisms.joints if joint.path==spec.chain[0])
        chain=tuple(joint for joint in mechanisms.joints
                    if joint.side is spec.side and joint.role.value=='ik'
                    and joint.path in (spec.solver_joint_list or spec.chain[:2])+(spec.chain[-1],))
        from .source_limb_pole import source_limb_build_pole
        index=next(index for index,joint in enumerate(chain) if joint.path==middle.path)
        pole,straight=(source_limb_build_pole(tuple(joint.world_position for joint in chain),index,start.world_axes)
                       if source_pole_placement else (spec.pole_position,False))
        # The original query takes the middle of the full source chain;
        # the mechanism plan already carries the corresponding bind point.
        specs.append(replace(spec,source_aligned_graph=True,
            pole_position=pole,source_straight_chain=straight,source_original_pole=source_pole_placement,
            ik_local_mode=item.ik_local_mode if item else None,
            source_middle_position=middle.world_position,
            source_middle_axes=middle.world_axes,
            source_rotation_order=end.rotation_order,
            source_foot_orientation=bool(end.label and 'Foot' in end.label.text)))
    return replace(ik,limbs=tuple(specs))
