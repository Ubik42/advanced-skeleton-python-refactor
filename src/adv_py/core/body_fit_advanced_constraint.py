"""Map ADV Fit constraint targets to the built FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


_KINDS = ("parent", "point", "orient", "scale")


@dataclass(frozen=True, slots=True)
class BodyFitAdvancedConstraintSpec:
    kind: str
    source_joint: str
    target_joint: str
    fk_control: str
    fk_offset: str
    static_name: str
    weight_name: str
    reverse_name: str
    constraint_name: str

    @property
    def attribute(self) -> str:
        return self.kind + "Constraint"

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.static_name, self.weight_name,
                self.reverse_name, self.constraint_name)


def plan_body_fit_advanced_constraints(
    metadata: tuple[FitJointMetadata, ...],
    controls: tuple,
    body_joints: tuple,
) -> tuple[BodyFitAdvancedConstraintSpec, ...]:
    """Resolve side-aware targets; defer scene ownership checks to Maya."""
    by_name = {joint.name.rsplit(":", 1)[-1]: joint.path
               for joint in body_joints}
    if len(by_name) != len(body_joints):
        raise ValueError("Advanced Constraint Body 关节短名重复")
    result = []
    used = set()
    for item in metadata:
        targets = tuple((kind, getattr(item, kind + "_constraint"))
                        for kind in _KINDS
                        if getattr(item, kind + "_constraint") is not None)
        if not targets:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        matches = tuple(control for control in controls
                        if source_name in control.fit_joint_names)
        # MEL skips Fit joints without an FK control, including most ends.
        for control in matches:
            side = control.side.value
            for kind, target_name in targets:
                lateral = by_name.get(target_name + "_" + side)
                central = by_name.get(target_name + "_M")
                if side == "M" and lateral is None and central is None and (
                        by_name.get(target_name + "_R") is not None or
                        by_name.get(target_name + "_L") is not None):
                    raise ValueError(
                        "中央 FK 约束到双侧关节需要原版左右平均分支："
                        + source_name)
                target = lateral or central
                if target is None:
                    raise ValueError("Advanced Constraint 目标 Body 关节缺失："
                                     + target_name + "_" + side)
                if (target == control.driven_joint
                        or target.startswith(control.driven_joint + "|")):
                    raise ValueError("Advanced Constraint 目标依赖自身 FK："
                                     + target)
                key = (control.control_path, kind)
                if key in used:
                    raise ValueError("Advanced Constraint FK 控制重复："
                                     + control.control_path)
                used.add(key)
                leaf = control.control_path.rsplit("|", 1)[-1]
                prefix = leaf.split(":", 1)[0] + ":" if ":" in leaf else ""
                stem = prefix + "AdvPy_" + kind.title() + "Constrain" \
                    + source_name + "_" + side
                result.append(BodyFitAdvancedConstraintSpec(
                    kind, item.joint, target, control.control_path,
                    control.offset_path, stem + "Static",
                    stem + "Weight", stem + "Reverse",
                    stem + "Constraint"))
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Advanced Constraint 生成节点名称重复")
    return tuple(result)
