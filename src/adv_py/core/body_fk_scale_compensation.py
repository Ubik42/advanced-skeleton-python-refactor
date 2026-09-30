"""Keep FK child position under parent scaling without inheriting its scale."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .fit_metadata import FitJointMetadata
from .fit_scale_compensation import fit_segment_scale_compensate
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
    independent_parent: bool = False
    main_scale_source_path: str | None = None
    mel_non_opm_fkx: bool = False
    driven_joint_path: str | None = None

    @property
    def fkps1_name(self) -> str:
        return self.world_matrix_name + "FKPS1"

    @property
    def fkps2_name(self) -> str:
        return self.world_matrix_name + "FKPS2"

    @property
    def fkps_scale_constraint_name(self) -> str:
        return self.world_matrix_name + "FKPSScale"

    @property
    def fkps_point_constraint_name(self) -> str:
        return self.world_matrix_name + "FKPSPoint"

    @property
    def main_scale_pick_name(self) -> str:
        return self.world_matrix_name + "MainScalePick"

    @property
    def inherit_scale_reverse_name(self) -> str:
        return self.world_matrix_name + "InheritScaleReverse"

    @property
    def node_names(self) -> tuple[str, ...]:
        if self.mel_non_opm_fkx:
            return (() if self.inherit_scale else
                    (self.fkps1_name, self.fkps2_name,
                     self.fkps_scale_constraint_name,
                     self.fkps_point_constraint_name))
        names = (self.world_matrix_name, self.pick_matrix_name,
                 self.relative_matrix_name)
        if self.independent_parent:
            names += (self.main_scale_pick_name,
                      self.inherit_scale_reverse_name)
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
    parent_controls = dict(controls_by_path)
    if not use_offset_parent_matrix:
        for item in controls:
            if item.source_override_joint and item.source_override_path:
                if item.source_override_path in parent_controls:
                    raise ValueError("FKX 父级路径与控制器重复："
                                     + item.source_override_path)
                parent_controls[item.source_override_path] = item
    metadata_by_name: dict[str, set[str]] = {}
    for item in metadata:
        metadata_by_name.setdefault(
            item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1],
            set()).add(item.joint)

    def fit_source(control: BodyLimbFkControlSpec) -> str | None:
        source = source_by_output.get(
            generated_source_by_output.get(control.driven_joint,
                                           control.driven_joint))
        if source is not None:
            return source
        # Arm/Leg FK mechanism joints are generated after Body symmetry;
        # their original Fit identity is carried by the control spec.
        candidates = set().union(*(
            metadata_by_name.get(name, set())
            for name in control.fit_joint_names))
        if len(candidates) > 1:
            raise ValueError("FK 缩放补偿来源 Fit 名称不唯一："
                             + control.control_path)
        return next(iter(candidates)) if candidates else None
    result = []
    names = set()
    for control in controls:
        parent_control = parent_controls.get(control.parent_path)
        if parent_control is None:
            continue
        source = fit_source(control)
        fit = metadata_by_source.get(source)
        if fit is None:
            raise ValueError("FK 缩放补偿缺少 Fit 元数据："
                             + control.driven_joint)
        leaf = control.driven_joint.rsplit("|", 1)[-1]
        parent_source = fit_source(parent_control)
        enabled = fit_segment_scale_compensate(
            fit, source.rsplit("|", 1)[-1],
            parent_source.rsplit("|", 1)[-1] if parent_source else "",
            use_offset_parent_matrix=use_offset_parent_matrix,
            is_finger=control.control_path in finger_control_paths)
        prefix = "AdvPy_" + leaf + "_FkScaleComp"
        spec = BodyFkScaleCompensationSpec(
            control.offset_path, control.parent_path,
            parent_control.sub_control_path or parent_control.control_path,
            control.control_path, not enabled, use_offset_parent_matrix,
            control.world_position, control.world_axes,
            prefix + "World", prefix + "Pick",
            prefix + "Relative", prefix + "Decompose",
            mel_non_opm_fkx=(
                not use_offset_parent_matrix
                and parent_control.source_override_joint
                and parent_control.source_override_path == control.parent_path),
            driven_joint_path=control.driven_joint)
        if any(name in names for name in spec.node_names):
            raise ValueError("FK 缩放补偿节点名称重复：" + leaf)
        names.update(spec.node_names)
        result.append(spec)
    return tuple(result)
