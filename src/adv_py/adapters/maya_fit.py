from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Sequence

from adv_py.core.fit_metadata import (
    FitJointField,
    FitJointFieldEdit,
    FitJointMetadata,
    FitJointValidationError,
)
from adv_py.core.joint_labels import JointLabel


_MAYA_LABEL_NAMES = {
    0: "None",
    1: "Root",
    2: "Hip",
    3: "Knee",
    4: "Foot",
    5: "Toe",
    6: "Spine",
    7: "Neck",
    8: "Head",
    9: "Collar",
    10: "Shoulder",
    11: "Elbow",
    12: "Hand",
    13: "Finger",
    14: "Thumb",
    15: "PropA",
    16: "PropB",
    17: "PropC",
    18: "Other",
}
_MAYA_LABEL_TYPES = {name.casefold(): code for code, name in _MAYA_LABEL_NAMES.items()}


@dataclass(frozen=True, slots=True)
class _MayaFitAttribute:
    name: str
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    enum_names: tuple[str, ...] = ()


_FIT_ATTRIBUTES = {
    FitJointField.TWIST_JOINTS: _MayaFitAttribute("twistJoints", "long", 0),
    FitJointField.BENDY_CONTROLS: _MayaFitAttribute("bendyCtrls", "long", 0),
    FitJointField.INBETWEEN_JOINTS: _MayaFitAttribute("inbetweenJoints", "long", 0),
    FitJointField.UNTWISTER: _MayaFitAttribute("unTwister", "bool"),
    FitJointField.NO_MIRROR: _MayaFitAttribute("noMirror", "bool"),
    FitJointField.NO_MIRROR_LEFT: _MayaFitAttribute("noMirrorLeft", "bool"),
    FitJointField.CHILD_OF_PART: _MayaFitAttribute("childOfPart", "long", 1, 10),
    FitJointField.GLOBAL_WEIGHT: _MayaFitAttribute("global", "double", 0, 10),
    FitJointField.GLOBAL_TRANSLATE: _MayaFitAttribute("globalTranslate", "bool"),
    FitJointField.WORLD_ORIENT_UP: _MayaFitAttribute(
        "worldOrientUp",
        "enum",
        enum_names=("xUp", "yUp", "zUp", "xDown", "yDown", "zDown"),
    ),
    FitJointField.WORLD_ORIENT_FORWARD: _MayaFitAttribute(
        "worldOrientForward",
        "enum",
        enum_names=(
            "xForward",
            "yForward",
            "zForward",
            "xBackward",
            "yBackward",
            "zBackward",
            "free",
        ),
    ),
    FitJointField.IK_LOCAL_MODE: _MayaFitAttribute(
        "ikLocal",
        "enum",
        enum_names=("addCtrl", "nonZero", "localOrient"),
    ),
}


class MayaFitJointHost:
    """Maya adapter for explicit Fit joint queries and edits."""

    def __init__(self) -> None:
        from maya import cmds  # type: ignore[import-not-found]

        self._cmds = cmds
        self._transaction_active = False
        self._transaction_changed = False

    def resolve_joints(self, names: Sequence[str]) -> tuple[str, ...]:
        resolved: list[str] = []
        errors: list[str] = []
        for name in names:
            matches = self._cmds.ls(name, long=True) or []
            if not matches:
                errors.append(f"关节不存在：{name}")
                continue
            if len(matches) != 1:
                errors.append(f"关节名称不唯一：{name}")
                continue
            joint = matches[0]
            if self._cmds.nodeType(joint) != "joint":
                errors.append(f"节点不是 joint：{name}")
                continue
            resolved.append(joint)
        if errors:
            raise FitJointValidationError("；".join(errors))
        if len(resolved) != len(set(resolved)):
            raise FitJointValidationError("多个名称解析到了同一个关节")
        return tuple(resolved)

    def read_fit_joint_metadata(self, joint: str) -> FitJointMetadata:
        present = frozenset(
            field
            for field, spec in _FIT_ATTRIBUTES.items()
            if self._attribute_exists(joint, spec.name)
        )
        return FitJointMetadata(
            joint=joint,
            twist_joints=self._optional_number(joint, "twistJoints", int),
            bendy_controls=self._optional_number(joint, "bendyCtrls", int),
            inbetween_joints=self._optional_number(joint, "inbetweenJoints", int),
            untwister=self._optional_bool(joint, "unTwister"),
            no_mirror=self._optional_bool(joint, "noMirror"),
            no_mirror_left=self._optional_bool(joint, "noMirrorLeft"),
            child_of_part=self._optional_number(joint, "childOfPart", int),
            global_weight=self._optional_number(joint, "global", float),
            global_translate=self._optional_bool(joint, "globalTranslate"),
            world_orient_up=self._optional_enum(joint, "worldOrientUp"),
            world_orient_forward=self._optional_enum(joint, "worldOrientForward"),
            ik_local_mode=self._optional_enum(joint, "ikLocal"),
            present_fields=present,
        )

    def apply_fit_joint_edit(self, joint: str, edit: FitJointFieldEdit) -> None:
        self._require_transaction()
        spec = _FIT_ATTRIBUTES[edit.field]
        exists = self._attribute_exists(joint, spec.name)
        if edit.value is None:
            if exists:
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.{spec.name}")
            return

        if not exists:
            options = {
                "longName": spec.name,
                "attributeType": spec.kind,
                "keyable": True,
            }
            if spec.minimum is not None:
                options["minValue"] = spec.minimum
            if spec.maximum is not None:
                options["maxValue"] = spec.maximum
            if spec.enum_names:
                options["enumName"] = ":".join(spec.enum_names)
            self._transaction_changed = True
            self._cmds.addAttr(joint, **options)

        self._transaction_changed = True
        if spec.enum_names:
            value = spec.enum_names.index(str(edit.value))
        else:
            value = edit.value
        self._cmds.setAttr(f"{joint}.{spec.name}", value)

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        if self._transaction_active:
            raise RuntimeError("MayaFitJointHost 不支持嵌套事务")
        self._transaction_active = True
        self._transaction_changed = False
        self._cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            self._cmds.undoInfo(closeChunk=True)
            if self._transaction_changed:
                self._cmds.undo()
            raise
        else:
            self._cmds.undoInfo(closeChunk=True)
        finally:
            self._transaction_active = False
            self._transaction_changed = False

    def set_joint_label(self, joint: str, label: JointLabel) -> None:
        self._require_transaction()
        code = _MAYA_LABEL_TYPES.get(label.text.casefold(), 18)
        self._transaction_changed = True
        self._cmds.setAttr(f"{joint}.drawLabel", True)
        self._cmds.setAttr(f"{joint}.type", code)
        if code == 18:
            self._cmds.setAttr(f"{joint}.otherType", label.text, type="string")

    def clear_joint_label(self, joint: str) -> None:
        self._require_transaction()
        self._transaction_changed = True
        self._cmds.setAttr(f"{joint}.drawLabel", False)

    def read_joint_label(self, joint: str) -> JointLabel | None:
        if not self._cmds.getAttr(f"{joint}.drawLabel"):
            return None
        code = int(self._cmds.getAttr(f"{joint}.type"))
        if code == 18:
            text = self._cmds.getAttr(f"{joint}.otherType") or "Other"
        else:
            text = _MAYA_LABEL_NAMES.get(code)
            if text is None:
                raise RuntimeError(f"不支持的 Maya joint label type：{code}")
        return JointLabel.parse(text)

    def _attribute_exists(self, joint: str, attribute: str) -> bool:
        return bool(self._cmds.attributeQuery(attribute, node=joint, exists=True))

    def _optional_number(self, joint: str, attribute: str, cast):
        if not self._attribute_exists(joint, attribute):
            return None
        value = self._cmds.getAttr(f"{joint}.{attribute}")
        try:
            return cast(value)
        except (TypeError, ValueError) as error:
            raise FitJointValidationError(
                f"{joint}.{attribute} 不是有效数值：{value!r}"
            ) from error

    def _optional_bool(self, joint: str, attribute: str) -> bool:
        if not self._attribute_exists(joint, attribute):
            return False
        return bool(self._cmds.getAttr(f"{joint}.{attribute}"))

    def _optional_enum(self, joint: str, attribute: str) -> str | None:
        if not self._attribute_exists(joint, attribute):
            return None
        names = self._cmds.attributeQuery(attribute, node=joint, listEnum=True)
        if not names:
            raise FitJointValidationError(f"{joint}.{attribute} 不是 enum 属性")
        options = names[0].split(":")
        index = int(self._cmds.getAttr(f"{joint}.{attribute}"))
        if not 0 <= index < len(options):
            raise FitJointValidationError(
                f"{joint}.{attribute} 的 enum 值越界：{index}"
            )
        return options[index]

    def _require_transaction(self) -> None:
        if not self._transaction_active:
            raise RuntimeError("Fit joint 修改必须发生在事务内")


MayaJointLabelHost = MayaFitJointHost
