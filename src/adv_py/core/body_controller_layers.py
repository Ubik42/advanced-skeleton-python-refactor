"""Source-shaped controller topology for AdvancedSkeleton 6.925."""
from __future__ import annotations

from dataclasses import dataclass

from .body_build_options import BodyBuildOptions
from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True, slots=True)
class BodyControllerLayerSpec:
    kind: str
    name: str
    side: str
    parent_path: str
    offset_path: str
    extra_path: str
    control_path: str
    sub_path: str | None
    extra_shape_path: str | None
    sub_visibility_source: str | None
    extra_visibility_source: str | None
    sub_shape_scale: float = 0.9
    extra_shape_scale: float = 1.1
    sub_color: int = 30
    extra_color: int = 29

    @property
    def transform_paths(self) -> tuple[str, ...]:
        return (self.offset_path, self.extra_path, self.control_path) + (
            (self.sub_path,) if self.sub_path is not None else ())


@dataclass(frozen=True, slots=True)
class BodyControllerLayerSnapshot:
    """Host readback, using full DAG paths and source plugs."""

    transform_paths: tuple[str, ...]
    parent_by_path: tuple[tuple[str, str], ...]
    shape_by_transform: tuple[tuple[str, str], ...]
    visibility_sources: tuple[tuple[str, str], ...]
    sub_shape_scale: float | None
    extra_shape_scale: float | None
    sub_color: int | None
    extra_color: int | None


@dataclass(frozen=True, slots=True)
class BodySubControllerState:
    path: str
    parent_path: str | None
    shape_type: str | None
    visibility_source: str | None
    color: int | None
    shape_scale: float | None


@dataclass(frozen=True, slots=True)
class BodyExtraControllerState:
    path: str
    parent_path: str | None
    shape_path: str | None
    shape_type: str | None
    visibility_source: str | None
    color: int | None
    shape_scale: float | None


def audit_body_extra_controller(
    offset_path: str,
    control_path: str,
    extra_path: str,
    state: BodyExtraControllerState | None,
    *,
    extra_curve: bool,
    tolerance: float = 1e-4,
) -> tuple[str, ...]:
    if state is None:
        return ("缺少 Extra 层",)
    issues: list[str] = []
    if state.path != extra_path or state.parent_path != offset_path:
        issues.append("Extra 层父链不一致")
    if extra_curve:
        if state.shape_path != extra_path + "|" + extra_path.rsplit(
                "|", 1)[-1] + "Shape":
            issues.append("Extra 曲线名称不一致")
        if state.shape_type != "nurbsCurve":
            issues.append("Extra 层缺少曲线")
        if state.visibility_source != control_path + ".extraControl":
            issues.append("Extra 曲线可见性连接不一致")
        if state.color != 29:
            issues.append("Extra 曲线颜色不一致")
        if (state.shape_scale is None
                or abs(state.shape_scale - 1.1) > tolerance):
            issues.append("Extra 曲线尺寸不一致")
    elif state.shape_path is not None or state.shape_type is not None:
        issues.append("Extra 层存在计划外曲线")
    return tuple(issues)


def audit_body_sub_controller(
    control_path: str,
    sub_path: str | None,
    state: BodySubControllerState | None,
    *,
    tolerance: float = 1e-4,
) -> tuple[str, ...]:
    if sub_path is None:
        return ("存在计划外 Sub 控制器",) if state is not None else ()
    if state is None:
        return ("缺少 Sub 控制器",)
    issues: list[str] = []
    if state.path != sub_path or state.parent_path != control_path:
        issues.append("Sub 控制器父链不一致")
    if state.shape_type != "nurbsCurve":
        issues.append("Sub 控制器缺少曲线")
    if state.visibility_source != control_path + ".subControl":
        issues.append("Sub 控制器可见性连接不一致")
    if state.color != 30:
        issues.append("Sub 控制器颜色不一致")
    if (state.shape_scale is None
            or abs(state.shape_scale - 0.9) > tolerance):
        issues.append("Sub 控制器尺寸不一致")
    return tuple(issues)


def plan_body_controller_layers(
    kind: str,
    name: str,
    side: str,
    parent_path: str,
    options: BodyBuildOptions,
) -> BodyControllerLayerSpec:
    if (not isinstance(kind, str) or not kind or not kind.isalnum()
            or not isinstance(name, str) or not name or not name.isalnum()
            or not isinstance(side, str) or not side.startswith("_")
            or not side[1:].isalnum()
            or not isinstance(parent_path, str)
            or not parent_path.startswith("|")
            or parent_path.endswith("|")
            or not isinstance(options, BodyBuildOptions)):
        raise FitSkeletonValidationError("控制器层级输入无效")
    stem = kind + name + side
    offset = parent_path + "|" + kind + "Offset" + name + side
    extra = offset + "|" + kind + "Extra" + name + side
    control = extra + "|" + stem
    use_variants = kind in ("FK", "IK")
    sub = control + "|" + kind + "Sub" + name + side if (
        use_variants and options.sub_controllers) else None
    extra_shape = extra + "|" + kind + "Extra" + name + side + "Shape" if (
        use_variants and options.extra_controllers) else None
    return BodyControllerLayerSpec(
        kind=kind, name=name, side=side, parent_path=parent_path,
        offset_path=offset, extra_path=extra, control_path=control,
        sub_path=sub, extra_shape_path=extra_shape,
        sub_visibility_source=control + ".subControl" if sub else None,
        extra_visibility_source=control + ".extraControl" if extra_shape else None,
    )


def audit_body_controller_layers(
    spec: BodyControllerLayerSpec,
    snapshot: BodyControllerLayerSnapshot,
) -> tuple[str, ...]:
    issues: list[str] = []
    if set(snapshot.transform_paths) != set(spec.transform_paths) or (
            len(snapshot.transform_paths) != len(spec.transform_paths)):
        issues.append("控制器 Transform 集合与计划不一致")
    expected_parents = {
        spec.offset_path: spec.parent_path,
        spec.extra_path: spec.offset_path,
        spec.control_path: spec.extra_path,
    }
    if spec.sub_path is not None:
        expected_parents[spec.sub_path] = spec.control_path
    if dict(snapshot.parent_by_path) != expected_parents or (
            len(snapshot.parent_by_path) != len(expected_parents)):
        issues.append("控制器父链与计划不一致")
    expected_shapes = {spec.control_path: "nurbsCurve"}
    if spec.sub_path is not None:
        expected_shapes[spec.sub_path] = "nurbsCurve"
    if spec.extra_shape_path is not None:
        expected_shapes[spec.extra_path] = "nurbsCurve"
    if dict(snapshot.shape_by_transform) != expected_shapes or (
            len(snapshot.shape_by_transform) != len(expected_shapes)):
        issues.append("控制器曲线集合与计划不一致")
    expected_sources = {}
    if spec.sub_path is not None:
        expected_sources[spec.sub_path + "Shape.visibility"] = (
            spec.sub_visibility_source)
    if spec.extra_shape_path is not None:
        expected_sources[spec.extra_shape_path + ".visibility"] = (
            spec.extra_visibility_source)
    if dict(snapshot.visibility_sources) != expected_sources or (
            len(snapshot.visibility_sources) != len(expected_sources)):
        issues.append("控制器可见性连接与计划不一致")
    if spec.sub_path is not None and (
            snapshot.sub_shape_scale != spec.sub_shape_scale
            or snapshot.sub_color != spec.sub_color):
        issues.append("Sub 控制器曲线规格不一致")
    if spec.extra_shape_path is not None and (
            snapshot.extra_shape_scale != spec.extra_shape_scale
            or snapshot.extra_color != spec.extra_color):
        issues.append("Extra 控制器曲线规格不一致")
    return tuple(issues)
