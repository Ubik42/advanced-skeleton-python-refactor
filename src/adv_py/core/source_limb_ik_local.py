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


def plan_source_internal_ik_local(body,fk,limbs,metadata):
    by_path={joint.path:joint for joint in body.joints}
    meta={item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]:item for item in metadata}
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
                item=meta.get(body_joint.name.rsplit('_',1)[0])
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


def configure_source_limb_ik(ik,mechanisms,body,metadata,end_name):
    by_name={joint.name:joint for joint in body.joints}
    item=next((item for item in metadata
               if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]==end_name),None)
    specs=[]
    for spec in ik.limbs:
        end=by_name[end_name+'_'+spec.side.value]
        middle=next(joint for joint in mechanisms.joints if joint.path==spec.chain[1])
        # The original query takes the middle of the full source chain;
        # the mechanism plan already carries the corresponding bind point.
        specs.append(replace(spec,source_aligned_graph=True,
            ik_local_mode=item.ik_local_mode if item else None,
            source_middle_position=middle.world_position,
            source_middle_axes=middle.world_axes,
            source_rotation_order=end.rotation_order,
            source_foot_orientation=bool(end.label and 'Foot' in end.label.text)))
    return replace(ik,limbs=tuple(specs))
