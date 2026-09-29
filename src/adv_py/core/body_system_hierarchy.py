"""Expected system containers for a newly built AdvancedSkeleton Body."""
from __future__ import annotations


BODY_SYSTEM_RESERVED_NAMES = (
    "Group", "DeformationSystem", "Geometry", "MotionSystem",
    "FKSystem", "IKSystem", "FKIKSystem", "TwistSystem", "BendSystem",
    "RootSystem", "RootFollowMain", "GlobalSystem", "GlobalFollowMain",
    "AimSystem", "ConstraintSystem", "DynamicSystem", "DrivingSystem",
)


def expected_body_system_hierarchy(
    body_root_path: str,
    fit_container_path: str = "|Group|FitSkeleton",
    *, include_dynamic: bool = True,
) -> tuple[tuple[str, str | None, str], ...]:
    group = "|Group"
    motion = group + "|MotionSystem"
    deformation = group + "|DeformationSystem"
    rows = [
        (group, None, "transform"),
        (fit_container_path, group, "transform"),
        (deformation, group, "transform"),
        (group + "|Geometry", group, "transform"),
        (motion, group, "transform"),
    ]
    rows.extend((motion + "|" + name, motion, "transform") for name in (
        "FKSystem", "IKSystem", "FKIKSystem", "TwistSystem", "BendSystem",
        "RootSystem",
    ))
    rows.append((motion + "|RootSystem|RootFollowMain",
                 motion + "|RootSystem", "transform"))
    rows.append((motion + "|GlobalSystem", motion, "transform"))
    rows.append((motion + "|GlobalSystem|GlobalFollowMain",
                 motion + "|GlobalSystem", "transform"))
    rows.extend((motion + "|" + name, motion, "transform") for name in (
        "AimSystem", "ConstraintSystem",
        *(("DynamicSystem",) if include_dynamic else ()),
        "DrivingSystem",
    ))
    rows.append((body_root_path, deformation, "joint"))
    return tuple(rows)
