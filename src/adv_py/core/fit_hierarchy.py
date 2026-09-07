from __future__ import annotations

from dataclasses import dataclass


Vector3 = tuple[float, float, float]


class FitHierarchyValidationError(ValueError):
    """Raised when a hierarchy cannot be captured or accepted safely."""


@dataclass(frozen=True, slots=True)
class FitHierarchyNode:
    """One Maya-independent joint entry captured from a FitSkeleton DAG."""

    path: str
    short_name: str
    dag_parent: str | None
    local_position: Vector3
    world_position: Vector3


@dataclass(frozen=True, slots=True)
class FitHierarchySnapshot:
    container: str
    joints: tuple[FitHierarchyNode, ...]


@dataclass(frozen=True, slots=True)
class FitHierarchyPolicy:
    expected_root_name: str = "Root"
    center_tolerance: float = 0.01
    reject_underscores: bool = True
    reject_leading_digits: bool = True

    def __post_init__(self) -> None:
        if not self.expected_root_name:
            raise ValueError("期望根关节名称不能为空")
        if self.center_tolerance < 0:
            raise ValueError("中心容差不能小于 0")


@dataclass(frozen=True, slots=True)
class FitHierarchyIssue:
    code: str
    message: str
    nodes: tuple[str, ...] = ()


def audit_fit_hierarchy(
    snapshot: FitHierarchySnapshot,
    policy: FitHierarchyPolicy | None = None,
) -> tuple[FitHierarchyIssue, ...]:
    """Audit deterministic build prerequisites without importing a DCC API."""

    active_policy = policy or FitHierarchyPolicy()
    issues: list[FitHierarchyIssue] = []
    nodes_by_path: dict[str, FitHierarchyNode] = {}

    for node in snapshot.joints:
        if node.path in nodes_by_path:
            issues.append(
                FitHierarchyIssue(
                    "duplicate_path",
                    "层级快照包含重复的完整路径",
                    (node.path,),
                )
            )
        else:
            nodes_by_path[node.path] = node

    if not snapshot.joints:
        return (FitHierarchyIssue("no_joints", "FitSkeleton 下没有关节"),)

    roots = tuple(
        node for node in snapshot.joints if node.dag_parent == snapshot.container
    )
    if len(roots) != 1:
        issues.append(
            FitHierarchyIssue(
                "root_count",
                f"FitSkeleton 必须有且只有一个直接根关节，当前为 {len(roots)} 个",
                tuple(node.path for node in roots),
            )
        )
    else:
        root = roots[0]
        if root.short_name != active_policy.expected_root_name:
            issues.append(
                FitHierarchyIssue(
                    "unexpected_root_name",
                    f"根关节应命名为 {active_policy.expected_root_name}",
                    (root.path,),
                )
            )
        if abs(root.local_position[0]) > active_policy.center_tolerance:
            issues.append(
                FitHierarchyIssue(
                    "root_off_center",
                    "根关节相对 FitSkeleton 的 X 位置超出中心容差",
                    (root.path,),
                )
            )

    names: dict[str, list[str]] = {}
    for node in snapshot.joints:
        names.setdefault(node.short_name, []).append(node.path)
        if not node.short_name:
            issues.append(
                FitHierarchyIssue("empty_name", "关节短名不能为空", (node.path,))
            )
        elif active_policy.reject_leading_digits and node.short_name[0].isdigit():
            issues.append(
                FitHierarchyIssue(
                    "leading_digit",
                    "Fit joint 名称不能以数字开头",
                    (node.path,),
                )
            )
        if active_policy.reject_underscores and "_" in node.short_name:
            issues.append(
                FitHierarchyIssue(
                    "underscore_in_name",
                    "Fit joint 名称不能包含下划线",
                    (node.path,),
                )
            )

        parent = node.dag_parent
        if parent == snapshot.container:
            continue
        if parent is None:
            issues.append(
                FitHierarchyIssue(
                    "detached_joint",
                    "关节没有 DAG 父节点，未连接到 FitSkeleton",
                    (node.path,),
                )
            )
        elif parent not in nodes_by_path:
            issues.append(
                FitHierarchyIssue(
                    "non_joint_parent",
                    "关节与 FitSkeleton 之间存在非 joint 父节点或父链缺失",
                    (node.path, parent),
                )
            )

    for short_name, paths in names.items():
        if len(paths) > 1:
            issues.append(
                FitHierarchyIssue(
                    "duplicate_short_name",
                    f"Fit joint 短名不唯一：{short_name}",
                    tuple(paths),
                )
            )

    cycle_nodes = _find_cycle_nodes(nodes_by_path)
    if cycle_nodes:
        issues.append(
            FitHierarchyIssue(
                "parent_cycle",
                "关节父链包含循环",
                tuple(sorted(cycle_nodes)),
            )
        )
    return tuple(issues)


def _find_cycle_nodes(nodes_by_path: dict[str, FitHierarchyNode]) -> set[str]:
    state: dict[str, int] = {}
    cycles: set[str] = set()

    def visit(path: str, stack: list[str]) -> None:
        current_state = state.get(path, 0)
        if current_state == 2:
            return
        if current_state == 1:
            start = stack.index(path)
            cycles.update(stack[start:])
            return

        state[path] = 1
        stack.append(path)
        parent = nodes_by_path[path].dag_parent
        if parent in nodes_by_path:
            visit(parent, stack)
        stack.pop()
        state[path] = 2

    for path in nodes_by_path:
        visit(path, [])
    return cycles
