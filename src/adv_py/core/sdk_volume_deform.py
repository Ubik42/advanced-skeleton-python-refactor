"""Portable build request for a pose-driven auxiliary Skin influence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SdkVolumeSpec:
    name: str
    path: str
    parent: str
    driver_name: str
    guide: Mapping[str, object]
