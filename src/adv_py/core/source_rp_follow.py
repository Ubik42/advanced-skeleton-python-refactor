"""ADV asFollowLevels and Advanced IK PoleAim defaults (74370, 81733)."""
from dataclasses import dataclass
from .body_fit_follow_spaces import BodyFitFollowSpaceTarget, BodyFitFollowSpacesSpec
from .body_leg_pole_aim import BodyLegPoleAimSpec


@dataclass(frozen=True, slots=True)
class SourceRpFollowPlan:
    control: str
    pole: str
    handle_twist: str
    spaces: tuple[BodyFitFollowSpacesSpec, ...]
    pole_aim: BodyLegPoleAimSpec | None = None


def plan_source_rp_follows(body, limbs, global_control, root, *, leg_aim=()):
    joints={joint.path:joint for joint in body.joints}
    chest=next((joint.path for joint in body.joints if joint.name=='Chest_M'),None)
    plans=[]
    for limb in limbs:
        for ik in limb.ik.limbs:
            start=next(joint for joint in limb.mechanisms.joints if joint.path==ik.chain[0])
            end=next(joint for joint in limb.mechanisms.joints if joint.path==ik.chain[-1])
            parent=joints[start.source_joint].parent_path
            while parent in joints and 'Part' in joints[parent].name:
                parent=joints[parent].parent_path
            is_leg='Leg' in limb.label
            stem='AdvPy_'+limb.label+'Follow_'+ik.side.value
            pole_aim=None
            if is_leg:
                source=root.leg_lock_path if parent==body.root else parent
                if source is None:raise ValueError('来源 Leg PoleAim 缺少起点父级')
                pole_aim=BodyLegPoleAimSpec(
                    ik.side,source,ik.root_path,ik.wrist_control_path,
                    ik.wrist_sub_path or ik.wrist_control_path,ik.pole_offset_path,
                    ik.pole_position,ik.wrist_control_path+'.swivel',ik.handle_name+'.twist',
                    stem+'Frame',stem+'Aligned',stem+'Aim',stem+'Target',
                    stem+'AM',stem+'SwivelCM',stem+'MM',
                    aligned_orientation_source=end.source_joint)
            sources=[('MainExtra'+str(index),global_control.extra_control_paths[index-1])
                     for index in range(len(global_control.extra_control_paths),0,-1)]
            sources += [('Main',global_control.control_path),('Root',root.root_x.control_path)]
            if chest and end.source_joint.startswith(chest+'|'):
                sources.append(('Chest',chest))
            spaces=[]
            # MEL excludes default IK follow on centerBetweenFeet legs and
            # arms whose LegAim parent supplies automatic Scapula movement.
            auto_scapula=any(spec.label==limb.label and spec.side==ik.side.value
                              for spec in leg_aim)
            for role,control,offset in (('IK',ik.wrist_control_path,ik.wrist_offset_path),
                                        ('Pole',ik.pole_control_path,ik.pole_offset_path)):
                if role=='IK' and (is_leg and root.center_between_feet or auto_scapula):continue
                targets=list(sources)
                if role=='Pole':
                    targets.append((limb.label,pole_aim.target_path if pole_aim else ik.wrist_control_path))
                prefix=stem+role
                rows=tuple(BodyFitFollowSpaceTarget(label,source,
                    10. if label=='Main' or role=='Pole' and is_leg and label==limb.label else 0.,
                    prefix+label+'MM',prefix+label+'Weight') for label,source in targets)
                spaces.append(BodyFitFollowSpacesSpec(end.source_joint,control,offset,
                    offset.rsplit('|',1)[0],rows,prefix+'BM',prefix+'OutputMM'))
            plans.append(SourceRpFollowPlan(ik.wrist_control_path,ik.pole_control_path,
                                           ik.handle_name+'.twist',tuple(spaces),pole_aim))
    return tuple(plans)
