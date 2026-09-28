"""Resolve ADV Fit ``noControl`` onto generated FK curve transforms."""
from __future__ import annotations

from .body_limb_controls import BodyLimbFkControlSpec
from .fit_metadata import FitJointMetadata


def plan_body_no_control(
    metadata: tuple[FitJointMetadata, ...],
    controls: tuple[BodyLimbFkControlSpec, ...],
) -> tuple[str, ...]:
    by_name: dict[str, list[FitJointMetadata]] = {}
    for item in metadata:
        name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        by_name.setdefault(name, []).append(item)
    hidden = []
    for control in controls:
        matches = next((by_name[name] for name in control.fit_joint_names
                        if name in by_name), ())
        if len(matches) > 1:
            raise ValueError("No Control 来源 Fit 关节短名不唯一："
                             + "／".join(control.fit_joint_names))
        source = matches[0] if matches else None
        if source is not None and source.no_control:
            if control.control_path in hidden:
                raise ValueError("No Control 目标 FK 控制重复："
                                 + control.control_path)
            hidden.append(control.control_path)
    return tuple(hidden)
