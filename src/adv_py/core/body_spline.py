"""Variable-length FK/spline spine with independent curve controls."""
from dataclasses import dataclass,replace
from math import sqrt,isfinite

from .body_limb_controls import (
    BodyLimbFkControlSpec, reparent_body_fk_control,
)
from .body_limb_mechanisms import (
    BodyLimbMechanismJointSpec, BodyLimbMechanismRole, body_limb_parent_matches,
)
from .fit_settings import FitSkeletonValidationError
from .body_build_options import BodyBuildOptions


CURRENT_SPLINE_VERSION = 27


def spline_owner_version(marker: str) -> int:
    prefix = 'adv_py.spline.v'
    if not isinstance(marker, str) or not marker.startswith(prefix):
        raise FitSkeletonValidationError('Spline 所有权标记无效')
    suffix = marker[len(prefix):]
    if not suffix.isdecimal():
        raise FitSkeletonValidationError('Spline 所有权标记无效')
    version = int(suffix)
    if not 1 <= version <= CURRENT_SPLINE_VERSION or marker != prefix + str(version):
        raise FitSkeletonValidationError('Spline 所有权标记无效')
    return version


def current_spline_owner(curved: bool, even_stretch_graph: bool = True,
                         twist_ramp_graph: bool = False,
                         mid_follow_graph: bool = False,
                         isolated_mid_follow_graph: bool = False) -> str:
    if twist_ramp_graph and not even_stretch_graph:
        raise FitSkeletonValidationError('Spline 中间扭转图要求 stretchEven 双链')
    if mid_follow_graph and not twist_ramp_graph:
        raise FitSkeletonValidationError('Spline 中间跟随要求中间扭转控制')
    if isolated_mid_follow_graph and not mid_follow_graph:
        raise FitSkeletonValidationError('Spline 独立跟随层要求中间跟随图')
    newest = (27 if isolated_mid_follow_graph else
              25 if mid_follow_graph else 23 if twist_ramp_graph else
              21 if even_stretch_graph else 19)
    return f'adv_py.spline.v{newest if curved else newest - 1}'


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
    use_offset_parent_matrix: bool = False
    even_stretch_graph: bool = False
    twist_ramp_graph: bool = False
    mid_follow_graph: bool = False
    isolated_mid_follow_graph: bool = False
    sub_targets: tuple[str, ...] = ()
    extra_curve: bool = False
    fk_root_point_from_receiver: bool = True
    source_curve_points: tuple = ()
    fake_mid_control: bool = False
    source_hybrid_graph: bool = False
    source_control_axes: tuple = ()
    source_ik_local: bool = False
    source_cv_axes: tuple = ()

    @property
    def source_matrix_targets(self):
        return tuple(target+f'|AdvPy_SplineIK{i}X' for i,target in enumerate(self.driver_targets))

    @property
    def hybrid_controls(self):
        if not self.source_hybrid_graph:
            return ()
        controls = []
        parent = self.pelvis_control
        for index in range(len(self.targets)):
            control = parent + f'|AdvPy_SplineHybrid{index}Offset|AdvPy_SplineHybrid{index}'
            controls.append(control)
            parent = control
        return tuple(controls)

    def target_parent(self, index):
        if self.source_hybrid_graph:
            if index == 0:
                return self.hybrid_controls[0].rsplit('|',1)[0]
            if index == len(self.targets)-1:
                return self.hybrid_controls[-1]
        return (self.mid_follow_parent if self.isolated_mid_follow_graph
                and 0<index<len(self.targets)-1 else self.pelvis_control)

    @property
    def curve_points(self):
        return self.source_curve_points or self.positions

    @property
    def curve_degree(self):
        return 1 if len(self.curve_points) < 4 else 3

    @property
    def cv_controls(self):
        return tuple(self.root_path + f'|AdvPy_SplineCV{i}Offset|AdvPy_SplineCV{i}'
                     for i in range(1, len(self.source_curve_points) - 1))

    @property
    def extra_targets(self) -> tuple[str, ...]:
        parents = tuple(target.rsplit('|', 1)[0]
                        for target in self.targets)
        if all(parent.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
               == f'AdvPy_SplineIK{index}Extra'
               for index, parent in enumerate(parents)):
            return parents
        return ()

    @property
    def driver_targets(self) -> tuple[str, ...]:
        return self.sub_targets or self.targets

    @property
    def offset_targets(self) -> tuple[str, ...]:
        return tuple(extra.rsplit('|', 1)[0]
                     for extra in self.extra_targets) if self.extra_targets else tuple(
                         target.rsplit('|', 1)[0] for target in self.targets)

    @property
    def mid_follow_parent(self):
        return self.pelvis_control+'|AdvPy_SplineIKFollowMain'

    @property
    def settings(self):return self.targets[-1]
    @property
    def curve(self):return self.root_path+'|AdvPy_SplineCurve'
    @property
    def curved(self):
        if not self.source_curve_points and len(self.targets)>4:return True
        start,end=self.curve_points[0],self.curve_points[-1]
        direction=tuple(b-a for a,b in zip(start,end))
        squared=sum(value*value for value in direction)
        if squared<1e-10:return True
        for point in self.curve_points[1:-1]:
            offset=tuple(b-a for a,b in zip(start,point))
            projection=sum(a*b for a,b in zip(offset,direction))/squared
            if sum((a-projection*b)**2 for a,b in zip(offset,direction))>1e-10:
                return True
        return False
    @property
    def ik_outputs(self):
        n=len(self.body_joints)
        return tuple((self.root_path+f'|AdvPy_SplineIKOutput{i}'
                      if self.even_stretch_graph else self.joints[n+i].path)
                     +(f'|AdvPy_SplineIKRest{i}' if self.curved and i else '')
                     for i in range(n))
    @property
    def scale_reference(self):
        follow='|Group|MotionSystem|RootSystem|RootFollowMain'
        return follow if self.root_path.startswith(follow+'|') else self.pelvis_control
    @property
    def node_names(self):
        fixed=('AdvPy_SplineMechanisms','AdvPy_SplineChestSpace','AdvPy_SplineCurve','AdvPy_SplineCurveShape',
            'AdvPy_SplineIKHandle','AdvPy_SplineIKEffector','AdvPy_SplineFKRootPoint','AdvPy_SplineIKRootPoint',
            'AdvPy_SplineChestOrient','AdvPy_SplineReverse','AdvPy_SplineArc',
            'AdvPy_SplineRatio','AdvPy_SplineStretchBlend','AdvPy_SplineClamp','AdvPy_SplineVolumeExponent','AdvPy_SplineVolume',
            'AdvPy_SplineVolumeRatioClamp','AdvPy_SplineVolumeBlend',
            'AdvPy_SplineFlipUpAxis','AdvPy_SplineFlipVector') + (
            ('AdvPy_SplineIKEndLocalStartOrient',)
            if len(self.body_joints)>2 else ())
        targets=tuple(f'AdvPy_SplineIK{i}{suffix}' for i in range(len(self.targets)) for suffix in
                      (('Offset','','Shape') if self.source_curve_points else ('Offset','','Shape','Matrix','Position')))
        cvs = (tuple(f'AdvPy_SplineCV{i}{suffix}'
                     for i in range(len(self.source_curve_points))
                     for suffix in ('Matrix', 'Position')) + tuple(
                     f'AdvPy_SplineCV{i}{suffix}'
                     for i in range(1, len(self.source_curve_points) - 1)
                     for suffix in ('Offset', '', 'Shape', 'Follow1', 'Follow2', 'Blend', 'ParentMatrix'))
               + tuple(f'AdvPy_SplineStiff{i}' for i in (0, len(self.targets)-1))
               if len(self.source_curve_points)>3 else tuple(
                     f'AdvPy_SplineCV{i}{suffix}' for i in range(len(self.source_curve_points))
                     for suffix in ('Matrix', 'Position')) + tuple(
                     f'AdvPy_SplineCV{i}{suffix}'
                     for i in range(1, len(self.source_curve_points)-1)
                     for suffix in ('Offset', '', 'Shape', 'Follow1', 'Follow2', 'Blend', 'ParentMatrix')))
        if self.source_curve_points and not self.use_offset_parent_matrix:
            cvs += tuple(f'AdvPy_SplineCV{i}Decompose'
                         for i in range(1, len(self.source_curve_points)-1))
        outputs=tuple(f'AdvPy_Spline{kind}{i}' for i in range(1,len(self.body_joints)) for kind in ('Point','Orient','Scale','Length','FKWorldScale','IKWorldScale'))
        rests=tuple(f'AdvPy_SplineIKRest{i}' for i in range(1,len(self.body_joints))) if self.curved else ()
        chest = (('AdvPy_SplineChestSpaceMM', 'AdvPy_SplineChestSpacePM')
                 if self.use_offset_parent_matrix else
                 ('AdvPy_SplineChestSpaceParent',))
        scaling=('AdvPy_SplineVolumeDelta',
                 'AdvPy_SplineStretchUnit','AdvPy_SplineVolumeUnit')+tuple(
            f'AdvPy_SplineIKScale{kind}{i}'
            for i in range(len(self.body_joints))
            for kind in ('Blend','Relative','Decompose','Volume')
        )+tuple(
            f'AdvPy_SplineIKScale{kind}{i}'
            for i in range(1,len(self.body_joints))
            for kind in ('Weight','Add')
        )
        orientations=tuple(f'AdvPy_SplineIKLocalOrient{i}'
                           for i in range(len(self.targets)))
        even=('AdvPy_SplineStretchEvenUnit','AdvPy_SplineStretchEvenReverse',
              'AdvPy_SplineStretchEvenWeight')+tuple(
            f'AdvPy_SplineIK{kind}{i}'
            for i in range(len(self.body_joints))
            for kind in ('ArcSample','ArcFrame','Output','OutputPoint',
                         'OutputOrient','OutputScale','OutputReverse'))+tuple(
            f'AdvPy_SplineIKArcAim{i}'
            for i in range(len(self.body_joints)-1))+(
            f'AdvPy_SplineIKArcEndOrient{len(self.body_joints)-1}',)
        twist=('AdvPy_SplineTwistRamp',)+tuple(
            f'AdvPy_SplineTwist{kind}{i}'
            for i in range(1,len(self.targets)-1)
            for kind in ('Relative','Decompose','QuatToEuler'))
        follow=('AdvPy_SplineFollowStart','AdvPy_SplineFollowEnd',
                'AdvPy_SplineFollowStartConstraint',
                'AdvPy_SplineFollowEndConstraint',
                'AdvPy_SplineMidFlipAxis')+tuple(
            f'AdvPy_SplineFollow{kind}{i}'
            for i in range(1,len(self.targets)-1)
            for kind in ('Weight','Reverse','Constraint'))
        layers = (tuple(path.rsplit('|', 1)[-1] for path in self.extra_targets)
                  + tuple(extra.rsplit('|', 1)[-1] + 'Shape'
                          for extra in self.extra_targets)
                  if self.extra_curve else tuple(
                      path.rsplit('|', 1)[-1] for path in self.extra_targets))
        layers += tuple(name for sub in self.sub_targets
                        for name in (sub.rsplit('|', 1)[-1],
                                     sub.rsplit('|', 1)[-1] + 'Shape'))
        hybrids = tuple(f'AdvPy_SplineHybrid{i}{suffix}' for i in range(len(self.hybrid_controls))
                        for suffix in ('Offset','','Shape'))
        proxies = tuple(f'AdvPy_SplineIK{i}{suffix}' for i in range(len(self.targets))
                        for suffix in ('X','XParent')) if self.source_curve_points else ()
        return (fixed+chest+tuple(j.name for j in self.joints)+targets+cvs+hybrids+proxies+layers+outputs+
                rests+scaling+orientations+(even if self.even_stretch_graph else ())+
                (twist if self.twist_ramp_graph else ())+
                (follow if self.mid_follow_graph else ())+
                (('AdvPy_SplineIKFollowMain',) if self.isolated_mid_follow_graph else ()))


def spline_ik_scale_weights(joint_index: int, joint_count: int,
                            target_count: int) -> tuple[float, ...]:
    if not (2 <= joint_count <= 64 and target_count >= 2
            and 0 <= joint_index < joint_count):
        raise FitSkeletonValidationError('Spline IK 缩放权重输入无效')
    position = joint_index / (joint_count - 1)
    weights = []
    for index in range(target_count):
        value = 1.0 - abs(position - index / (target_count - 1))
        factor = max(0.0, min(1.0, (value - 0.5) / 0.5))
        weight = factor * factor * (3.0 - 2.0 * factor)
        if joint_index in (0, joint_count - 1) and index not in (0, target_count - 1):
            weight = 0.0
        weights.append(weight)
    return tuple(weights)


def _basis(count, parameter):
    spans=count-3
    if parameter>=spans:return tuple(0. for _ in range(count-1))+(1.,)
    knots=(0.,)*4+tuple(float(i) for i in range(1,spans))+(float(spans),)*4
    row=[float(a<=parameter<b) for a,b in zip(knots,knots[1:])]
    for degree in range(1,4):
        row=[((parameter-knots[i])/(knots[i+degree]-knots[i])*row[i] if knots[i+degree]>knots[i] else 0.)
             +((knots[i+degree+1]-parameter)/(knots[i+degree+1]-knots[i+1])*row[i+1]
               if knots[i+degree+1]>knots[i+1] else 0.) for i in range(len(row)-1)]
    return tuple(row)


def _solve(matrix,values):
    rows=[list(row)+[value] for row,value in zip(matrix,values)]
    for column in range(len(rows)):
        pivot=max(range(column,len(rows)),key=lambda i:abs(rows[i][column]))
        rows[column],rows[pivot]=rows[pivot],rows[column]
        divisor=rows[column][column]
        if abs(divisor)<1e-12:raise FitSkeletonValidationError('绑定曲线拟合矩阵不可逆')
        rows[column]=[value/divisor for value in rows[column]]
        for i in range(len(rows)):
            if i==column:continue
            factor=rows[i][column]
            rows[i]=[a-factor*b for a,b in zip(rows[i],rows[column])]
    return tuple(row[-1] for row in rows)


def fit_spline_controls(points):
    """Fit a clamped cubic curve through a polyline's joint positions."""
    points=tuple(tuple(float(value) for value in point) for point in points)
    if len(points)<2 or any(len(point)!=3 or not all(isfinite(value) for value in point) for point in points):
        raise FitSkeletonValidationError('绑定曲线需要两个以上有限三维关节位置')
    lengths=tuple(sqrt(sum((b-a)**2 for a,b in zip(left,right))) for left,right in zip(points,points[1:]))
    if min(lengths)<1e-5:raise FitSkeletonValidationError('绑定曲线包含零长度骨段')
    cumulative=(0.,)+tuple(sum(lengths[:i]) for i in range(1,len(points)))
    total=cumulative[-1]
    count=max(4,len(points)+1)
    guide=[]
    for i in range(count):
        distance=total*i/(count-1)
        segment=next((j for j in range(len(lengths)) if distance<=cumulative[j+1]),len(lengths)-1)
        weight=(distance-cumulative[segment])/lengths[segment]
        guide.append(tuple(a+(b-a)*weight for a,b in zip(points[segment],points[segment+1])))
    interior=count-2
    rows=[];targets=[]
    for point,distance in zip(points[1:-1],cumulative[1:-1]):
        basis=_basis(count,(count-3)*distance/total)
        rows.append(basis[1:-1])
        targets.append(tuple(value-basis[0]*points[0][axis]-basis[-1]*points[-1][axis]
                             for axis,value in enumerate(point)))
    regularizer=1e-8
    normal=tuple(tuple(sum(row[i]*row[j] for row in rows)+(regularizer if i==j else 0.)
                       for j in range(interior)) for i in range(interior))
    coordinates=tuple(_solve(normal,tuple(sum(row[i]*target[axis] for row,target in zip(rows,targets))
                                     +regularizer*guide[i+1][axis] for i in range(interior))) for axis in range(3))
    return (points[0],)+tuple(tuple(coordinates[axis][i] for axis in range(3)) for i in range(interior))+(points[-1],)


def with_spline_ik(body, torso, description,
                   build_options: BodyBuildOptions = BodyBuildOptions(),
                   *, fk_root_point_from_receiver: bool = True):
    states = description.validate(body)
    source = tuple(states[name] for name in description.spine)
    controls, plan = plan_body_spline_fk_chain(
        source, torso.controls,
        use_offset_parent_matrix=torso.use_offset_parent_matrix,
        build_options=build_options,
        fk_root_point_from_receiver=fk_root_point_from_receiver)
    return replace(torso, controls=controls, spline=plan)


def plan_body_spline_fk_chain(source, controls, *,
                             use_offset_parent_matrix: bool,
                             build_options: BodyBuildOptions = BodyBuildOptions(),
                             fk_root_point_from_receiver: bool = True,
                             source_control_count: int | None = None):
    """Shared original spline graph for a resolved Fit start/end chain."""
    if type(fk_root_point_from_receiver) is not bool:
        raise FitSkeletonValidationError('Spline FK 起点位置来源开关无效')
    if len(source) < 2 or len({joint.path for joint in source}) != len(source):
        raise FitSkeletonValidationError('Spline 来源链必须至少包含两个唯一关节')
    if any(not body_limb_parent_matches(child.parent_path, parent.path,
            allow_part_parents=True) for parent, child in zip(source, source[1:])):
        raise FitSkeletonValidationError('Spline 来源关节父链不连续')
    if not controls.controls or controls.controls[0].driven_joint != source[0].path:
        raise FitSkeletonValidationError('Spline 基部控制必须对应来源起点')
    delta=tuple(b-a for a,b in zip(source[0].world_position,source[-1].world_position))
    total=sqrt(sum(v*v for v in delta))
    if not isfinite(total) or total<1e-5:raise FitSkeletonValidationError('Spline 脊柱首尾距离必须为非零有限值')
    x=tuple(v/total for v in delta)
    lengths=[];curved=False
    for a,b in zip(source,source[1:]):
        offset=tuple(v-u for u,v in zip(a.world_position,b.world_position))
        length=sqrt(sum(v*v for v in offset))
        if not isfinite(length) or length<1e-5:
            raise FitSkeletonValidationError('Spline 脊柱骨段长度必须为正有限值')
        curved|=abs(sum(u*v for u,v in zip(offset,x))-length)>1e-5
        lengths.append(length)
    root_axis=tuple((b-a)/lengths[0] for a,b in zip(source[0].world_position,source[1].world_position))
    guide=min(source[1].world_axes,key=lambda axis:abs(sum(a*b for a,b in zip(axis,root_axis))))
    x=root_axis
    dot=sum(a*b for a,b in zip(guide,x));y=tuple(a-dot*b for a,b in zip(guide,x));norm=sqrt(sum(v*v for v in y));y=tuple(v/norm for v in y)
    z=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]);axes=(x,y,z)
    source=(replace(source[0],world_axes=axes),*source[1:])
    def ik_axes(index):
        if index==len(source)-1:return source[index].world_axes
        direction=tuple((b-a)/lengths[index] for a,b in zip(source[index].world_position,source[index+1].world_position))
        guide=min(source[index].world_axes,key=lambda axis:abs(sum(a*b for a,b in zip(axis,direction))))
        projection=sum(a*b for a,b in zip(guide,direction))
        second=tuple(a-projection*b for a,b in zip(guide,direction))
        magnitude=sqrt(sum(value*value for value in second))
        second=tuple(value/magnitude for value in second)
        third=(direction[1]*second[2]-direction[2]*second[1],direction[2]*second[0]-direction[0]*second[2],direction[0]*second[1]-direction[1]*second[0])
        return (direction,second,third)
    root=controls.root_path+'|AdvPy_SplineMechanisms';specs=[]
    for role in (BodyLimbMechanismRole.FK,BodyLimbMechanismRole.IK):
        parent=root
        for index,joint in enumerate(source):
            name=f'AdvPy_Spline{role.value.upper()}Joint{index}'
            specs.append(BodyLimbMechanismJointSpec(role,joint.side,joint.path,parent+'|'+name,name,parent,joint.world_position,ik_axes(index) if curved and role==BodyLimbMechanismRole.IK else joint.world_axes))
            parent=specs[-1].path
    pelvis=controls.controls[0]
    pelvis_parent=(pelvis.source_override_path
                   if pelvis.source_override_joint
                   and not use_offset_parent_matrix
                   else pelvis.control_path)
    offset=pelvis_parent+'|AdvPy_SplineBaseFKOffset'
    extra_name='AdvPy_SplineBaseFKExtra'
    extra=offset+'|'+extra_name
    base_control=extra+'|AdvPy_SplineBaseFK'
    sub_name=('AdvPy_SplineBaseFKSub'
              if pelvis.sub_control_path is not None else None)
    sub_path=(base_control+'|'+sub_name if sub_name else None)
    use_fkx=pelvis.source_override_joint
    base_fkx=((sub_path or base_control)+'|AdvPy_SplineBaseFKX'
              if use_fkx else None)
    base=BodyLimbFkControlSpec(
        source[0].side,specs[0].path,offset,'AdvPy_SplineBaseFKOffset',
        base_control,'AdvPy_SplineBaseFK',pelvis_parent,
        'AdvPy_SplineBaseFKOrient',source[0].world_position,axes,
        pelvis.radius,
        extra_path=extra,extra_name=extra_name,
        extra_curve=pelvis.extra_curve,
        sub_control_path=sub_path,
        sub_control_name=sub_name,
        source_override_path=base_fkx,
        source_override_joint=use_fkx,
        source_override_segment_scale_compensate=(
            not use_offset_parent_matrix),
        fit_joint_names=(source[0].name.rsplit("_", 1)[0],))
    def child_parent(control):
        return (control.source_override_path
                if control.source_override_joint
                and not use_offset_parent_matrix
                else control.control_path)
    updated=[pelvis,base];parent=child_parent(base);fk=[base.control_path]
    by_joint={c.driven_joint:c for c in controls.controls}
    for index,joint in enumerate(source[1:],1):
        old=by_joint[joint.path]
        control=reparent_body_fk_control(
            old,parent,driven_joint=specs[index].path)
        updated.append(control);parent=child_parent(control)
        fk.append(control.control_path)
    space=controls.root_path+'|AdvPy_SplineChestSpace';mapping={}
    for old in controls.controls:
        if old.driven_joint in {j.path for j in source}:continue
        parent=mapping.get(old.parent_path,space)
        control=reparent_body_fk_control(old,parent)
        mapping[old.control_path]=control.control_path
        if old.source_override_path is not None:
            mapping[old.source_override_path]=child_parent(control)
        updated.append(control)
    source_points = ()
    fake_mid = False
    if source_control_count is not None:
        from .source_spline_cv import source_spline_control_positions
        if type(source_control_count) is not int or not 2 <= source_control_count <= 64:
            raise FitSkeletonValidationError('来源 Spline 控制器数量无效')
        source_points = tuple(j.world_position for j in source)
        fake_mid = source_control_count == 2
        positions = source_spline_control_positions(source_points, max(3, source_control_count))
    else:
        positions=(fit_spline_controls(tuple(j.world_position for j in source)) if curved else
               tuple(tuple(a+(b-a)*i/3 for a,b in zip(source[0].world_position,source[-1].world_position)) for i in range(4)))
    isolated_follow=len(source)>2
    targets=tuple((pelvis.control_path+
                   ('|AdvPy_SplineIKFollowMain' if isolated_follow and 0<i<len(positions)-1 else '')+
                   f'|AdvPy_SplineIK{i}Offset|AdvPy_SplineIK{i}Extra|AdvPy_SplineIK{i}')
                  for i in range(len(positions)))
    subs=tuple(target+f'|AdvPy_SplineIK{i}Sub'
               for i,target in enumerate(targets)) if build_options.sub_controllers else ()
    plan=BodySplinePlan(root,tuple(specs),tuple(j.path for j in source),tuple(fk),pelvis.control_path,space,targets,positions,axes,tuple(lengths),use_offset_parent_matrix,True,isolated_follow,isolated_follow,isolated_follow,subs,build_options.extra_controllers,
                        fk_root_point_from_receiver=fk_root_point_from_receiver,
                        source_curve_points=source_points, fake_mid_control=fake_mid,
                        source_hybrid_graph=bool(source_points))
    if plan.source_hybrid_graph:
        targets = tuple(plan.target_parent(i) +
                        f'|AdvPy_SplineIK{i}Offset|AdvPy_SplineIK{i}Extra|AdvPy_SplineIK{i}'
                        for i in range(len(plan.targets)))
        subs = tuple(target+f'|AdvPy_SplineIK{i}Sub' for i,target in enumerate(targets)) if subs else ()
        plan = replace(plan, targets=targets, sub_targets=subs)
    return replace(controls, controls=tuple(updated)), plan
