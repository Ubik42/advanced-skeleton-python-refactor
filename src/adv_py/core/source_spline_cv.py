"""ADV 6.925 Spline CV neighbour selection and distance blend weights."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .body_spline import _basis
from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True)
class SourceSplineCvBinding:
    index: int
    first: int
    second: int
    weight: float
    stiffness_control: int | None = None


def source_spline_cv_bindings(points, controls):
    """First nearest by distance, then only a +/-1 neighbour (v6.6641).

    The first target is the blendMatrix target, not its input. Stiffness
    moves that target's weight towards one for the first/last interior CV.
    """
    if len(points) < 2 or len(controls) < 3:
        raise FitSkeletonValidationError('来源 Spline CV 或主控数量不足')
    result = []
    for index, point in enumerate(points[1:-1], 1):
        distances = tuple(sqrt(sum((a-b)**2 for a, b in zip(point, control)))
                          for control in controls)
        first = min(range(len(controls)), key=lambda i: distances[i])
        neighbours = tuple(i for i in (first-1, first+1) if 0 <= i < len(controls))
        second = min(neighbours, key=lambda i: distances[i])
        stiffness = None
        if len(points) > 3:
            if index == 1:
                stiffness = 0
                if second == 0:
                    first, second = second, first
            if index == len(points)-2:
                stiffness = len(controls)-1
                if second == stiffness:
                    first, second = second, first
        total = distances[first] + distances[second]
        if total < 1e-12:
            raise FitSkeletonValidationError('来源 Spline 相邻主控重合')
        result.append(SourceSplineCvBinding(index, first, second,
                                             distances[second]/total, stiffness))
    return tuple(result)


def source_spline_control_positions(points, count):
    """Offline arc-fraction guide; the Maya boundary captures exact motionPath positions.

    CVs stay at source joint positions. They are never replaced by the
    interpolation-fit curve used by the legacy standard-spine path.
    """
    degree = 1 if len(points) < 4 else 3
    if degree == 1:
        samples = tuple(points)
    else:
        steps = max(256, (len(points)-3)*64)
        samples = tuple(tuple(sum(weight*point[axis] for weight, point in
                            zip(_basis(len(points), (len(points)-3)*i/steps), points))
                            for axis in range(3)) for i in range(steps+1))
    lengths = tuple(sqrt(sum((a-b)**2 for a,b in zip(left,right)))
                    for left,right in zip(samples,samples[1:]))
    total = sum(lengths)
    if total <= 1e-12:
        raise FitSkeletonValidationError('来源 Spline 曲线长度为零')
    result = [tuple(points[0])]
    segment = 0
    distance_before = 0.
    for index in range(1, count-1):
        distance = total*index/(count-1)
        while segment < len(lengths)-1 and distance_before+lengths[segment] < distance:
            distance_before += lengths[segment]
            segment += 1
        fraction = (distance-distance_before)/lengths[segment]
        result.append(tuple(a+(b-a)*fraction for a,b in
                            zip(samples[segment],samples[segment+1])))
    return tuple(result) + (tuple(points[-1]),)
