"""Build four original-name chest and scapula weighted influences."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.chest_volume_deform import ChestVolumeSpec, plan_chest_volume_influences


class ChestVolumeHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def transaction(self, label: str): ...
    def create_chest_volume_joint(self, spec: ChestVolumeSpec) -> None: ...
    def capture_chest_volume_joint(self, spec: ChestVolumeSpec) -> tuple[str, str]: ...


class BuildChestVolumeDeform:
    def __init__(self, host: ChestVolumeHost):
        self._host = host

    def apply(self, guide: Mapping[str, object], root: str = "Root_M") -> tuple[ChestVolumeSpec, ...]:
        specs = plan_chest_volume_influences(self._host.capture_body_skeleton(root), guide)
        for spec in specs:
            for name in (spec.name, "AdvPy_VolumeBase_" + spec.name,
                         "AdvPy_VolumeOffset_" + spec.name,
                         "AdvPy_VolumeSDK_" + spec.name,
                         "AdvPy_VolumeTarget_" + spec.name,
                         "AdvPy_VolumeScale_" + spec.name,
                         "AdvPy_VolumeConstraint_" + spec.name):
                if self._host.find_name_collisions(name):
                    raise ValueError("胸部体积关节节点名称冲突：" + name)
            for name in spec.guide["sdk_sources"]:
                if self._host.find_name_collisions("AdvPy_" + name):
                    raise ValueError("胸部体积驱动节点名称冲突：" + name)
        with self._host.transaction("构建胸部和肩胛体积关节"):
            for spec in specs:
                self._host.create_chest_volume_joint(spec)
            for spec in specs:
                path, parent = self._host.capture_chest_volume_joint(spec)
                if path != spec.path or parent != spec.parent:
                    raise RuntimeError("胸部体积关节写后复检失败：" + spec.name)
        return specs
