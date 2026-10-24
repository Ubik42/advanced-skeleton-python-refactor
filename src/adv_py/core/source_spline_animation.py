"""Original Spline control order and registered FK/IK channel ownership."""
from dataclasses import dataclass
from math import sqrt,floor

from .body_spline import BodySplinePlan
from .character_registry import CharacterRegistryError


@dataclass(frozen=True)
class SourceSplineAnimationBinding:
    plan: BodySplinePlan
    physical_chain: tuple[str, ...]
    fk_controls: tuple[str, ...]
    fk_drivers: tuple[str, ...]
    ik_drivers: tuple[str, ...]
    blend_key: str

    @property
    def mode_maximum(self):
        return self.plan.mode_maximum

    @property
    def blend_plug(self):
        return self.plan.mode_plug

    @property
    def controls(self):
        return tuple(dict.fromkeys((*self.fk_controls,*self.plan.targets,
                                   *self.plan.hybrid_controls)))

    def animation_keys(self,registration):
        controls=set(self.controls)
        return frozenset(channel.key for channel in registration.channels
            if channel.key==self.blend_key or channel.node in controls
            and channel.attribute in tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ'))


def source_spline_align_order(count):
    """MEL aligns first, last, then the interior controls (10996–11019)."""
    if type(count) is not int or count<2:
        raise CharacterRegistryError('来源 Spline 至少需要两个控制器')
    return (0,count-1,*range(1,count-1))


def source_spline_nearest_deform(position,joints):
    """asGetDeformJointsByDistance filters and three-decimal sort (26401)."""
    eligible=[]
    for path,point in joints:
        leaf=path.rsplit('|',1)[-1]
        if leaf.endswith('_L') or 'Partial_' in leaf or 'Fix' in leaf:continue
        distance=sqrt(sum((a-b)**2 for a,b in zip(position,point)))
        # Native sorts padded TEXT, including the namespace. Keep the five
        # integer digits as a minimum width (not a numeric-sort shortcut).
        rounded=floor(distance*1000.+.5)
        integer,fraction=divmod(rounded,1000)
        key=str(integer).zfill(5)+'.'+str(fraction).zfill(3)+'|'+leaf
        eligible.append((key,path))
    if not eligible:raise CharacterRegistryError('来源 Spline 没有可对齐的 Deform 关节')
    return min(eligible)[1]


def resolve_source_spline(registration,system=None):
    plans=tuple(plan for plan in (registration.spine,*registration.additional_spines)
                if isinstance(plan,BodySplinePlan) and plan.source_curve_points)
    if system is None:
        if len(plans)!=1:
            raise CharacterRegistryError('请指定要切换的来源 Spline 系统')
        plan=plans[0]
    else:
        matches=tuple(plan for plan in plans if plan.system_name==system)
        if len(matches)!=1:
            raise CharacterRegistryError('来源 Spline 系统缺失或不唯一：'+str(system))
        plan=matches[0]
    from .character_body_retirement import complete_body_bindings
    body={joint.path:joint for joint in complete_body_bindings(registration)}
    chain=[]
    current=plan.body_joints[-1]
    while True:
        if current in chain or current not in body:
            raise CharacterRegistryError('来源 Spline 物理骨链中断')
        chain.append(current)
        if current==plan.body_joints[0]:break
        current=body[current].parent
    chain.reverse()
    controls=(plan.pelvis_control,*plan.fk_controls[1:])
    # The independent BaseFK is an internal receiver; MEL aligns the actual
    # start-joint FK controller, including Root, rather than skipping index 0.
    drivers=[]
    for index,control in enumerate(controls):
        leaf=control.rsplit('|',1)[-1]
        driver_leaf=leaf+'X' if leaf.endswith('FK') else leaf.replace('FK_','FKX_')
        candidates=tuple(node.path for node in registration.nodes
            if node.path.startswith(control+'|')
            and node.path.rsplit('|',1)[-1]==driver_leaf)
        if len(candidates)==1:
            drivers.append(candidates[0])
        else:
            sub_leaf=leaf+'Sub' if leaf.endswith('FK') else leaf.replace('FK_','FKSub_')
            subs=tuple(node.path for node in registration.nodes
                       if node.path.startswith(control+'|') and node.path.rsplit('|',1)[-1]==sub_leaf)
            drivers.append((subs[0] if len(subs)==1 else control) if index==0 else plan.joints[index].path)
    modes=tuple(ch for ch in registration.channels
                if ch.node==plan.mode_control and ch.attribute==plan.mode_attribute)
    if len(modes)!=1:
        raise CharacterRegistryError('来源 Spline 模式通道登记不唯一')
    first=(plan.root_path+'|'+plan.node_name('AdvPy_SplineFirstFixedOutput'))
    ik=(first,*plan.ik_outputs[1:])
    return SourceSplineAnimationBinding(plan,tuple(chain),controls,tuple(drivers),ik,modes[0].key)


def registered_spline_mode_channel(registration):
    """Use the stored receiver, not the old standard-spine channel prefix."""
    if not isinstance(registration.spine,BodySplinePlan):
        raise CharacterRegistryError('当前角色没有 Spline 模式通道')
    matches=tuple(channel for channel in registration.channels
                  if channel.node==registration.spine.mode_control and channel.attribute==registration.spine.mode_attribute)
    if len(matches)!=1:raise CharacterRegistryError('Spline 模式通道登记缺失或不唯一')
    return matches[0]


def registered_spline_control_keys(registration):
    plan=registration.spine
    if not isinstance(plan,BodySplinePlan):return frozenset()
    controls=set((*plan.targets,*plan.sub_targets,*plan.extra_targets,*plan.cv_controls,
                  *plan.cv_extras,*plan.hybrid_controls,*plan.hybrid_extras))
    return frozenset(channel.key for channel in registration.channels if channel.node in controls)
