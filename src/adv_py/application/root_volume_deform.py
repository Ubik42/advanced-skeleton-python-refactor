"""Build both weighted RootA influences in one Maya undo transaction."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.root_volume_deform import RootVolumeSpec, plan_root_volume_influences


class RootVolumeHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def transaction(self, label: str): ...
    def create_root_volume_joint(self, spec: RootVolumeSpec) -> None: ...
    def capture_root_volume_joint(self, spec: RootVolumeSpec) -> tuple[str, str, tuple[float, float, float]]: ...


class BuildRootVolumeDeform:
    def __init__(self, host: RootVolumeHost):
        self._host = host

    def apply(self, guide: Mapping[str, object], root: str = "Root_M") -> tuple[RootVolumeSpec, RootVolumeSpec]:
        specs = plan_root_volume_influences(self._host.capture_body_skeleton(root), guide)
        for spec in specs:
            if self._host.find_name_collisions(spec.name):
                raise ValueError("Root 体积关节名称冲突：" + spec.name)
        with self._host.transaction("构建 Root 体积变形关节"):
            for spec in specs:
                self._host.create_root_volume_joint(spec)
            for spec in specs:
                path, parent, local_translate = self._host.capture_root_volume_joint(spec)
                if path != spec.path or parent != spec.parent or any(
                    abs(a - b) > 1e-5 for a, b in zip(local_translate, spec.translate)
                ):
                    raise RuntimeError("Root 体积关节写后复检失败：" + spec.name)
        return specs
