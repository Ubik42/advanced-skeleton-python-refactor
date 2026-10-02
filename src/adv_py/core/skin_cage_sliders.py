"""Naming and selection contract of the 6.925 SkinCage sliders."""
from __future__ import annotations

from dataclasses import dataclass
import re


_PROFILE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)_([LRM])_(start|middle|end|twist)Profile([0-9]*)$")


@dataclass(frozen=True)
class SkinCageSlider:
    profile: str
    deform_joint: str
    segment: str
    stem: str
    side: str
    restore_joint: str
    indices: tuple[int, ...]
    bend_axis: int

    def joint(self, index: int) -> str:
        return f"{self.stem}{self.segment}Slider{index}_{self.side}"


def plan_skin_cage_sliders(
        rows: tuple[tuple[str, str, str, int, str], ...]
        ) -> tuple[SkinCageSlider, ...]:
    """Rows contain profile, resolved joint, restore joint, bend axis, segment."""
    result = []
    seen = set()
    for profile, deform_joint, restore_joint, bend_axis, segment in rows:
        leaf = profile.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        match = _PROFILE.fullmatch(leaf)
        if match is None or not deform_joint or not restore_joint:
            raise ValueError("无效的 SkinCage 滑块截面：" + leaf)
        profile_stem, side, kind, ordinal = match.groups()
        if kind == "twist" and not ordinal:
            raise ValueError("扭转截面缺少编号：" + leaf)
        if segment not in ("start", "middle", "end") or (
                kind != "twist" and kind != segment):
            raise ValueError("截面和滑块位置不匹配：" + leaf)
        joint_leaf = deform_joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        joint_stem, separator, joint_side = joint_leaf.rpartition("_")
        if not separator or joint_side != side or not joint_stem:
            raise ValueError("截面与关节左右侧不匹配：" + leaf)
        indices = ((1, 3) if bend_axis == 1 else (0, 2)
                   if bend_axis == 2 else (0, 1, 2, 3))
        if bend_axis not in (0, 1, 2):
            raise ValueError("SkinCage 弯曲轴无效：" + leaf)
        key = (joint_stem, side, segment)
        if key in seen:
            continue
        seen.add(key)
        result.append(SkinCageSlider(profile, deform_joint, segment,
                                     joint_stem, side, restore_joint, indices,
                                     bend_axis))
    return tuple(result)
