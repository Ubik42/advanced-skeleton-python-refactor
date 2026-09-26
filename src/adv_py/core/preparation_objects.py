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
    if not objects:
        raise ValueError(f"请先选择 {role.value} 模型")
    if len(objects) != len(set(objects)) or any(not name for name in objects):
        raise ValueError("所选模型包含重复或空路径")
    if role in (PreparationObjectRole.RIGHT_EYE,
                PreparationObjectRole.LEFT_EYE) and len(objects) != 1:
        raise ValueError(f"{role.value} 只接受一个眼球模型")
    return objects
