"""Plan one surface-projected Warp for each selected mesh and PolyBox."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WarpSpec:
    source: str
    box: str
    joint: str
    name: str
    divisions: int


def plan_warps(sources: tuple[str, ...], boxes: tuple[str, ...],
               occupied: frozenset[str] = frozenset()) -> tuple[WarpSpec, ...]:
    if not sources:
        raise ValueError("Warp 需要选择至少一个多边形网格")
    if not boxes:
        raise ValueError("Warp 需要先创建 PolyBoxes")
    if len(set(sources)) != len(sources) or len(set(boxes)) != len(boxes):
        raise ValueError("Warp 来源网格或盒体重复")
    names = set(occupied)
    result = []
    for source in sources:
        for box in boxes:
            if not box.endswith(("Box_M", "Box_R", "Box_L")):
                raise ValueError("Warp 盒体名称无效：" + box)
            stem, side = box[:-5], box[-2:]
            name = next((candidate for index in range(1, 99)
                         if (candidate := f"{stem}BoxWarp{index}{side}")
                         not in names), None)
            if name is None:
                name=f"{stem}BoxWarp99{side}"
            names.add(name)
            joint = stem + side
            result.append(WarpSpec(source, box, joint, name,
                                   4 if joint == "Head_M" else 2))
    return tuple(result)
