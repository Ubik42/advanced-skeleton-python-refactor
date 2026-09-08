from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.body_hand_controls import (
    BodyHandFkControlPlan,
    BodyHandFkControlSnapshot,
    BodyHandPosePlan,
    BodyHandPoseSnapshot,
    audit_body_hand_fk_controls,
    audit_body_hand_pose_controls,
    plan_body_hand_fk_controls,
    plan_body_hand_pose_controls,
)
from adv_py.core.body_hand_pose_io import (
    BodyHandPoseChangeSet,
    BodyHandPoseChannelSnapshot,
    BodyHandPoseDocument,
    audit_body_hand_pose_channels,
    body_hand_pose_changes,
    body_hand_pose_document_from_json,
    body_hand_pose_document_from_snapshot,
    body_hand_pose_document_to_json,
)
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyHandPoseDocumentHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_hand_fk_controls(
        self,
        plan: BodyHandFkControlPlan,
    ) -> BodyHandFkControlSnapshot: ...
    def capture_body_hand_pose(
        self,
        plan: BodyHandPosePlan,
    ) -> BodyHandPoseSnapshot: ...
    def capture_body_hand_pose_channels(
        self,
        hand: BodyHandFkControlPlan,
        pose: BodyHandPosePlan,
    ) -> BodyHandPoseChannelSnapshot: ...
    def apply_body_hand_pose_changes(
        self,
        changes: BodyHandPoseChangeSet,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BodyHandPoseRigInspection:
    body: BodySkeletonSnapshot
    hand: BodyHandFkControlPlan
    pose: BodyHandPosePlan
    hand_snapshot: BodyHandFkControlSnapshot
    pose_snapshot: BodyHandPoseSnapshot
    channels: BodyHandPoseChannelSnapshot


@dataclass(frozen=True, slots=True)
class BodyHandPoseExportPlan:
    destination: Path
    rig: BodyHandPoseRigInspection
    document: BodyHandPoseDocument


@dataclass(frozen=True, slots=True)
class BodyHandPoseExportResult:
    plan: BodyHandPoseExportPlan
    bytes_written: int


@dataclass(frozen=True, slots=True)
class BodyHandPoseImportPlan:
    source: Path
    document: BodyHandPoseDocument
    rig: BodyHandPoseRigInspection
    changes: BodyHandPoseChangeSet

    @property
    def changed_channel_count(self) -> int:
        return self.changes.changed_channel_count


@dataclass(frozen=True, slots=True)
class BodyHandPoseImportResult:
    plan: BodyHandPoseImportPlan
    rig: BodyHandPoseRigInspection

    @property
    def changed_channel_count(self) -> int:
        return self.plan.changed_channel_count


class InspectBodyHandPoseRig:
    """Validate the owned Maya Hand rig without requiring a neutral pose."""

    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._host = host

    def execute(
        self,
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        expected_joint_count: int = 70,
        control_radius: float = 0.3,
    ) -> BodyHandPoseRigInspection:
        body = self._host.capture_body_skeleton(body_root_name)
        provenance_issues = audit_body_provenance(
            oriented_body_provenance(source_container, expected_joint_count),
            body.provenance,
        )
        if provenance_issues:
            raise FitSkeletonValidationError(
                "Hand Pose 需要本工程拥有的完整 70 关节 Body："
                + "；".join(issue.message for issue in provenance_issues)
            )
        hand = plan_body_hand_fk_controls(body, radius=control_radius)
        pose = plan_body_hand_pose_controls(hand)
        hand_snapshot = self._host.capture_body_hand_fk_controls(hand)
        hand_issues = audit_body_hand_fk_controls(
            hand,
            hand_snapshot,
            check_initial_pose=False,
        )
        pose_snapshot = self._host.capture_body_hand_pose(pose)
        pose_issues = audit_body_hand_pose_controls(
            pose,
            pose_snapshot,
            check_initial_pose=False,
        )
        channels = self._host.capture_body_hand_pose_channels(hand, pose)
        channel_issues = audit_body_hand_pose_channels(hand, pose, channels)
        issues = hand_issues + pose_issues + channel_issues
        if issues:
            raise FitSkeletonValidationError(
                "Hand Pose 场景结构预检失败，场景未修改："
                + "；".join(
                    issue.message
                    + (f"：{issue.subject}" if issue.subject is not None else "")
                    for issue in issues
                )
            )
        return BodyHandPoseRigInspection(
            body,
            hand,
            pose,
            hand_snapshot,
            pose_snapshot,
            channels,
        )


class ExportBodyHandPose:
    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._inspector = InspectBodyHandPoseRig(host)

    def plan(
        self,
        destination: str | os.PathLike[str],
        **inspection_options,
    ) -> BodyHandPoseExportPlan:
        path = _json_path(destination)
        if not path.parent.is_dir():
            raise FitSkeletonValidationError("Hand Pose 导出目录不存在")
        if path.exists():
            raise FitSkeletonValidationError("Hand Pose 导出目标已存在，拒绝覆盖")
        rig = self._inspector.execute(**inspection_options)
        document = body_hand_pose_document_from_snapshot(rig.channels)
        return BodyHandPoseExportPlan(path, rig, document)

    def apply(
        self,
        destination: str | os.PathLike[str],
        **inspection_options,
    ) -> BodyHandPoseExportResult:
        plan = self.plan(destination, **inspection_options)
        text = body_hand_pose_document_to_json(plan.document)
        temporary = None
        try:
            handle, temporary = tempfile.mkstemp(
                prefix=f".{plan.destination.name}.",
                suffix=".tmp",
                dir=plan.destination.parent,
            )
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            written = Path(temporary).read_text(encoding="utf-8")
            if body_hand_pose_document_from_json(written) != plan.document:
                raise RuntimeError("Hand Pose 导出临时文件复检失败")
            if plan.destination.exists():
                raise FitSkeletonValidationError(
                    "Hand Pose 导出目标在写入前已出现"
                )
            os.replace(temporary, plan.destination)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        saved = plan.destination.read_text(encoding="utf-8")
        if body_hand_pose_document_from_json(saved) != plan.document:
            raise RuntimeError("Hand Pose 导出文件复检失败")
        return BodyHandPoseExportResult(plan, len(saved.encode("utf-8")))


class ImportBodyHandPose:
    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._host = host
        self._inspector = InspectBodyHandPoseRig(host)

    def plan(
        self,
        source: str | os.PathLike[str],
        **inspection_options,
    ) -> BodyHandPoseImportPlan:
        path = _json_path(source)
        if not path.is_file():
            raise FitSkeletonValidationError("Hand Pose 导入文件不存在")
        document = body_hand_pose_document_from_json(
            path.read_text(encoding="utf-8")
        )
        rig = self._inspector.execute(**inspection_options)
        changes = body_hand_pose_changes(document, rig.channels)
        return BodyHandPoseImportPlan(path, document, rig, changes)

    def apply(
        self,
        source: str | os.PathLike[str],
        **inspection_options,
    ) -> BodyHandPoseImportResult:
        plan = self.plan(source, **inspection_options)
        current_document = body_hand_pose_document_from_json(
            plan.source.read_text(encoding="utf-8")
        )
        if current_document != plan.document:
            raise FitSkeletonValidationError(
                "Hand Pose 导入文件在执行前发生变化"
            )
        current_rig = self._inspector.execute(**inspection_options)
        if current_rig != plan.rig:
            raise FitSkeletonValidationError(
                "Hand Pose 导入场景在执行前发生变化"
            )
        if plan.changed_channel_count == 0:
            return BodyHandPoseImportResult(plan, current_rig)

        with self._host.transaction("导入双手 Hand Pose"):
            transaction_document = body_hand_pose_document_from_json(
                plan.source.read_text(encoding="utf-8")
            )
            if transaction_document != plan.document:
                raise RuntimeError("Hand Pose 事务开始后导入文件发生变化")
            transaction_rig = self._inspector.execute(**inspection_options)
            if transaction_rig != plan.rig:
                raise RuntimeError("Hand Pose 事务开始后场景发生变化")
            self._host.apply_body_hand_pose_changes(plan.changes)
            result_rig = self._inspector.execute(**inspection_options)
            result_document = body_hand_pose_document_from_snapshot(
                result_rig.channels
            )
            if result_document != plan.document:
                raise RuntimeError("Hand Pose 导入后姿态复检失败")
        return BodyHandPoseImportResult(plan, result_rig)


def _json_path(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise FitSkeletonValidationError("Hand Pose 文件路径无效") from error
    if path.suffix.casefold() != ".json":
        raise FitSkeletonValidationError("Hand Pose 文件必须使用 .json 扩展名")
    return path
