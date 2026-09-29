"""Captured ownership boundary for removing a generated FaceSetup graph."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FaceDeleteSkin:
    path: str
    identifier: str
    face_influences: tuple[str, ...]
    face_influence_ids: tuple[str, ...]
    add_head_before_removal: bool
    geometry: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FaceDeletePlan:
    motion: str
    motion_id: str
    face_set: str
    face_set_id: str
    fit: str
    fit_id: str
    head: str
    head_id: str
    owned_paths: tuple[str, ...]
    owned_ids: tuple[str, ...]
    skins: tuple[FaceDeleteSkin, ...]
    extra_nodes: tuple[str, ...]
    extra_ids: tuple[str, ...]
    keep_build_pose: bool = False
