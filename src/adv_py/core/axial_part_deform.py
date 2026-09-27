"""Two weighted deformation joints per described axial Body segment."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .body_description import BodyAxialDescription
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


def plan_axial_parts(
    body: BodySkeletonSnapshot,
    description: BodyAxialDescription | None = None,
) -> tuple[AxialPartSpec, ...]:
    axial = description or BodyAxialDescription()
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("Body 关节名称不唯一")
    specs = []
    for start_name, end_name in (
        *zip(axial.spine, axial.spine[1:]),
        *zip(axial.neck, axial.neck[1:]),
    ):
        if start_name not in by_name or end_name not in by_name:
            raise ValueError("轴向分段缺少 Body 关节：" +
                             (start_name if start_name not in by_name
                              else end_name))
        start = by_name[start_name]
        end = by_name[end_name]
        if end.parent_path != start.path:
            raise ValueError("轴向分段描述与 Body 父子链不一致：" + end_name)
        delta = tuple(b - a for a, b in zip(start.world_position,
                                             end.world_position))
        length = sqrt(sum(value * value for value in delta))
        if not isfinite(length) or length < 1e-5:
            raise ValueError("轴向分段长度无效：" + start_name + " → " + end_name)
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
