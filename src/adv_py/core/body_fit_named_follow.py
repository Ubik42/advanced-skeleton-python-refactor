"""Plan ADV's per-target follow* channels for built FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata
from .source_fit_identity import source_fit_build_name, source_fit_control_matches


@dataclass(frozen=True, slots=True)
class BodyFitNamedFollowTarget:
    name: str
    weight: float
    matrix_node: str
    weight_node: str


@dataclass(frozen=True, slots=True)
class BodyFitNamedFollowSpec:
    source_body: str
    fk_control: str
    fk_offset: str
    receiver: str
    side: str
    targets: tuple[BodyFitNamedFollowTarget, ...]
    blend_node: str
    receiver_node: str

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.blend_node, self.receiver_node) + tuple(
            node for target in self.targets
            for node in (target.matrix_node, target.weight_node))


@dataclass(frozen=True, slots=True)
class BodyFitNamedFollowState:
    target_paths: tuple[str, ...]
    target_worlds: tuple[tuple[float, ...], ...]
    offset_world: tuple[float, ...]
    receiver_world: tuple[float, ...]
    receiver_opm_source: str | None
    receiver_opm_value: tuple[float, ...]


def plan_body_fit_named_follow(
    metadata: tuple[FitJointMetadata, ...], controls: tuple,
    body_joints: tuple, *, instances: tuple = (),
) -> tuple[BodyFitNamedFollowSpec, ...]:
    by_name = {joint.name.rsplit(":", 1)[-1]: joint.path
               for joint in body_joints}
    if len(by_name) != len(body_joints):
        raise ValueError("Fit Follow* Body 关节短名重复")
    result = []
    used = set()
    for item in metadata:
        if not item.follow_by_name:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if instances:
            source_name = source_fit_build_name(source_name)
        for control in controls:
            if not source_fit_control_matches(item, control, instances):
                continue
            if control.control_path in used:
                raise ValueError("Fit Follow* 来源 FK 控制重复："
                                 + control.control_path)
            used.add(control.control_path)
            side = control.side.value
            source_body = by_name.get(source_name + "_" + side)
            if source_body is None:
                raise ValueError("Fit Follow* 来源 Body 关节缺失："
                                 + source_name + "_" + side)
            prefix = control.offset_path + "|"
            if not control.control_path.startswith(prefix):
                raise ValueError("Fit Follow* 控制器不在 FK Offset 下")
            receiver = prefix + control.control_path[len(prefix):].split("|", 1)[0]
            leaf = control.control_path.rsplit("|", 1)[-1]
            namespace = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
            stem = namespace + "AdvPy_FollowByName" + source_name + "_" + side
            targets = tuple(BodyFitNamedFollowTarget(
                name, float(weight), stem + name + "MM",
                stem + name + "Weight")
                for name, weight in item.follow_by_name)
            result.append(BodyFitNamedFollowSpec(
                source_body, control.control_path, control.offset_path,
                receiver, side, targets, stem + "BM", stem + "ReceiverMM"))
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Fit Follow* 生成节点名称重复")
    return tuple(result)
