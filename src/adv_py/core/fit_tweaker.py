"""Plan OPM Tweaker controls for Fit joints and generated Part joints."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata
from .fit_part import FitPartFinalPaths, FitPartJointSpec
from .fit_symmetry import FitSymmetryInstance


@dataclass(frozen=True, slots=True)
class FitTweakerSpec:
    source_joint: str
    target_path: str
    offset_path: str
    control_path: str
    x_path: str
    base_world_name: str
    offset_matrix_name: str
    local_inverse_name: str
    final_matrix_name: str

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.offset_path.rsplit("|", 1)[-1],
                self.control_path.rsplit("|", 1)[-1],
                self.x_path.rsplit("|", 1)[-1],
                self.base_world_name, self.offset_matrix_name,
                self.local_inverse_name, self.final_matrix_name)


@dataclass(frozen=True, slots=True)
class FitTweakerPlan:
    system_path: str
    global_control_path: str
    controls: tuple[FitTweakerSpec, ...]


@dataclass(frozen=True, slots=True)
class FitTweakerSourceState:
    parent_path: str | None
    offset_matrix_source: str | None
    static_offset_matrix: tuple[float, ...]
    world_matrix: tuple[float, ...]


def plan_fit_tweakers(
    instances: tuple[FitSymmetryInstance, ...],
    metadata: tuple[FitJointMetadata, ...],
    parts: tuple[FitPartJointSpec, ...],
    *,
    motion_system_path: str,
    global_control_path: str,
    final_paths: FitPartFinalPaths | None = None,
) -> FitTweakerPlan:
    by_source = {item.joint: item for item in metadata}
    if len(by_source) != len(metadata):
        raise ValueError("Tweaker Fit 来源重复")
    if not motion_system_path.startswith("|") or not global_control_path.startswith("|"):
        raise ValueError("Tweaker 需要明确的 MotionSystem 与总控路径")
    if parts and final_paths is None:
        raise ValueError("Tweaker Part 需要最终关节路径映射")
    ns = motion_system_path.rsplit("|", 1)[-1].rsplit(":", 1)
    prefix = ns[0] + ":" if len(ns) == 2 else ""
    system_path = motion_system_path + "|" + prefix + "TweakerSystem"
    part_paths = dict(final_paths.part_paths) if final_paths else {}
    result: list[FitTweakerSpec] = []
    targets: set[str] = set()
    names: set[str] = set()

    def add(source: str, target: str) -> None:
        if target in targets:
            raise ValueError("Tweaker 目标关节重复：" + target)
        leaf = target.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        stem = prefix + "AdvPy_Tweaker" + leaf
        offset = system_path + "|" + stem + "Offset"
        control = offset + "|" + stem
        x_path = control + "|" + stem + "X"
        spec = FitTweakerSpec(
            source, target, offset, control, x_path,
            stem + "BaseWorld", stem + "OffsetMM",
            stem + "LocalInverse", stem + "FinalMM")
        if names.intersection(spec.node_names):
            raise ValueError("Tweaker 节点名称重复：" + leaf)
        names.update(spec.node_names)
        targets.add(target)
        result.append(spec)

    for instance in instances:
        fit = by_source.get(instance.source_joint)
        if fit is None:
            raise ValueError("Tweaker 缺少 Fit 元数据："
                             + instance.source_joint)
        if not fit.tweaker_control:
            continue
        body = (final_paths.remap_body_reference(instance.output_path)
                if final_paths else instance.output_path)
        add(instance.source_joint, body)
        for part in parts:
            if (part.source_joint == instance.source_joint
                    and part.side is instance.side
                    and part.start_body == instance.output_path):
                if part.name not in part_paths:
                    raise ValueError("Tweaker Part 缺少最终路径："
                                     + part.name)
                add(instance.source_joint,
                    part_paths[part.name])
    return FitTweakerPlan(system_path, global_control_path, tuple(result))
