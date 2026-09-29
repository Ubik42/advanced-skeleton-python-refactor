"""Map ADV Fit constraint targets to the built FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


_KINDS = ("parent", "point", "orient", "scale")


@dataclass(frozen=True, slots=True)
class BodyFitAdvancedConstraintSpec:
    kind: str
    source_joint: str
    source_body: str
    target_joints: tuple[str, ...]
    fk_control: str
    fk_offset: str
    static_name: str
    weight_name: str
    reverse_name: str
    constraint_name: str
    split_name: str | None = None
    align_target: bool = False
    reoffset_name: str | None = None

    @property
    def attribute(self) -> str:
        return self.kind + "Constraint"

    @property
    def fk_root(self) -> str:
        prefix = self.fk_offset + "|"
        if not self.fk_control.startswith(prefix):
            raise ValueError("Advanced Constraint FK 控制器不在 Offset 层下")
        return prefix + self.fk_control[len(prefix):].split("|", 1)[0]

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.static_name, self.weight_name,
                self.reverse_name, self.constraint_name) + (
                    (self.split_name,) if self.split_name is not None else ()) + (
                    (self.reoffset_name,) if self.reoffset_name is not None else ())


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
        if item.orient_constraint_maintain_offset and not targets:
            raise ValueError("Constraint 保持控制器朝向需要约束目标："+item.joint)
        if not targets:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        matches = tuple(control for control in controls
                        if source_name in control.fit_joint_names)
        # MEL skips Fit joints without an FK control, including most ends.
        for control in matches:
            side = control.side.value
            driven_body = by_name.get(source_name + "_" + side)
            if driven_body is None:
                raise ValueError("Advanced Constraint 来源 Body 关节缺失："
                                 + source_name + "_" + side)
            for kind, target_name in targets:
                central = by_name.get(target_name + "_M")
                if side == "M" and central is None:
                    right = by_name.get(target_name + "_R")
                    left = by_name.get(target_name + "_L")
                    if right is None or left is None:
                        raise ValueError(
                            "中央 FK 约束目标需要完整的左右 Body 关节："
                            + target_name)
                    target_paths = (right, left)
                else:
                    lateral = by_name.get(target_name + "_" + side)
                    target = lateral or central
                    target_paths = (target,) if target is not None else ()
                if not target_paths:
                    raise ValueError("Advanced Constraint 目标 Body 关节缺失："
                                     + target_name + "_" + side)
                if any(target == driven_body
                       or target.startswith(driven_body + "|")
                       for target in target_paths):
                    raise ValueError("Advanced Constraint 目标依赖自身 FK："
                                     + "、".join(target_paths))
                key = (control.control_path, kind)
                if key in used:
                    raise ValueError("Advanced Constraint FK 控制重复："
                                     + control.control_path)
                used.add(key)
                leaf = control.control_path.rsplit("|", 1)[-1]
                prefix = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
                stem = prefix + "AdvPy_" + kind.title() + "Constrain" \
                    + source_name + "_" + side
                result.append(BodyFitAdvancedConstraintSpec(
                    kind, item.joint, driven_body, target_paths,
                    control.control_path,
                    control.offset_path, stem + "Static",
                    stem + "Weight", stem + "Reverse",
                    stem + "Constraint",
                    stem + "Split" if len(target_paths) == 2 else None,
                    item.orient_constraint_maintain_offset,
                    (stem + "ReOffset"
                     if item.orient_constraint_maintain_offset else None)))
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Advanced Constraint 生成节点名称重复")
    return tuple(result)
