"""Source-order Face stages and original rebuild option defaults."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OriginalFaceKeepOptions:
    # Defaults match the original UI; BlendShapes is unchecked and disabled.
    all: bool = True
    skin_weights: bool = True
    added_joints: bool = True
    head_squash: bool = True
    blend_shapes: bool = False
    corrective_shapes: bool = True
    driving_systems: bool = True
    curve_shapes: bool = True
    custom_controls: bool = True
    custom_orient: bool = True


ORIGINAL_FACE_BUILD_STEPS = (
    "Prep", "CtrlBox", "EyeBall", "EyeLid", "EyeBlink", "EyeWide", "Lip",
    "LipFalloff", "FaceCage", "CageToSkin", "EyeBrow", "Squint", "SmilePull",
    "FrownPull", "Cheek", "CheekRaiser", "JawWeighing", "JawOpen", "LipUp",
    "LipDown", "LipSide", "Snarl", "Tongue", "Regions", "EyeAim", "UpMidLo",
    "Phonemes", "Emotions", "Finish", "RebuildRestore")


