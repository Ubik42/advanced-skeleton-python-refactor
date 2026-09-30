"""Captured scope for deleting a generated Body rig without its Fit source."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BodyDeletePlan:
    fit: str
    fit_id: str
    group: str | None
    geometry_children: tuple[str, ...]
    retained_geometry_ids: tuple[str, ...]
    preserved_animation_ids: tuple[str, ...]
    owned_nodes: tuple[str, ...]
    owned_ids: tuple[str, ...]
    set_nodes: tuple[str, ...]
    scene_up_axis: str
    face_fit_group: str | None = None
    face_fit_group_id: str | None = None
    retained_nested_geometry_paths: tuple[str, ...] = ()
    retained_nested_geometry_ids: tuple[str, ...] = ()
