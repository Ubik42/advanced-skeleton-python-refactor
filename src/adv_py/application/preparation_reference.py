"""Preparation: reference a saved model into the current rig scene."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelReferenceResult:
    source: Path
    namespace: str
    reference_node: str
    top_nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelReferenceInfo:
    source: Path
    namespace: str
    reference_node: str
    top_nodes: tuple[str, ...]


class PreparationReferenceHost(Protocol):
    def reference_model(self, source: Path) -> ModelReferenceResult: ...
    def inspect_model_reference(self, namespace: str) -> ModelReferenceInfo: ...
    def reload_model_reference(self, info: ModelReferenceInfo) -> ModelReferenceInfo: ...
    def replace_model_reference(self, info: ModelReferenceInfo,
                                source: Path) -> ModelReferenceInfo: ...
    def remove_model_reference(self, info: ModelReferenceInfo) -> None: ...


class ReferencePreparationModel:
    def __init__(self, host: PreparationReferenceHost):
        self.host = host

    def execute(self, source: Path) -> ModelReferenceResult:
        source = Path(source).expanduser().resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in {".ma", ".mb"}:
            raise ValueError("模型文件必须是现有的 Maya .ma 或 .mb 场景")
        return self.host.reference_model(source)


class ManagePreparationModelReference:
    def __init__(self, host: PreparationReferenceHost):
        self.host = host

    def reload(self, namespace: str) -> ModelReferenceInfo:
        info = self.host.inspect_model_reference(namespace)
        return self.host.reload_model_reference(info)

    def replace(self, namespace: str, source: Path) -> ModelReferenceInfo:
        source = Path(source).expanduser().resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in {".ma", ".mb"}:
            raise ValueError("替换模型必须是现有的 Maya .ma 或 .mb 场景")
        info = self.host.inspect_model_reference(namespace)
        if source == info.source:
            return self.host.reload_model_reference(info)
        return self.host.replace_model_reference(info, source)

    def remove(self, namespace: str) -> ModelReferenceInfo:
        info = self.host.inspect_model_reference(namespace)
        self.host.remove_model_reference(info)
        return info
