"""Source-shaped chain descriptions for AdvancedSkeleton 6.925 Bendy."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata
from .fit_part import FitPartJointSpec
from .body_skeleton import BodyJointSpec


@dataclass(frozen=True, slots=True)
class FitBendyChainSpec:
    source_joint: str
    start_body: str
    end_body: str
    side: str
    part_names: tuple[str, ...]
    control_count: int
    start_position: tuple[float, float, float]
    end_position: tuple[float, float, float]
    part_positions: tuple[tuple[float, float, float], ...]

    @property
    def control_positions(self) -> tuple[tuple[float, float, float], ...]:
        """Start control, then evenly spaced interior controls."""
        return (self.start_position, *(tuple(
            a + (b - a) * index / (self.control_count + 1)
            for a, b in zip(self.start_position, self.end_position))
            for index in range(1, self.control_count + 1)))

    @property
    def stem(self) -> str:
        return self.start_body.rsplit("|", 1)[-1].rsplit("_", 1)[0]

    @property
    def prefix(self) -> str:
        return f"Bend{self.stem}"

    @property
    def curve_name(self) -> str:
        return f"{self.prefix}Curve_{self.side}"

    @property
    def influence_names(self) -> tuple[str, ...]:
        middle = (("Mid",) if self.control_count == 1 else
                  tuple(f"Mid{index}" for index in
                        range(1, self.control_count + 1)))
        return tuple(f"{self.prefix}{label}_{self.side}"
                     for label in ("Start", *middle, "End"))

    @property
    def control_names(self) -> tuple[str, ...]:
        return (f"{self.prefix}_{self.side}",
                *(f"{self.prefix}{index}_{self.side}"
                  for index in range(self.control_count + 1)))

    @property
    def end_proxy_name(self) -> str:
        return f"BendX{self.stem}{self.control_count + 1}_{self.side}"

    @property
    def follow_node_names(self) -> tuple[str, ...]:
        return (f"AdvPy_{self.prefix}StartSource_{self.side}",
                f"AdvPy_{self.prefix}EndSource_{self.side}",
                f"AdvPy_{self.prefix}StartWorld_{self.side}",
                f"AdvPy_{self.prefix}EndWorld_{self.side}",
                f"AdvPy_{self.prefix}StartBlend_{self.side}",
                f"AdvPy_{self.prefix}EndBlend_{self.side}",
                *(f"AdvPy_{name}Follow" for name in self.control_names),
                *(name + "Offset" for name in self.control_names),
                f"AdvPy_{self.end_proxy_name}Follow")

    @property
    def skin_name(self) -> str:
        return f"{self.prefix}SC_{self.side}"

    @property
    def guide_node_names(self) -> tuple[str, ...]:
        return (self.curve_name, self.curve_name + "Shape",
                self.skin_name, *self.influence_names,
                *self.control_names,
                *(name + "Shape" for name in self.control_names),
                *("AdvPy_BendGuide" + name
                  for name in self.influence_names),
                self.end_proxy_name, *self.motion_path_names,
                *self.motion_transform_names)

    @property
    def motion_path_names(self) -> tuple[str, ...]:
        return tuple(f"BendyMP{self.stem}{index}_{self.side}"
                     for index in range(len(self.part_names) + 1))

    @property
    def motion_transform_names(self) -> tuple[str, ...]:
        return tuple(f"BendMPX{self.stem}{index}_{self.side}"
                     for index in range(len(self.part_names) + 1))

    @property
    def deform_names(self) -> tuple[str, ...]:
        return (self.start_body.rsplit("|", 1)[-1], *self.part_names)

    @property
    def micro_offset_names(self) -> tuple[str, ...]:
        return tuple("MicroOffset" + name for name in self.deform_names)

    @property
    def micro_control_names(self) -> tuple[str, ...]:
        return tuple("Micro" + name for name in self.deform_names)

    @property
    def micro_output_names(self) -> tuple[str, ...]:
        return tuple("MicroX" + name for name in self.deform_names)

    @property
    def micro_node_names(self) -> tuple[str, ...]:
        return (*self.micro_offset_names, *self.micro_control_names,
                *(name + "Shape" for name in self.micro_control_names),
                *self.micro_output_names,
                *(name + "Aim" for name in self.motion_transform_names),
                *(name + "MicroFollow" for name in self.motion_transform_names))


def plan_fit_bendy_chains(
    parts: tuple[FitPartJointSpec, ...],
    metadata: tuple[FitJointMetadata, ...],
    body_specs: tuple[BodyJointSpec, ...],
) -> tuple[FitBendyChainSpec, ...]:
    """Resolve every positive bendyCtrls value to one complete Twist chain."""
    by_source = {item.joint: item for item in metadata}
    if len(by_source) != len(metadata):
        raise ValueError("Fit Bendy 来源关节重复")
    by_body = {item.path: item for item in body_specs}
    if len(by_body) != len(body_specs):
        raise ValueError("Fit Bendy Body 路径重复")
    by_start: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        if part.kind == "twist":
            by_start.setdefault(part.start_body, []).append(part)
    result = []
    for chain in by_start.values():
        chain.sort(key=lambda item: item.index)
        first = chain[0]
        setting = by_source.get(first.source_joint)
        if setting is None:
            raise ValueError("Fit Bendy 缺少来源元数据：" + first.source_joint)
        requested_controls = setting.bendy_controls or 0
        if requested_controls <= 0:
            continue
        # MEL adds one base controller before constructing the Bendy chain.
        count = requested_controls + 1
        if (len(chain) != first.count
                or tuple(part.index for part in chain)
                != tuple(range(1, first.count + 1))
                or any(part.end_body != first.end_body
                       or part.side is not first.side for part in chain)):
            raise ValueError("Fit Bendy 的 Twist Part 链不完整："
                             + first.start_body_name)
        if first.start_body not in by_body or first.end_body not in by_body:
            raise ValueError("Fit Bendy 缺少两端 Body："
                             + first.start_body_name)
        result.append(FitBendyChainSpec(
            first.source_joint, first.start_body, first.end_body,
            first.side.value, tuple(part.name for part in chain), count,
            by_body[first.start_body].world_position,
            by_body[first.end_body].world_position,
            tuple(part.world_position for part in chain)))
    # An enabled Bendy joint without a same-side child cannot be constructed.
    planned_sources = {item.source_joint for item in result}
    missing = [item.joint for item in metadata
               if (item.bendy_controls or 0) > 0
               and item.joint not in planned_sources]
    if missing:
        raise ValueError("Fit Bendy 缺少可用 Twist 骨段："
                         + "、".join(missing))
    return tuple(result)
