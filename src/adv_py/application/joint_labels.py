from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, Sequence

from adv_py.core.joint_labels import JointLabel, JointLabelValidationError


class JointLabelHost(Protocol):
    def resolve_joints(self, names: Sequence[str]) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def set_joint_label(self, joint: str, label: JointLabel) -> None: ...

    def clear_joint_label(self, joint: str) -> None: ...

    def read_joint_label(self, joint: str) -> JointLabel | None: ...


@dataclass(frozen=True, slots=True)
class JointLabelResult:
    joints: tuple[str, ...]
    label: JointLabel | None


class EditJointLabels:
    """Explicit joint-label use cases with preflight before mutation."""

    def __init__(self, host: JointLabelHost) -> None:
        self._host = host

    def apply(self, joints: Sequence[str], label: str) -> JointLabelResult:
        parsed = JointLabel.parse(label)
        resolved = self._preflight(joints)
        with self._host.transaction(f"设置 {len(resolved)} 个关节标签"):
            for joint in resolved:
                self._host.set_joint_label(joint, parsed)
        return JointLabelResult(joints=resolved, label=parsed)

    def clear(self, joints: Sequence[str]) -> JointLabelResult:
        resolved = self._preflight(joints)
        with self._host.transaction(f"隐藏 {len(resolved)} 个关节标签"):
            for joint in resolved:
                self._host.clear_joint_label(joint)
        return JointLabelResult(joints=resolved, label=None)

    def read(self, joint: str) -> JointLabel | None:
        resolved = self._preflight((joint,))
        return self._host.read_joint_label(resolved[0])

    def _preflight(self, joints: Sequence[str]) -> tuple[str, ...]:
        names = tuple(joints)
        if not names:
            raise JointLabelValidationError("至少需要一个关节")
        if any(not name.strip() for name in names):
            raise JointLabelValidationError("关节名称不能为空")
        if len(names) != len(set(names)):
            raise JointLabelValidationError("关节列表不能包含重复项")
        return self._host.resolve_joints(names)
