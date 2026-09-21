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
    def curved(self):
        if len(self.targets)>4:return True
        start,end=self.positions[0],self.positions[-1]
        direction=tuple(b-a for a,b in zip(start,end))
        squared=sum(value*value for value in direction)
        if squared<1e-10:return True
        for point in self.positions[1:-1]:
            offset=tuple(b-a for a,b in zip(start,point))
            projection=sum(a*b for a,b in zip(offset,direction))/squared
            if sum((a-projection*b)**2 for a,b in zip(offset,direction))>1e-10:
                return True
        return False
    @property
    def ik_outputs(self):
        n=len(self.body_joints)
        return tuple(self.joints[n+i].path+(f'|AdvPy_SplineIKRest{i}' if self.curved and i else '') for i in range(n))
    @property
    def node_names(self):
        fixed=('AdvPy_SplineMechanisms','AdvPy_SplineChestSpace','AdvPy_SplineCurve','AdvPy_SplineCurveShape',
            'AdvPy_SplineIKHandle','AdvPy_SplineIKEffector','AdvPy_SplineFKRootPoint','AdvPy_SplineIKRootPoint',
            'AdvPy_SplineChestOrient','AdvPy_SplineChestSpaceParent','AdvPy_SplineReverse','AdvPy_SplineArc',
            'AdvPy_SplineRatio','AdvPy_SplineStretchBlend','AdvPy_SplineClamp','AdvPy_SplineVolumeExponent','AdvPy_SplineVolume')
        targets=tuple(f'AdvPy_SplineIK{i}{suffix}' for i in range(len(self.targets)) for suffix in ('Offset','','Shape','Matrix','Position'))
        outputs=tuple(f'AdvPy_Spline{kind}{i}' for i in range(1,len(self.body_joints)) for kind in ('Point','Orient','Scale','Length','FKWorldScale','IKWorldScale'))
        rests=tuple(f'AdvPy_SplineIKRest{i}' for i in range(1,len(self.body_joints))) if self.curved else ()
        return fixed+tuple(j.name for j in self.joints)+targets+outputs+rests


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


def with_spline_ik(body,torso,description):
    states=description.validate(body)
    source=tuple(states[name] for name in description.spine)
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
    root=torso.controls.root_path+'|AdvPy_SplineMechanisms';specs=[]
    for role in (BodyLimbMechanismRole.FK,BodyLimbMechanismRole.IK):
        parent=root
        for index,joint in enumerate(source):
            name=f'AdvPy_Spline{role.value.upper()}Joint{index}'
            specs.append(BodyLimbMechanismJointSpec(role,joint.side,joint.path,parent+'|'+name,name,parent,joint.world_position,ik_axes(index) if curved and role==BodyLimbMechanismRole.IK else joint.world_axes))
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
    positions=(fit_spline_controls(tuple(j.world_position for j in source)) if curved else
               tuple(tuple(a+(b-a)*i/3 for a,b in zip(source[0].world_position,source[-1].world_position)) for i in range(4)))
    targets=tuple(pelvis.control_path+f'|AdvPy_SplineIK{i}Offset|AdvPy_SplineIK{i}' for i in range(len(positions)))
    plan=BodySplinePlan(root,tuple(specs),tuple(j.path for j in source),tuple(fk),pelvis.control_path,space,targets,positions,axes,tuple(lengths))
    return replace(torso,controls=replace(torso.controls,controls=tuple(updated)),spline=plan)
