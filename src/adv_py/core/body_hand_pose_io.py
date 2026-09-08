from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import isfinite

from .body_hand_controls import (
    BodyHandControlIssue,
    BodyHandFkControlPlan,
    BodyHandPosePlan,
)
from .body_hand_fit import BODY_HAND_DIGITS, BodyHandDigit
from .fit_hierarchy import TRANSLATION_AXES
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]

BODY_HAND_POSE_DOCUMENT_FORMAT = "adv_py_body_hand_pose"
BODY_HAND_POSE_DOCUMENT_SCHEMA_VERSION = 1
BODY_HAND_POSE_AGGREGATE_RANGES = (
    ("handCurl", -90.0, 90.0),
    *((f"{digit.value.lower()}Curl", -45.0, 45.0)
      for digit in BODY_HAND_DIGITS),
    ("handSpread", -30.0, 30.0),
)
BODY_HAND_POSE_FK_SEGMENTS = ("1", "2", "3")


class BodyHandPoseDocumentValidationError(ValueError):
    """Raised when a semantic Hand Pose document is unsafe to use."""


@dataclass(frozen=True, slots=True)
class BodyHandAggregatePoseValue:
    side: FitBuildSide
    name: str
    value: float


@dataclass(frozen=True, slots=True)
class BodyHandFkPoseValue:
    side: FitBuildSide
    digit: BodyHandDigit
    segment: str
    rotation: Vector3


@dataclass(frozen=True, slots=True)
class BodyHandPoseDocument:
    aggregates: tuple[BodyHandAggregatePoseValue, ...]
    controls: tuple[BodyHandFkPoseValue, ...]
    content_sha256: str
    schema_version: int = BODY_HAND_POSE_DOCUMENT_SCHEMA_VERSION
    format_name: str = BODY_HAND_POSE_DOCUMENT_FORMAT


@dataclass(frozen=True, slots=True)
class BodyHandAggregatePoseChannelState:
    side: FitBuildSide
    name: str
    plug: str
    value: float
    minimum: float | None
    maximum: float | None
    writable: bool
    incoming_source: str | None


@dataclass(frozen=True, slots=True)
class BodyHandFkPoseChannelState:
    side: FitBuildSide
    digit: BodyHandDigit
    segment: str
    control_path: str
    rotation: Vector3
    writable_rotation_axes: frozenset[str]
    rotation_sources: tuple[str | None, str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyHandPoseChannelSnapshot:
    aggregates: tuple[BodyHandAggregatePoseChannelState, ...]
    controls: tuple[BodyHandFkPoseChannelState, ...]


@dataclass(frozen=True, slots=True)
class BodyHandAggregatePoseChange:
    side: FitBuildSide
    name: str
    plug: str
    before: float
    after: float


@dataclass(frozen=True, slots=True)
class BodyHandFkPoseChange:
    side: FitBuildSide
    digit: BodyHandDigit
    segment: str
    control_path: str
    before: Vector3
    after: Vector3


@dataclass(frozen=True, slots=True)
class BodyHandPoseChangeSet:
    aggregates: tuple[BodyHandAggregatePoseChange, ...]
    controls: tuple[BodyHandFkPoseChange, ...]

    @property
    def changed_channel_count(self) -> int:
        return len(self.aggregates) + len(self.controls)


def body_hand_pose_document_from_snapshot(
    snapshot: BodyHandPoseChannelSnapshot,
) -> BodyHandPoseDocument:
    aggregate_states = _unique_by_key(
        snapshot.aggregates,
        lambda item: (item.side, item.name),
        "Hand Pose 聚合通道",
    )
    control_states = _unique_by_key(
        snapshot.controls,
        lambda item: (item.side, item.digit, item.segment),
        "Hand Pose FK 通道",
    )
    expected_aggregates = _expected_aggregate_keys()
    expected_controls = _expected_control_keys()
    if set(aggregate_states) != set(expected_aggregates):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 文档需要完整双侧聚合通道"
        )
    if set(control_states) != set(expected_controls):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 文档需要完整双侧五指 FK 通道"
        )
    aggregates = tuple(
        BodyHandAggregatePoseValue(side, name, aggregate_states[(side, name)].value)
        for side, name in expected_aggregates
    )
    controls = tuple(
        BodyHandFkPoseValue(
            side,
            digit,
            segment,
            control_states[(side, digit, segment)].rotation,
        )
        for side, digit, segment in expected_controls
    )
    return _make_document(aggregates, controls)


def body_hand_pose_document_to_json(document: BodyHandPoseDocument) -> str:
    _validate_document(document)
    return json.dumps(
        {**_document_payload(document), "content_sha256": document.content_sha256},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def body_hand_pose_document_from_json(text: str) -> BodyHandPoseDocument:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 文件不是有效 JSON"
        ) from error
    _require_object(
        data,
        {
            "format",
            "schema_version",
            "aggregates",
            "controls",
            "content_sha256",
        },
        "Hand Pose 文档根对象",
    )
    if data["format"] != BODY_HAND_POSE_DOCUMENT_FORMAT:
        raise BodyHandPoseDocumentValidationError("不支持的 Hand Pose 文档格式")
    if (
        isinstance(data["schema_version"], bool)
        or not isinstance(data["schema_version"], int)
        or data["schema_version"] != BODY_HAND_POSE_DOCUMENT_SCHEMA_VERSION
    ):
        raise BodyHandPoseDocumentValidationError(
            "不支持的 Hand Pose schema 版本"
        )
    if not isinstance(data["aggregates"], list):
        raise BodyHandPoseDocumentValidationError("Hand Pose aggregates 必须是数组")
    if not isinstance(data["controls"], list):
        raise BodyHandPoseDocumentValidationError("Hand Pose controls 必须是数组")
    aggregates = []
    for item in data["aggregates"]:
        _require_object(item, {"side", "name", "value"}, "Hand Pose 聚合值")
        aggregates.append(BodyHandAggregatePoseValue(
            _parse_side(item["side"]),
            _require_string(item["name"], "Hand Pose 聚合名称"),
            _finite_number(item["value"], "Hand Pose 聚合值"),
        ))
    controls = []
    for item in data["controls"]:
        _require_object(
            item,
            {"side", "digit", "segment", "rotation"},
            "Hand Pose FK 值",
        )
        rotation = item["rotation"]
        if not isinstance(rotation, list) or len(rotation) != 3:
            raise BodyHandPoseDocumentValidationError(
                "Hand Pose FK rotation 必须是三个有限数值"
            )
        controls.append(BodyHandFkPoseValue(
            _parse_side(item["side"]),
            _parse_digit(item["digit"]),
            _require_string(item["segment"], "Hand Pose FK segment"),
            tuple(
                _finite_number(value, "Hand Pose FK rotation")
                for value in rotation
            ),
        ))
    document = _make_document(tuple(aggregates), tuple(controls))
    if (
        not isinstance(data["content_sha256"], str)
        or data["content_sha256"] != document.content_sha256
    ):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 文档内容摘要不匹配"
        )
    return document


def audit_body_hand_pose_channels(
    hand: BodyHandFkControlPlan,
    pose: BodyHandPosePlan,
    snapshot: BodyHandPoseChannelSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyHandControlIssue, ...]:
    issues = []
    expected_attributes = {
        (spec.side, spec.name): spec for spec in pose.attributes
    }
    actual_attributes = _issue_safe_unique(
        snapshot.aggregates,
        lambda item: (item.side, item.name),
    )
    if (
        len(actual_attributes) != len(snapshot.aggregates)
        or set(actual_attributes) != set(expected_attributes)
    ):
        issues.append(BodyHandControlIssue(
            "hand_pose_io_aggregate_set_mismatch",
            "Hand Pose 聚合通道集合不一致",
        ))
    for key in sorted(set(expected_attributes) & set(actual_attributes), key=_key_sort):
        spec = expected_attributes[key]
        state = actual_attributes[key]
        if not (
            state.plug == spec.plug
            and _is_finite_number(state.value)
            and spec.minimum - tolerance <= state.value <= spec.maximum + tolerance
            and state.minimum is not None
            and abs(state.minimum - spec.minimum) <= tolerance
            and state.maximum is not None
            and abs(state.maximum - spec.maximum) <= tolerance
            and state.writable
            and state.incoming_source is None
        ):
            issues.append(BodyHandControlIssue(
                "hand_pose_io_aggregate_unsafe",
                "Hand Pose 聚合通道配置、范围或可写性无效",
                spec.plug,
            ))

    expected_controls = _control_spec_by_key(hand)
    actual_controls = _issue_safe_unique(
        snapshot.controls,
        lambda item: (item.side, item.digit, item.segment),
    )
    if (
        len(actual_controls) != len(snapshot.controls)
        or set(actual_controls) != set(expected_controls)
    ):
        issues.append(BodyHandControlIssue(
            "hand_pose_io_fk_set_mismatch",
            "Hand Pose FK 通道集合不一致",
        ))
    for key in sorted(set(expected_controls) & set(actual_controls), key=_key_sort):
        spec = expected_controls[key]
        state = actual_controls[key]
        if not (
            state.control_path == spec.control_path
            and _is_vector3(state.rotation)
            and state.writable_rotation_axes == TRANSLATION_AXES
            and not any(source is not None for source in state.rotation_sources)
        ):
            issues.append(BodyHandControlIssue(
                "hand_pose_io_fk_unsafe",
                "Hand Pose FK rotate 通道不可完整安全写入",
                spec.control_path,
            ))
    return tuple(issues)


def body_hand_pose_changes(
    document: BodyHandPoseDocument,
    snapshot: BodyHandPoseChannelSnapshot,
    *,
    tolerance: float = 1e-6,
) -> BodyHandPoseChangeSet:
    _validate_document(document)
    aggregates = _unique_by_key(
        snapshot.aggregates,
        lambda item: (item.side, item.name),
        "Hand Pose 目标聚合通道",
    )
    controls = _unique_by_key(
        snapshot.controls,
        lambda item: (item.side, item.digit, item.segment),
        "Hand Pose 目标 FK 通道",
    )
    if set(aggregates) != set(_expected_aggregate_keys()):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 目标聚合通道集合不完整"
        )
    if set(controls) != set(_expected_control_keys()):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 目标 FK 通道集合不完整"
        )
    aggregate_changes = []
    for target in document.aggregates:
        state = aggregates.get((target.side, target.name))
        if state is None:
            raise BodyHandPoseDocumentValidationError(
                "Hand Pose 目标缺少聚合通道"
            )
        if abs(state.value - target.value) > tolerance:
            aggregate_changes.append(BodyHandAggregatePoseChange(
                target.side,
                target.name,
                state.plug,
                state.value,
                target.value,
            ))
    control_changes = []
    for target in document.controls:
        state = controls.get((target.side, target.digit, target.segment))
        if state is None:
            raise BodyHandPoseDocumentValidationError(
                "Hand Pose 目标缺少 FK 通道"
            )
        if not _vectors_match(state.rotation, target.rotation, tolerance):
            control_changes.append(BodyHandFkPoseChange(
                target.side,
                target.digit,
                target.segment,
                state.control_path,
                state.rotation,
                target.rotation,
            ))
    return BodyHandPoseChangeSet(tuple(aggregate_changes), tuple(control_changes))


def _make_document(
    aggregates: tuple[BodyHandAggregatePoseValue, ...],
    controls: tuple[BodyHandFkPoseValue, ...],
) -> BodyHandPoseDocument:
    document = BodyHandPoseDocument(aggregates, controls, "")
    _validate_document(document, check_digest=False)
    return replace(document, content_sha256=_document_digest(document))


def _validate_document(
    document: BodyHandPoseDocument,
    *,
    check_digest: bool = True,
) -> None:
    if document.format_name != BODY_HAND_POSE_DOCUMENT_FORMAT:
        raise BodyHandPoseDocumentValidationError("不支持的 Hand Pose 文档格式")
    if document.schema_version != BODY_HAND_POSE_DOCUMENT_SCHEMA_VERSION:
        raise BodyHandPoseDocumentValidationError(
            "不支持的 Hand Pose schema 版本"
        )
    if tuple((item.side, item.name) for item in document.aggregates) != (
        _expected_aggregate_keys()
    ):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose 聚合通道集合或顺序无效"
        )
    ranges = {
        name: (minimum, maximum)
        for name, minimum, maximum in BODY_HAND_POSE_AGGREGATE_RANGES
    }
    for item in document.aggregates:
        if not _is_finite_number(item.value):
            raise BodyHandPoseDocumentValidationError(
                "Hand Pose 聚合值必须是有限数值"
            )
        minimum, maximum = ranges[item.name]
        if not minimum <= item.value <= maximum:
            raise BodyHandPoseDocumentValidationError(
                f"Hand Pose 聚合值超出范围：{item.side.value}.{item.name}"
            )
    if tuple(
        (item.side, item.digit, item.segment) for item in document.controls
    ) != _expected_control_keys():
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose FK 通道集合或顺序无效"
        )
    if any(not _is_vector3(item.rotation) for item in document.controls):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose FK rotation 必须是三个有限数值"
        )
    if check_digest and document.content_sha256 != _document_digest(document):
        raise BodyHandPoseDocumentValidationError("Hand Pose 文档内容摘要无效")


def _control_spec_by_key(hand: BodyHandFkControlPlan) -> dict:
    by_name = {spec.control_name: spec for spec in hand.controls}
    if len(by_name) != len(hand.controls):
        return {}
    values = {}
    for side, digit, segment in _expected_control_keys():
        name = f"AdvPy_{digit.value}{segment}FK_{side.value}"
        spec = by_name.get(name)
        if spec is not None and spec.side is side:
            values[(side, digit, segment)] = spec
    return values


def _expected_aggregate_keys() -> tuple[tuple[FitBuildSide, str], ...]:
    return tuple(
        (side, name)
        for side in (FitBuildSide.RIGHT, FitBuildSide.LEFT)
        for name, _minimum, _maximum in BODY_HAND_POSE_AGGREGATE_RANGES
    )


def _expected_control_keys(
) -> tuple[tuple[FitBuildSide, BodyHandDigit, str], ...]:
    return tuple(
        (side, digit, segment)
        for side in (FitBuildSide.RIGHT, FitBuildSide.LEFT)
        for digit in BODY_HAND_DIGITS
        for segment in BODY_HAND_POSE_FK_SEGMENTS
    )


def _document_payload(document: BodyHandPoseDocument) -> dict:
    return {
        "format": document.format_name,
        "schema_version": document.schema_version,
        "aggregates": [
            {"side": item.side.value, "name": item.name, "value": item.value}
            for item in document.aggregates
        ],
        "controls": [
            {
                "side": item.side.value,
                "digit": item.digit.value,
                "segment": item.segment,
                "rotation": list(item.rotation),
            }
            for item in document.controls
        ],
    }


def _document_digest(document: BodyHandPoseDocument) -> str:
    encoded = json.dumps(
        _document_payload(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _require_object(value, expected_keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise BodyHandPoseDocumentValidationError(f"{label}字段集合无效")


def _require_string(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BodyHandPoseDocumentValidationError(f"{label}无效")
    return value


def _parse_side(value) -> FitBuildSide:
    try:
        side = FitBuildSide(value)
    except (TypeError, ValueError) as error:
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose side 必须是 R 或 L"
        ) from error
    if side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose side 必须是 R 或 L"
        )
    return side


def _parse_digit(value) -> BodyHandDigit:
    try:
        return BodyHandDigit(value)
    except (TypeError, ValueError) as error:
        raise BodyHandPoseDocumentValidationError(
            "Hand Pose digit 无效"
        ) from error


def _finite_number(value, label: str) -> float:
    if not _is_finite_number(value):
        raise BodyHandPoseDocumentValidationError(f"{label}必须是有限数值")
    return float(value)


def _is_finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(float(value))
    )


def _is_vector3(value) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and all(_is_finite_number(item) for item in value)
    )


def _vectors_match(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _unique_by_key(values, key, label: str) -> dict:
    result = _issue_safe_unique(values, key)
    if len(result) != len(values):
        raise BodyHandPoseDocumentValidationError(f"{label}包含重复语义键")
    return result


def _issue_safe_unique(values, key) -> dict:
    return {key(item): item for item in values}


def _key_sort(value) -> tuple[str, ...]:
    return tuple(item.value if hasattr(item, "value") else str(item) for item in value)
