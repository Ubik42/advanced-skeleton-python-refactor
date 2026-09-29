from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .body_skeleton import (
    BodySkeletonProvenance,
    BodySkeletonSnapshot,
    audit_body_provenance,
)
from .fit_symmetry import FitSymmetryInstance
from .fit_part import FitPartFinalPaths


class BodyExternalDependencyKind(str, Enum):
    ANIMATION = "animation"
    CONNECTION = "connection"
    CONSTRAINT = "constraint"
    SKIN_CLUSTER = "skin_cluster"


@dataclass(frozen=True, slots=True)
class BodyExternalDependency:
    kind: BodyExternalDependencyKind
    body_plug: str
    external_plug: str


@dataclass(frozen=True, slots=True)
class BodyRebuildSceneState:
    root: str
    dag_paths: tuple[str, ...]
    external_dependencies: tuple[BodyExternalDependency, ...]


@dataclass(frozen=True, slots=True)
class BodyRebuildIssue:
    code: str
    message: str
    subject: str | None = None


def audit_body_rebuild_safety(
    instances: tuple[FitSymmetryInstance, ...],
    body: BodySkeletonSnapshot,
    scene: BodyRebuildSceneState,
    provenance: BodySkeletonProvenance,
    *,
    part_paths: FitPartFinalPaths | None = None,
) -> tuple[BodyRebuildIssue, ...]:
    """Audit whether an owned Body tree has a replaceable scene boundary."""

    issues = [
        BodyRebuildIssue(issue.code, issue.message, issue.joint)
        for issue in audit_body_provenance(provenance, body.provenance)
    ]
    expected = {
        (part_paths.remap_body_reference(instance.output_path)
         if part_paths is not None else instance.output_path): instance
        for instance in instances
    }
    expected_parts = (dict(part_paths.part_paths)
                      if part_paths is not None else {})
    part_joint_paths = set(expected_parts.values())
    # Body snapshots intentionally omit auxiliary Part influences, whereas
    # the raw DAG dependency snapshot still includes them.
    allowed_dag_paths = set(expected) | part_joint_paths
    actual = {state.path: state for state in body.joints}
    if len(expected) != len(instances):
        issues.append(
            BodyRebuildIssue("duplicate_expected_joint", "ReBuild 期望关节路径重复")
        )
    if len(actual) != len(body.joints):
        issues.append(
            BodyRebuildIssue("duplicate_body_joint", "Body 实际关节路径重复")
        )
    if body.root != scene.root:
        issues.append(
            BodyRebuildIssue(
                "root_mismatch",
                "Body 快照与 DAG 依赖快照的根路径不一致",
                scene.root,
            )
        )
    if part_paths is not None and (
            len(expected_parts) != len(part_paths.part_paths)
            or len(part_joint_paths) != len(expected_parts)
            or len(expected) != len(instances)
            or set(expected) & part_joint_paths):
        issues.append(BodyRebuildIssue(
            "invalid_part_paths", "Part 最终路径映射重复或与 Body 冲突"))
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodyRebuildIssue("missing_body_joint", "缺少预期 Body joint", path))
    for path in sorted(set(actual) - set(expected)):
        issues.append(
            BodyRebuildIssue("unexpected_body_joint", "存在计划外 Body joint", path)
        )
    for path in sorted(set(expected) & set(actual)):
        instance = expected[path]
        state = actual[path]
        if (
            state.name != instance.output_name
            or state.parent_path != (
                path.rsplit("|", 1)[0] or None
                if part_paths is not None else instance.parent_output_path)
            or state.side is not instance.side
        ):
            issues.append(
                BodyRebuildIssue(
                    "body_topology_mismatch",
                    "Body joint 名称、父级或 side 与构建合同不一致",
                    path,
                )
            )
    dag_paths = set(scene.dag_paths)
    for path in sorted(allowed_dag_paths - dag_paths):
        issues.append(
            BodyRebuildIssue("missing_dag_node", "DAG 中缺少预期 Body joint", path)
        )
    for path in sorted(dag_paths - allowed_dag_paths):
        issues.append(
            BodyRebuildIssue(
                "unexpected_dag_descendant",
                "Body 根节点下存在计划外 DAG 节点",
                path,
            )
        )
    for dependency in scene.external_dependencies:
        dependency_node = dependency.body_plug.split(".", 1)[0]
        dependency_name = dependency_node.rsplit("|", 1)[-1].rsplit(
            ":", 1)[-1]
        if (part_paths is not None
                and (dependency_node in part_joint_paths
                     or dependency_name in expected_parts)):
            # These newly inserted Part influences are owned by the same
            # in-flight build; their shaping nodes are not legacy attachments.
            continue
        issues.append(
            BodyRebuildIssue(
                f"external_{dependency.kind.value}",
                "Body 节点存在外部依赖连接",
                f"{dependency.body_plug} -> {dependency.external_plug}",
            )
        )
    return tuple(issues)
