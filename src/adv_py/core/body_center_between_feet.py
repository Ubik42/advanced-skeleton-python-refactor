"""Plan ADV Root.centerBetweenFeet on the existing RootX Offset."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


@dataclass(frozen=True, slots=True)
class BodyCenterBetweenFeetSpec:
    root_offset: str
    root_control: str
    offset_parent: str
    right_ik: str
    left_ik: str
    center: str = "AdvPy_RootCenterBetweenFeet"
    point_constraint: str = "AdvPy_RootCenterFeetPoint"
    orient_constraint: str = "AdvPy_RootCenterFeetOrient"
    static_matrix: str = "AdvPy_RootCenterStaticMM"
    attached_matrix: str = "AdvPy_RootCenterFeetMM"
    blend_matrix: str = "AdvPy_RootCenterBM"
    weight_node: str = "AdvPy_RootCenterWeight"
    state_condition: str = "AdvPy_RootCenterNodeState"
    output_matrix: str = "AdvPy_RootCenterOutputMM"
    source_targets: tuple[str,...] = ()

    @property
    def targets(self):
        return self.source_targets or (self.right_ik,self.left_ik)

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.center, self.point_constraint,
                self.orient_constraint, self.static_matrix,
                self.attached_matrix, self.blend_matrix,
                self.weight_node, self.state_condition,
                self.output_matrix)


@dataclass(frozen=True, slots=True)
class BodyCenterBetweenFeetState:
    offset_world: tuple[float, ...]
    parent_world: tuple[float, ...]
    opm_source: str | None
    opm_value: tuple[float, ...]


def plan_body_center_between_feet(
    metadata: tuple[FitJointMetadata, ...], root_x,
    leg_ik: tuple,
) -> BodyCenterBetweenFeetSpec | None:
    roots = tuple(item for item in metadata
                  if item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                  == "Root")
    if len(roots) != 1:
        raise ValueError("Center Between Feet 需要唯一 Root Fit 关节")
    if roots[0].center_between_feet is not True:
        return None
    if root_x is None:
        raise ValueError("Center Between Feet 需要 RootX 控制层")
    by_side = {limb.side.value: limb.ankle_control_path for limb in leg_ik}
    if set(by_side) != {"R", "L"} or len(leg_ik) != 2:
        raise ValueError("Center Between Feet 需要左右 IK Leg 控制器")
    parent = root_x.offset_path.rsplit("|", 1)[0]
    if not parent or any(path.startswith(root_x.offset_path + "|")
                         for path in by_side.values()):
        raise ValueError("Center Between Feet 的 RootX／IK Leg 层级形成循环")
    return BodyCenterBetweenFeetSpec(
        root_x.offset_path, root_x.control_path, parent,
        by_side["R"], by_side["L"])


def plan_source_center_between_feet(root_x,targets):
    """MEL uses every IKLeg control; quadrupeds are not reduced to a pair."""
    if not targets or len(set(targets))!=len(targets):
        raise ValueError('来源 Center Between Feet 缺少唯一 IK Leg 控制')
    if any(path.startswith(root_x.offset_path+'|') for path in targets):
        raise ValueError('来源 Center Between Feet 的 RootX／IK Leg 层级形成循环')
    return BodyCenterBetweenFeetSpec(root_x.offset_path,root_x.control_path,
        root_x.offset_path.rsplit('|',1)[0],targets[0],targets[-1],source_targets=targets)
