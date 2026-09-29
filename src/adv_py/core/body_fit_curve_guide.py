"""CurveGuide inputs from the Fit hierarchy and built FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .body_skeleton import BodyJointSpec
from .fit_metadata import FitJointMetadata
from .fit_part import FitPartFinalPaths
from .fit_symmetry import FitSymmetryInstance


@dataclass(frozen=True, slots=True)
class BodyFitCurveGuideSpec:
    fit_joint: str
    source_curve: str
    curve_name: str
    side: str
    control: BodyLimbFkControlSpec
    parent_body: str
    tangent_sign: int
    follow_positions: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True, slots=True)
class BodyFitCurveGuideBuilt:
    curve_path: str
    ik_control_path: str
    cv_control_paths: tuple[str, ...]
    helper_paths: tuple[str, ...]


def plan_body_fit_curve_guides(
    metadata: tuple[FitJointMetadata, ...],
    instances: tuple[FitSymmetryInstance, ...],
    body_specs: tuple[BodyJointSpec, ...],
    controls: tuple[BodyLimbFkControlSpec, ...],
    *, final_paths: FitPartFinalPaths | None = None,
) -> tuple[BodyFitCurveGuideSpec, ...]:
    marked = {item.joint: item for item in metadata
              if item.curve_guide is not None}
    if not marked:
        return ()
    by_control = {
        (name, control.side.value): control
        for control in controls for name in control.fit_joint_names
    }
    by_body = {(spec.source_joint, spec.side.value): spec
               for spec in body_specs}
    guides: list[BodyFitCurveGuideSpec] = []
    curve_sources: dict[str, str] = {}
    for instance in instances:
        item = marked.get(instance.source_joint)
        if item is None:
            continue
        if item.aim:
            raise ValueError("Curve Guide 与同一关节的 Aim 标记不能共用 FK Aim 层："
                             + instance.source_joint)
        name = instance.output_name.rsplit("_", 1)[0]
        control = by_control.get((name, instance.side.value))
        if control is None:
            raise ValueError("Curve Guide 标记的关节缺少 FK 控制器："
                             + instance.source_joint)
        if control.aim_path is None:
            raise ValueError("Curve Guide 缺少 FK Aim 接收层："
                             + control.control_path)
        body = by_body[(instance.source_joint, instance.side.value)]
        if body.parent_path is None:
            raise ValueError("Curve Guide 关节缺少父级：" + body.name)
        parent = (final_paths.remap_body_reference(body.parent_path)
                  if final_paths is not None else body.parent_path)
        source = item.curve_guide
        assert source is not None
        stem = source.rsplit("|", 1)[-1].replace(":", "__")
        curve_name = "AdvPy_CurveGuide_" + stem + "_" + instance.side.value
        existing_source = curve_sources.setdefault(curve_name, source)
        if existing_source != source:
            raise ValueError("Curve Guide 输出名称对应多个来源曲线："
                             + curve_name)
        guides.append(BodyFitCurveGuideSpec(
            fit_joint=instance.source_joint,
            source_curve=source,
            curve_name=curve_name,
            side=instance.side.value,
            control=control,
            parent_body=parent,
            tangent_sign=-1 if instance.side.value == "L" else 1,
            follow_positions=tuple(
                joint.world_position for joint in instances
                if joint.side is instance.side
                and (joint.output_path == instance.output_path
                     or joint.output_path.startswith(
                         instance.output_path + "|"))),
        ))
    return tuple(guides)
