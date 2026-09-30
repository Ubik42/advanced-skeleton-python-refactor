"""Inputs for ADV 6.925 asFaceLip; topology and graph order stay in the host."""
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class FaceLipInput:
    geometry: str
    head: str
    skin: str
    face_scale: float
    control_scale: float
    control_count: int = 12
    multi_skin_clusters: bool = False
    non_symmetrical: bool = False
    long_snout: bool = False
    legacy_orient: bool = False

    @property
    def end(self): return self.control_count//4

    @property
    def ribbon_spans(self): return self.control_count//2-1
