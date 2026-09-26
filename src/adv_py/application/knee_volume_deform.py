"""Build four KneeC/D weighted influences as one undoable operation."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.knee_volume_deform import plan_knee_volume_influences
from adv_py.core.sdk_volume_deform import SdkVolumeSpec


class KneeVolumeHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def preflight_sdk_volume_parent(self, spec: SdkVolumeSpec) -> None: ...
    def transaction(self, label: str): ...
    def create_sdk_volume_joint(self, spec: SdkVolumeSpec) -> None: ...
    def capture_sdk_volume_joint(self, spec: SdkVolumeSpec) -> tuple[str, str]: ...


class BuildKneeVolumeDeform:
    def __init__(self, host: KneeVolumeHost):
        self._host = host

    def apply(self, guide: Mapping[str, object], root: str = "Root_M") -> tuple[SdkVolumeSpec, ...]:
        specs = plan_knee_volume_influences(self._host.capture_body_skeleton(root), guide)
        for spec in specs:
            self._host.preflight_sdk_volume_parent(spec)
            for name in (spec.name, "AdvPy_VolumeBase_" + spec.name,
                         "AdvPy_VolumeOffset_" + spec.name,
                         "AdvPy_VolumeSDK_" + spec.name,
                         "AdvPy_VolumeTarget_" + spec.name,
                         "AdvPy_VolumeScale_" + spec.name,
                         "AdvPy_VolumeConstraint_" + spec.name):
                if self._host.find_name_collisions(name):
                    raise ValueError("膝体积关节节点名称冲突：" + name)
            for name in spec.guide["sdk_sources"]:
                if self._host.find_name_collisions("AdvPy_" + name):
                    raise ValueError("膝体积驱动节点名称冲突：" + name)
        with self._host.transaction("构建膝 C/D 体积关节"):
            for spec in specs:
                self._host.create_sdk_volume_joint(spec)
            for spec in specs:
                path, parent = self._host.capture_sdk_volume_joint(spec)
                if path != spec.path or parent != spec.parent:
                    raise RuntimeError("膝体积关节写后复检失败：" + spec.name)
        return specs
