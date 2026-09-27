"""Root Inbetween HipSwingReverse graph from the 6.925 OPM branch."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_part import FitPartJointSpec
from .fit_orientation import FitOrientationSnapshot


@dataclass(frozen=True, slots=True)
class HipSwingFitSelection:
    enabled: bool
    root_joint: str
    child_joint: str
    child_name: str
    root_inbetween_count: int


def plan_hip_swing_fit_selection(
    fit: FitOrientationSnapshot,
) -> HipSwingFitSelection:
    """Follow MEL's default Spine1 and explicit root-child label rules."""
    nodes = {node.path: node for node in fit.hierarchy.joints}
    metadata = {item.joint: item for item in fit.metadata}
    if (len(nodes) != len(fit.hierarchy.joints)
            or len(metadata) != len(fit.metadata)
            or set(nodes) != set(metadata)):
        raise ValueError("HipSwinger 需要完整唯一的 Fit 元数据")
    roots = [node for node in nodes.values()
             if node.short_name == "Root"
             and node.dag_parent == fit.hierarchy.container]
    if len(roots) != 1:
        raise ValueError("HipSwinger 需要唯一的 Fit Root")
    root = roots[0]
    children = [node for node in nodes.values()
                if node.dag_parent == root.path]
    labelled = [node for node in children
                if metadata[node.path].hip_swinger is not None]
    if len(labelled) > 1:
        raise ValueError("Root 下有多个 HipSwinger 来源标记")
    child = (labelled[0] if labelled else next(
        (node for node in children if node.short_name == "Spine1"),
        None))
    if child is None:
        raise ValueError("HipSwinger 缺少 Spine1 或显式标记的 Root 子关节")
    return HipSwingFitSelection(
        metadata[root.path].hip_swinger is not False,
        root.path, child.path, child.short_name,
        metadata[root.path].inbetween_joints or 0,
    )


@dataclass(frozen=True, slots=True)
class HipSwingReversePart:
    index: int
    name: str
    aligned_name: str
    aligned_matrix_name: str
    correction_name: str | None
    fk_matrix_name: str | None


@dataclass(frozen=True, slots=True)
class HipSwingReversePlan:
    start_fk_offset_path: str
    start_fk_control_path: str
    start_body_path: str
    end_body_path: str
    root_inbetween_matrix_name: str
    part1_name: str
    count: int
    rotate_order: int
    radius: float
    control_offset_name: str
    control_name: str
    reverse_name: str
    blend_name: str
    decompose_name: str
    parts: tuple[HipSwingReversePart, ...]

    @property
    def control_path(self) -> str:
        return (self.start_fk_control_path + "|" + self.control_offset_name
                + "|" + self.control_name)

    @property
    def reverse_root_name(self) -> str:
        return self.parts[0].aligned_name


def plan_hip_swing_reverse(
    body_parts: tuple[FitPartJointSpec, ...], *,
    start_fk_offset_path: str,
    start_fk_control_path: str,
    end_body_path: str,
    radius: float,
) -> HipSwingReversePlan:
    """Insert per-Part correction matrices before the existing FK matrices.

    The source MEL builds reverse transforms from count down to zero and
    inserts their relative matrices into RootPart FKMM. Index zero also
    rebases RootInbetweenMM. The graph is planned only for a Root Part chain;
    HipSwinger without Root Inbetween needs a separate branch.
    """
    if (not body_parts or not start_fk_offset_path.startswith("|")
            or not start_fk_control_path.startswith(
                start_fk_offset_path + "|")
            or not end_body_path.startswith("|")
            or isinstance(radius, bool)
            or not isinstance(radius, (int, float))
            or not isfinite(radius) or radius <= 0):
        raise ValueError("HipSwingReverse 需要 Root FK 控制和正半径")
    ordered = tuple(sorted(body_parts, key=lambda item: item.index))
    first = ordered[0]
    if (first.start_body_name != "Root_M"
            or len({part.name for part in ordered}) != len(ordered)
            or any(part.kind != "inbetween"
                   or part.start_body != first.start_body
                   or part.end_body != first.end_body
                   or part.count != len(ordered)
                   or part.index != index
                   or part.rotation_order != first.rotation_order
                   for index, part in enumerate(ordered, 1))):
        raise ValueError("HipSwingReverse 仅接受连续 Root Inbetween Part")
    n = len(ordered)
    parts = tuple(HipSwingReversePart(
        index,
        f"AdvPy_HipSwingReversePart{index}",
        f"AdvPy_HipSwingReversePart{index}A",
        f"AdvPy_HipSwingReversePart{index}AMM",
        (f"AdvPy_RootPart{index}_M_HipSwingMM"
         if index else None),
        ("AdvPy_" + ordered[index - 1].name + "_InbetweenFKMM"
         if index else None),
    ) for index in range(n + 1))
    return HipSwingReversePlan(
        start_fk_offset_path, start_fk_control_path,
        first.start_body, end_body_path, "AdvPy_Root_M_InbetweenMM",
        first.name, n, first.rotation_order, float(radius),
        "AdvPy_HipSwingerOffset", "AdvPy_HipSwinger",
        "AdvPy_HipSwingReverse", "AdvPy_HipSwingReversePartBM",
        "AdvPy_HipSwingPartDM", parts,
    )
