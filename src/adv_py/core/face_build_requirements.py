"""Original FaceSetup fitting prerequisites for each Include setting."""
from __future__ import annotations

from enum import Enum


class FaceInclude(str, Enum):
    ALL = "Complete"
    SKIP_ABOVE = "Skip Above Eyes"
    SKIP_BELOW = "Skip Below Eyes"
    EYES_ONLY = "Skip Above+Below Eyes"


_BASE = ("FitEyeBall", "FaceFitEyeLidOuter",
         "FaceFitEyeLidMain", "FaceFitEyeLidInner")
_BELOW = ("FaceFitLipOuter", "FaceFitLipMain", "FaceFitLipInner",
          "FaceFitJawPivot", "FaceFitJawCorner", "FaceFitJawLine",
          "FaceFitJaw", "FaceFitChinCrease", "FaceFitThroat",
          "FaceFitCheek", "FaceFitCheekBone", "FaceFitSmileBulge",
          "FaceFitFrownBulge", "FaceFitNose", "FaceFitNoseUnder",
          "FaceFitNoseCorner", "FaceFitNoseSide", "FaceFitNoseBridge",
          "FaceFitNostril")
_ABOVE = ("FaceFitEyeBrowInner", "FaceFitEyeBrowOuter",
          "FaceFitEyeBrowCenter", "FaceFitForeHead")


def required_face_fit_nodes(include: FaceInclude,
                            non_symmetrical: bool = False) -> tuple[str, ...]:
    if not isinstance(include, FaceInclude):
        raise ValueError("Face Include 选项无效")
    required = list(_BASE)
    if include in (FaceInclude.ALL, FaceInclude.SKIP_ABOVE):
        required.extend(_BELOW)
    if include in (FaceInclude.ALL, FaceInclude.SKIP_BELOW):
        required.extend(_ABOVE)
    if non_symmetrical:
        required.extend(name + "Left" for name in tuple(required))
    return tuple(required)
