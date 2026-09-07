from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weight_io import (
    SkinWeightDocument,
    audit_skin_weight_document_target,
    skin_weight_document_from_json,
    skin_weight_document_from_state,
    skin_weight_document_to_json,
)
from adv_py.core.skin_weights import SkinWeightInputState

from .skin_weights import (
    EditSkinWeights,
    SkinWeightEditPlan,
    SkinWeightEditResult,
    SkinWeightHost,
)


class SkinWeightDocumentHost(SkinWeightHost, Protocol):
    def capture_all_skin_weights(
        self,
        skin_name: str,
        mesh_path: str,
    ) -> SkinWeightInputState: ...


@dataclass(frozen=True, slots=True)
class SkinWeightExportPlan:
    destination: Path
    document: SkinWeightDocument


@dataclass(frozen=True, slots=True)
class SkinWeightExportResult:
    plan: SkinWeightExportPlan
    bytes_written: int


@dataclass(frozen=True, slots=True)
class SkinWeightImportPlan:
    source: Path
    document: SkinWeightDocument
    target_state: SkinWeightInputState
    edit_plan: SkinWeightEditPlan

    @property
    def ready(self) -> bool:
        return self.edit_plan.ready


@dataclass(frozen=True, slots=True)
class SkinWeightImportResult:
    plan: SkinWeightImportPlan
    edit_result: SkinWeightEditResult


class ExportSkinWeights:
    def __init__(self, host: SkinWeightDocumentHost) -> None:
        self._host = host

    def plan(
        self,
        skin_name: str,
        mesh_path: str,
        destination: str | os.PathLike[str],
    ) -> SkinWeightExportPlan:
        path = _json_path(destination)
        if not path.parent.is_dir():
            raise FitSkeletonValidationError("权重导出目录不存在")
        if path.exists():
            raise FitSkeletonValidationError("权重导出目标已存在，拒绝覆盖")
        state = self._host.capture_all_skin_weights(skin_name, mesh_path)
        document = skin_weight_document_from_state(state)
        if document.skin_name != skin_name or document.mesh_path != mesh_path:
            raise FitSkeletonValidationError("权重导出目标与场景快照不一致")
        return SkinWeightExportPlan(path, document)

    def apply(
        self,
        skin_name: str,
        mesh_path: str,
        destination: str | os.PathLike[str],
    ) -> SkinWeightExportResult:
        plan = self.plan(skin_name, mesh_path, destination)
        text = skin_weight_document_to_json(plan.document)
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
            if skin_weight_document_from_json(written) != plan.document:
                raise RuntimeError("权重导出临时文件复检失败")
            if plan.destination.exists():
                raise FitSkeletonValidationError("权重导出目标在写入前已出现")
            os.replace(temporary, plan.destination)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        saved = plan.destination.read_text(encoding="utf-8")
        if skin_weight_document_from_json(saved) != plan.document:
            raise RuntimeError("权重导出文件复检失败")
        return SkinWeightExportResult(plan, len(saved.encode("utf-8")))


class ImportSkinWeights:
    def __init__(self, host: SkinWeightDocumentHost) -> None:
        self._host = host
        self._editor = EditSkinWeights(host)

    def plan(
        self,
        source: str | os.PathLike[str],
    ) -> SkinWeightImportPlan:
        path = _json_path(source)
        if not path.is_file():
            raise FitSkeletonValidationError("权重导入文件不存在")
        document = skin_weight_document_from_json(path.read_text(encoding="utf-8"))
        state = self._host.capture_all_skin_weights(
            document.skin_name,
            document.mesh_path,
        )
        issues = audit_skin_weight_document_target(document, state)
        if issues:
            raise FitSkeletonValidationError(
                "权重导入目标预检失败，场景未修改："
                + "；".join(issue.message for issue in issues)
            )
        edit_plan = self._editor.plan(
            document.skin_name,
            document.mesh_path,
            document.vertices,
        )
        return SkinWeightImportPlan(path, document, state, edit_plan)

    def apply(
        self,
        source: str | os.PathLike[str],
    ) -> SkinWeightImportResult:
        plan = self.plan(source)
        current_document = skin_weight_document_from_json(
            plan.source.read_text(encoding="utf-8")
        )
        if current_document != plan.document:
            raise FitSkeletonValidationError("权重导入文件在执行前发生变化")
        current_state = self._host.capture_all_skin_weights(
            plan.document.skin_name,
            plan.document.mesh_path,
        )
        if current_state != plan.target_state:
            raise FitSkeletonValidationError("权重导入场景在执行前发生变化")
        result = self._editor.apply(
            plan.document.skin_name,
            plan.document.mesh_path,
            plan.document.vertices,
        )
        return SkinWeightImportResult(plan, result)


def _json_path(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise FitSkeletonValidationError("权重文件路径无效") from error
    if path.suffix.casefold() != ".json":
        raise FitSkeletonValidationError("权重文件必须使用 .json 扩展名")
    return path
