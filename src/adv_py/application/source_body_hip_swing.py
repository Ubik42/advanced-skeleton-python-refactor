"""Connect original HipSwinger branches to source Root and Part receivers."""
from dataclasses import replace

from adv_py.core.fit_hip_swing_no_parts import HipSwingNoPartsTopology,plan_hip_swing_no_parts
from adv_py.core.fit_inbetween_hip_swing import plan_hip_swing_reverse
from adv_py.core.fit_settings import FitSkeletonValidationError


def build_source_hip_swing(host,selection,root,body,fk,segments,parts):
    if selection is None or not selection.enabled:
        return None
    root_joint=next(joint for joint in body.joints if joint.path==body.root)
    child=next((joint for joint in body.joints if joint.name==selection.child_name+'_M'),None)
    if child is None:
        raise FitSkeletonValidationError('来源 HipSwinger 子关节缺失')
    child_fk=next((control for control in fk.controls
        if selection.child_name in control.fit_joint_names and control.side.value=='M'),None)
    if child_fk is None:
        raise FitSkeletonValidationError('来源 HipSwinger 子关节 FK 接收层缺失')
    root_control=next(control for control in fk.controls if control.control_path==root.fk_control)
    if selection.root_inbetween_count:
        segment=next((segment for segment in segments
            if segment.fk.anchor.start_body_name=='Root_M'),None)
        if segment is None or segment.fk.parts is None:
            raise FitSkeletonValidationError('来源 HipSwinger 缺少 Root Inbetween 图'
                + f' count={selection.root_inbetween_count}'
                + f' segments={[(item.fk.anchor.start_body_name, item.fk.parts is not None) for item in segments]}'
                + f' parts={[(item.name, item.kind) for item in parts]}')
        root_parts=tuple(part for part in parts if part.kind=='inbetween'
                         and part.start_body_name=='Root_M')
        plan=plan_hip_swing_reverse(root_parts,
            start_fk_offset_path=root.fk_offset,start_fk_control_path=root.fk_control,
            end_body_path=child.path,radius=root_control.radius,root_profile=root_joint.deform_profile)
        host.preflight_hip_swing_reverse(plan)
        host.create_hip_swing_reverse(plan)
        return plan
    topology=HipSwingNoPartsTopology(root.fk_control,root.fk_offset,root.fk_receiver,
        child_fk.offset_path,'AdvPy_SourceRootRemoveRotMM.matrixIn[0]',body.root,child.path,
        leg_lock_weight='AdvPy_SourceRootLegLockUnit.output' if root.leg_lock_enabled else None,
        root_fk_weight=root.spline_reverse,
        root_fkx_parent_inverse=root.fk_receiver+'.parentInverseMatrix[0]',
        leg_lock_enabled=root.leg_lock_enabled,
        independent_child_receiver=any(follower.path==child_fk.parent_path for follower in fk.followers))
    plan=plan_hip_swing_no_parts(selection,topology,radius=root_control.radius,
        root_profile=root_joint.deform_profile,use_offset_parent_matrix=root.use_offset_parent_matrix)
    plan=replace(plan,frame_name=root.hs_path.rsplit('|',1)[-1])
    host.preflight_hip_swing_no_parts(plan)
    host.create_hip_swing_no_parts(plan)
    return plan
