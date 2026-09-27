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
    symmetry_checked: bool = True

    @property
    def clean(self) -> bool:
        return self.symmetry_checked and not (self.transform_issues or self.history_issues
                    or self.symmetry_issues)


@dataclass(frozen=True, slots=True)
class ModelCheckGate:
    category: str
    subject: str
    issues: tuple[ModelTransformIssue | ModelHistoryNode |
                  ModelSymmetryIssue, ...]


def plan_model_check_gates(
    result: ModelCheckResult,
    transform_order: tuple[str, ...],
) -> tuple[ModelCheckGate, ...]:
    """Mirror the MEL prompt order: each Transform, history, symmetry."""
    if len(set(transform_order)) != len(transform_order):
        raise ValueError("模型父级变换顺序包含重复对象")
    unknown = {issue.path for issue in result.transform_issues} - set(transform_order)
    if unknown:
        raise ValueError("模型变换问题不属于所选模型父链")
    gates = []
    for path in transform_order:
        issues = tuple(issue for issue in result.transform_issues
                       if issue.path == path)
        if issues:
            gates.append(ModelCheckGate("transform", path, issues))
    if result.history_issues:
        gates.append(ModelCheckGate("history", result.mesh,
                                    result.history_issues))
    if result.symmetry_checked and result.symmetry_issues:
        gates.append(ModelCheckGate("symmetry", result.mesh,
                                    result.symmetry_issues))
    return tuple(gates)


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
