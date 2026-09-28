"""Control-curve projection decisions from AdvancedSkeleton 6.925."""
from __future__ import annotations

from fnmatch import fnmatchcase


def fbx_fk_projection_factor(
    control_name: str, cv_index: int, local_position: tuple[float, float, float],
) -> float | None:
    """Return the surface clearance factor, or None for a protected CV."""
    if all(abs(value) < .001 for value in local_position):
        return None
    if (fnmatchcase(control_name, "FKShoulder_*")
            or fnmatchcase(control_name, "FKHip_*")) and cv_index < 3:
        return None
    if fnmatchcase(control_name, "FKCup_*") and 1 < cv_index < 5:
        return None
    if fnmatchcase(control_name, "FKThumbFinger[1-2]_*") and cv_index < 3:
        return None
    if "Eye" in control_name or "Jaw" in control_name:
        return None
    if control_name == "FKChest_M" and cv_index in (1, 5):
        return None
    if control_name == "RootX_M" and cv_index in (5, 15, 25, 35):
        return 1.56
    return 1.3
