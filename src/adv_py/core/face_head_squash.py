"""ADV 6.925 HeadSquash lattice, control and influence specifications."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

HEAD_SQUASH_CONTROLS = ("squashTop_M", "squashMiddle_M", "squashBottom_M", "squashBase_M")
HEAD_SQUASH_BOX = ((1,1,1),(1,-1,1),(-1,-1,1),(-1,1,1),(1,1,1),
                   (1,1,-1),(1,-1,-1),(1,-1,1),(1,-1,-1),(-1,-1,-1),
                   (-1,1,-1),(1,1,-1),(-1,1,-1),(-1,1,1),(-1,-1,1),(-1,-1,-1))
HEAD_SQUASH_NAMES = (
    "SquashSet", "SquashSetup", "SquashControls", *HEAD_SQUASH_CONTROLS,
    "squashTopOffset", "squashMiddleOffset", "squashBottomOffset",
    "squashFfd", "squashFfdLattice", "squashFfdBase", "squashFfdSet",
    "squashXup", "squashIKHandle", "squashIKEffector", "squashIKECurve",
    "squashIKSC", "squashTopVolumeUC", "squashIKCurveInfo",
    "squashIKCurveInfoNormalize", "squashIKCurveInfoMainScale",
    "squashIKCurveInfoMainScaleDM", "squashIKScale", "squashIKStretch",
    "squashVolume1Over", "squashVolumePow", "squashBlendTwo",
    *(f"squashIKX{i}" for i in range(10)),
    *(f"squashIKCluster{i}" for i in range(5)),
    *(f"squashIKClusterHandle{i}" for i in range(5)))

@dataclass(frozen=True, slots=True)
class FaceHeadSquashInput:
    head: str
    face: str
    skin: str
    geometry: tuple[str, ...]
    control_shapes: tuple[str, ...]
    extra_control_shapes: tuple[str, ...]
    face_scale: float
    bottom_y: float
    top_y: float
    use_offset_parent_matrix: bool

    def __post_init__(self):
        if any(not isinstance(item,str) or not item for item in (self.head,self.face,self.skin)):
            raise ValueError("HeadSquash 需要头关节、面部网格和 Skin")
        if not self.geometry and not self.control_shapes:
            raise ValueError("HeadSquash 没有可变形对象")
        if any(isinstance(value,bool) or not isinstance(value,(int,float))
               or not isfinite(value) for value in (self.face_scale,self.bottom_y,self.top_y)):
            raise ValueError("HeadSquash 范围必须是有限数值")
        if self.face_scale <= 0 or self.top_y <= self.bottom_y:
            raise ValueError("HeadSquash 头部高度和缩放必须为正")
        if type(self.use_offset_parent_matrix) is not bool:
            raise ValueError("HeadSquash OPM 选项无效")

    @property
    def scale(self): return self.face_scale / 3.0
    @property
    def height(self): return self.top_y - self.bottom_y
    @property
    def center_y(self): return (self.top_y + self.bottom_y) / 2.0

@dataclass(frozen=True, slots=True)
class FaceHeadSquashResult:
    controls: tuple[str, ...]
    lattice: str
    deformer: str
    skin: str
    members: tuple[str, ...]
