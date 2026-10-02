"""ADV 6.925 asFitAutoScale / asFitAutoPlace's scale-and-eye phase."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class FitAutoScaleJoint:
    path: str
    position: tuple[float, float, float]
    fat: float | None = None


@dataclass(frozen=True, slots=True)
class FitAutoScaleSnapshot:
    container: str
    joints: tuple[FitAutoScaleJoint, ...]
    container_scale_y: float
    geometry_max_y: float
    icon_max_x: float


@dataclass(frozen=True, slots=True)
class FitAutoScalePlan:
    before: FitAutoScaleSnapshot
    factor: float
    positions: tuple[tuple[str, tuple[float, float, float]], ...]
    fats: tuple[tuple[str, float], ...]
    icon_factor: float
    joint_display_scale: float


def plan_fit_auto_scale(snapshot: FitAutoScaleSnapshot) -> FitAutoScalePlan:
    if not snapshot.joints or len({joint.path for joint in snapshot.joints}) != len(snapshot.joints):
        raise ValueError('自动缩放需要唯一且非空的 Fit 关节链')
    values=(snapshot.container_scale_y,snapshot.geometry_max_y,snapshot.icon_max_x)
    if any(isinstance(value,bool) or not isfinite(value) for value in values):
        raise ValueError('自动缩放的容器和模型尺寸必须有限')
    if snapshot.icon_max_x <= 1e-10:
        raise ValueError('Fit 容器曲线的 X 尺寸退化')
    for joint in snapshot.joints:
        if (not joint.path or len(joint.position)!=3
                or any(isinstance(value,bool) or not isfinite(value) for value in joint.position)
                or joint.fat is not None and (isinstance(joint.fat,bool) or not isfinite(joint.fat))):
            raise ValueError('自动缩放的关节位置或 fat 无效')
    # MEL uses the maximum world Y, not height=maxY-minY, and retains Fit.sy.
    maximum=max(.1,max(0.,*(joint.position[1] for joint in snapshot.joints)))
    factor=snapshot.geometry_max_y / maximum * snapshot.container_scale_y
    return FitAutoScalePlan(snapshot,factor,
        tuple((joint.path,tuple(value*factor for value in joint.position)) for joint in snapshot.joints),
        tuple((joint.path,joint.fat*factor) for joint in snapshot.joints if joint.fat is not None),
        snapshot.geometry_max_y / 5.5 / snapshot.icon_max_x,
        snapshot.geometry_max_y / 100.)
