"""Plan the standalone Body / Game Engine Root Motion command."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class GameRootMotionInput:
    deformation: str
    root_system: str
    main_system: str
    main_control: str
    constraint_system: str
    body_root: str
    control_set: str
    build_pose: str
    namespace_prefix: str
    character_height: float
    use_offset_parent_matrix: bool
    exists: bool


@dataclass(frozen=True, slots=True)
class GameRootMotionPlan:
    create: bool
    source: GameRootMotionInput
    joint_path: str
    body_path: str
    offset_path: str
    follow_path: str
    extra_path: str
    control_path: str
    range_name: str
    follow_constraint_name: str
    body_constraint_name: str
    matrix_name: str
    radius: float

    @property
    def node_names(self) -> tuple[str, ...]:
        names = (self.joint_path.rsplit("|", 1)[-1],
                 self.offset_path.rsplit("|", 1)[-1],
                 self.follow_path.rsplit("|", 1)[-1],
                 self.extra_path.rsplit("|", 1)[-1],
                 self.control_path.rsplit("|", 1)[-1],
                 self.range_name, self.follow_constraint_name,
                 self.body_constraint_name)
        return names + ((self.matrix_name,)
                        if self.source.use_offset_parent_matrix else ())


@dataclass(frozen=True, slots=True)
class GameRootMotionState:
    joint_path: str | None
    body_path: str
    offset_path: str | None
    follow_path: str | None
    extra_path: str | None
    control_path: str | None
    follow_main_source: str | None
    body_driver_source: str | None
    in_control_set: bool
    in_build_pose: bool
    residual_nodes: tuple[str, ...] = ()


def plan_game_root_motion(source: GameRootMotionInput, *,
                          create: bool) -> GameRootMotionPlan:
    if (type(create) is not bool or type(source.exists) is not bool
            or type(source.use_offset_parent_matrix) is not bool
            or not isfinite(source.character_height)
            or source.character_height <= 0
            or not source.deformation.startswith("|")
            or not source.root_system.startswith("|")
            or not source.main_system.startswith("|")
            or not source.main_control.startswith(source.main_system + "|")
            or not source.body_root.startswith("|")
            or source.exists == create):
        raise ValueError("Game Engine Root Motion 场景状态或操作无效")
    prefix = source.namespace_prefix
    if prefix and not prefix.endswith(":"):
        raise ValueError("Root Motion 命名空间格式无效")
    joint = source.deformation + "|" + prefix + "RootMotion_M"
    offset = source.root_system + "|" + prefix + "FKOffsetRootMotion_M"
    follow = offset + "|" + prefix + "FKFollowRootMotion_M"
    extra = follow + "|" + prefix + "FKExtraRootMotion_M"
    control = extra + "|" + prefix + "FKRootMotion_M"
    body_name = source.body_root.rsplit("|", 1)[-1]
    if body_name.rsplit(":", 1)[-1] != "Root_M":
        raise ValueError("Root Motion 只接已登记的 Root_M")
    expected_body = (source.deformation + "|" + body_name
                     if create else joint + "|" + body_name)
    if source.body_root != expected_body:
        raise ValueError("Root Motion 的 Body 根父级不符")
    return GameRootMotionPlan(
        create, source, joint,
        joint + "|" + body_name if create else source.deformation + "|" + body_name,
        offset, follow, extra, control,
        prefix + "RootMotion_MRange",
        prefix + "FKFollowRootMotion_M_parentConstraint1",
        prefix + "RootMotion_M_parentConstraint1",
        prefix + "RootMotion_MFollowMM",
        max(source.character_height / 20.0, 0.01))


def audit_game_root_motion(plan: GameRootMotionPlan,
                           state: GameRootMotionState) -> tuple[str, ...]:
    if not plan.create:
        return (() if state.joint_path is None
                and state.body_path == plan.body_path
                and state.control_path is None
                and not state.residual_nodes else
                ("Root Motion 删除后仍有角色节点",))
    issues = []
    for actual, expected, label in (
            (state.joint_path, plan.joint_path, "关节"),
            (state.body_path, plan.body_path, "Body 父链"),
            (state.offset_path, plan.offset_path, "Offset"),
            (state.follow_path, plan.follow_path, "Follow"),
            (state.extra_path, plan.extra_path, "Extra"),
            (state.control_path, plan.control_path, "控制器"),
            (state.follow_main_source,
             plan.control_path + ".followMain", "followMain"),
            (state.body_driver_source,
             (plan.matrix_name + ".matrixSum"
              if plan.source.use_offset_parent_matrix else
              plan.control_path), "Body 驱动")):
        if actual != expected:
            issues.append("Root Motion " + label + "不一致")
    if not state.in_control_set or not state.in_build_pose:
        issues.append("Root Motion 控制器未进入角色选择集或构建姿态")
    return tuple(issues)
