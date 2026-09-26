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
from .maya_finger_mid import MayaFingerMidHost
from .maya_limb_part import MayaLimbPartHost
from .maya_root_volume import MayaRootVolumeHost
from .maya_sdk_volume import MayaSdkVolumeHost
from .maya_volume_half_parent import MayaVolumeHalfParentHost
from .maya_angle_sampler import MayaAngleSamplerHost
from .maya_dense_skin import MayaDenseSkinHost
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
    "MayaFingerMidHost",
    "MayaLimbPartHost",
    "MayaRootVolumeHost",
    "MayaSdkVolumeHost",
    "MayaVolumeHalfParentHost",
    "MayaAngleSamplerHost",
    "MayaDenseSkinHost",
    "MayaFitJointHost",
    "MayaJointLabelHost",
    "MayaMocapSourceReader",
    "MayaMocapMappingReader",
    "MayaMocapConnectionHost",
    "MayaRigHost",
]
