"""Reversible ADV-to-Unreal naming and hierarchy operation."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.unreal_rename import UnrealRenamePlan, plan_unreal_rename


class UnrealRenameHost(Protocol):
    def capture_joint_names(self) -> tuple[str, ...]: ...
    def capture_spine_names(self) -> tuple[str, ...]: ...
    def preflight_rename(self, plan: UnrealRenamePlan) -> None: ...
    def preflight_restore(self) -> None: ...
    def transaction(self, label: str): ...
    def create_export_root(self) -> None: ...
    def rename_joints(self, plan: UnrealRenamePlan) -> None: ...
    def flatten_twist_hierarchy(self, plan: UnrealRenamePlan) -> None: ...
    def unparent_export_geometry(self) -> None: ...
    def restore_twist_hierarchy(self) -> None: ...
    def restore_joint_names(self) -> None: ...
    def restore_export_root(self) -> None: ...
    def reparent_export_geometry(self) -> None: ...
    def is_renamed(self) -> bool: ...


class RenameToUnreal:
    def __init__(self, host: UnrealRenameHost):
        self.host = host

    def apply(self) -> UnrealRenamePlan:
        plan = plan_unreal_rename(self.host.capture_joint_names(),
                                  self.host.capture_spine_names())
        self.host.preflight_rename(plan)
        with self.host.transaction("重命名为 Unreal 骨架"):
            self.host.create_export_root()
            self.host.rename_joints(plan)
            self.host.flatten_twist_hierarchy(plan)
            self.host.unparent_export_geometry()
            if not self.host.is_renamed():
                raise RuntimeError("Unreal 骨架重命名复检失败")
        return plan


class RestoreAdvNames:
    def __init__(self, host: UnrealRenameHost):
        self.host = host

    def apply(self) -> None:
        self.host.preflight_restore()
        with self.host.transaction("恢复 ADV 关节名称"):
            self.host.restore_twist_hierarchy()
            self.host.restore_joint_names()
            self.host.restore_export_root()
            self.host.reparent_export_geometry()
            if self.host.is_renamed():
                raise RuntimeError("ADV 关节名称恢复复检失败")
