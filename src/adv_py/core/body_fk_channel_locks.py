"""Carry locked Fit transform channels onto generated FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .fit_hierarchy import FitHierarchySnapshot
from .source_fit_identity import source_fit_control_reference


FK_LOCK_ATTRIBUTES = frozenset(
    kind + axis for kind in ("translate", "rotate", "scale")
    for axis in "XYZ"
)


@dataclass(frozen=True, slots=True)
class BodyFkChannelLockSpec:
    control: str
    source_fit_joint: str
    attributes: tuple[str, ...]


def plan_body_fk_channel_locks(
    hierarchy: FitHierarchySnapshot,
    controls: tuple[BodyLimbFkControlSpec, ...],
    source_locks: tuple[tuple[str, tuple[str, ...]], ...],
    *, instances=(),
) -> tuple[BodyFkChannelLockSpec, ...]:
    if not isinstance(hierarchy, FitHierarchySnapshot):
        raise ValueError("FK 锁定缺少 Fit 层级")
    fit_paths = {item.path for item in hierarchy.joints}
    locks = dict(source_locks)
    if (len(locks) != len(source_locks) or set(locks) != fit_paths
            or any(len(values) != len(set(values))
                   or not set(values) <= FK_LOCK_ATTRIBUTES
                   for values in locks.values())):
        raise ValueError("FK 锁定来源通道集合无效")
    parents = {item.dag_parent for item in hierarchy.joints}
    by_name: dict[str, list[str]] = {}
    for path in fit_paths:
        by_name.setdefault(path.rsplit("|", 1)[-1]
                           .rsplit(":", 1)[-1], []).append(path)
    result: list[BodyFkChannelLockSpec] = []
    seen_controls: set[str] = set()
    for control in controls:
        reference = source_fit_control_reference(control, instances)
        matches = ((reference,) if reference is not None else
                   next((by_name[name] for name in control.fit_joint_names
                         if name in by_name), ()))
        if len(matches) > 1:
            raise ValueError("FK 锁定来源 Fit 短名不唯一："
                             + "／".join(control.fit_joint_names))
        if control.control_path in seen_controls:
            raise ValueError("FK 锁定目标控制器重复：" + control.control_path)
        seen_controls.add(control.control_path)
        if not matches or matches[0] not in parents:
            continue
        attributes = locks[matches[0]]
        if attributes:
            result.append(BodyFkChannelLockSpec(
                control.control_path, matches[0], attributes))
    return tuple(result)
