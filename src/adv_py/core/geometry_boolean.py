"""Plan original PolyBoxes Boolean intersections by source mesh and box."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BooleanSpec:
    source: str
    box: str
    joint: str
    name: str


def plan_booleans(sources: tuple[str, ...],
                  boxes: tuple[str, ...]) -> tuple[BooleanSpec, ...]:
    if not sources:
        raise ValueError("Boolean 需要选择至少一个多边形网格")
    if not boxes:
        raise ValueError("Boolean 需要先创建 PolyBoxes")
    if len(set(sources)) != len(sources) or len(set(boxes)) != len(boxes):
        raise ValueError("Boolean 来源网格或盒体重复")
    plan = []
    for index, source in enumerate(sources):
        for box in boxes:
            if not box.endswith(("Box_M", "Box_R", "Box_L")):
                raise ValueError("Boolean 盒体名称无效：" + box)
            joint = box[:-5] + box[-2:]
            name = box[:-5] + "Bool" + box[-2:]
            if index:
                name += "_" + str(index + 1)
            plan.append(BooleanSpec(source, box, joint, name))
    return tuple(plan)
