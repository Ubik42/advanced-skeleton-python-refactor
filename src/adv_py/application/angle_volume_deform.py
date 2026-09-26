"""Build all hip, shoulder, wrist, and ankle angle-driven influences."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.angle_volume_deform import plan_angle_volume_influences
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.sdk_volume_deform import SdkVolumeSpec


class AngleVolumeHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def preflight_sdk_volume_parent(self, spec: SdkVolumeSpec) -> None: ...
    def preflight_sdk_graph_node(self, source_name: str, node: dict) -> None: ...
    def preflight_sdk_volume_driver(self, spec: SdkVolumeSpec) -> None: ...
    def transaction(self, label: str): ...
    def create_sdk_volume_joint(self, spec: SdkVolumeSpec) -> None: ...
    def capture_sdk_volume_joint(self, spec: SdkVolumeSpec) -> tuple[str, str]: ...


class BuildAngleVolumeDeform:
    def __init__(self, host: AngleVolumeHost):
        self._host = host

    def apply(self, guide: Mapping[str, object], root: str = "Root_M") -> tuple[SdkVolumeSpec, ...]:
        specs = plan_angle_volume_influences(self._host.capture_body_skeleton(root), guide)
        for spec in specs:
            self._host.preflight_sdk_volume_parent(spec)
            self._host.preflight_sdk_volume_driver(spec)
            for name in (spec.name, "AdvPy_VolumeBase_" + spec.name,
                         "AdvPy_VolumeOffset_" + spec.name,
                         "AdvPy_VolumeSDK_" + spec.name,
                         "AdvPy_VolumeTarget_" + spec.name,
                         "AdvPy_VolumeScale_" + spec.name,
                         "AdvPy_VolumeConstraint_" + spec.name):
                if self._host.find_name_collisions(name):
                    raise ValueError("角度体积关节节点名称冲突：" + name)
            for name, node in spec.guide["sdk_sources"].items():
                self._host.preflight_sdk_graph_node(name, node)
        with self._host.transaction("构建角度驱动体积关节"):
            for spec in specs:
                self._host.create_sdk_volume_joint(spec)
            for spec in specs:
                path, parent = self._host.capture_sdk_volume_joint(spec)
                if path != spec.path or parent != spec.parent:
                    raise RuntimeError("角度体积关节写后复检失败：" + spec.name)
        return specs
