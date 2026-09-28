"""6.925 Control Mesh color cycle and one-time normal expansion."""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from math import isfinite
import re


SHADER_COLORS = {
    "asRedSG": (1.0, 0.0, 0.0),
    "asRed2SG": (1.0, 0.0, 1.0),
    "asGreenSG": (0.0, 1.0, 0.0),
    "asGreen2SG": (1.0, 1.0, 0.0),
    "asBlueSG": (0.0, 0.0, 1.0),
    "asBlue2SG": (0.0, 1.0, 1.0),
    "asWhiteSG": (1.0, 1.0, 1.0),
    "asBlackSG": (0.0, 0.0, 0.0),
    "asBonesSG": (0.78, 0.76, 0.72),
    "asRedSSSG": (1.0, 0.0, 0.0),
}


@dataclass(frozen=True, slots=True)
class ControlMeshColorSource:
    joint_path: str
    mesh_shape: str
    expanded: bool


@dataclass(frozen=True, slots=True)
class ControlMeshColorItem:
    mesh_shape: str
    shader: str
    expand_distance: float
    already_expanded: bool


_JOINT_OVERRIDES = (
    ("Head_*", "asBlueSG"),
    ("JawJoint_*", "asGreenSG"),
    ("FrownBulgeJoint_*", "asBlue2SG"),
    ("SmileBulgeJoint_*", "asGreen2SG"),
    ("CheekRaiserJoint_*", "asRed2SG"),
    ("EyeBrowCenterJoint_*", "asBlue2SG"),
    ("EyeBrowInnerJoint_*", "asGreenSG"),
    ("EyeBrowMid1Joint_*", "asGreen2SG"),
    ("EyeBrowMid2Joint_*", "asRed2SG"),
    ("EyeBrowMid3Joint_*", "asBlue2SG"),
    ("EyeBrowOuterJoint_*", "asGreen2SG"),
    ("NoseCornerJoint_*", "asGreenSG"),
    ("NostrilJoint_*", "asRed2SG"),
    ("NoseSideJoint_*", "asBlue2SG"),
    ("NoseBridgeJoint_*", "asGreen2SG"),
    ("NoseJoint_*", "asRedSG"),
    ("upperLidBaseJoint_*", "asRed2SG"),
)

_MESH_OVERRIDES = (
    ("*LipA_*MeshCtrl*", "asRedSG"),
    ("*LipB_*MeshCtrl*", "asRed2SG"),
    ("*Lip_*MeshCtrl*", "asRedSG"),
    ("*Lip_MMeshCtrl*", "asGreen2SG"),
    ("*upperLid_*MeshCtrl*", "asGreen2SG"),
    ("*lowerLid_*MeshCtrl*", "asGreen2SG"),
    ("*OuterLid_*MeshCtrl*", "asRedSG"),
    ("*InnerLid_*MeshCtrl*", "asRedSG"),
    ("*outerLid_*MeshCtrl*", "asRed2SG"),
    ("*innerLid_*MeshCtrl*", "asRed2SG"),
    ("*upperLidOuter_*MeshCtrl*", "asGreenSG"),
    ("*lowerLidOuter_*MeshCtrl*", "asGreenSG"),
    ("*OuterLidOuter_*MeshCtrl*", "asBlue2SG"),
    ("*InnerLidOuter_*MeshCtrl*", "asBlue2SG"),
    ("*outerLidOuter_*MeshCtrl*", "asGreenSG"),
    ("*innerLidOuter_*MeshCtrl*", "asGreenSG"),
)


def _shader(source: ControlMeshColorSource) -> str:
    joint = source.joint_path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    mesh = source.mesh_shape.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    depth = sum(1 for segment in source.joint_path.split("|") if segment
                and not re.search(r"Part[0-9]+",
                                  segment.rsplit(":", 1)[-1])
                and not fnmatchcase(segment.rsplit(":", 1)[-1], "Cup_*"))
    shader = ("asRedSG", "asBlueSG", "asGreenSG")[depth % 3]
    for pattern, value in _JOINT_OVERRIDES:
        if fnmatchcase(joint, pattern):
            shader = value
    for pattern, value in _MESH_OVERRIDES:
        if fnmatchcase(mesh, pattern):
            shader = value
    return shader


def plan_control_mesh_colors(
    sources: tuple[ControlMeshColorSource, ...], char_height: float,
) -> tuple[ControlMeshColorItem, ...]:
    if (not sources or not isfinite(char_height) or char_height <= 0):
        raise ValueError("Control Mesh 着色需要角色高度和已建网格")
    planned = {}
    for source in sources:
        if not source.mesh_shape or not source.joint_path:
            raise ValueError("Control Mesh 着色来源无效")
        planned[source.mesh_shape] = ControlMeshColorItem(
            source.mesh_shape, _shader(source), char_height / 1000.0,
            source.expanded)
    return tuple(planned.values())
