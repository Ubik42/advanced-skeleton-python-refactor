"""AdvancedSkeleton panel color preferences, independent of Maya widgets."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


PANEL_COLOR_DEFAULTS: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("Background", (0.3, 0.3, 0.4)),
    ("Level1", (0.4, 0.2, 0.2)),
    ("Level2", (0.3, 0.4, 0.3)),
    ("Buttons", (0.35, 0.45, 0.45)),
    ("DropDowns", (0.12, 0.30, 0.32)),
    ("CheckBoxes", (0.2, 0.3, 0.3)),
)
PANEL_COLOR_KINDS = frozenset(kind for kind, _ in PANEL_COLOR_DEFAULTS)


def panel_rgb(value) -> tuple[float, float, float]:
    if (not isinstance(value, (tuple, list)) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not isfinite(v) or not 0.0 <= v <= 1.0 for v in value)):
        raise ValueError("面板颜色必须是三个 0～1 的有限数")
    return tuple(float(v) for v in value)


@dataclass(frozen=True, slots=True)
class PanelPalette:
    enabled: bool
    colors: tuple[tuple[str, tuple[float, float, float]], ...]

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("自定义颜色开关无效")
        if tuple(kind for kind, _ in self.colors) != tuple(
                kind for kind, _ in PANEL_COLOR_DEFAULTS):
            raise ValueError("面板颜色栏目顺序无效")
        for _, rgb in self.colors:
            panel_rgb(rgb)

    def color(self, kind: str) -> tuple[float, float, float]:
        return dict(self.colors)[kind]
