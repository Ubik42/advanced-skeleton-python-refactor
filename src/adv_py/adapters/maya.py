from __future__ import annotations

from dataclasses import dataclass
import importlib.util


@dataclass(frozen=True, slots=True)
class MayaAdapterStatus:
    """Discovery surface for the future Maya implementation of RigHost."""

    available: bool
    implementation: str = "planned"
    responsibility: str = "DAG、joint、constraint、Undo Chunk 与场景复检"

    @classmethod
    def detect(cls) -> "MayaAdapterStatus":
        return cls(available=importlib.util.find_spec("maya") is not None)

