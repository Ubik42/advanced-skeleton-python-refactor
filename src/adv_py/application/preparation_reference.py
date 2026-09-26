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


class PreparationReferenceHost(Protocol):
    def reference_model(self, source: Path) -> ModelReferenceResult: ...


class ReferencePreparationModel:
    def __init__(self, host: PreparationReferenceHost):
        self.host = host

    def execute(self, source: Path) -> ModelReferenceResult:
        source = Path(source).expanduser().resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in {".ma", ".mb"}:
            raise ValueError("模型文件必须是现有的 Maya .ma 或 .mb 场景")
        return self.host.reference_model(source)
