"""Build an ADV character around a previously bound FBX skeleton."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Protocol

from adv_py.core.fbx_rig_import import (
    FBXRigImportPlan, FBXRigSourceJoint, plan_fbx_rig_import,
)


@dataclass(frozen=True, slots=True)
class FBXRigSourceCapture:
    joints: tuple[FBXRigSourceJoint, ...]
    animation_key_times: tuple[float, ...]
    highest_descendant_y: float
    detected_application: str | None
    bound_meshes: tuple[str, ...]
    current_time: float
    playback_start: float
    playback_end: float
    auto_key_enabled: bool

    def __post_init__(self) -> None:
        if (type(self.auto_key_enabled) is not bool
                or len(set(self.bound_meshes)) != len(self.bound_meshes)
                or any(not mesh for mesh in self.bound_meshes)
                or any(not isfinite(value) for value in (
                    self.current_time, self.playback_start,
                    self.playback_end))
                or self.playback_end < self.playback_start):
            raise ValueError("FBX rig 来源场景时间或绑定模型记录无效")


@dataclass(frozen=True, slots=True)
class FBXRigBuildAudit:
    fit_guide_count: int
    paired_side_count: int
    connected_control_names: tuple[str, ...]
    original_skeleton_constrained: bool
    control_animation_baked: bool
    game_root_motion_connected: bool
    bound_meshes_preserved: bool
    temporary_bake_links_removed: bool = False
    source_joint_animation_removed: bool = False


class FBXRigHost(Protocol):
    def existing_advanced_skeleton_nodes(self) -> tuple[str, ...]: ...
    def capture_fbx_rig_source(self) -> FBXRigSourceCapture: ...
    def choose_fbx_rig_route(
        self, detected_application: str | None,
    ) -> str: ...  # fbx_rig, name_matcher, cancel
    def route_to_fbx_name_matcher(self) -> None: ...
    def preflight_fbx_rig_import(
        self, plan: FBXRigImportPlan, source: FBXRigSourceCapture,
    ) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def prepare_fbx_bind_pose(
        self, plan: FBXRigImportPlan, source: FBXRigSourceCapture,
    ) -> None: ...
    def move_fbx_source_to_namespace(
        self, plan: FBXRigImportPlan,
    ) -> Mapping[str, str]: ...
    def create_fbx_fit_guides(self, plan: FBXRigImportPlan) -> None: ...
    def build_fbx_advanced_skeleton(self, plan: FBXRigImportPlan) -> None: ...
    def enlarge_small_fbx_fk_controls(self, plan: FBXRigImportPlan) -> None: ...
    def connect_fbx_source_animation_to_controls(
        self, plan: FBXRigImportPlan, source_paths: Mapping[str, str],
    ) -> None: ...
    def bake_fbx_control_animation(
        self, plan: FBXRigImportPlan, source_paths: Mapping[str, str],
    ) -> None: ...
    def remove_fbx_source_animation_and_bake_links(
        self, plan: FBXRigImportPlan, source_paths: Mapping[str, str],
    ) -> None: ...
    def connect_fbx_controls_to_source(
        self, plan: FBXRigImportPlan, source_paths: Mapping[str, str],
    ) -> None: ...
    def connect_fbx_game_root_motion(
        self, plan: FBXRigImportPlan, source_paths: Mapping[str, str],
    ) -> None: ...
    def capture_fbx_rig_audit(self, plan: FBXRigImportPlan) -> FBXRigBuildAudit: ...
    def restore_fbx_scene_time(self, source: FBXRigSourceCapture) -> None: ...


class FBXRigCancelled(RuntimeError):
    pass


class BuildFBXRig:
    def __init__(self, host: FBXRigHost) -> None:
        self._host = host

    def plan(self) -> tuple[FBXRigSourceCapture, FBXRigImportPlan]:
        existing = self._host.existing_advanced_skeleton_nodes()
        if existing:
            raise ValueError("场景已有 AdvancedSkeleton 角色：" +
                             "、".join(existing))
        source = self._host.capture_fbx_rig_source()
        plan = plan_fbx_rig_import(
            source.joints,
            animation_key_times=source.animation_key_times,
            highest_descendant_y=source.highest_descendant_y)
        return source, plan

    def execute(self) -> FBXRigBuildAudit:
        source, plan = self.plan()
        route = self._host.choose_fbx_rig_route(
            source.detected_application)
        if route == "name_matcher":
            self._host.route_to_fbx_name_matcher()
            raise FBXRigCancelled("FBX rig 已转至 NameMatcher")
        if route != "fbx_rig":
            if route == "cancel":
                raise FBXRigCancelled("FBX rig 已取消")
            raise ValueError("FBX rig 入口选择无效")
        self._host.preflight_fbx_rig_import(plan, source)
        with self._host.transaction("从 FBX 骨架构建 ADV 控制"):
            try:
                self._host.prepare_fbx_bind_pose(plan, source)
                source_paths = self._host.move_fbx_source_to_namespace(plan)
                if (set(source_paths) != {joint.path for joint in source.joints}
                        or len(set(source_paths.values())) != len(source_paths)):
                    raise RuntimeError("FBX rig 来源骨架迁入命名空间后路径不完整")
                self._host.create_fbx_fit_guides(plan)
                self._host.build_fbx_advanced_skeleton(plan)
                self._host.enlarge_small_fbx_fk_controls(plan)
                if plan.last_bake_frame is not None:
                    self._host.connect_fbx_source_animation_to_controls(
                        plan, source_paths)
                    self._host.bake_fbx_control_animation(plan, source_paths)
                    self._host.remove_fbx_source_animation_and_bake_links(
                        plan, source_paths)
                if plan.game_root_joint is not None:
                    self._host.connect_fbx_game_root_motion(plan, source_paths)
                self._host.connect_fbx_controls_to_source(plan, source_paths)
                audit = self._host.capture_fbx_rig_audit(plan)
                candidates = {link.control_name
                              for link in plan.candidate_control_links}
                if (audit.fit_guide_count != len(plan.fit_guides)
                        or audit.paired_side_count != len(plan.mirror_pairs)
                        or len(set(audit.connected_control_names)) !=
                            len(audit.connected_control_names)
                        or not set(audit.connected_control_names) <= candidates
                        or "FKRoot_M" not in audit.connected_control_names
                        or not audit.original_skeleton_constrained
                        or not audit.bound_meshes_preserved
                        or audit.control_animation_baked !=
                            (plan.last_bake_frame is not None)
                        or (plan.last_bake_frame is not None
                            and (not audit.temporary_bake_links_removed
                                 or not audit.source_joint_animation_removed))
                        or audit.game_root_motion_connected !=
                            (plan.game_root_joint is not None)):
                    raise RuntimeError("FBX rig 构建写后复检不完整")
            finally:
                self._host.restore_fbx_scene_time(source)
        return audit
