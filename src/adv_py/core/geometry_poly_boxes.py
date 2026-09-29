"""Plan AdvancedSkeleton's Fit-derived PolyBoxes on Body joints."""
from __future__ import annotations

from dataclasses import dataclass
from math import dist, isfinite


Vec3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class PolyBoxSource:
    stem: str
    side: str
    start_joint: str
    end_joint: str
    start: Vec3
    end: Vec3
    start_front: float
    start_width: float
    end_front: float
    end_width: float
    parts: int
    floor_foot: bool = False
    heel: Vec3 | None = None


@dataclass(frozen=True, slots=True)
class PolyBoxSpec:
    name: str
    driver: str
    start: Vec3
    end: Vec3
    front_start: float
    width_start: float
    front_end: float
    width_end: float
    floor_foot: bool = False
    heel: Vec3 | None = None


def plan_poly_boxes(sources: tuple[PolyBoxSource, ...]) -> tuple[PolyBoxSpec, ...]:
    if not sources:
        raise ValueError("当前 Body 没有可生成 PolyBoxes 的 Fit 骨段")
    boxes = []
    for source in sources:
        if (source.side not in ("_M", "_R", "_L")
                or not source.stem or source.parts < 1
                or dist(source.start, source.end) < 1e-5):
            raise ValueError("PolyBoxes Fit 骨段无效：" + source.stem)
        widths = (source.start_front, source.start_width,
                  source.end_front, source.end_width)
        if any(not isfinite(value) or value <= 0 for value in widths):
            raise ValueError("PolyBoxes Fit 体积参数无效：" + source.stem)
        for index in range(source.parts):
            a = index / source.parts
            b = (index + 1) / source.parts
            start = tuple(source.start[axis] * (1 - a) +
                          source.end[axis] * a for axis in range(3))
            end = tuple(source.start[axis] * (1 - b) +
                        source.end[axis] * b for axis in range(3))
            front_a = source.start_front * (1 - a) + source.end_front * a
            front_b = source.start_front * (1 - b) + source.end_front * b
            width_a = source.start_width * (1 - a) + source.end_width * a
            width_b = source.start_width * (1 - b) + source.end_width * b
            stem = source.stem + ("Part" + str(index) if index else "")
            boxes.append(PolyBoxSpec(
                stem + "Box" + source.side,
                (stem + source.side if index else source.start_joint),
                start, end, front_a, width_a, front_b, width_b,
                source.floor_foot and index == 0,
                source.heel if index == 0 else None))
    if len({box.name for box in boxes}) != len(boxes):
        raise ValueError("PolyBoxes 目标名称重复")
    return tuple(boxes)


def plan_poly_box_mirror(names: tuple[str, ...],
                         source_side: str) -> tuple[tuple[str, str], ...]:
    if source_side not in ("L", "R"):
        raise ValueError("PolyBoxes 镜像来源侧必须是 L 或 R")
    target = "R" if source_side == "L" else "L"
    available = set(names)
    return tuple((name, name[:-1] + target)
                 for name in sorted(available)
                 if name.endswith("_" + source_side)
                 and name[:-1] + target in available)
