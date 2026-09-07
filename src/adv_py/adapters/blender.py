from __future__ import annotations

from dataclasses import dataclass
import importlib.util


@dataclass(frozen=True, slots=True)
class BlenderAdapterStatus:
    """Discovery surface for the future Blender implementation of RigHost."""

    available: bool
    implementation: str = "planned"
    responsibility: str = "Armature/EditBone/PoseBone、constraints、撤销与场景复检"

    @classmethod
    def detect(cls) -> "BlenderAdapterStatus":
        return cls(available=importlib.util.find_spec("bpy") is not None)

