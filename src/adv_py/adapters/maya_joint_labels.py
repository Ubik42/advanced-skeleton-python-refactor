from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Sequence

from adv_py.core.joint_labels import JointLabel, JointLabelValidationError


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


class MayaJointLabelHost:
    """Maya attribute adapter for the joint-label application use case."""

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
            raise JointLabelValidationError("；".join(errors))
        if len(resolved) != len(set(resolved)):
            raise JointLabelValidationError("多个名称解析到了同一个关节")
        return tuple(resolved)

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        if self._transaction_active:
            raise RuntimeError("MayaJointLabelHost 不支持嵌套事务")
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

    def _require_transaction(self) -> None:
        if not self._transaction_active:
            raise RuntimeError("关节标签修改必须发生在事务内")
