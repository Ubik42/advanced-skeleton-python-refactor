"""MEL ScaleBlend's local Spline scaler inputs for Bendy MicroOffsets."""
from dataclasses import dataclass
from .source_rp_dynamics import SourceRpNode


@dataclass(frozen=True,slots=True)
class SourceSplineBendyScale:
    body: str
    node: SourceRpNode
    outputs: tuple[str,...]


def plan_source_spline_bendy_scales(chains,fk,splines):
    plans=splines if isinstance(splines,tuple) else (splines,) if splines is not None else ()
    controls={control.driven_joint:control for control in fk.controls}
    result=[]
    for chain in chains:
        if not chain.source_deform_matrix:continue
        matches=[(plan,index) for plan in plans for index,body in enumerate(plan.body_joints)
                 if body==chain.start_body and (index>0 or body in controls)]
        if not matches:continue
        if len(matches)!=1:
            raise ValueError('来源 Bendy Spline 缩放系统身份不唯一')
        plan,index=matches[0]
        control=controls.get(chain.start_body if index==0 else plan.joints[index].path)
        if control is None:
            raise ValueError('来源 Bendy Spline 缺少主 FK 缩放来源')
        name='AdvPy_BendySourceScale'+chain.start_body.rsplit('|',1)[-1]
        scaler=plan.node_name(f'AdvPy_SplineIKScaleVolume{index}')
        node=SourceRpNode(name,'blendColors',connections=(
            (plan.mode_weight,'blender'),)+tuple(
            (scaler+'.output'+axis,'color1'+component) for axis,component in zip('XYZ','RGB'))+tuple(
            (control.control_path+'.scale'+axis,'color2'+component) for axis,component in zip('XYZ','RGB')))
        result.append(SourceSplineBendyScale(chain.start_body,node,tuple(name+'.output'+component for component in 'RGB')))
    return tuple(result)
