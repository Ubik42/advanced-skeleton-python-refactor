"""Source inputs for ADV 6.925 Jaw weighing and Teeth stages."""
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class FaceJawInput:
    geometry: str
    head: str
    skin: str
    face_scale: float
    use_offset_parent_matrix: bool
    multi_skin_clusters: bool
    long_snout: bool
    non_symmetrical: bool
    upper_teeth: tuple[str,...] = ()
    lower_teeth: tuple[str,...] = ()
    tongue: tuple[str,...] = ()
    smooth_iterations: int = 50
