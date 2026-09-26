"""Build and verify axial Skin influence joints in one Maya transaction."""
from __future__ import annotations

from typing import Mapping, Protocol

from adv_py.core.axial_part_deform import AxialPartSpec, plan_axial_parts
from adv_py.core.body_skeleton import BodySkeletonSnapshot


class AxialPartHost(Protocol):
    def capture_body_skeleton(self, root: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str): ...
    def preflight_axial_part_guide(self, spec: AxialPartSpec,
                                  guide: Mapping[str, object]) -> None: ...
    def transaction(self, label: str): ...
    def create_axial_part(self, spec: AxialPartSpec,
                          guide: Mapping[str, object] | None = None) -> None: ...
    def complete_guided_axial_body(self) -> None: ...
    def capture_axial_part(self, spec: AxialPartSpec) -> tuple[str, str, tuple[float, float, float]]: ...


class BuildAxialPartDeform:
    def __init__(self, host: AxialPartHost):
        self._host = host

    def apply(self, root: str = "Root_M",
              guide: Mapping[str, object] | None = None
              ) -> tuple[AxialPartSpec, ...]:
        specs = plan_axial_parts(self._host.capture_body_skeleton(root))
        for spec in specs:
            if guide is not None:
                self._host.preflight_axial_part_guide(spec, guide)
            for name in (spec.name, spec.name + "_pointConstraint",
                         spec.name + "_orientConstraint"):
                if self._host.find_name_collisions(name):
                    raise ValueError("轴向分段节点名称冲突：" + name)
            if guide is not None:
                stem = spec.name.split("Part", 1)[0]
                names = ["AdvPy_AxialFKX" + spec.name,
                         "AdvPy_AxialPoint" + spec.name,
                         *(prefix + spec.name for prefix in (
                             "AdvPy_AxialBlend_", "AdvPy_AxialRelative_",
                             "AdvPy_AxialDecompose_"))]
                if "Part1" in spec.name:
                    names.extend(("AdvPy_AxialFKX" + stem + "_M",
                                  "AdvPy_AxialBase" + stem + "_M",
                                  "AdvPy_AxialTarget" + stem + "_M"))
                    if stem in ("Spine1", "Neck"):
                        names.extend(("AdvPy_AxialFrame" + stem + "_M",
                                      "AdvPy_AxialControl" + stem + "_M"))
                for name in names:
                    if self._host.find_name_collisions(name):
                        raise ValueError("轴向分段驱动节点名称冲突：" + name)
        with self._host.transaction("构建轴向分段变形关节"):
            for spec in specs:
                if guide is None:
                    self._host.create_axial_part(spec)
                else:
                    self._host.create_axial_part(spec, guide)
            if guide is not None:
                self._host.complete_guided_axial_body()
            for spec in specs:
                path, parent, position = self._host.capture_axial_part(spec)
                if (path != spec.path or parent != spec.parent
                        or any(abs(a - b) > 1e-5 for a, b in zip(
                            position, spec.position))):
                    raise RuntimeError("轴向分段关节写后复检失败：" + spec.name)
        return specs
