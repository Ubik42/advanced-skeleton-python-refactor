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
    world_position: tuple[float, float, float]
    world_axes: tuple[tuple[float, float, float], ...]
    world_matrix_name: str
    pick_matrix_name: str
    relative_matrix_name: str

    @property
    def node_names(self) -> tuple[str, str, str]:
        return (self.world_matrix_name, self.pick_matrix_name,
                self.relative_matrix_name)


def plan_body_fk_scale_compensation(
    controls: tuple[BodyLimbFkControlSpec, ...],
    instances: tuple[FitSymmetryInstance, ...],
    metadata: tuple[FitJointMetadata, ...],
) -> tuple[BodyFkScaleCompensationSpec, ...]:
    source_by_output = {item.output_path: item.source_joint
                        for item in instances}
    metadata_by_source = {item.joint: item for item in metadata}
    if (len(source_by_output) != len(instances)
            or len(metadata_by_source) != len(metadata)):
        raise ValueError("FK 缩放补偿需要唯一的 Fit 来源")
    control_paths = {item.control_path for item in controls}
    if len(control_paths) != len(controls):
        raise ValueError("FK 缩放补偿控制器路径重复")
    result = []
    names = set()
    for control in controls:
        if control.parent_path not in control_paths:
            continue
        source = source_by_output.get(control.driven_joint)
        fit = metadata_by_source.get(source)
        if fit is None:
            raise ValueError("FK 缩放补偿缺少 Fit 元数据："
                             + control.driven_joint)
        leaf = control.driven_joint.rsplit("|", 1)[-1]
        stem = leaf.rsplit("_", 1)[0]
        parent_leaf = control.parent_path.rsplit("|", 1)[-1]
        parent_stem = parent_leaf.rsplit("_", 1)[0]
        enabled = (fit.seg_scale_comp if fit.seg_scale_comp is not None
                   else not (any(token in stem for token in
                                 ("Finger", "Cup", "Toes"))
                             or "Head" in parent_stem
                             or re.search(r"Part[0-9]", stem) is not None))
        if not enabled:
            continue
        prefix = "AdvPy_" + leaf + "_FkScaleComp"
        spec = BodyFkScaleCompensationSpec(
            control.offset_path, control.parent_path,
            control.world_position, control.world_axes,
            prefix + "World", prefix + "Pick",
            prefix + "Relative")
        if any(name in names for name in spec.node_names):
            raise ValueError("FK 缩放补偿节点名称重复：" + leaf)
        names.update(spec.node_names)
        result.append(spec)
    return tuple(result)
