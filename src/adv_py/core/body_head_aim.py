"""Head aiming adds a blended parent frame, leaving animator FK rotations free."""
from dataclasses import dataclass,replace
from math import sqrt,isfinite
from .fit_settings import FitSkeletonValidationError
from .fit_container import FitUpAxis


@dataclass(frozen=True)
class HeadAimPlan:
    head_control: str
    offset: str
    pivot: str
    target_offset: str
    target: str
    position: tuple
    axes: tuple
    radius: float
    aim_axis: tuple
    up_axis: tuple

    @property
    def rest(self):return self.offset+'|AdvPy_HeadAimRest'
    @property
    def solved(self):return self.offset+'|AdvPy_HeadAimSolved'
    @property
    def node_names(self):return ('AdvPy_HeadAimBlend','AdvPy_HeadAimOffset','AdvPy_HeadAim','AdvPy_HeadAimShape',
        'AdvPy_HeadAimRest','AdvPy_HeadAimSolved','AdvPy_HeadAimConstraint','AdvPy_HeadAimOrient','AdvPy_HeadAimReverse')


def with_head_aim(torso,body,description,up_axis=FitUpAxis.Z):
    joints=description.validate(body)
    head=joints[description.neck[-1]]
    control=next(c for c in torso.controls.controls if c.driven_joint==head.path)
    parent=joints[description.neck[-2] if len(description.neck)>1 else description.spine[-1]]
    length=sqrt(sum((a-b)**2 for a,b in zip(head.world_position,parent.world_position)))
    if not isfinite(length) or length<1e-5:raise FitSkeletonValidationError('头部瞄准要求非零有限颈头长度')
    if up_axis not in (FitUpAxis.Y,FitUpAxis.Z):raise FitSkeletonValidationError('头部瞄准只接受 Y/Z 向上')
    forward=(0.,1.,0.) if up_axis is FitUpAxis.Z else (0.,0.,1.)
    upward=(0.,0.,1.) if up_axis is FitUpAxis.Z else (0.,1.,0.)
    aim_axis=tuple(sum(a*b for a,b in zip(axis,forward)) for axis in head.world_axes)
    local_up=tuple(sum(a*b for a,b in zip(axis,upward)) for axis in head.world_axes)
    pivot=control.offset_path+'|AdvPy_HeadAimBlend'
    updated=replace(control,control_parent_path=pivot,control_path=pivot+'|'+control.control_name)
    target_offset=torso.controls.root_path+'|AdvPy_HeadAimOffset'
    plan=HeadAimPlan(updated.control_path,control.offset_path,pivot,target_offset,target_offset+'|AdvPy_HeadAim',
        tuple(p+length*3*x for p,x in zip(head.world_position,forward)),head.world_axes,control.radius*.6,aim_axis,local_up)
    return replace(torso,controls=replace(torso.controls,controls=tuple(updated if c==control else c for c in torso.controls.controls)),head_aim=plan)
