"""Build original locator-distance angle inputs in one transaction."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.angle_sampler_deform import AngleSamplerSpec, plan_angle_samplers
from adv_py.core.body_skeleton import BodySkeletonSnapshot


class AngleSamplerHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def preflight_angle_sampler(self, spec: AngleSamplerSpec) -> None: ...
    def transaction(self, label: str): ...
    def create_angle_sampler(self, spec: AngleSamplerSpec) -> None: ...
    def capture_angle_sampler(self, spec: AngleSamplerSpec) -> Mapping[str, float]: ...


class BuildAngleSamplers:
    def __init__(self, host: AngleSamplerHost):
        self._host = host

    def apply(self, guide: Mapping[str, object], root: str = "Root_M") -> tuple[AngleSamplerSpec, ...]:
        specs = plan_angle_samplers(self._host.capture_body_skeleton(root), guide)
        for spec in specs:
            self._host.preflight_angle_sampler(spec)
            for name in (*spec.ancestors,
                         *(node["transform"] for node in spec.graph.values()
                           if node["type"] == "locator"),
                         *spec.graph,
                         spec.stem + "_" + spec.side + "AngleSamplerBase_pointConstraint",
                         spec.stem + "_" + spec.side + "AngleSamplerRotate_orientConstraint"):
                if self._host.find_name_collisions("AdvPy_" + name):
                    raise ValueError("角度采样器节点名称冲突：" + name)
            for axis in spec.outputs:
                if self._host.find_name_collisions(spec.target + ".angle" + axis):
                    raise ValueError("角度采样器属性已存在：" + axis)
        with self._host.transaction("构建原版体积角度采样器"):
            for spec in specs:
                self._host.create_angle_sampler(spec)
            for spec in specs:
                values = self._host.capture_angle_sampler(spec)
                if (set(values) != set(spec.values)
                        or any(abs(values[axis] - value) > 1e-3
                               for axis, value in spec.values.items())):
                    raise RuntimeError("体积角度采样器写后复检失败："
                                       + spec.stem + spec.side)
        return specs
