"""Typed inputs from AdvancedSkeleton Preparation / Rig."""
from __future__ import annotations

from enum import Enum


class PreparationObjectRole(str, Enum):
    SKIN = "Skin"
    ALL = "All"
    RIGHT_EYE = "Right Eye"
    LEFT_EYE = "Left Eye"


def validate_preparation_objects(
    role: PreparationObjectRole, objects: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(role, PreparationObjectRole):
        raise ValueError("未知的准备模型分类")
    # The source writes object/component lists for all four fields, including
    # an empty list to clear a previously recorded field.
    if any(not name for name in objects):
        raise ValueError("所选模型包含空路径")
    return objects
