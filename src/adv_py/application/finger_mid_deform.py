"""Build the ten weighted finger midpoint helpers as one operation."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.finger_mid_deform import FingerMidSpec, plan_finger_mid_influences


class FingerMidHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def transaction(self, label: str): ...
    def create_finger_mid(self, spec: FingerMidSpec) -> None: ...
    def capture_finger_mid(self, spec: FingerMidSpec) -> tuple[str, str, tuple[float, float, float]]: ...


class BuildFingerMidDeform:
    def __init__(self, host: FingerMidHost):
        self._host = host

    def apply(self, root: str = "Root_M") -> tuple[FingerMidSpec, ...]:
        specs = plan_finger_mid_influences(self._host.capture_body_skeleton(root))
        for spec in specs:
            for name in (spec.name, spec.zero_name,
                         spec.name + "_pointConstraint",
                         spec.name + "_orientConstraint"):
                if self._host.find_name_collisions(name):
                    raise ValueError("手指分段节点名称冲突：" + name)
        with self._host.transaction("构建手指末段变形关节"):
            for spec in specs:
                self._host.create_finger_mid(spec)
            for spec in specs:
                path, parent, position = self._host.capture_finger_mid(spec)
                if path != spec.path or parent != spec.parent or any(
                        abs(a - b) > 1e-5 for a, b in zip(position, spec.position)):
                    raise RuntimeError("手指分段关节写后复检失败：" + spec.name)
        return specs
