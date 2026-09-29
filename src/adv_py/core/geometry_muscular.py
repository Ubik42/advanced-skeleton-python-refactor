"""Name and influence rules for ADV 6.925 Muscular geometry."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MuscleBoneMatch:
    template: str
    skeleton: str


def plan_muscle_bone_matches(imported: tuple[str, ...],
                             skeleton: set[str]) -> tuple[MuscleBoneMatch, ...]:
    """Pair each imported Muscular_* mesh with a created Skeleton bone."""
    result = []
    for name in imported:
        if not name.startswith("Muscular_"):
            continue
        target = name[len("Muscular_"): ]
        if target in skeleton:
            result.append(MuscleBoneMatch(name, target))
    return tuple(result)


def resolve_muscle_influence(source: str, parents: dict[str, str],
                             skeleton: set[str]) -> str:
    """Walk template parents until its matching live Skeleton bone exists."""
    visited: set[str] = set()
    current = source
    while current and current not in visited:
        visited.add(current)
        target = current.removeprefix("Muscular_")
        if target in skeleton:
            return target
        current = parents.get(current, "")
    raise ValueError("肌肉曲线没有可映射的骨形影响关节：" + source)


def mirrored_name(name: str) -> str:
    if not name.endswith("_R"):
        raise ValueError("肌肉镜像来源必须在右侧：" + name)
    return name[:-2] + "_L"

