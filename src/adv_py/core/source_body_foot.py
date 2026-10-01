"""Resolve Foot descendants by Fit labels, then use the shared ADV roll graph."""
from dataclasses import fields,is_dataclass,replace
from enum import Enum
import re

from .body_leg_ik import BodyLegIkPlan,BodyLegIkSpec
from .body_leg_foot import plan_body_leg_foot
from .body_limb_mechanisms import BodyLimbMechanismRole
from .fit_settings import FitSkeletonValidationError


def source_foot_roles(body,end_name,sides):
    by_path={joint.path:joint for joint in body.joints}
    by_name={joint.name:joint for joint in body.joints}
    result={}
    for side in sides:
        end=by_name[end_name+'_'+side.value]
        if end.label is None or 'Foot' not in end.label.text:
            continue
        roles={'Ankle':end}
        for joint in body.joints:
            if not joint.path.startswith(end.path+'|') or joint.label is None:
                continue
            label=joint.label.text
            for role in ('Heel','BigToe','PinkyToe','FootSideOuter','FootSideInner','ToesEnd'):
                if role in label:
                    roles[role]=joint
            if 'Toes' in label and 'ToesEnd' not in label and 'QToes' not in label:
                roles['Toes']=joint
        if 'Toes' not in roles:
            continue  # The MEL skips Foot Roll when no Toes label exists.
        chain=[]
        current=roles.get('ToesEnd',roles['Toes'])
        while current.path!=end.path:
            if 'Part' not in current.name:
                chain.append(current)
            if current.parent_path not in by_path:
                raise FitSkeletonValidationError('来源脚趾没有连接到 Foot：'+end.name)
            current=by_path[current.parent_path]
        roles['chain']=tuple(reversed(chain))
        result[side]=roles
    if result and set(result)!=set(sides):
        raise FitSkeletonValidationError('来源同组 Foot 的脚趾标签侧别不完整')
    return result


def source_foot_joint_names(names,roles):
    if not roles:
        return names
    tails=tuple(tuple(joint.name.rsplit('_',1)[0] for joint in role['chain'])
                for role in roles.values())
    if any(tail!=tails[0] for tail in tails[1:]):
        raise FitSkeletonValidationError('来源同组 Foot 的脚趾主链名称或顺序不同')
    return names+tails[0]


def plan_source_body_foot(body,limb,roles,metadata,*,base_radius):
    if not roles:
        return None
    # Canonical role names are an in-memory planner view. Every actual DAG
    # path, label, frame and deformation profile stays from the source Body.
    role_aliases={joint.path:role+'_'+side.value for side,items in roles.items()
                  for role,joint in items.items() if role!='chain'}
    for side in roles:
        start=next(joint for joint in limb.mechanisms.joints
                   if joint.side is side and joint.role is BodyLimbMechanismRole.IK
                   and joint.parent_path==limb.mechanisms.root_path)
        role_aliases[start.source_joint]='Hip_'+side.value
    reserved=set(role_aliases.values())
    view=replace(body,joints=tuple(replace(joint,name=role_aliases.get(joint.path,
        '__source_'+joint.name if joint.name in reserved else joint.name))
        for joint in body.joints))
    drivers={(joint.source_joint,joint.role):joint.path for joint in limb.mechanisms.joints}
    ik_specs=[]
    for source in limb.ik.limbs:
        items=roles[source.side]
        toes=drivers[(items['Toes'].path,BodyLimbMechanismRole.IK)]
        end=drivers[(items['ToesEnd'].path,BodyLimbMechanismRole.IK)] if 'ToesEnd' in items else ''
        ik_specs.append(BodyLegIkSpec(source.side,source.chain,source.root_path,
            source.wrist_offset_path,source.wrist_offset_name,source.wrist_control_path,
            source.wrist_control_name,source.pole_offset_path,source.pole_offset_name,
            source.pole_control_path,source.pole_control_name,source.handle_name,
            source.pole_constraint_name,source.wrist_position,source.wrist_axes,
            source.pole_position,source.radius,source.wrist_constraint_name,toes,end,
            ankle_sub_path=source.wrist_sub_path,ankle_extra_path=source.wrist_extra_path,
            ankle_extra_curve=source.wrist_extra_curve,
            toe_solver_joint_list=(source.chain[-1],),toe_end_solver_joint_list=(toes,)))
    meta=next((item for item in metadata if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]
               ==limb.joint_names[-1]),None)
    plan=plan_body_leg_foot(view,BodyLegIkPlan(limb.ik.root_path,limb.ik.root_name,
        tuple(ik_specs),base_radius),limb.mechanisms,
        foot_pivots_by_side=frozenset(roles) if meta and meta.foot_pivots else frozenset(),
        qtoes_suffixes=tuple(side.value for side in roles),allow_open_toe_chain=True)
    protected={part.split('.',1)[0] for joint in limb.mechanisms.joints
               for part in joint.path.split('|')}
    for source in limb.ik.limbs:
        for field in fields(source):
            value=getattr(source,field.name)
            if isinstance(value,str):
                protected.update(part.split('.',1)[0] for part in value.split('|'))
    def scope(value):
        if isinstance(value,Enum):
            return value
        if isinstance(value,str):
            return re.sub(r'AdvPy_[A-Za-z0-9_]+',lambda match:match[0] if match[0] in protected
                          else 'AdvPy_'+limb.label+'_Foot_'+match[0][6:],value)
        if is_dataclass(value):
            return replace(value,**{field.name:scope(getattr(value,field.name)) for field in fields(value)})
        if isinstance(value,tuple):
            return tuple(scope(item) for item in value)
        return value
    plan=scope(plan)
    rows=[]
    for side in plan.sides:
        source=next(source for source in limb.ik.limbs if source.side is side.side)
        rows.append(replace(side,initial_handle_parent_path=source.wrist_sub_path or source.wrist_control_path,
            source_end_matrix=source.source_orientation_matrix,
            source_end_receiver=source.orientation_source,
            source_end_world_matrix='AdvPy_'+limb.label+'_Foot_EndOrientation_'+side.side.value,
            source_toe_fit_name=roles[side.side]['Toes'].name.rsplit('_',1)[0]))
    return replace(plan,sides=tuple(rows))
