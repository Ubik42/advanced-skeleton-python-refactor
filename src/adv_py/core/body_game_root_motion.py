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
    root_joint_name: str = "RootMotion_M"
    deformation_children: tuple[str, ...] | None = None
    range_node_name: str | None = None
    constraint_node_name: str | None = None
    root_joint_path: str | None = None


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
    locked_control_channels: bool = False


def plan_game_root_motion(source: GameRootMotionInput, *,
                          create: bool) -> GameRootMotionPlan:
    if (type(create) is not bool or type(source.exists) is not bool
            or type(source.use_offset_parent_matrix) is not bool
            or not isfinite(source.character_height)
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
    root_name = source.root_joint_name
    if root_name not in ("RootMotion_M", "root"):
        raise ValueError("Root Motion 原版关节名无效")
    joint = ((source.root_joint_path or source.deformation + "|" + prefix + root_name)
             if not create else source.deformation + "|" + prefix + root_name)
    if (not joint.startswith(source.deformation + '|')
            or joint.rsplit('|', 1)[-1] != prefix + root_name):
        raise ValueError('Root Motion 已存在关节路径无效')
    offset = source.root_system + "|" + prefix + "FKOffset" + root_name
    follow = offset + "|" + prefix + "FKFollow" + root_name
    extra = follow + "|" + prefix + "FKExtra" + root_name
    control = extra + "|" + prefix + "FK" + root_name
    body_name = source.body_root.rsplit("|", 1)[-1]
    if body_name.rsplit(":", 1)[-1] != "Root_M":
        raise ValueError("Root Motion 只接已登记的 Root_M")
    if not source.body_root.startswith(source.deformation + "|"):
        raise ValueError("Root Motion 的 Body 根不在变形系统下")
    # MEL moves direct joint children, which may be export wrappers rather
    # than Root_M. An empty RootMotion joint after Unreal export is valid:
    # deleting it leaves the separate UnrealRoot branch where it is.
    parent = source.deformation if create else joint
    children = source.deformation_children
    if children is None:
        children = (parent + "|" + body_name,)
    if any(not child.startswith(parent + "|")
           or "|" in child[len(parent) + 1:] for child in children):
        raise ValueError("Root Motion 直接子关节记录无效")
    destination = joint if create else source.deformation
    body_path = source.body_root
    for child in children:
        if body_path == child or body_path.startswith(child + "|"):
            body_path = destination + "|" + child.rsplit("|", 1)[-1] + body_path[len(child):]
            break
    return GameRootMotionPlan(
        create, source, joint,
        body_path,
        offset, follow, extra, control,
        source.range_node_name or prefix + root_name + "Range",
        prefix + "FKFollow" + root_name + "_parentConstraint1",
        source.constraint_node_name or prefix + root_name + "_parentConstraint1",
        prefix + ("RootMotionMM_M" if root_name == "RootMotion_M" else "rootMM_root"),
        source.character_height / 20.0)


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
    if not state.locked_control_channels:
        issues.append("Root Motion 控制器缩放或可见性未锁定")
    return tuple(issues)
