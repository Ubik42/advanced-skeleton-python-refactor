"""Topology-preserving face target deformation from sparse vertex anchors."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .face_shapes import FaceMeshSnapshot


@dataclass(frozen=True, slots=True)
class FaceLandmark:
    vertex: int
    displacement: tuple[float, float, float]
    radius: float

    def __post_init__(self):
        if (type(self.vertex) is not int or self.vertex < 0
                or not isinstance(self.displacement, tuple)
                or len(self.displacement) != 3
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not isfinite(value) for value in self.displacement)
                or isinstance(self.radius, bool)
                or not isinstance(self.radius, (int, float))
                or not isfinite(self.radius) or self.radius <= 0.):
            raise ValueError("面部标记顶点、位移或作用半径无效")


def deform_face_landmarks(
    neutral: FaceMeshSnapshot,
    landmarks: tuple[FaceLandmark, ...],
) -> tuple[tuple[float, float, float], ...]:
    if (not isinstance(neutral, FaceMeshSnapshot)
            or not isinstance(landmarks, tuple)
            or not 1 <= len(landmarks) <= 128
            or any(not isinstance(item, FaceLandmark)
                   or item.vertex >= neutral.vertex_count for item in landmarks)
            or len({item.vertex for item in landmarks}) != len(landmarks)
            or not any(any(abs(value) > 1e-7 for value in item.displacement)
                       for item in landmarks)):
        raise ValueError("面部标记清单无效或没有有效位移")
    anchors = {item.vertex: item for item in landmarks}
    points = []
    for vertex, point in enumerate(neutral.points):
        if vertex in anchors:
            delta = anchors[vertex].displacement
        else:
            influences = []
            for item in landmarks:
                anchor = neutral.points[item.vertex]
                distance = sqrt(sum((a - b) ** 2 for a, b in zip(point, anchor)))
                if distance < item.radius:
                    ratio = distance / item.radius
                    influences.append(((1. - ratio * ratio) ** 2,
                                       item.displacement))
            total = sum(weight for weight, _ in influences)
            delta = tuple(sum(weight * shift[axis] for weight, shift in influences)
                          / max(1., total) for axis in range(3))
        points.append(tuple(float(point[axis] + delta[axis]) for axis in range(3)))
    if any(not isfinite(value) for point in points for value in point):
        raise ValueError("面部目标顶点位置超出有限数值范围")
    return tuple(points)
