"""Visible Skeleton geometry actions using original ADV mesh templates."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_skeleton import (BoneCopy, plan_finger_bones,
                                           plan_skeleton_bones,
                                           plan_skeleton_mirror)


class SkeletonGeometryHost(Protocol):
    def capture_skeleton_input(self) -> tuple[set[str], str]: ...
    def preflight_skeleton_create(self, plan: tuple[BoneCopy, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create_skeleton_geometry(self, plan: tuple[BoneCopy, ...]) -> int: ...
    def capture_skeleton_geometry(self, count: int) -> bool: ...
    def skeleton_geometry_exists(self) -> bool: ...
    def delete_skeleton_geometry(self) -> None: ...
    def capture_skeleton_bone_names(self) -> set[str]: ...
    def preflight_skeleton_mirror(self, pairs: tuple[tuple[str, str], ...]) -> None: ...
    def mirror_skeleton_geometry(self, pairs: tuple[tuple[str, str], ...]) -> int: ...


class CreateSkeletonGeometry:
    def __init__(self, host: SkeletonGeometryHost) -> None:
        self.host = host

    def execute(self) -> int:
        joints, template = self.host.capture_skeleton_input()
        plan = plan_skeleton_bones(joints, template) + plan_finger_bones(joints, template)
        self.host.preflight_skeleton_create(plan)
        with self.host.transaction("创建原版骨骼几何"):
            count = self.host.create_skeleton_geometry(plan)
            if not self.host.capture_skeleton_geometry(count):
                raise RuntimeError("骨骼几何创建后节点或蒙皮状态不完整")
        return count


class DeleteSkeletonGeometry:
    def __init__(self, host: SkeletonGeometryHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.skeleton_geometry_exists():
            return
        with self.host.transaction("删除原版骨骼几何"):
            self.host.delete_skeleton_geometry()
            if self.host.skeleton_geometry_exists():
                raise RuntimeError("骨骼几何删除后仍有生成物")


class MirrorSkeletonGeometry:
    def __init__(self, host: SkeletonGeometryHost) -> None:
        self.host = host

    def execute(self, source_side: str) -> int:
        pairs = plan_skeleton_mirror(
            self.host.capture_skeleton_bone_names(), source_side)
        self.host.preflight_skeleton_mirror(pairs)
        with self.host.transaction("镜像原版骨骼几何"):
            return self.host.mirror_skeleton_geometry(pairs)
