"""Two weighted deformation joints per standard axial Body segment."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class AxialPartSpec:
    name: str
    path: str
    parent: str
    start: str
    end: str
    fraction: float
    position: tuple[float, float, float]


def plan_axial_parts(body: BodySkeletonSnapshot) -> tuple[AxialPartSpec, ...]:
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("Body 关节名称不唯一")
    specs = []
    for start_name, end_name in (("Root_M", "Spine1_M"),
                                 ("Spine1_M", "Chest_M"),
                                 ("Neck_M", "Head_M")):
        start = by_name.get(start_name)
        end = by_name.get(end_name)
        if start is None or end is None or end.parent_path != start.path:
            raise ValueError("轴向分段需要 Root/Spine1/Chest 和 Neck/Head 直接父子链")
        stem = start_name.rsplit("_", 1)[0]
        parent = start.path
        for index in (1, 2):
            fraction = index / 3.0
            name = f"{stem}Part{index}_M"
            path = f"{parent}|{name}"
            position = tuple(a + (b - a) * fraction
                             for a, b in zip(start.world_position,
                                             end.world_position))
            specs.append(AxialPartSpec(name, path, parent, start.path,
                                       end.path, fraction, position))
            parent = path
    return tuple(specs)
