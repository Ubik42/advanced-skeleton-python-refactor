from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_container import FitUpAxis


Vector3 = tuple[float, float, float]


class BodyCharacterGlobalValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyCharacterGlobalPlan:
    root_name: str
    root_path: str
    offset_name: str
    offset_path: str
    control_name: str
    control_path: str
    shape_name: str
    up_axis: FitUpAxis
    radius: float
    scale_attribute: str
    scale_default: float
    scale_minimum: float
    driven_roots: tuple[str, ...]
    scale_destinations: tuple[str, ...]

    @property
    def node_names(self) -> tuple[str, str, str, str]:
        return (
            self.root_name,
            self.offset_name,
            self.control_name,
            self.shape_name,
        )

    @property
    def scale_source(self) -> str:
        return f"{self.control_path}.{self.scale_attribute}"

    @property
    def circle_normal(self) -> Vector3:
        return (
            (0.0, 1.0, 0.0)
            if self.up_axis is FitUpAxis.Y
            else (0.0, 0.0, 1.0)
        )


@dataclass(frozen=True, slots=True)
class BodyCharacterDrivenRootState:
    path: str
    parent_path: str | None
    translation_sources: tuple[str | None, str | None, str | None]
    rotation_sources: tuple[str | None, str | None, str | None]
    scale_sources: tuple[str | None, str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyCharacterGlobalSnapshot:
    root_path: str
    root_parent_path: str | None
    root_translation: Vector3
    root_rotation: Vector3
    root_scale: Vector3
    offset_path: str
    offset_parent_path: str | None
    offset_translation: Vector3
    offset_rotation: Vector3
    offset_scale: Vector3
    control_path: str
    control_parent_path: str | None
    control_shape_type: str | None
    control_translation: Vector3
    control_rotation: Vector3
    control_scale: Vector3
    scale_attribute_plug: str
    scale_attribute_value: float
    scale_attribute_minimum: float | None
    control_scale_sources: tuple[str | None, str | None, str | None]
    driven_roots: tuple[BodyCharacterDrivenRootState, ...]
    scale_destination_sources: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True, slots=True)
class BodyCharacterGlobalIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_character_global(
    *,
    up_axis: FitUpAxis,
    body_root: str,
    driven_roots: tuple[str, ...],
    scale_destinations: tuple[str, ...],
    radius: float = 12.0,
    body_root_via_controls: bool = False,
) -> BodyCharacterGlobalPlan:
    if (
        not isinstance(up_axis, FitUpAxis)
        or not isinstance(body_root, str)
        or not body_root.startswith("|")
        or not isinstance(driven_roots, tuple)
        or not driven_roots
        or not isinstance(scale_destinations, tuple)
        or not isinstance(body_root_via_controls, bool)
        or (not body_root_via_controls and body_root not in driven_roots)
        or (body_root_via_controls and (
            body_root in driven_roots
            or not all(f"{body_root}.scale{axis}" in scale_destinations for axis in "XYZ")
        ))
        or len(set(driven_roots)) != len(driven_roots)
        or any(
            not isinstance(path, str)
            or not path.startswith("|")
            or path.count("|") != 1
            for path in driven_roots
        )
        or not isinstance(scale_destinations, tuple)
        or not scale_destinations
        or len(set(scale_destinations)) != len(scale_destinations)
        or any(
            not isinstance(plug, str)
            or "." not in plug
            for plug in scale_destinations
        )
        or isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or float(radius) <= 0.0
    ):
        raise BodyCharacterGlobalValidationError(
            "角色总控的宿主轴、根节点、缩放目标或半径无效"
        )

    root_name = "AdvPy_CharacterControls"
    root_path = f"|{root_name}"
    offset_name = "AdvPy_GlobalOffset"
    offset_path = f"{root_path}|{offset_name}"
    control_name = "AdvPy_Global"
    control_path = f"{offset_path}|{control_name}"
    names = {root_name, offset_name, control_name, f"{control_name}Shape"}
    if any(path.rsplit("|", 1)[-1] in names for path in driven_roots):
        raise BodyCharacterGlobalValidationError(
            "角色总控名称与被驱动根节点冲突"
        )
    return BodyCharacterGlobalPlan(
        root_name=root_name,
        root_path=root_path,
        offset_name=offset_name,
        offset_path=offset_path,
        control_name=control_name,
        control_path=control_path,
        shape_name=f"{control_name}Shape",
        up_axis=up_axis,
        radius=float(radius),
        scale_attribute="globalScale",
        scale_default=1.0,
        scale_minimum=0.0001,
        driven_roots=driven_roots,
        scale_destinations=scale_destinations,
    )


def audit_body_character_global(
    plan: BodyCharacterGlobalPlan,
    snapshot: BodyCharacterGlobalSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyCharacterGlobalIssue, ...]:
    issues = []
    neutral = (0.0, 0.0, 0.0)
    one = (1.0, 1.0, 1.0)
    if not (
        snapshot.root_path == plan.root_path
        and snapshot.root_parent_path is None
        and _close(snapshot.root_translation, neutral, tolerance)
        and _close(snapshot.root_rotation, neutral, tolerance)
        and _close(snapshot.root_scale, one, tolerance)
    ):
        issues.append(BodyCharacterGlobalIssue(
            "root_mismatch",
            "角色总控根层级或中性通道不一致",
            plan.root_path,
        ))
    if not (
        snapshot.offset_path == plan.offset_path
        and snapshot.offset_parent_path == plan.root_path
        and _close(snapshot.offset_translation, neutral, tolerance)
        and _close(snapshot.offset_rotation, neutral, tolerance)
        and _close(snapshot.offset_scale, one, tolerance)
    ):
        issues.append(BodyCharacterGlobalIssue(
            "offset_mismatch",
            "角色总控 offset 层级或中性通道不一致",
            plan.offset_path,
        ))
    scale_plug = plan.scale_source
    if not (
        snapshot.control_path == plan.control_path
        and snapshot.control_parent_path == plan.offset_path
        and snapshot.control_shape_type == "nurbsCurve"
        and _close(snapshot.control_translation, neutral, tolerance)
        and _close(snapshot.control_rotation, neutral, tolerance)
        and _close(snapshot.control_scale, one, tolerance)
        and snapshot.scale_attribute_plug == scale_plug
        and abs(snapshot.scale_attribute_value - plan.scale_default) <= tolerance
        and snapshot.scale_attribute_minimum is not None
        and abs(snapshot.scale_attribute_minimum - plan.scale_minimum) <= tolerance
        and snapshot.control_scale_sources == (scale_plug, scale_plug, scale_plug)
    ):
        issues.append(BodyCharacterGlobalIssue(
            "control_mismatch",
            "角色总控曲线、通道或 uniform scale 属性不一致",
            plan.control_path,
        ))

    actual_roots = {state.path: state for state in snapshot.driven_roots}
    if set(actual_roots) != set(plan.driven_roots):
        issues.append(BodyCharacterGlobalIssue(
            "driven_root_set_mismatch",
            "角色总控被驱动根集合不一致",
        ))
    expected_translate = tuple(
        f"{plan.control_path}.translate{axis}" for axis in "XYZ"
    )
    expected_rotate = tuple(
        f"{plan.control_path}.rotate{axis}" for axis in "XYZ"
    )
    expected_scale = (scale_plug, scale_plug, scale_plug)
    for path in plan.driven_roots:
        state = actual_roots.get(path)
        if state is None:
            continue
        if not (
            state.parent_path is None
            and state.translation_sources == expected_translate
            and state.rotation_sources == expected_rotate
            and state.scale_sources == expected_scale
        ):
            issues.append(BodyCharacterGlobalIssue(
                "driven_root_wiring_mismatch",
                "角色总控根节点变换接线不一致",
                path,
            ))

    expected_destinations = tuple(
        (destination, scale_plug)
        for destination in plan.scale_destinations
    )
    if snapshot.scale_destination_sources != expected_destinations:
        issues.append(BodyCharacterGlobalIssue(
            "scale_destination_mismatch",
            "Arm/Leg 全局比例补偿接线不一致",
        ))
    return tuple(issues)


def _close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right)
    )
