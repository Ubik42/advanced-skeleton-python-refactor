"""Original 6.925 FK anchor topology for an Inbetween start joint."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InbetweenFkAnchorPlan:
    start_body_name: str
    fk_offset_path: str
    fk_control_path: str
    rotate_order: int
    base_name: str
    target_name: str
    extra_name: str
    fkx_name: str

    @property
    def base_world_plug(self) -> str:
        return self.base_name + ".worldMatrix[0]"

    @property
    def target_world_plug(self) -> str:
        return self.target_name + ".worldMatrix[0]"

    @property
    def parent_inverse_plug(self) -> str:
        return self.extra_name + ".parentInverseMatrix[0]"

    @property
    def start_fkx_opm_plug(self) -> str:
        return self.fkx_name + ".offsetParentMatrix"


def plan_inbetween_fk_anchor(
    start_body_name: str, *,
    fk_offset_path: str,
    fk_control_path: str,
    rotate_order: int,
) -> InbetweenFkAnchorPlan:
    """Add Base/Target/Extra/FKX without changing registered FK paths.

    Target follows the animated FK control. Base, Extra and FKX share its
    offset parent. Extra's parentInverseMatrix converts a world blend into
    FKX's local matrix, as in the original Inbetween graph.
    """
    if (not start_body_name or "|" in start_body_name
            or not fk_offset_path.startswith("|")
            or not fk_control_path.startswith(fk_offset_path + "|")
            or not isinstance(rotate_order, int)
            or isinstance(rotate_order, bool)
            or not 0 <= rotate_order <= 5):
        raise ValueError("Inbetween FK 起点控制层输入无效")
    prefix = "AdvPy_" + start_body_name + "_Inbetween"
    return InbetweenFkAnchorPlan(
        start_body_name, fk_offset_path, fk_control_path, rotate_order,
        prefix + "Base", prefix + "Target",
        prefix + "Extra", prefix + "FKX")
