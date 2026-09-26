"""AdvancedSkeleton Preparation model-check rules without Maya dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from math import dist, isfinite


MODEL_SYMMETRY_TOLERANCE = 0.001
_ALLOWED_HISTORY_TYPES = frozenset({
    "skinCluster", "blendShape", "tweak", "deltaMush", "shadingEngine",
})
_TRANSFORM_FIELDS = (
    ("translate", (0.0, 0.0, 0.0)),
    ("rotate", (0.0, 0.0, 0.0)),
    ("scale", (1.0, 1.0, 1.0)),
    ("rotatePivot", (0.0, 0.0, 0.0)),
    ("scalePivot", (0.0, 0.0, 0.0)),
)


@dataclass(frozen=True, slots=True)
class ModelTransformState:
    path: str
    translate: tuple[float, float, float]
    rotate: tuple[float, float, float]
    scale: tuple[float, float, float]
    rotatePivot: tuple[float, float, float]
    scalePivot: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class ModelTransformIssue:
    path: str
    attribute: str
    value: float
    expected: float


@dataclass(frozen=True, slots=True)
class ModelHistoryNode:
    name: str
    node_type: str


@dataclass(frozen=True, slots=True)
class ModelSymmetryIssue:
    vertex: int
    closest_vertex: int
    distance: float


@dataclass(frozen=True, slots=True)
class ModelCheckResult:
    mesh: str
    vertex_count: int
    transform_issues: tuple[ModelTransformIssue, ...]
    history_issues: tuple[ModelHistoryNode, ...]
    symmetry_issues: tuple[ModelSymmetryIssue, ...]

    @property
    def clean(self) -> bool:
        return not (self.transform_issues or self.history_issues
                    or self.symmetry_issues)


def inspect_model_transforms(
    states: tuple[ModelTransformState, ...],
) -> tuple[ModelTransformIssue, ...]:
    issues = []
    for state in states:
        for field, expected in _TRANSFORM_FIELDS:
            actual = getattr(state, field)
            if len(actual) != 3 or any(not isfinite(value) for value in actual):
                raise ValueError("模型变换含非有限三轴数值：" + state.path)
            for axis, value, default in zip("XYZ", actual, expected):
                if value != default:
                    issues.append(ModelTransformIssue(
                        state.path, field + axis.upper(), value, default))
    return tuple(issues)


def inspect_model_history(
    nodes: tuple[ModelHistoryNode, ...], *, game_engine: bool = False,
) -> tuple[ModelHistoryNode, ...]:
    return tuple(node for node in nodes
        if not node.name.startswith(("asResetTransform", "rl4Embedded"))
        and (node.node_type not in _ALLOWED_HISTORY_TYPES
             or (game_engine and node.node_type == "deltaMush")))


def inspect_model_symmetry(
    points: tuple[tuple[float, float, float], ...],
    closest_vertices: tuple[int, ...], *,
    tolerance: float = MODEL_SYMMETRY_TOLERANCE,
) -> tuple[ModelSymmetryIssue, ...]:
    if (not isfinite(tolerance) or tolerance <= 0
            or len(points) != len(closest_vertices)):
        raise ValueError("模型对称检查输入无效")
    issues = []
    for index, (point, other_index) in enumerate(zip(points, closest_vertices)):
        if len(point) != 3 or any(not isfinite(value) for value in point):
            raise ValueError("模型顶点坐标无效")
        if point[0] > tolerance:
            continue
        if other_index < 0 or other_index >= len(points):
            raise ValueError("镜像最近顶点索引越界")
        other = points[other_index]
        error = dist((-point[0], point[1], point[2]), other)
        if error > tolerance:
            issues.append(ModelSymmetryIssue(index, other_index, error))
    return tuple(issues)
