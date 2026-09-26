"""Build twelve original _50 volume-parent helpers in one transaction."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.volume_half_parent import VolumeHalfParentSpec, plan_volume_half_parents


class VolumeHalfParentHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def preflight_volume_half_parent(self, spec: VolumeHalfParentSpec) -> None: ...
    def transaction(self, label: str): ...
    def create_volume_half_parent(self, spec: VolumeHalfParentSpec) -> None: ...
    def capture_volume_half_parent(self, spec: VolumeHalfParentSpec
                                   ) -> tuple[str, str, tuple[float, ...]]: ...


class BuildVolumeHalfParents:
    def __init__(self, host: VolumeHalfParentHost):
        self._host = host

    def apply(self, guide: Mapping[str, object], root: str = "Root_M") -> tuple[VolumeHalfParentSpec, ...]:
        specs = plan_volume_half_parents(self._host.capture_body_skeleton(root), guide)
        for spec in specs:
            self._host.preflight_volume_half_parent(spec)
            for name in (spec.name, spec.zero_name,
                         spec.name + "_pointConstraint",
                         spec.name + "_orientConstraint"):
                if self._host.find_name_collisions(name):
                    raise ValueError("体积中间关节节点名称冲突：" + name)
        with self._host.transaction("构建体积关节中间父链"):
            for spec in specs:
                self._host.create_volume_half_parent(spec)
            for spec in specs:
                path, parent, world = self._host.capture_volume_half_parent(spec)
                if (path != spec.path or parent != spec.parent
                        or max(abs(a - b) for a, b in zip(
                            world, spec.world_matrix)) > 1e-4):
                    raise RuntimeError("体积中间关节写后复检失败：" + spec.name)
        return specs
