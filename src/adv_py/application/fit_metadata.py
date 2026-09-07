from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, Sequence

from adv_py.core.fit_metadata import (
    FitJointIssue,
    FitJointField,
    FitJointFieldEdit,
    FitJointMetadata,
    FitJointPatch,
    FitJointValidationError,
    audit_fit_joint,
    fit_joint_value,
    predict_fit_joint_metadata,
)


class FitJointMetadataReader(Protocol):
    def resolve_joints(self, names: Sequence[str]) -> tuple[str, ...]: ...

    def read_fit_joint_metadata(self, joint: str) -> FitJointMetadata: ...


class FitJointMetadataHost(FitJointMetadataReader, Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def apply_fit_joint_edit(self, joint: str, edit: FitJointFieldEdit) -> None: ...


@dataclass(frozen=True, slots=True)
class FitJointAudit:
    joints: tuple[FitJointMetadata, ...]
    issues: tuple[FitJointIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


class InspectFitJoints:
    """Read all requested joints first, then audit portable relationships."""

    def __init__(self, host: FitJointMetadataReader) -> None:
        self._host = host

    def execute(self, joints: Sequence[str]) -> FitJointAudit:
        names = tuple(joints)
        if not names:
            raise FitJointValidationError("至少需要一个 Fit joint")
        if any(not name.strip() for name in names):
            raise FitJointValidationError("Fit joint 名称不能为空")
        if len(names) != len(set(names)):
            raise FitJointValidationError("Fit joint 列表不能包含重复项")

        resolved = self._host.resolve_joints(names)
        metadata = tuple(
            self._host.read_fit_joint_metadata(joint) for joint in resolved
        )
        issues = tuple(
            issue for item in metadata for issue in audit_fit_joint(item)
        )
        return FitJointAudit(joints=metadata, issues=issues)


@dataclass(frozen=True, slots=True)
class FitJointChange:
    joint: str
    field: FitJointField
    previous_present: bool
    previous_value: object
    desired_present: bool
    desired_value: object


@dataclass(frozen=True, slots=True)
class FitJointChangePlan:
    before: tuple[FitJointMetadata, ...]
    after: tuple[FitJointMetadata, ...]
    changes: tuple[FitJointChange, ...]


@dataclass(frozen=True, slots=True)
class FitJointEditResult:
    plan: FitJointChangePlan
    verified: tuple[FitJointMetadata, ...]


class EditFitJointMetadata:
    """Preview and atomically apply a portable Fit joint metadata patch."""

    def __init__(self, host: FitJointMetadataHost) -> None:
        self._host = host
        self._inspector = InspectFitJoints(host)

    def plan(
        self, joints: Sequence[str], patch: FitJointPatch
    ) -> FitJointChangePlan:
        before_audit = self._inspector.execute(joints)
        after = tuple(
            predict_fit_joint_metadata(item, patch) for item in before_audit.joints
        )
        issues = tuple(item for metadata in after for item in audit_fit_joint(metadata))
        if issues:
            messages = "；".join(f"{issue.joint}: {issue.message}" for issue in issues)
            raise FitJointValidationError(f"变更后的 Fit joint 配置无效：{messages}")

        changes: list[FitJointChange] = []
        for previous, desired in zip(before_audit.joints, after):
            for edit in patch.edits:
                previous_present = edit.field in previous.present_fields
                desired_present = edit.field in desired.present_fields
                previous_value = fit_joint_value(previous, edit.field)
                desired_value = fit_joint_value(desired, edit.field)
                if (
                    previous_present != desired_present
                    or previous_value != desired_value
                ):
                    changes.append(
                        FitJointChange(
                            joint=previous.joint,
                            field=edit.field,
                            previous_present=previous_present,
                            previous_value=previous_value,
                            desired_present=desired_present,
                            desired_value=desired_value,
                        )
                    )
        return FitJointChangePlan(
            before=before_audit.joints,
            after=after,
            changes=tuple(changes),
        )

    def apply(
        self, joints: Sequence[str], patch: FitJointPatch
    ) -> FitJointEditResult:
        plan = self.plan(joints, patch)
        if not plan.changes:
            return FitJointEditResult(plan=plan, verified=plan.before)

        edits = {edit.field: edit for edit in patch.edits}
        with self._host.transaction(f"更新 {len(plan.before)} 个 Fit joint"):
            for change in plan.changes:
                self._host.apply_fit_joint_edit(change.joint, edits[change.field])
            verified = tuple(
                self._host.read_fit_joint_metadata(item.joint) for item in plan.after
            )
            self._verify(plan.after, verified, patch)
        return FitJointEditResult(plan=plan, verified=verified)

    @staticmethod
    def _verify(
        expected: tuple[FitJointMetadata, ...],
        actual: tuple[FitJointMetadata, ...],
        patch: FitJointPatch,
    ) -> None:
        if len(expected) != len(actual):
            raise RuntimeError("Fit joint 构建后复检失败：返回关节数量不一致")
        for wanted, found in zip(expected, actual):
            issues = audit_fit_joint(found)
            if issues:
                raise RuntimeError(
                    "Fit joint 构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            for edit in patch.edits:
                wanted_present = edit.field in wanted.present_fields
                found_present = edit.field in found.present_fields
                if wanted_present != found_present or fit_joint_value(
                    wanted, edit.field
                ) != fit_joint_value(found, edit.field):
                    raise RuntimeError(
                        f"Fit joint 构建后复检失败：{found.joint}.{edit.field.value}"
                    )
