from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .mocap_mapping import MocapBodyMappingPlan, MocapMappingValidationError


MOCAP_CONNECTION_PREFIX = "AdvPy_Mocap_"


class MocapConstraintKind(str, Enum):
    PARENT = "parentConstraint"
    ORIENT = "orientConstraint"


@dataclass(frozen=True, slots=True)
class MocapConstraintSpec:
    name: str
    source_path: str
    target_path: str
    kind: MocapConstraintKind
    target_attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MocapBodyConnectionPlan:
    mapping: MocapBodyMappingPlan
    constraints: tuple[MocapConstraintSpec, ...]


@dataclass(frozen=True, slots=True)
class MocapTargetInputState:
    target_path: str
    attribute: str
    source_node: str | None


@dataclass(frozen=True, slots=True)
class MocapConstraintState:
    name: str
    source_path: str
    target_path: str
    kind: MocapConstraintKind


@dataclass(frozen=True, slots=True)
class MocapBodyConnectionSnapshot:
    constraints: tuple[MocapConstraintState, ...]
    target_inputs: tuple[MocapTargetInputState, ...]


@dataclass(frozen=True, slots=True)
class MocapTargetPose:
    target_path: str
    world_matrix: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class MocapConnectionIssue:
    code: str
    message: str
    names: tuple[str, ...] = ()


def plan_mocap_body_connection(
    mapping: MocapBodyMappingPlan,
) -> MocapBodyConnectionPlan:
    namespace = _namespace(mapping.target_root)
    constraints = []
    for entry in mapping.entries:
        is_root = entry.target_path == mapping.target_root
        kind = (
            MocapConstraintKind.PARENT if is_root
            else MocapConstraintKind.ORIENT
        )
        suffix = "ParentConstraint" if is_root else "OrientConstraint"
        name = f"{MOCAP_CONNECTION_PREFIX}{entry.target_name}_{suffix}"
        if namespace:
            name = f"{namespace}:{name}"
        attributes = (
            ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ")
            if is_root
            else ("rotateX", "rotateY", "rotateZ")
        )
        constraints.append(MocapConstraintSpec(
            name=name,
            source_path=entry.source_path,
            target_path=entry.target_path,
            kind=kind,
            target_attributes=attributes,
        ))
    names = [item.name for item in constraints]
    if len(names) != len(set(names)):
        raise MocapMappingValidationError("MoCap 临时约束名称不唯一")
    return MocapBodyConnectionPlan(mapping, tuple(constraints))


def audit_mocap_connection_input(
    plan: MocapBodyConnectionPlan,
    name_collisions: tuple[str, ...],
    inputs: tuple[MocapTargetInputState, ...],
) -> tuple[MocapConnectionIssue, ...]:
    issues = []
    if name_collisions:
        issues.append(MocapConnectionIssue(
            "name_collision", "MoCap 临时约束名称已被占用", name_collisions
        ))
    expected = {
        (spec.target_path, attribute)
        for spec in plan.constraints
        for attribute in spec.target_attributes
    }
    actual = {(item.target_path, item.attribute) for item in inputs}
    if actual != expected:
        issues.append(MocapConnectionIssue(
            "input_snapshot_mismatch", "MoCap 目标输入快照不完整"
        ))
    occupied = tuple(
        f"{item.target_path}.{item.attribute}"
        for item in inputs if item.source_node is not None
    )
    if occupied:
        issues.append(MocapConnectionIssue(
            "occupied_target", "Body 目标通道已有输入", occupied
        ))
    return tuple(issues)


def audit_mocap_connection(
    plan: MocapBodyConnectionPlan,
    snapshot: MocapBodyConnectionSnapshot,
) -> tuple[MocapConnectionIssue, ...]:
    issues = []
    expected = {item.name: item for item in plan.constraints}
    actual = {item.name: item for item in snapshot.constraints}
    if set(actual) != set(expected):
        issues.append(MocapConnectionIssue(
            "constraint_set", "MoCap 临时约束集合与计划不一致",
            tuple(sorted(set(expected) ^ set(actual))),
        ))
    for name in sorted(set(expected) & set(actual)):
        spec, state = expected[name], actual[name]
        if (
            state.kind != spec.kind
            or state.source_path != spec.source_path
            or state.target_path != spec.target_path
        ):
            issues.append(MocapConnectionIssue(
                "constraint_structure", f"MoCap 临时约束结构无效：{name}",
                (name,),
            ))
    input_by_key = {
        (item.target_path, item.attribute): item.source_node
        for item in snapshot.target_inputs
    }
    for spec in plan.constraints:
        for attribute in spec.target_attributes:
            if input_by_key.get((spec.target_path, attribute)) != spec.name:
                issues.append(MocapConnectionIssue(
                    "constraint_output",
                    f"MoCap 临时约束未独占目标输入：{spec.target_path}.{attribute}",
                    (spec.name,),
                ))
    return tuple(issues)


def mocap_target_poses_match(
    before: tuple[MocapTargetPose, ...],
    after: tuple[MocapTargetPose, ...],
    tolerance: float = 1e-5,
) -> bool:
    if tuple(item.target_path for item in before) != tuple(
        item.target_path for item in after
    ):
        return False
    return all(
        len(left.world_matrix) == len(right.world_matrix) == 16
        and all(abs(a - b) <= tolerance for a, b in zip(left.world_matrix, right.world_matrix))
        for left, right in zip(before, after)
    )


def _namespace(path: str) -> str:
    leaf = path.rsplit("|", 1)[-1]
    namespace, separator, _ = leaf.rpartition(":")
    return namespace if separator else ""
