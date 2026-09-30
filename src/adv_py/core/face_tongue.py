"""ADV Tongue Fit and controller-chain values; no Maya dependencies."""
from dataclasses import dataclass
from math import isfinite

TONGUE_FIT_NAMES = ("FaceFitTongue", "FaceFitTongueGeo", "FaceFitTongueCurve",
                    "FaceFitTongueLoc", "TongueCurve", "TongueCylinder",
                    *(f"Tongue{i}" for i in range(5)))
GNM_TONGUE_JAW_FACES = ("14566:14597","14614:14625","14658:14661","14674:14677",
    "14682:14729","14750:14765","14806:14837","14898:14901","14906:14909",
    "14970:14981","15006:15021","15042:15053","15110:15117","15142:15145","15318:15477")

@dataclass(frozen=True, slots=True)
class FaceTongueInput:
    geometry: tuple[str, ...]
    face: str
    all_head: tuple[str, ...]
    fit_positions: tuple[tuple[float,float,float], ...]
    use_offset_parent_matrix: bool
    skin: str | None
    face_skin: str
    modifiers: int

    def __post_init__(self):
        if not self.geometry or not self.face or not self.face_skin:
            raise ValueError("Tongue 需要已记录的舌头对象和 Face Skin")
        if len(self.fit_positions)<2 or any(len(p)!=3 or
                any(not isfinite(x) for x in p) for p in self.fit_positions):
            raise ValueError("Tongue Fit 至少需要起点和末端两个有限位置")
        if type(self.use_offset_parent_matrix) is not bool:
            raise ValueError("Tongue OPM 选项无效")

    @property
    def control_count(self): return len(self.fit_positions)-1
    @property
    def controls(self): return tuple(f"Tongue{i}_M" for i in range(self.control_count))
    @property
    def joints(self): return tuple(f"Tongue{i}Joint_M" for i in range(self.control_count))
    @property
    def component_geometry(self): return any("." in node for node in self.geometry)
