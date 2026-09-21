"""Variable-length FK/spline spine with independent curve controls."""
from dataclasses import dataclass,replace
from math import sqrt,isfinite

from .body_limb_controls import BodyLimbFkControlSpec
from .body_limb_mechanisms import BodyLimbMechanismJointSpec,BodyLimbMechanismRole
from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True)
class BodySplinePlan:
    root_path: str
    joints: tuple
    body_joints: tuple[str,...]
    fk_controls: tuple[str,...]
    pelvis_control: str
    chest_space: str
    targets: tuple[str,...]
    positions: tuple
    axes: tuple
    lengths: tuple[float,...]

    @property
    def settings(self):return self.targets[-1]
    @property
    def curve(self):return self.root_path+'|AdvPy_SplineCurve'
    @property
    def node_names(self):
        fixed=('AdvPy_SplineMechanisms','AdvPy_SplineChestSpace','AdvPy_SplineCurve','AdvPy_SplineCurveShape',
            'AdvPy_SplineIKHandle','AdvPy_SplineIKEffector','AdvPy_SplineFKRootPoint','AdvPy_SplineIKRootPoint',
            'AdvPy_SplineChestOrient','AdvPy_SplineChestSpaceParent','AdvPy_SplineReverse','AdvPy_SplineArc',
            'AdvPy_SplineRatio','AdvPy_SplineStretchBlend','AdvPy_SplineClamp','AdvPy_SplineVolumeExponent','AdvPy_SplineVolume')
        targets=tuple(f'AdvPy_SplineIK{i}{suffix}' for i in range(4) for suffix in ('Offset','','Shape','Matrix','Position'))
        outputs=tuple(f'AdvPy_Spline{kind}{i}' for i in range(1,len(self.body_joints)) for kind in ('Point','Orient','Scale','Length','FKWorldScale','IKWorldScale'))
        return fixed+tuple(j.name for j in self.joints)+targets+outputs


def with_spline_ik(body,torso,description):
    states=description.validate(body)
    source=tuple(states[name] for name in description.spine)
    delta=tuple(b-a for a,b in zip(source[0].world_position,source[-1].world_position))
    total=sqrt(sum(v*v for v in delta))
    if not isfinite(total) or total<1e-5:raise FitSkeletonValidationError('Spline 脊柱首尾距离必须为非零有限值')
    x=tuple(v/total for v in delta)
    lengths=[]
    for a,b in zip(source,source[1:]):
        offset=tuple(v-u for u,v in zip(a.world_position,b.world_position))
        length=sqrt(sum(v*v for v in offset))
        if not isfinite(length) or length<1e-5 or abs(sum(u*v for u,v in zip(offset,x))-length)>1e-5:
            raise FitSkeletonValidationError('当前 Spline 绑定要求直线且按骨盆到胸部顺序排列；弯曲绑定需要曲线拟合协议')
        lengths.append(length)
    guide=min(source[1].world_axes,key=lambda axis:abs(sum(a*b for a,b in zip(axis,x))))
    dot=sum(a*b for a,b in zip(guide,x));y=tuple(a-dot*b for a,b in zip(guide,x));norm=sqrt(sum(v*v for v in y));y=tuple(v/norm for v in y)
    z=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]);axes=(x,y,z)
    source=(replace(source[0],world_axes=axes),*source[1:])
    if any(abs(sum(a*b for a,b in zip(j.world_axes[0],x))-1.)>1e-5 for j in source[:-1]):
        raise FitSkeletonValidationError('Spline 脊柱骨段必须沿父关节本地 +X')
    root=torso.controls.root_path+'|AdvPy_SplineMechanisms';specs=[]
    for role in (BodyLimbMechanismRole.FK,BodyLimbMechanismRole.IK):
        parent=root
        for index,joint in enumerate(source):
            name=f'AdvPy_Spline{role.value.upper()}Joint{index}'
            specs.append(BodyLimbMechanismJointSpec(role,joint.side,joint.path,parent+'|'+name,name,parent,joint.world_position,joint.world_axes))
            parent=specs[-1].path
    pelvis=torso.controls.controls[0]
    offset=pelvis.control_path+'|AdvPy_SplineBaseFKOffset'
    base=BodyLimbFkControlSpec(source[0].side,specs[0].path,offset,'AdvPy_SplineBaseFKOffset',offset+'|AdvPy_SplineBaseFK',
        'AdvPy_SplineBaseFK',pelvis.control_path,'AdvPy_SplineBaseFKOrient',source[0].world_position,axes,pelvis.radius)
    updated=[pelvis,base];parent=base.control_path;fk=[parent]
    by_joint={c.driven_joint:c for c in torso.controls.controls}
    for index,joint in enumerate(source[1:],1):
        old=by_joint[joint.path];offset=parent+'|'+old.offset_name
        control=replace(old,parent_path=parent,offset_path=offset,control_path=offset+'|'+old.control_name,driven_joint=specs[index].path)
        updated.append(control);parent=control.control_path;fk.append(parent)
    space=torso.controls.root_path+'|AdvPy_SplineChestSpace';mapping={}
    for old in torso.controls.controls:
        if old.driven_joint in {j.path for j in source}:continue
        parent=mapping.get(old.parent_path,space);offset=parent+'|'+old.offset_name
        control=replace(old,parent_path=parent,offset_path=offset,control_path=offset+'|'+old.control_name)
        mapping[old.control_path]=control.control_path;updated.append(control)
    targets=tuple(pelvis.control_path+f'|AdvPy_SplineIK{i}Offset|AdvPy_SplineIK{i}' for i in range(4))
    positions=tuple(tuple(a+(b-a)*i/3 for a,b in zip(source[0].world_position,source[-1].world_position)) for i in range(4))
    plan=BodySplinePlan(root,tuple(specs),tuple(j.path for j in source),tuple(fk),pelvis.control_path,space,targets,positions,axes,tuple(lengths))
    return replace(torso,controls=replace(torso.controls,controls=tuple(updated)),spline=plan)
