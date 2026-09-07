from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaFitJointHost
        from adv_py.application import (
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            EditFitJointMetadata,
            PlanFitSymmetry,
        )
        from adv_py.core import FitJointPatch, FitSkeletonField

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableSymmetrySelection",
            skipSelect=True,
        )
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        cmds.select(marker, replace=True)
        source_result = BuildSyntheticBodySourceFit(host).apply(container)
        source_by_name = {
            node.short_name: node
            for node in source_result.orientation.verified.hierarchy.joints
        }
        right_source_verified = (
            source_by_name["Hip"].world_position[0] < -0.01
            and source_by_name["Scapula"].world_position[0] < -0.01
        )

        planner = PlanFitSymmetry(host)
        cmds.file(modified=False)
        plan = planner.execute(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        by_name = {instance.output_name: instance for instance in plan.instances}
        side_counts = {
            side: sum(instance.side.value == side for instance in plan.instances)
            for side in ("M", "R", "L")
        }
        topology_verified = (
            by_name["Root_M"].parent_output_path is None
            and by_name["Hip_R"].parent_output_path == "|Root_M"
            and by_name["Knee_L"].parent_output_path == "|Root_M|Hip_L"
            and by_name["Wrist_L"].parent_output_path.endswith("|Elbow_L")
        )
        reflection_verified = (
            by_name["Hip_R"].world_position[0]
            == -by_name["Hip_L"].world_position[0]
            and by_name["Hip_L"].mirrored
            and by_name["Wrist_L"].mirrored
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        EditFitJointMetadata(host).apply(
            (source_by_name["Hip"].path,),
            FitJointPatch.from_values(
                no_mirror=True,
                no_mirror_left=True,
            ),
        )
        left_only_plan = planner.execute(container)
        left_only_names = {
            instance.output_name for instance in left_only_plan.instances
        }
        inherited_left_only_verified = (
            len(left_only_plan.instances) == 22
            and "Hip_R" not in left_only_names
            and "ToesEnd_R" not in left_only_names
            and "Hip_L" in left_only_names
            and "ToesEnd_L" in left_only_names
            and "Wrist_R" in left_only_names
            and "Wrist_L" in left_only_names
        )

        cmds.undo()
        metadata_undo_restored = len(planner.execute(container).instances) == 30
        cmds.undo()
        source_undo_removed_tree = not (cmds.ls(type="joint") or [])
        container_survived = cmds.objExists(container)
        settings_survived = len(
            host.read_fit_skeleton_settings(container).present_fields
        ) == len(FitSkeletonField)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("FitSkeleton", long=True) or []
        remaining += cmds.ls("PortableSymmetrySelection", long=True) or []
        passed = all(
            (
                len(source_by_name) == 18,
                right_source_verified,
                preview_clean,
                len(plan.instances) == 30,
                side_counts == {"M": 6, "R": 12, "L": 12},
                topology_verified,
                reflection_verified,
                selection_preserved,
                inherited_left_only_verified,
                metadata_undo_restored,
                source_undo_removed_tree,
                container_survived,
                settings_survived,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_symmetry_expansion",
            "source_joint_count": len(source_by_name),
            "right_source_verified": right_source_verified,
            "preview_did_not_modify_scene": preview_clean,
            "expanded_instance_count": len(plan.instances),
            "side_counts": side_counts,
            "output_topology_verified": topology_verified,
            "yz_plane_position_reflection_verified": reflection_verified,
            "selection_preserved": selection_preserved,
            "inherited_left_only_verified": inherited_left_only_verified,
            "metadata_undo_restored_default_expansion": metadata_undo_restored,
            "source_single_undo_removed_tree": source_undo_removed_tree,
            "container_survived_undo": container_survived,
            "settings_survived_undo": settings_survived,
            "unrelated_node_survived": marker_survived,
            "cleanup": not remaining,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
