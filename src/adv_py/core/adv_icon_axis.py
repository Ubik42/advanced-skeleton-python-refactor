"""ADV 6.925 controller icon orientation from asSetOrientOffsetFromAxis."""
from __future__ import annotations

from math import cos, radians, sin


def icon_axis_offset(primary: str, secondary: str) -> tuple[float, float, float]:
    axes = {"X", "Y", "Z"}
    if (not isinstance(primary, str) or not isinstance(secondary, str)
            or primary.lstrip("-") not in axes
            or secondary.lstrip("-") not in axes
            or primary.lstrip("-") == secondary.lstrip("-")
            or primary.count("-") > 1 or secondary.count("-") > 1
            or ("-" in primary and not primary.startswith("-"))
            or ("-" in secondary and not secondary.startswith("-"))):
        raise ValueError("控制器图标主轴与副轴无效")
    negative_primary = primary.startswith("-")
    negative_secondary = secondary.startswith("-")
    sign = -1 if negative_primary else 1
    x = 180 if negative_secondary else 0
    y = 180 if negative_primary else 0
    pair = (primary[-1], secondary[-1])
    if pair == ("X", "Y"):
        return (x, y, 0)
    if pair == ("X", "Z"):
        return (x + 90 * sign, y, 0)
    if pair == ("Y", "Z"):
        return (x + 90 * sign, y, 90)
    if pair == ("Y", "X"):
        return (x + 180 * sign, y, 90)
    if pair == ("Z", "X"):
        return (x - 90 * sign, y - 90, 0)
    return (x, y - 90, 0)


def rotate_icon_point(
    point: tuple[float, float, float],
    offset: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Apply Maya's default XYZ Euler offset to one local curve point."""
    x, y, z = point
    rx, ry, rz = (radians(value) for value in offset)
    y, z = y * cos(rx) - z * sin(rx), y * sin(rx) + z * cos(rx)
    x, z = x * cos(ry) + z * sin(ry), -x * sin(ry) + z * cos(ry)
    x, y = x * cos(rz) - y * sin(rz), x * sin(rz) + y * cos(rz)
    return (x, y, z)
