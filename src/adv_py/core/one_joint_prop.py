"""Fit inputs of ADV 6.925 asOneJointProp, MEL 77122–77173."""
from dataclasses import dataclass
from math import isfinite

from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True, slots=True)
class OneJointPropFitPlan:
    position: tuple[float, float, float]
    joint_orient: tuple[float, float, float]
    fat: float
    fit_cv_scale: float


def plan_one_joint_prop_fit(world_bounds):
    if (len(world_bounds) != 6 or
            any(not isfinite(float(value)) for value in world_bounds) or
            any(world_bounds[axis] > world_bounds[axis + 3] for axis in range(3))):
        raise FitSkeletonValidationError('One Joint Prop 世界包围盒无效')
    bounds = tuple(float(value) for value in world_bounds)
    # Preserve the source's absolute upper Y rather than replacing it with
    # object height; even zero/negative input goes to Maya's source attributes.
    size = bounds[4] / 2.
    return OneJointPropFitPlan(
        tuple((bounds[axis] + bounds[axis + 3]) / 2. for axis in range(3)),
        (90., 0., 90.), size, size)
