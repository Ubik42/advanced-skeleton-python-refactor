"""Map PolyBoxes to their Body influences for the combined BoxSkin mesh."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoxSkinPair:
    box: str
    joint: str


def plan_box_skin(boxes: tuple[str, ...]) -> tuple[BoxSkinPair, ...]:
    if not boxes:
        raise ValueError("BoxSkin 没有可用的 PolyBoxes")
    pairs = []
    for box in boxes:
        if not box.endswith(("Box_M", "Box_R", "Box_L")):
            raise ValueError("BoxSkin 盒体名称无效：" + box)
        pairs.append(BoxSkinPair(box, box[:-5] + box[-2:]))
    if len({item.box for item in pairs}) != len(pairs):
        raise ValueError("BoxSkin 盒体名称重复")
    return tuple(pairs)
