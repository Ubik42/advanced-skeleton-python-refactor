from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointValidationError


class JointLabelValidationError(FitJointValidationError):
    """Raised before a host scene is modified."""


@dataclass(frozen=True, slots=True)
class JointLabel:
    """A host-independent, user-facing joint label."""

    text: str

    @classmethod
    def parse(cls, value: str) -> "JointLabel":
        text = value.strip()
        if not text:
            raise JointLabelValidationError("关节标签不能为空")
        if "\x00" in text or "\n" in text or "\r" in text:
            raise JointLabelValidationError("关节标签不能包含换行或空字符")
        return cls(text=text)
