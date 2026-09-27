"""Scene-independent plans for ADV Body Partial Joints operations."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class PartialJointCandidate:
    joint: str
    parent: str | None
    child_count: int
    existing_single: bool
    existing_multi: bool


@dataclass(frozen=True, slots=True)
class PartialJointSpec:
    joint: str
    parent: str
    stem: str
    side: str
    count: int
    include_controller: bool
    auto_bind: bool
    use_opm: bool = False

    @property
    def names(self) -> tuple[str, ...]:
        if self.count == 1:
            names = [self.stem + "Partial_" + self.side]
            if self.use_opm:
                names.extend((self.stem + "PartialBM_" + self.side,
                              ("FK" + self.stem + "Partial_" + self.side
                               if self.include_controller else self.stem + "Partial_" + self.side)
                              + "FollowMDL_" + self.side))
                if self.include_controller:
                    names.append(self.stem + "PartialMM_" + self.side)
            else:
                names.extend((self.stem + "_" + self.side + "_00",
                              self.stem + "_" + self.side + "_00Offset",
                              "FK" + self.stem + "Partial_" + self.side + "SR",
                              self.stem + "_" + self.side + "_00Offset_parentConstraint1"))
            target = self.stem + "Partial_" + self.side
            if self.include_controller:
                names.extend(("FKOffset" + self.stem + "Partial_" + self.side,
                              "FKExtra" + self.stem + "Partial_" + self.side,
                              "FK" + self.stem + "Partial_" + self.side,
                              target + "_parentConstraint1",
                              target + "_scaleConstraint1"))
                target = "FKOffset" + target
            if not self.use_opm:
                names.extend(target + "_" + kind + "Constraint1"
                             for kind in ("orient", "point", "scale"))
            return tuple(names)
        names = [self.stem + "Partial%d_%s" % (index, self.side)
                 for index in range(1, self.count + 1)]
        names.extend(prefix + self.stem + "_" + self.side for prefix in (
            "PartialMultiJoints", "IkHandlePartial", "EffectorPartial",
            "IKCurve", "IKCurveInfo", "IKCurveInfoNormalize",
            "IKCurveInfoAllMultiply", "IKCurveTxMultiply"))
        names.extend("PMJLoc%d%s_%s" % (index, self.stem, self.side)
                     for index in range(4))
        names.extend("PMJX%d%s_%s" % (index, self.stem, self.side)
                     for index in range(4))
        return tuple(names)


@dataclass(frozen=True, slots=True)
class PartialJointPlan:
    specs: tuple[PartialJointSpec, ...]


@dataclass(frozen=True, slots=True)
class PartialDeleteSpec:
    joint: str
    stem: str
    side: str
    single: bool
    multi: bool


@dataclass(frozen=True, slots=True)
class PartialDeletePlan:
    specs: tuple[PartialDeleteSpec, ...]
    delete_all: bool


def _selected_candidates(
        candidates: tuple[PartialJointCandidate, ...],
        selected: tuple[str, ...]) -> tuple[PartialJointCandidate, ...]:
    by_joint = {candidate.joint: candidate for candidate in candidates}
    if len(by_joint) != len(candidates):
        raise ValueError("DeformSet 包含重复关节")
    if selected and (len(set(selected)) != len(selected)
                     or any(joint not in by_joint for joint in selected)):
        raise ValueError("Partial Joints 目标须为唯一的 DeformSet 关节")
    return tuple(by_joint[joint] for joint in selected) if selected else candidates


def _stem_side(joint: str) -> tuple[str, str] | None:
    leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    match = re.fullmatch(r"([^_:|]+)_([LRM])", leaf)
    return match.groups() if match else None


def plan_create_partial_joints(
        candidates: tuple[PartialJointCandidate, ...],
        selected: tuple[str, ...] = (), *,
        count: int = 1, include_controller: bool = False,
        auto_bind: bool = False, use_opm: bool = False) -> PartialJointPlan:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 128:
        raise ValueError("Partial 关节段数须为 1～128")
    if (not isinstance(include_controller, bool)
            or not isinstance(auto_bind, bool)
            or not isinstance(use_opm, bool)):
        raise ValueError("Partial 选项须为布尔值")
    if auto_bind and count == 1:
        raise ValueError("自动蒙皮只适用于多段 Partial Joints")
    if include_controller and count > 1:
        raise ValueError("原版多段 Partial Joints 不创建独立 FK 控制器")
    specs = []
    for candidate in _selected_candidates(candidates, selected):
        naming = _stem_side(candidate.joint)
        leaf = candidate.joint.rsplit("|", 1)[-1]
        ineligible = (not candidate.parent or candidate.child_count == 0
                      or naming is None or re.search(r"Part[0-9]", leaf) is not None)
        already_exists = (candidate.existing_single if count == 1
                          else candidate.existing_multi)
        if ineligible or already_exists:
            continue
        stem, side = naming
        specs.append(PartialJointSpec(candidate.joint, candidate.parent,
                                      stem, side, count,
                                      include_controller, auto_bind,
                                      use_opm and count == 1))
    if not specs:
        raise ValueError("没有可创建的 Partial Joints 目标")
    names = [name for spec in specs for name in spec.names]
    if len(names) != len(set(names)):
        raise ValueError("Partial Joints 节点名称冲突")
    return PartialJointPlan(tuple(specs))


def plan_delete_partial_joints(
        candidates: tuple[PartialJointCandidate, ...],
        selected: tuple[str, ...] = ()) -> PartialDeletePlan:
    specs = []
    for candidate in _selected_candidates(candidates, selected):
        naming = _stem_side(candidate.joint)
        if naming is None or not (candidate.existing_single
                                   or candidate.existing_multi):
            continue
        stem, side = naming
        specs.append(PartialDeleteSpec(candidate.joint, stem, side,
                                       candidate.existing_single,
                                       candidate.existing_multi))
    if not specs:
        raise ValueError("没有可删除的 Partial Joints")
    return PartialDeletePlan(tuple(specs), not selected)
