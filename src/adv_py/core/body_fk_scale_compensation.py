"""Keep FK child position under parent scaling without inheriting its scale."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .body_limb_controls import BodyLimbFkControlSpec
from .fit_metadata import FitJointMetadata
from .fit_symmetry import FitSymmetryInstance


@dataclass(frozen=True, slots=True)
class BodyFkScaleCompensationSpec:
    offset_path: str
    parent_control_path: str
    scale_source_path: str
    control_path: str
    inherit_scale: bool
    use_offset_parent_matrix: bool
    world_position: tuple[float, float, float]
    world_axes: tuple[tuple[float, float, float], ...]
    world_matrix_name: str
    pick_matrix_name: str
    relative_matrix_name: str
    decompose_matrix_name: str

    @property
    def node_names(self) -> tuple[str, ...]:
        names = (self.world_matrix_name, self.pick_matrix_name,
                 self.relative_matrix_name)
        return (names if self.use_offset_parent_matrix
                else names + (self.decompose_matrix_name,))


def plan_body_fk_scale_compensation(
    controls: tuple[BodyLimbFkControlSpec, ...],
    instances: tuple[FitSymmetryInstance, ...],
    metadata: tuple[FitJointMetadata, ...],
    *,
    use_offset_parent_matrix: bool,
    finger_control_paths: frozenset[str] = frozenset(),
    generated_joint_sources: tuple[tuple[str, str], ...] = (),
) -> tuple[BodyFkScaleCompensationSpec, ...]:
    if type(use_offset_parent_matrix) is not bool:
        raise ValueError("FK 缩放补偿需要明确的 OPM 构建选项")
    source_by_output = {item.output_path: item.source_joint
                        for item in instances}
    generated_source_by_output = dict(generated_joint_sources)
    metadata_by_source = {item.joint: item for item in metadata}
    if (len(source_by_output) != len(instances)
            or len(metadata_by_source) != len(metadata)
            or len(generated_source_by_output) != len(generated_joint_sources)
            or any(source not in source_by_output
                   for source in generated_source_by_output.values())
            or any(output in source_by_output
                   for output in generated_source_by_output)):
        raise ValueError("FK 缩放补偿需要唯一的 Fit 来源")
    controls_by_path = {item.control_path: item for item in controls}
    if len(controls_by_path) != len(controls):
        raise ValueError("FK 缩放补偿控制器路径重复")
    if not finger_control_paths <= controls_by_path.keys():
        raise ValueError("FK 缩放补偿手指控制器不在当前构建计划中")
    result = []
    names = set()
    for control in controls:
        parent_control = controls_by_path.get(control.parent_path)
        if parent_control is None:
            continue
        source = source_by_output.get(
            generated_source_by_output.get(control.driven_joint,
                                           control.driven_joint))
        fit = metadata_by_source.get(source)
        if fit is None:
            raise ValueError("FK 缩放补偿缺少 Fit 元数据："
                             + control.driven_joint)
        leaf = control.driven_joint.rsplit("|", 1)[-1]
        stem = leaf.rsplit("_", 1)[0]
        parent_leaf = control.parent_path.rsplit("|", 1)[-1]
        parent_stem = parent_leaf.rsplit("_", 1)[0]
        enabled = (fit.seg_scale_comp if fit.seg_scale_comp is not None
                   else not (control.control_path in finger_control_paths
                             or any(token in stem for token in
                                 ("Finger", "Cup", "Toes"))
                             or "Head" in parent_stem
                             or re.search(r"Part[0-9]", stem) is not None))
        prefix = "AdvPy_" + leaf + "_FkScaleComp"
        spec = BodyFkScaleCompensationSpec(
            control.offset_path, control.parent_path,
            parent_control.sub_control_path or parent_control.control_path,
            control.control_path, not enabled, use_offset_parent_matrix,
            control.world_position, control.world_axes,
            prefix + "World", prefix + "Pick",
            prefix + "Relative", prefix + "Decompose")
        if any(name in names for name in spec.node_names):
            raise ValueError("FK 缩放补偿节点名称重复：" + leaf)
        names.update(spec.node_names)
        result.append(spec)
    return tuple(result)
