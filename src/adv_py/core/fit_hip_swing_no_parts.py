"""The 6.925 HipSwinger branch used when Root has no Inbetween Part."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_skeleton import FitDeformProfile
from .fit_inbetween_hip_swing import HipSwingFitSelection


@dataclass(frozen=True, slots=True)
class HipSwingNoPartsTopology:
    """Receivers in the active torso graph, with optional matrix branches."""

    fk_root_path: str
    fk_root_offset_path: str
    root_fkx_path: str
    child_fk_offset_path: str
    leg_lock_matrix_input: str
    root_body_path: str
    child_body_path: str
    fk_root_matrix_input: str | None = None
    child_no_shear_input: str | None = None
    leg_lock_weight: str | None = None
    root_fk_weight: str | None = None
    root_body_matrix_source: str | None = None
    root_child_inverter_matrix_target: str | None = None


@dataclass(frozen=True, slots=True)
class HipSwingNoPartsPlan:
    topology: HipSwingNoPartsTopology
    radius: float
    control_local_x_bias: float
    frame_name: str
    control_offset_name: str
    control_name: str
    reverse_name: str
    reverse_root_name: str
    remove_rotation_matrix_name: str
    remove_rotation_blend_name: str
    remove_rotation_pick_name: str
    remove_rotation_inverse_name: str
    fk_weight_blend_name: str
    root_child_matrix_name: str

    @property
    def frame_path(self) -> str:
        return self.topology.fk_root_path + "|" + self.frame_name

    @property
    def control_path(self) -> str:
        return (self.topology.fk_root_path + "|" + self.control_offset_name
                + "|" + self.control_name)

    @property
    def control_shape_name(self) -> str:
        return self.control_name + "Shape"

    @property
    def reverse_root_path(self) -> str:
        # 6.925 first aligns Reverse under FKOffsetRoot, then reparents it
        # under FKRoot when leg lock is built. This is its final DAG path.
        return (self.topology.fk_root_path + "|" + self.reverse_name
                + "|" + self.reverse_root_name)

    @property
    def root_fkx_constraint(self) -> tuple[str, str]:
        """Source and driven Root FKX for the no-Part parent constraint."""
        return self.reverse_root_path, self.topology.root_fkx_path

    @property
    def root_fkx_constraint_name(self) -> str:
        return "AdvPy_HipSwingRootFKXParent"

    @property
    def control_position_sources(self) -> tuple[str, str]:
        """The visible offset uses the Root/Spine1 midpoint before X bias."""
        return (self.topology.root_body_path,
                self.topology.child_body_path)

    @property
    def reverse_alignment_target(self) -> str:
        """The reverse pivot starts aligned to the selected Root child."""
        return self.topology.child_body_path

    @property
    def matrix_links(self) -> tuple[tuple[str, str], ...]:
        """Directed graph edges; host creates nodes before applying these."""
        frame = self.frame_path
        t = self.topology
        mm = self.remove_rotation_matrix_name
        bm = self.remove_rotation_blend_name
        pick = self.remove_rotation_pick_name
        inverse = self.remove_rotation_inverse_name
        fk_blend = self.fk_weight_blend_name
        child = self.root_child_matrix_name
        return ((self.control_path + ".rotate", self.reverse_name + ".rotate"),) + (
            ((frame + ".worldInverseMatrix[0]", t.fk_root_matrix_input),)
            if t.fk_root_matrix_input else ()
        ) + (
            ((frame + ".worldMatrix[0]", t.child_no_shear_input),)
            if t.child_no_shear_input else ()
        ) + (
            (frame + ".worldMatrix[0]", mm + ".matrixIn[0]"),
            (t.fk_root_offset_path + ".worldInverseMatrix[0]",
             mm + ".matrixIn[1]"),
            (mm + ".matrixSum", bm + ".target[0].targetMatrix"),
        ) + (
            ((t.leg_lock_weight, bm + ".target[0].weight"),)
            if t.leg_lock_weight else ()
        ) + (
            (bm + ".outputMatrix", pick + ".inputMatrix"),
            (pick + ".outputMatrix", inverse + ".inputMatrix"),
            (inverse + ".outputMatrix",
             fk_blend + ".target[0].targetMatrix"),
        ) + (
            ((t.root_fk_weight, fk_blend + ".target[0].weight"),)
            if t.root_fk_weight else ()
        ) + (
            (fk_blend + ".outputMatrix", t.leg_lock_matrix_input),
        ) + ((
            (inverse + ".outputMatrix", child + ".matrixIn[0]"),
            (t.root_body_matrix_source, child + ".matrixIn[1]"),
            (child + ".matrixSum", t.root_child_inverter_matrix_target),
        ) if t.root_child_inverter_matrix_target else ())

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.frame_name, self.control_offset_name, self.control_name,
                self.control_shape_name,
                self.reverse_name, self.reverse_root_name,
                self.remove_rotation_matrix_name,
                self.remove_rotation_blend_name,
                self.remove_rotation_pick_name,
                self.remove_rotation_inverse_name, self.fk_weight_blend_name,
                self.root_fkx_constraint_name) + (
                    (self.root_child_matrix_name,)
                    if self.topology.root_child_inverter_matrix_target else ())


def plan_hip_swing_no_parts(
    selection: HipSwingFitSelection,
    topology: HipSwingNoPartsTopology,
    *,
    radius: float,
    root_profile: FitDeformProfile,
) -> HipSwingNoPartsPlan:
    """Describe the Root reverse pivot and every available receiver.

    The standard Python torso uses a direct Root FKX parent constraint and
    the existing Spine1 FK parent chain. Hosts with the original MEL matrix
    inputs may additionally provide those ports and a Root-child inverter.
    """
    if (not selection.enabled or selection.root_inbetween_count != 0
            or selection.child_name != "Spine1"
            or isinstance(radius, bool)
            or not isinstance(radius, (int, float))
            or not isfinite(radius) or radius <= 0
            or not isinstance(root_profile, FitDeformProfile)):
        raise ValueError("无分段 HipSwinger 需要标准 Root→Spine1 和正半径")
    if not isinstance(topology, HipSwingNoPartsTopology):
        raise ValueError("无分段 HipSwinger 缺少 Root／腿部空间拓扑")
    paths = (topology.fk_root_path, topology.fk_root_offset_path,
             topology.root_fkx_path, topology.root_body_path,
             topology.child_body_path, topology.child_fk_offset_path)
    plugs = (topology.leg_lock_matrix_input,
             *((topology.fk_root_matrix_input,)
               if topology.fk_root_matrix_input else ()),
             *((topology.child_no_shear_input,)
               if topology.child_no_shear_input else ()),
             *((topology.leg_lock_weight,)
               if topology.leg_lock_weight else ()),
             *((topology.root_fk_weight,)
               if topology.root_fk_weight else ()),
             *((topology.root_body_matrix_source,
                topology.root_child_inverter_matrix_target)
               if topology.root_child_inverter_matrix_target else ()))
    if (any(not path.startswith("|") for path in paths)
            or len(set(paths)) != len(paths)
            or any("." not in plug or not plug.split(".", 1)[0]
                   for plug in plugs)
            or len(set(plugs)) != len(plugs)
            or (topology.root_child_inverter_matrix_target is not None
                and topology.root_body_matrix_source is None)
            or (topology.child_no_shear_input is None
                and not topology.child_fk_offset_path.startswith(
                    topology.fk_root_path + "|"))
            or topology.child_body_path.rsplit("|", 1)[-1] != "Spine1_M"
            or topology.root_body_path.rsplit("|", 1)[-1] != "Root_M"):
        raise ValueError("无分段 HipSwinger 的宿主路径或矩阵端口不完整")
    plan = HipSwingNoPartsPlan(
        topology, float(radius),
        -1.4 * root_profile.fat * root_profile.fat_width,
        "AdvPy_FKHSRoot",
        "AdvPy_HipSwingerOffset", "AdvPy_HipSwinger",
        "AdvPy_HipSwingReverse", "AdvPy_HipSwingReverseRoot",
        "AdvPy_FKRootRemoveInbtRotMM2",
        "AdvPy_FKRootRemoveInbtRotBM",
        "AdvPy_FKRootRemoveInbtRotPM",
        "AdvPy_FKRootRemoveInbtRotIM",
        "AdvPy_FKRootRemoveInbtRotBM2",
        "AdvPy_RootXformInverterRemoveInbtRotMM",
    )
    if len(set(plan.node_names)) != len(plan.node_names):
        raise ValueError("无分段 HipSwinger 节点名称重复")
    return plan
