"""Resolve ADV followSpaces levels for registered FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


@dataclass(frozen=True, slots=True)
class BodyFitFollowSpaceTarget:
    label: str
    source: str
    weight: float
    matrix_node: str
    weight_node: str


@dataclass(frozen=True, slots=True)
class BodyFitFollowSpacesSpec:
    source_body: str
    fk_control: str
    fk_offset: str
    offset_parent: str
    targets: tuple[BodyFitFollowSpaceTarget, ...]
    blend_node: str
    output_node: str

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.blend_node, self.output_node) + tuple(
            node for target in self.targets
            for node in (target.matrix_node, target.weight_node))


@dataclass(frozen=True, slots=True)
class BodyFitFollowSpacesState:
    offset_world: tuple[float, ...]
    parent_world: tuple[float, ...]
    target_worlds: tuple[tuple[float, ...], ...]
    opm_source: str | None
    opm_value: tuple[float, ...]


def plan_body_fit_follow_spaces(
    metadata: tuple[FitJointMetadata, ...], controls: tuple,
    body_joints: tuple, *, main_path: str, root_path: str,
) -> tuple[BodyFitFollowSpacesSpec, ...]:
    by_name = {joint.name.rsplit(":", 1)[-1]: joint.path
               for joint in body_joints}
    by_path = {joint.path: joint for joint in body_joints}
    if len(by_name) != len(body_joints):
        raise ValueError("Follow Spaces Body 关节短名重复")
    result = []
    used = set()
    chest = by_name.get("Chest_M")
    for item in metadata:
        if not item.follow_spaces:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        for control in controls:
            if source_name not in control.fit_joint_names:
                continue
            if control.control_path in used:
                raise ValueError("Follow Spaces 来源 FK 控制重复："
                                 + control.control_path)
            used.add(control.control_path)
            side = control.side.value
            source_body = by_name.get(source_name + "_" + side)
            if source_body is None:
                raise ValueError("Follow Spaces 来源 Body 关节缺失："
                                 + source_name + "_" + side)
            parent_body = by_path[source_body].parent_path
            parent_controls = tuple(
                candidate for candidate in controls
                if candidate.driven_joint == parent_body)
            if len(parent_controls) > 1:
                raise ValueError("Follow Spaces 父级 FK 控制不唯一："
                                 + str(parent_body))
            parent_control = parent_controls[0] if parent_controls else None
            parent_source = (
                (parent_control.source_override_path
                 or parent_control.control_path)
                if parent_control is not None else
                (root_path if parent_body == by_name.get("Root_M") else
                 parent_body or root_path))
            sources = [("Main", main_path), ("Root", root_path)]
            if chest is not None and source_body.startswith(chest + "|"):
                sources.append(("Chest", chest))
            sources.append(("Parent", parent_source))
            if any(source == source_body
                   or source.startswith(source_body + "|")
                   or source == control.offset_path
                   or source.startswith(control.offset_path + "|")
                   for _, source in sources):
                raise ValueError("Follow Spaces 目标依赖自身 FK："
                                 + source_body)
            leaf = control.control_path.rsplit("|", 1)[-1]
            namespace = leaf.split(":", 1)[0] + ":" if ":" in leaf else ""
            stem = namespace + "AdvPy_FollowSpaces" + source_name + "_" + side
            targets = tuple(BodyFitFollowSpaceTarget(
                label, source, 10.0 if label == "Parent" else 0.0,
                stem + label + "MM", stem + label + "Weight")
                for label, source in sources)
            result.append(BodyFitFollowSpacesSpec(
                source_body, control.control_path, control.offset_path,
                control.offset_path.rsplit("|", 1)[0], targets,
                stem + "BM", stem + "OutputMM"))
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Follow Spaces 生成节点名称重复")
    return tuple(result)
