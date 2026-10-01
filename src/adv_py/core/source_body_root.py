"""ADV Advanced Root, COG and root-rotation removal for source-named rigs."""
from dataclasses import dataclass,replace

from .body_torso import BodyRootControlSpec
from .fit_settings import FitSkeletonValidationError
from .body_controller_appearance import body_fk_curve_radius


@dataclass(frozen=True)
class SourceBodyRootPlan:
    body_root: str
    root_x: BodyRootControlSpec
    cogs: tuple[BodyRootControlSpec,...]
    fk_control: str
    fk_offset: str
    fk_receiver: str
    fk_orient: str
    position: tuple
    axes: tuple
    rotation_order: int
    use_offset_parent_matrix: bool
    leg_lock_enabled: bool
    center_between_feet: bool
    relative_source: str | None = None
    spline_ik_source: str | None = None
    spline_mode: str | None = None
    spline_reverse: str | None = None
    spline_output: str | None = None
    spline_first_control: str | None = None
    branch_offsets: tuple[str,...] = ()
    hip_swing_no_parts: bool = False
    leg_lock_opm: bool = False

    @property
    def leg_lock_path(self):
        return '|Group|MotionSystem|RootSystem|AdvPy_LegLockConstrained'

    @property
    def hs_path(self):
        return self.fk_control+'|AdvPy_SourceRootHS_M'

    @property
    def spline_fixed_path(self):
        return self.spline_ik_source

    @property
    def node_names(self):
        return tuple(name for control in (*self.cogs,self.root_x)
                     for name in (control.offset_name,control.extra_name,
                                  control.control_name,control.control_name+'Shape'))+(
            'AdvPy_SourceRootHS_M','AdvPy_SourceRootFollowMM',
            'AdvPy_LegLockConstrained','AdvPy_SourceLegLockOutputMM')+(
            ('AdvPy_SourceLegLockDM',) if not self.leg_lock_opm else ())+(
            ('AdvPy_SourceRootFollowDM',) if not self.use_offset_parent_matrix else ())+(
            ('AdvPy_SourceRootRelativeMM','AdvPy_SourceRootRemoveRotBM',
             'AdvPy_SourceRootRemoveRotPM','AdvPy_SourceRootRemoveRotIM',
             'AdvPy_SourceRootRemoveRotBM2') if self.leg_lock_enabled and not self.hip_swing_no_parts else ())+(
            ('AdvPy_SourceRootRemoveRotMM',) if self.leg_lock_enabled or self.hip_swing_no_parts else ())+(
            ('AdvPy_SourceRootLegLockUnit',) if self.leg_lock_enabled else ())+(
            ('AdvPy_SourceLegLockSplineBM',) if (self.leg_lock_enabled or self.hip_swing_no_parts) and self.spline_ik_source else ())+(
            tuple(offset.rsplit('|',1)[-1]+'LegLock'+suffix
                  for offset in self.branch_offsets
                  for suffix in (('MM',) if self.use_offset_parent_matrix else ('MM','DM'))))


def plan_source_body_root(body,fk,metadata,instances,options,*,base_radius=1.5):
    root=next(joint for joint in body.joints if joint.path==body.root)
    control=next((control for control in fk.controls if control.driven_joint==body.root),None)
    if control is None:
        raise FitSkeletonValidationError('来源 Advanced Root 缺少 Root FK 控制')
    root_meta=next(item for item in metadata
        if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]=='Root')
    by_name={joint.name:joint for joint in body.joints}
    metas={item.joint:item for item in metadata}
    selected=[by_name[instance.output_name] for instance in instances
              if metas[instance.source_joint].cog and instance.output_name in by_name]
    parent='|Group|MotionSystem|RootSystem|RootFollowMain'
    cogs=[]
    for joint in reversed(selected):
        offset=parent+'|AdvPy_COGOffset'+joint.name
        extra=offset+'|AdvPy_COGExtra'+joint.name
        cog=BodyRootControlSpec(offset,extra,extra+'|AdvPy_COG'+joint.name,
                               joint.world_position,body_fk_curve_radius(body,joint,base_radius))
        cogs.append(cog)
        parent=cog.control_path
    offset=parent+'|AdvPy_RootOffsetX_M'
    extra=offset+'|AdvPy_RootExtraX_M'
    root_x=BodyRootControlSpec(offset,extra,extra+'|AdvPy_RootX_M',
                             root.world_position,control.radius*.23)
    return SourceBodyRootPlan(body.root,root_x,tuple(cogs),control.control_path,
        control.offset_path,control.source_override_path or control.sub_control_path or control.control_path,
        control.constraint_name,root.world_position,root.world_axes,root.rotation_order,
        options.use_offset_parent_matrix,root_meta.leg_lock is not False,
        root_meta.center_between_feet is True,leg_lock_opm=options.use_offset_parent_matrix)


def finalize_source_body_root(plan,fk,splines,inbetween_segments):
    control=next(control for control in fk.controls if control.control_path==plan.fk_control)
    receiver=control.source_override_path or control.sub_control_path or control.control_path
    relative=None
    for segment in inbetween_segments:
        if segment.fk.anchor.start_body_name==plan.body_root.rsplit('|',1)[-1]:
            relative=segment.fk.matrices.steps[0].blend_name+'.outputMatrix'
            break
    spline=next((spline for spline in splines if spline.body_joints[0]==plan.body_root),None)
    return replace(plan,fk_receiver=receiver,relative_source=relative,
        spline_ik_source=spline.source_fixed_path if spline else None,
        spline_mode=spline.settings+'.spineIkFk' if spline else None,
        spline_reverse=spline.node_name('AdvPy_SplineReverse.outputX') if spline else None,
        spline_output=spline.root_path+'|'+spline.node_name('AdvPy_SplineFirstFixedOutput') if spline else None,
        spline_first_control=spline.targets[0] if spline else None)
