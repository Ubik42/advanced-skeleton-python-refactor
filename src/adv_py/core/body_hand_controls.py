from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_hand_fit import (
    BODY_HAND_DIGITS, BODY_HAND_SEGMENTS, BodyHandDigit,
    advanced_skeleton_hand_source_joint_names, body_hand_source_joint_names,
)
from .body_limb_controls import (
    BodyLimbControlIssue,
    BodyLimbFkControlPlan,
    BodyLimbFkControlSnapshot,
    BodyLimbFkControlSpec,
    BodyLimbFkControlState,
    audit_body_limb_fk_controls,
)
from .body_skeleton import BodySkeletonSnapshot
from .fit_hierarchy import TRANSLATION_AXES
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyHandControlValidationError(ValueError):
    """Raised when bilateral five-digit controls cannot be planned safely."""


BodyHandFkControlSpec = BodyLimbFkControlSpec
BodyHandFkControlState = BodyLimbFkControlState
BodyHandControlIssue = BodyLimbControlIssue


BODY_HAND_CURL_WEIGHTS = (("1", 0.45), ("2", 0.75), ("3", 1.0))
BODY_HAND_SPREAD_FACTORS = (
    (BodyHandDigit.THUMB, 1.0),
    (BodyHandDigit.INDEX, 0.5),
    (BodyHandDigit.MIDDLE, 0.0),
    (BodyHandDigit.RING, -0.5),
    (BodyHandDigit.PINKY, -1.0),
)


@dataclass(frozen=True, slots=True)
class BodyHandFkRootSpec:
    side: FitBuildSide
    wrist_joint: str
    path: str
    name: str
    parent_path: str
    world_position: Vector3
    world_axes: AxisFrame


@dataclass(frozen=True, slots=True)
class BodyHandFkControlPlan:
    roots: tuple[BodyHandFkRootSpec, ...]
    controls: tuple[BodyHandFkControlSpec, ...]

    @property
    def node_names(self) -> tuple[str, ...]:
        values = [root.name for root in self.roots]
        for control in self.controls:
            values.extend((
                control.offset_name,
                control.control_name,
                control.constraint_name,
            ))
            if (
                control.control_parent_path is not None
                and control.control_parent_path != control.offset_path
            ):
                values.append(
                    control.control_parent_path.rsplit("|", 1)[-1]
                )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyHandFkRootState:
    path: str
    parent_path: str | None
    world_position: Vector3
    world_axes: AxisFrame
    local_translation: Vector3
    local_rotation: Vector3
    local_scale: Vector3


@dataclass(frozen=True, slots=True)
class BodyHandFkControlSnapshot:
    roots: tuple[BodyHandFkRootState, ...]
    controls: tuple[BodyHandFkControlState, ...]


@dataclass(frozen=True, slots=True)
class BodyHandFkJointInputState:
    joint: str
    writable_rotation_axes: frozenset[str]
    rotation_sources: tuple[str | None, str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyHandFkInputSnapshot:
    joints: tuple[BodyHandFkJointInputState, ...]


@dataclass(frozen=True, slots=True)
class BodyHandPoseAttributeSpec:
    side: FitBuildSide
    root_path: str
    name: str
    plug: str
    minimum: float
    maximum: float
    default: float = 0.0


@dataclass(frozen=True, slots=True)
class BodyHandPoseLayerSpec:
    path: str
    name: str
    parent_path: str


@dataclass(frozen=True, slots=True)
class BodyHandCurlSpec:
    side: FitBuildSide
    digit: BodyHandDigit
    segment: str
    node_name: str
    source_plugs: tuple[str, str]
    weights: tuple[float, float]
    destination_plug: str


@dataclass(frozen=True, slots=True)
class BodyHandSpreadSpec:
    side: FitBuildSide
    digit: BodyHandDigit
    node_name: str
    source_plug: str
    factor: float
    destination_plug: str


@dataclass(frozen=True, slots=True)
class BodyHandPosePlan:
    layers: tuple[BodyHandPoseLayerSpec, ...]
    attributes: tuple[BodyHandPoseAttributeSpec, ...]
    curls: tuple[BodyHandCurlSpec, ...]
    spreads: tuple[BodyHandSpreadSpec, ...]

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(
            spec.node_name for spec in self.curls + self.spreads
        )


@dataclass(frozen=True, slots=True)
class BodyHandPoseAttributeState:
    plug: str
    value: float
    minimum: float | None
    maximum: float | None
    keyable: bool


@dataclass(frozen=True, slots=True)
class BodyHandPoseLayerState:
    path: str
    parent_path: str | None
    local_translation: Vector3
    local_rotation: Vector3
    local_scale: Vector3


@dataclass(frozen=True, slots=True)
class BodyHandCurlState:
    node_name: str
    node_type: str | None
    source_plugs: tuple[str | None, str | None]
    weights: tuple[float, float]
    destination_plug: str
    destination_source: str | None


@dataclass(frozen=True, slots=True)
class BodyHandSpreadState:
    node_name: str
    node_type: str | None
    source_plug: str | None
    factor: float
    destination_plug: str
    destination_source: str | None


@dataclass(frozen=True, slots=True)
class BodyHandPoseSnapshot:
    layers: tuple[BodyHandPoseLayerState, ...]
    attributes: tuple[BodyHandPoseAttributeState, ...]
    curls: tuple[BodyHandCurlState, ...]
    spreads: tuple[BodyHandSpreadState, ...]


def plan_body_hand_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    radius: float = 0.3,
    namespace: str | None = None,
) -> BodyHandFkControlPlan:
    if (
        isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or float(radius) <= 0.0
    ):
        raise BodyHandControlValidationError(
            "Hand FK 控制半径必须是正有限数值"
        )
    prefix = _namespace_prefix(namespace)
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise BodyHandControlValidationError("Body joint 名称不唯一")
    canonical = {f"{name}_{side}" for name in body_hand_source_joint_names()
                 for side in ("R", "L")}
    original = {f"{name}_{side}"
                for name in advanced_skeleton_hand_source_joint_names()
                for side in ("R", "L")}
    available = set(by_name)
    if canonical <= available and not original & available:
        original_names = False
    elif original <= available and not canonical & available:
        original_names = True
    else:
        raise BodyHandControlValidationError(
            "Body 五指关节必须完整使用模板名称或原版 Finger1～Finger4 名称")

    roots = []
    controls = []
    radius_factors = (1.0, 0.82, 0.68)
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        wrist = by_name.get(f"Wrist_{suffix}")
        if wrist is None or wrist.side is not side:
            raise BodyHandControlValidationError(
                f"Body 缺少唯一的 Wrist_{suffix}"
            )
        root_name = f"{prefix}AdvPy_HandFKControls_{suffix}"
        root_path = f"{wrist.path}|{root_name}"
        roots.append(BodyHandFkRootSpec(
            side=side,
            wrist_joint=wrist.path,
            path=root_path,
            name=root_name,
            parent_path=wrist.path,
            world_position=wrist.world_position,
            world_axes=wrist.world_axes,
        ))

        for digit in BODY_HAND_DIGITS:
            states = []
            previous_path = wrist.path
            if original_names and digit in (BodyHandDigit.RING, BodyHandDigit.PINKY):
                cup = by_name.get(f"Cup_{suffix}")
                if (cup is None or cup.side is not side
                        or cup.parent_path != wrist.path):
                    raise BodyHandControlValidationError(
                        f"原版 Hand 缺少 Wrist_{suffix} 下的 Cup_{suffix}")
                previous_path = cup.path
            for index, segment in enumerate(BODY_HAND_SEGMENTS, start=1):
                name = (f"{digit.value}Finger{index}" if original_names
                        else f"{digit.value}{segment}")
                state = by_name.get(f"{name}_{suffix}")
                if state is None:
                    raise BodyHandControlValidationError(
                        f"Body 缺少 {name}_{suffix}"
                    )
                if state.side is not side or state.parent_path != previous_path:
                    raise BodyHandControlValidationError(
                        f"{state.name} 不在预期 Hand 父链上"
                    )
                states.append(state)
                previous_path = state.path

            parent_path = root_path
            for index, state in enumerate(states[:-1], start=1):
                offset_name = (
                    f"{prefix}AdvPy_{digit.value}{index}FKOffset_{suffix}"
                )
                control_name = (
                    f"{prefix}AdvPy_{digit.value}{index}FK_{suffix}"
                )
                offset_path = f"{parent_path}|{offset_name}"
                pose_name = (
                    f"{prefix}AdvPy_{digit.value}{index}Pose_{suffix}"
                )
                pose_path = f"{offset_path}|{pose_name}"
                control_path = f"{pose_path}|{control_name}"
                controls.append(BodyHandFkControlSpec(
                    side=side,
                    driven_joint=state.path,
                    offset_path=offset_path,
                    offset_name=offset_name,
                    control_path=control_path,
                    control_name=control_name,
                    parent_path=parent_path,
                    constraint_name=(
                        f"{prefix}AdvPy_{digit.value}{index}FKOrient_{suffix}"
                    ),
                    world_position=state.world_position,
                    world_axes=state.world_axes,
                    radius=float(radius) * radius_factors[index - 1],
                    control_parent_path=pose_path,
                ))
                parent_path = control_path
    return BodyHandFkControlPlan(tuple(roots), tuple(controls))


def plan_body_hand_pose_controls(
    hand: BodyHandFkControlPlan,
) -> BodyHandPosePlan:
    roots = {root.side: root for root in hand.roots}
    namespaces = {_node_namespace(root.name) for root in hand.roots}
    if len(namespaces) != 1:
        raise BodyHandControlValidationError(
            "Hand 聚合姿态的双侧根必须位于同一 namespace"
        )
    namespace = next(iter(namespaces))
    if any(
        _node_namespace(control.control_name) != namespace
        for control in hand.controls
    ):
        raise BodyHandControlValidationError(
            "Hand 聚合姿态的 FK controls 必须位于同一 namespace"
        )
    prefix = _namespace_prefix(namespace)
    controls = {
        _base_node_name(control.control_name): control
        for control in hand.controls
    }
    if len(roots) != 2 or set(roots) != {
        FitBuildSide.RIGHT,
        FitBuildSide.LEFT,
    }:
        raise BodyHandControlValidationError(
            "Hand 聚合姿态需要唯一的双侧 Hand FK 根"
        )
    if len(controls) != len(hand.controls):
        raise BodyHandControlValidationError(
            "Hand 聚合姿态需要唯一的 FK control 名称"
        )

    attributes = []
    layers = []
    curls = []
    spreads = []
    spread_by_digit = dict(BODY_HAND_SPREAD_FACTORS)
    for suffix, side, side_factor in (
        ("R", FitBuildSide.RIGHT, 1.0),
        ("L", FitBuildSide.LEFT, -1.0),
    ):
        root = roots[side]
        attribute_ranges = (
            ("handCurl", -90.0, 90.0),
            *((f"{digit.value.lower()}Curl", -45.0, 45.0)
              for digit in BODY_HAND_DIGITS),
            ("handSpread", -30.0, 30.0),
        )
        attributes.extend(
            BodyHandPoseAttributeSpec(
                side,
                root.path,
                name,
                f"{root.path}.{name}",
                minimum,
                maximum,
            )
            for name, minimum, maximum in attribute_ranges
        )
        hand_curl = f"{root.path}.handCurl"
        hand_spread = f"{root.path}.handSpread"
        for digit in BODY_HAND_DIGITS:
            digit_curl = f"{root.path}.{digit.value.lower()}Curl"
            for segment, weight in BODY_HAND_CURL_WEIGHTS:
                control_name = f"AdvPy_{digit.value}{segment}FK_{suffix}"
                control = controls.get(control_name)
                if control is None or control.side is not side:
                    raise BodyHandControlValidationError(
                        f"Hand 聚合姿态缺少 {control_name}"
                    )
                if (
                    control.control_parent_path is None
                    or control.control_parent_path == control.offset_path
                ):
                    raise BodyHandControlValidationError(
                        f"Hand 聚合姿态缺少零通道 Pose 层：{control_name}"
                    )
                layers.append(BodyHandPoseLayerSpec(
                    path=control.control_parent_path,
                    name=control.control_parent_path.rsplit("|", 1)[-1],
                    parent_path=control.offset_path,
                ))
                curls.append(BodyHandCurlSpec(
                    side=side,
                    digit=digit,
                    segment=segment,
                    node_name=(
                        f"{prefix}AdvPy_HandCurl_"
                        f"{digit.value}{segment}_{suffix}"
                    ),
                    source_plugs=(hand_curl, digit_curl),
                    weights=(weight, weight),
                    destination_plug=(
                        f"{control.control_parent_path}.rotateZ"
                    ),
                ))
            spread_factor = spread_by_digit[digit] * side_factor
            if abs(spread_factor) > 1e-10:
                first = controls[f"AdvPy_{digit.value}1FK_{suffix}"]
                spreads.append(BodyHandSpreadSpec(
                    side=side,
                    digit=digit,
                    node_name=(
                        f"{prefix}AdvPy_HandSpread_{digit.value}_{suffix}"
                    ),
                    source_plug=hand_spread,
                    factor=spread_factor,
                    destination_plug=(
                        f"{first.control_parent_path}.rotateY"
                    ),
                ))
    return BodyHandPosePlan(
        tuple(layers),
        tuple(attributes),
        tuple(curls),
        tuple(spreads),
    )


def audit_body_hand_fk_input(
    plan: BodyHandFkControlPlan,
    snapshot: BodyHandFkInputSnapshot,
) -> tuple[BodyHandControlIssue, ...]:
    expected = {control.driven_joint for control in plan.controls}
    actual = {joint.joint: joint for joint in snapshot.joints}
    issues = []
    if len(actual) != len(snapshot.joints) or set(actual) != expected:
        issues.append(BodyHandControlIssue(
            "hand_input_joint_set_mismatch",
            "Hand FK 输入关节集合不一致",
        ))
    for path in sorted(expected & set(actual)):
        state = actual[path]
        if state.writable_rotation_axes != TRANSLATION_AXES:
            issues.append(BodyHandControlIssue(
                "hand_input_rotation_locked",
                "Hand FK 目标 rotate 不可完整写入",
                path,
            ))
        if any(source is not None for source in state.rotation_sources):
            issues.append(BodyHandControlIssue(
                "hand_input_rotation_connected",
                "Hand FK 目标 rotate 已有输入连接",
                path,
            ))
    return tuple(issues)


def audit_body_hand_pose_controls(
    plan: BodyHandPosePlan,
    snapshot: BodyHandPoseSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyHandControlIssue, ...]:
    issues = []
    expected_layers = {spec.path: spec for spec in plan.layers}
    actual_layers = {state.path: state for state in snapshot.layers}
    if (
        len(actual_layers) != len(snapshot.layers)
        or set(actual_layers) != set(expected_layers)
    ):
        issues.append(BodyHandControlIssue(
            "hand_pose_layer_set_mismatch",
            "Hand Pose 层集合不一致",
        ))
    for path in sorted(set(expected_layers) & set(actual_layers)):
        spec = expected_layers[path]
        state = actual_layers[path]
        if not (
            state.parent_path == spec.parent_path
            and _vector_matches(
                state.local_translation, (0.0, 0.0, 0.0), tolerance
            )
            and (
                not check_initial_pose
                or _vector_matches(
                    state.local_rotation, (0.0, 0.0, 0.0), tolerance
                )
            )
            and _vector_matches(
                state.local_scale, (1.0, 1.0, 1.0), tolerance
            )
        ):
            issues.append(BodyHandControlIssue(
                "hand_pose_layer_mismatch",
                "Hand Pose 层父级或中性通道不一致",
                path,
            ))
    expected_attributes = {spec.plug: spec for spec in plan.attributes}
    actual_attributes = {state.plug: state for state in snapshot.attributes}
    if (
        len(actual_attributes) != len(snapshot.attributes)
        or set(actual_attributes) != set(expected_attributes)
    ):
        issues.append(BodyHandControlIssue(
            "hand_pose_attribute_set_mismatch",
            "Hand 聚合姿态属性集合不一致",
        ))
    for plug in sorted(set(expected_attributes) & set(actual_attributes)):
        spec = expected_attributes[plug]
        state = actual_attributes[plug]
        if not (
            (not check_initial_pose or abs(state.value - spec.default) <= tolerance)
            and state.minimum is not None
            and abs(state.minimum - spec.minimum) <= tolerance
            and state.maximum is not None
            and abs(state.maximum - spec.maximum) <= tolerance
            and state.keyable
        ):
            issues.append(BodyHandControlIssue(
                "hand_pose_attribute_mismatch",
                "Hand 聚合姿态属性配置不一致",
                plug,
            ))

    expected_curls = {spec.node_name: spec for spec in plan.curls}
    actual_curls = {state.node_name: state for state in snapshot.curls}
    if (
        len(actual_curls) != len(snapshot.curls)
        or set(actual_curls) != set(expected_curls)
    ):
        issues.append(BodyHandControlIssue(
            "hand_curl_node_set_mismatch",
            "Hand curl 节点集合不一致",
        ))
    for name in sorted(set(expected_curls) & set(actual_curls)):
        spec = expected_curls[name]
        state = actual_curls[name]
        if not (
            state.node_type == "blendWeighted"
            and state.source_plugs == spec.source_plugs
            and _vector_matches(state.weights, spec.weights, tolerance)
            and state.destination_plug == spec.destination_plug
            and state.destination_source == f"{spec.node_name}.output"
        ):
            issues.append(BodyHandControlIssue(
                "hand_curl_wiring_mismatch",
                "Hand curl 聚合节点配置或连接不一致",
                name,
            ))

    expected_spreads = {spec.node_name: spec for spec in plan.spreads}
    actual_spreads = {state.node_name: state for state in snapshot.spreads}
    if (
        len(actual_spreads) != len(snapshot.spreads)
        or set(actual_spreads) != set(expected_spreads)
    ):
        issues.append(BodyHandControlIssue(
            "hand_spread_node_set_mismatch",
            "Hand spread 节点集合不一致",
        ))
    for name in sorted(set(expected_spreads) & set(actual_spreads)):
        spec = expected_spreads[name]
        state = actual_spreads[name]
        if not (
            state.node_type == "multDoubleLinear"
            and state.source_plug == spec.source_plug
            and abs(state.factor - spec.factor) <= tolerance
            and state.destination_plug == spec.destination_plug
            and state.destination_source == f"{spec.node_name}.output"
        ):
            issues.append(BodyHandControlIssue(
                "hand_spread_wiring_mismatch",
                "Hand spread 节点配置或连接不一致",
                name,
            ))
    return tuple(issues)


def audit_body_hand_fk_controls(
    plan: BodyHandFkControlPlan,
    snapshot: BodyHandFkControlSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyHandControlIssue, ...]:
    issues = []
    expected_roots = {root.path: root for root in plan.roots}
    actual_roots = {root.path: root for root in snapshot.roots}
    if (
        len(actual_roots) != len(snapshot.roots)
        or set(actual_roots) != set(expected_roots)
    ):
        issues.append(BodyHandControlIssue(
            "hand_root_set_mismatch",
            "Hand FK 根节点集合不一致",
        ))
    for path in sorted(set(expected_roots) & set(actual_roots)):
        spec = expected_roots[path]
        state = actual_roots[path]
        if state.parent_path != spec.parent_path:
            issues.append(BodyHandControlIssue(
                "hand_root_parent_mismatch",
                "Hand FK 根节点未挂在对应 Wrist 下",
                path,
            ))
        if not (
            _vector_matches(state.local_translation, (0.0, 0.0, 0.0), tolerance)
            and _vector_matches(state.local_rotation, (0.0, 0.0, 0.0), tolerance)
            and _vector_matches(state.local_scale, (1.0, 1.0, 1.0), tolerance)
        ):
            issues.append(BodyHandControlIssue(
                "hand_root_channels_mismatch",
                "Hand FK 根节点本地通道不中性",
                path,
            ))
        if check_initial_pose and not (
            _vector_matches(state.world_position, spec.world_position, tolerance)
            and _axes_match(state.world_axes, spec.world_axes, tolerance)
        ):
            issues.append(BodyHandControlIssue(
                "hand_root_pose_mismatch",
                "Hand FK 根节点世界帧与 Wrist 不一致",
                path,
            ))

    marker = "__body_hand_fk_control_set__"
    limb_issues = audit_body_limb_fk_controls(
        BodyLimbFkControlPlan(marker, marker, plan.controls),
        BodyLimbFkControlSnapshot(marker, snapshot.controls),
        limb_label="Hand",
        tolerance=tolerance,
        check_initial_pose=check_initial_pose,
    )
    issues.extend(limb_issues)
    return tuple(issues)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _axes_match(left: AxisFrame, right: AxisFrame, tolerance: float) -> bool:
    return all(
        _vector_matches(current, wanted, tolerance)
        for current, wanted in zip(left, right)
    )


def _namespace_prefix(namespace: str | None) -> str:
    if namespace is None:
        return ""
    if (
        not isinstance(namespace, str)
        or not namespace
        or namespace.startswith(":")
        or namespace.endswith(":")
        or "::" in namespace
        or any(character.isspace() for character in namespace)
        or any(character in namespace for character in "|.")
    ):
        raise BodyHandControlValidationError("Hand namespace 无效")
    return f"{namespace}:"


def _node_namespace(name: str) -> str | None:
    namespace, separator, _base = name.rpartition(":")
    return namespace if separator else None


def _base_node_name(name: str) -> str:
    return name.rsplit(":", 1)[-1]
