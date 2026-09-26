"""Build twelve weighted limb Part joints as one Maya transaction."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.limb_part_deform import LimbPartSegmentSpec, plan_limb_parts


class LimbPartHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def preflight_limb_part_source(self, spec: LimbPartSegmentSpec) -> None: ...
    def transaction(self, label: str): ...
    def create_limb_part_segment(self, spec: LimbPartSegmentSpec) -> None: ...
    def capture_limb_part_segment(self, spec: LimbPartSegmentSpec
                                  ) -> tuple[tuple[str, str, tuple[float, float, float]], ...]: ...


class BuildLimbPartDeform:
    def __init__(self, host: LimbPartHost):
        self._host = host

    def apply(self, root: str = "Root_M") -> tuple[LimbPartSegmentSpec, ...]:
        specs = plan_limb_parts(self._host.capture_body_skeleton(root))
        for spec in specs:
            self._host.preflight_limb_part_source(spec)
            for name in (spec.part1_name, spec.part2_name,
                         spec.translation_name,
                         spec.first_translation_name,
                         spec.scale_blend_name,
                         spec.fatness_add_name,
                         spec.twist_compose_name, spec.twist_decompose_name,
                         spec.twist_project_name,
                         spec.twist1_name, spec.twist2_name,
                         spec.twist1_sum_name, spec.twist2_sum_name,
                         spec.twist1_comp_name, spec.twist2_comp_name):
                if self._host.find_name_collisions(name):
                    raise ValueError("四肢分段节点名称冲突：" + name)
            for name in (spec.up_twist1_name, spec.up_twist2_name,
                         spec.up_fk_compose_name, spec.up_fk_decompose_name,
                         spec.up_fk_project_name, spec.up_blend_name):
                if name and self._host.find_name_collisions(name):
                    raise ValueError("四肢分段上游扭转名称冲突：" + name)
        with self._host.transaction("构建四肢分段变形关节"):
            for spec in specs:
                self._host.create_limb_part_segment(spec)
            for spec in specs:
                states = self._host.capture_limb_part_segment(spec)
                for (path, parent, position), wanted_path, wanted_parent, wanted_position in zip(
                        states, (spec.part1, spec.part2), (spec.start, spec.part1),
                        spec.positions):
                    if path != wanted_path or parent != wanted_parent or any(
                            abs(a - b) > 1e-4 for a, b in zip(position, wanted_position)):
                        raise RuntimeError("四肢分段关节写后复检失败：" + path)
        return specs
