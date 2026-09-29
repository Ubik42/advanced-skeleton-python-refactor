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

    def joint(self, index: int) -> str:
        return f"{self.stem}{self.segment}Slider{index}_{self.side}"


def plan_skin_cage_sliders(
        rows: tuple[tuple[str, str, str, int], ...]
        ) -> tuple[SkinCageSlider, ...]:
    """Rows contain profile, resolved deform joint, restore joint, bend axis."""
    if not rows:
        raise ValueError("请选择 SkinCage 截面曲线")
    result = []
    seen = set()
    for profile, deform_joint, restore_joint, bend_axis in rows:
        leaf = profile.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        match = _PROFILE.fullmatch(leaf)
        if match is None or not deform_joint or not restore_joint:
            raise ValueError("无效的 SkinCage 滑块截面：" + leaf)
        stem, side, kind, ordinal = match.groups()
        segment = "end" if kind == "twist" else kind
        if kind == "twist" and not ordinal:
            raise ValueError("扭转截面缺少编号：" + leaf)
        indices = ((1, 3) if bend_axis == 1 else (0, 2)
                   if bend_axis == 2 else (0, 1, 2, 3))
        if bend_axis not in (0, 1, 2):
            raise ValueError("SkinCage 弯曲轴无效：" + leaf)
        key = (stem, side, segment)
        if key in seen:
            raise ValueError("多个截面会写入同名 Sliders：" + leaf)
        seen.add(key)
        result.append(SkinCageSlider(profile, deform_joint, segment,
                                     stem, side, restore_joint, indices))
    return tuple(result)
