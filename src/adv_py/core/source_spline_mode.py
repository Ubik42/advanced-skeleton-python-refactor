"""Original Advanced FKIK controller identity and source Spline blend units."""
from dataclasses import dataclass
from math import isfinite
import re


@dataclass(frozen=True)
class SourceSplineModePlan:
    name: str
    fit_start_joint: str
    parent_source: str
    icon_scale: float
    chain_length: float
    start_joint: str
    middle_joint: str
    end_joint: str
    side_sign: int = 1

    def __post_init__(self):
        if (type(self.side_sign) is not int or self.side_sign not in (-1,1)
                or not re.fullmatch(r'FKIK[A-Za-z][A-Za-z0-9_]*_[MRL]',self.name)
                or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name)
                       for name in (self.fit_start_joint,self.start_joint,self.middle_joint,self.end_joint))
                or not self.parent_source.startswith('|')
                or any(isinstance(value,bool) or not isinstance(value,(int,float))
                       or not isfinite(value) or value<=0
                       for value in (self.icon_scale,self.chain_length))):
            raise ValueError('来源 Spline FKIK 控制器身份或尺寸无效')

    @property
    def token(self):return self.name[4:]

    @property
    def frame_name(self):return 'FKIKParentConstraint'+self.token

    @property
    def frame(self):return '|Group|MotionSystem|FKIKSystem|'+self.frame_name

    @property
    def control(self):return self.frame+'|'+self.name

    @property
    def weight_unit(self):return 'FKIKBlend'+self.token+'UnitConversion'

    @property
    def visibility_unit(self):
        stem,side=self.token.rsplit('_',1)
        return 'FKIKBlend'+stem+'UnitConversion_'+side

    @property
    def visibility_range(self):
        stem,side=self.token.rsplit('_',1)
        return 'FKIKBlend'+stem+'setRange_'+side

    @property
    def hybrid_visibility_unit(self):
        stem,side=self.token.rsplit('_',1)
        return 'FKIKBlend'+stem+'ConditionUnitConversion_'+side

    @property
    def radius(self):
        return self.chain_length/20. if self.icon_scale<self.chain_length/60. else self.icon_scale

    @property
    def node_names(self):
        return (self.frame_name,self.name,self.name+'Shape',self.weight_unit,
                self.visibility_unit,self.visibility_range,self.hybrid_visibility_unit)


def source_mode_icon_scale(hierarchy):
    """Original bounds use zero / 99 initial extrema (MEL 79476–79500)."""
    ranges=[]
    for axis in range(3):
        maximum=0.;minimum=0. if len(hierarchy.joints)==1 else 99.
        for joint in hierarchy.joints:
            maximum=max(maximum,joint.world_position[axis])
            minimum=min(minimum,joint.world_position[axis])
        ranges.append(maximum-minimum)
    value=max(ranges)/80.
    if not isfinite(value) or value<=0:
        raise ValueError('来源 Spline FKIK 图标需要非零 Fit 范围')
    return value
