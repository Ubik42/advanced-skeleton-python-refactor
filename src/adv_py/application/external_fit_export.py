"""Export a portable Fit document from a compatible external Maya rig."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_settings import FitSkeletonSettings, FitSkeletonValidationError
from adv_py.core.fit_skeleton_io import (
    FIT_SKELETON_DOCUMENT_SUFFIX, FitSkeletonDocument,
    fit_skeleton_document_from_json, fit_skeleton_document_from_snapshot,
    fit_skeleton_document_to_json,
)
from adv_py.core.joint_labels import JointLabel


class ExternalFitExportHost(Protocol):
    def capture_fit_orientation(self, container: str) -> FitOrientationSnapshot: ...
    def read_fit_skeleton_settings(self, container: str) -> FitSkeletonSettings: ...
    def read_joint_label(self, joint: str) -> JointLabel | None: ...


@dataclass(frozen=True, slots=True)
class ExternalFitExportPlan:
    destination: Path
    document: FitSkeletonDocument
    inferred_labels: tuple[str, ...]


class ExportExternalFitSkeleton:
    """Accept a nested original container and infer missing labels in the file."""

    def __init__(self, host: ExternalFitExportHost) -> None:
        self._host = host

    def plan(self, destination: str | os.PathLike[str],
             container: str = "FitSkeleton") -> ExternalFitExportPlan:
        path = Path(destination).expanduser().resolve()
        if not str(path).casefold().endswith(
                FIT_SKELETON_DOCUMENT_SUFFIX.casefold()):
            raise FitSkeletonValidationError("目标文件必须使用 .fit.json 扩展名")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise FitSkeletonValidationError("Fit 导出目录不存在或是符号链接")
        if path.exists() or path.is_symlink():
            raise FitSkeletonValidationError("Fit 导出目标已存在，拒绝覆盖")
        snapshot = self._host.capture_fit_orientation(container)
        settings = self._host.read_fit_skeleton_settings(
            snapshot.hierarchy.container)
        labels = []
        inferred = []
        for node in snapshot.hierarchy.joints:
            label = self._host.read_joint_label(node.path)
            if label is None:
                label = JointLabel.parse(node.short_name)
                inferred.append(node.path)
            labels.append((node.path, label))
        document = fit_skeleton_document_from_snapshot(
            snapshot, settings, tuple(labels))
        return ExternalFitExportPlan(path, document, tuple(inferred))

    def apply(self, destination: str | os.PathLike[str],
              container: str = "FitSkeleton") -> ExternalFitExportPlan:
        plan = self.plan(destination, container)
        content = fit_skeleton_document_to_json(plan.document)
        temporary = None
        try:
            handle, temporary = tempfile.mkstemp(
                prefix=f".{plan.destination.name}.", suffix=".tmp",
                dir=plan.destination.parent)
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if fit_skeleton_document_from_json(
                    Path(temporary).read_text(encoding="utf-8")) != plan.document:
                raise RuntimeError("外部 Fit 导出临时文件复检失败")
            try:
                os.link(temporary, plan.destination)
            except FileExistsError as error:
                raise FitSkeletonValidationError("Fit 导出目标已存在，拒绝覆盖") from error
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        if fit_skeleton_document_from_json(
                plan.destination.read_text(encoding="utf-8")) != plan.document:
            raise RuntimeError("外部 Fit 导出文件复检失败")
        return plan
