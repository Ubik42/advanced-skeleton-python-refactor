"""Build and verify axial Skin influence joints in one Maya transaction."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.axial_part_deform import AxialPartSpec, plan_axial_parts
from adv_py.core.body_skeleton import BodySkeletonSnapshot


class AxialPartHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def transaction(self, label: str): ...
    def create_axial_part(self, spec: AxialPartSpec) -> None: ...
    def capture_axial_part(self, spec: AxialPartSpec) -> tuple[str, str, tuple[float, float, float]]: ...


class BuildAxialPartDeform:
    def __init__(self, host: AxialPartHost):
        self._host = host

    def apply(self, root: str = "Root_M") -> tuple[AxialPartSpec, ...]:
        specs = plan_axial_parts(self._host.capture_body_skeleton(root))
        for spec in specs:
            for name in (spec.name, spec.name + "_pointConstraint",
                         spec.name + "_orientConstraint"):
                if self._host.find_name_collisions(name):
                    raise ValueError("轴向分段节点名称冲突：" + name)
        with self._host.transaction("构建轴向分段变形关节"):
            for spec in specs:
                self._host.create_axial_part(spec)
            for spec in specs:
                path, parent, position = self._host.capture_axial_part(spec)
                if (path != spec.path or parent != spec.parent
                        or any(abs(a - b) > 1e-5 for a, b in zip(
                            position, spec.position))):
                    raise RuntimeError("轴向分段关节写后复检失败：" + spec.name)
        return specs
