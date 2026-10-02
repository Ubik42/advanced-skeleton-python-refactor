"""Inputs for original curve palette, line width and 90-degree rotation."""
from dataclasses import dataclass
from math import isfinite
from .control_curves import ControlCurveValidationError


@dataclass(frozen=True,slots=True)
class ControlCurvePalette:
    index: int
    rgb: tuple[float,float,float] | None = None

    def __post_init__(self):
        if type(self.index) is not int or not 0<=self.index<=31:
            raise ControlCurveValidationError('曲线颜色索引须为 0 至 31')
        if self.rgb is not None and (len(self.rgb)!=3 or
            any(not isfinite(float(value)) or not 0<=value<=1 for value in self.rgb)):
            raise ControlCurveValidationError('RGB 颜色须为三个 0 至 1 的数值')

    def uses_rgb(self,default_rgb,maya_version):
        return maya_version>=2014 and self.index>0 and self.rgb is not None and tuple(default_rgb)!=tuple(self.rgb)


def validate_curve_width(width):
    if type(width) is not int or not -1<=width<=100:
        raise ControlCurveValidationError('曲线宽度须为 -1 至 100 的整数')
    return width


def snap_rotation(axis):
    if axis not in ('x','y','z'):
        raise ControlCurveValidationError('曲线旋转轴须为 x、y 或 z')
    return tuple(90. if coordinate==axis else 0. for coordinate in 'xyz')
