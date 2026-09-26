from __future__ import annotations

from enum import Enum
from math import isfinite

from .fit_container import FitUpAxis
from .fit_settings import FitSkeletonValidationError
from .fit_template import (
    FitJointSpec,
    FitTemplateSpec,
    synthetic_body_source_fit_template,
)
from .joint_labels import JointLabel


Vector3 = tuple[float, float, float]


class BodyHandDigit(str, Enum):
    THUMB = "Thumb"
    INDEX = "Index"
    MIDDLE = "Middle"
    RING = "Ring"
    PINKY = "Pinky"


BODY_HAND_DIGITS = tuple(BodyHandDigit)
BODY_HAND_SEGMENTS = ("1", "2", "3", "End")


def body_hand_source_joint_names() -> tuple[str, ...]:
    return tuple(
        f"{digit.value}{segment}"
        for digit in BODY_HAND_DIGITS
        for segment in BODY_HAND_SEGMENTS
    )


def advanced_skeleton_hand_source_joint_names() -> tuple[str, ...]:
    """Names used by the public AdvancedSkeleton 6.925 sample Fit hand."""
    return tuple(
        f"{digit.value}Finger{index}"
        for digit in BODY_HAND_DIGITS
        for index in range(1, 5)
    )


def synthetic_body_with_hand_source_fit_template(
    up_axis: FitUpAxis,
    *,
    scale: float = 1.0,
) -> FitTemplateSpec:
    """Return the synthetic body source with one complete five-digit hand."""

    if (
        not isinstance(up_axis, FitUpAxis)
        or isinstance(scale, bool)
        or not isinstance(scale, (int, float))
        or not isfinite(float(scale))
        or float(scale) <= 0.0
    ):
        raise FitSkeletonValidationError(
            "五指全身源 Fit 模板需要 Y/Z Up 和正有限缩放"
        )

    base = synthetic_body_source_fit_template(up_axis, scale=scale)
    unit = float(scale)
    finger_label = JointLabel.parse("Finger")

    def palm_offset(x: float, spread: float) -> Vector3:
        if up_axis is FitUpAxis.Y:
            return (x * unit, 0.0, spread * unit)
        return (x * unit, spread * unit, 0.0)

    definitions = (
        (BodyHandDigit.THUMB, -1.05, (0.72, 0.62, 0.52)),
        (BodyHandDigit.INDEX, -0.55, (0.98, 0.76, 0.58)),
        (BodyHandDigit.MIDDLE, 0.0, (1.08, 0.84, 0.64)),
        (BodyHandDigit.RING, 0.55, (0.98, 0.76, 0.58)),
        (BodyHandDigit.PINKY, 1.05, (0.82, 0.64, 0.48)),
    )
    joints = list(base.joints)
    for digit, spread, lengths in definitions:
        first = f"{digit.value}1"
        second = f"{digit.value}2"
        third = f"{digit.value}3"
        end = f"{digit.value}End"
        joints.extend((
            FitJointSpec(
                first,
                "Wrist",
                palm_offset(-0.35, spread),
                finger_label,
            ),
            FitJointSpec(
                second,
                first,
                palm_offset(-lengths[0], -0.12 if digit is BodyHandDigit.THUMB else 0.0),
                finger_label,
            ),
            FitJointSpec(
                third,
                second,
                palm_offset(-lengths[1], 0.0),
                finger_label,
            ),
            FitJointSpec(
                end,
                third,
                palm_offset(-lengths[2], 0.0),
                finger_label,
            ),
        ))
    return FitTemplateSpec(
        name="synthetic_body_with_hand_source",
        joints=tuple(joints),
    )
