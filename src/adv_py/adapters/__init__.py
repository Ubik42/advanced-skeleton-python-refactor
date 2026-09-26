"""Concrete and test host adapters."""

from .maya_mocap import MayaMocapBakeHost
from .maya_mocap_clip import MayaMocapClipHost
from .maya_mocap_control import MayaMocapControlHost
from .maya_character_spine_migration import (MayaCharacterSpineMigrationHost,
    MayaOriginalSkinSpineMigrationHost)
from .maya_spine_skin_handoff import MayaSpineSkinHandoffHost
from .maya_spine_original_promotion import MayaOriginalSpinePromotionHost

from .blender import BlenderAdapterStatus, BlenderRigHost
from .maya import MayaAdapterStatus, MayaRigHost
from .maya_body import MayaBodyBuildHost
from .maya_face import MayaFaceHost
from .maya_external_mesh import MayaExternalMeshHost
from .maya_axial_part import MayaAxialPartHost
from .maya_fit import MayaFitJointHost, MayaJointLabelHost
from .maya_mocap import (
    MayaMocapConnectionHost,
    MayaMocapMappingReader,
    MayaMocapSourceReader,
)
from .memory import InMemoryRigHost

__all__ = [
    "MayaMocapBakeHost",
    "MayaMocapClipHost",
    "MayaMocapControlHost",
    "MayaCharacterSpineMigrationHost",
    "MayaOriginalSkinSpineMigrationHost",
    "MayaSpineSkinHandoffHost",
    "MayaOriginalSpinePromotionHost",

    "BlenderAdapterStatus",
    "BlenderRigHost",
    "InMemoryRigHost",
    "MayaAdapterStatus",
    "MayaBodyBuildHost",
    "MayaFaceHost",
    "MayaExternalMeshHost",
    "MayaAxialPartHost",
    "MayaFitJointHost",
    "MayaJointLabelHost",
    "MayaMocapSourceReader",
    "MayaMocapMappingReader",
    "MayaMocapConnectionHost",
    "MayaRigHost",
]
