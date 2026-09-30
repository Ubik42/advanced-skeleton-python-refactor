"""Original Face Cage inputs, without inventing a second face architecture."""
from dataclasses import dataclass

CAGE_MARKERS=("CheekBone","NoseSide","NoseBridge","NoseCorner","NoseUnder",
              "FrownBulge","SmileBulge","Cheek","ChinCrease","Nose","Nostril")
CAGE_CENTER_MARKERS=frozenset(("NoseBridge","Nose","NoseUnder","ChinCrease","EyeBrowCenter"))

@dataclass(frozen=True,slots=True)
class FaceCageInput:
    geometry: str
    head: str
    skin: str
    face_scale: float
    multi_skin_clusters: bool
    simpler_eye_lid: bool
    has_above_eye: bool
    has_below_eye: bool
    use_offset_parent_matrix: bool

@dataclass(frozen=True,slots=True)
class FaceCageOptions:
    smooth_passes: int | None = None
    def __post_init__(self):
        if self.smooth_passes is not None and (type(self.smooth_passes) is not int or self.smooth_passes<0):
            raise ValueError("Face Cage 平滑次数必须是非负整数")
