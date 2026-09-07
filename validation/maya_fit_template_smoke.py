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
            CreateFitSkeleton,
            CreateFitTemplate,
            CreateMinimalFitTemplate,
        )
        from adv_py.core import (
            FitSkeletonField,
            FitSkeletonValidationError,
            FitUpAxis,
            synthetic_upper_body_fit_template,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply(
            "PortableFitTemplate",
            display_radius=2.5,
        ).state.path
        marker = cmds.createNode(
            "transform",
            name="PortableTemplateSelection",
            skipSelect=True,
        )
        cmds.select(marker, replace=True)

        use_case = CreateMinimalFitTemplate(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, segment_length=4.0)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, segment_length=4.0)
        names = tuple(node.short_name for node in result.hierarchy.joints)
        positions = tuple(node.local_position for node in result.hierarchy.joints)
        labels = tuple(
            host.read_joint_label(path).text for path in result.joint_paths
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]

        duplicate_blocked = False
        try:
            use_case.apply(container, segment_length=4.0)
        except FitSkeletonValidationError:
            duplicate_blocked = True
        joints_unchanged = len(cmds.ls(type="joint") or []) == 3

        cmds.undo()
        undo_removed_joints = not (cmds.ls(type="joint") or [])
        container_survived = cmds.objExists(container)
        settings_survived = len(
            host.read_fit_skeleton_settings(container).present_fields
        ) == len(FitSkeletonField)
        marker_survived = cmds.objExists(marker)

        upper_template = synthetic_upper_body_fit_template(FitUpAxis.Z)
        upper_creator = CreateFitTemplate(host)
        cmds.file(modified=False)
        upper_preview = upper_creator.plan(upper_template, container)
        upper_preview_clean = not bool(cmds.file(query=True, modified=True))
        upper_result = upper_creator.apply(upper_template, container)
        upper_names = tuple(
            node.short_name for node in upper_result.hierarchy.joints
        )
        upper_spine2 = next(
            node for node in upper_result.hierarchy.joints
            if node.short_name == "Spine2"
        )
        upper_spine2_children = {
            node.short_name for node in upper_result.hierarchy.joints
            if node.dag_parent == upper_spine2.path
        }
        upper_labels_verified = all(
            host.read_joint_label(path) == spec.label
            for path, spec in zip(upper_result.joint_paths, upper_template.joints)
        )
        upper_selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        upper_duplicate_blocked = False
        try:
            upper_creator.apply(upper_template, container)
        except FitSkeletonValidationError:
            upper_duplicate_blocked = True
        upper_duplicate_unchanged = len(cmds.ls(type="joint") or []) == 14
        cmds.undo()
        upper_undo_removed_joints = not (cmds.ls(type="joint") or [])

        cmds.delete(container, marker)
        remaining = cmds.ls("PortableFitTemplate*", long=True) or []
        remaining += cmds.ls("PortableTemplateSelection", long=True) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                names == ("Root", "Spine1", "Spine2"),
                positions
                == ((0.0, 0.0, 0.0), (0.0, 0.0, 4.0), (0.0, 0.0, 4.0)),
                labels == ("Root", "Spine", "Spine"),
                selection_preserved,
                duplicate_blocked,
                joints_unchanged,
                undo_removed_joints,
                container_survived,
                settings_survived,
                marker_survived,
                upper_preview.ready,
                upper_preview_clean,
                len(upper_names) == 14,
                upper_spine2_children
                == {"Neck", "ClavicleLeft", "ClavicleRight"},
                upper_labels_verified,
                upper_selection_preserved,
                upper_duplicate_blocked,
                upper_duplicate_unchanged,
                upper_undo_removed_joints,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_joint_templates",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "joint_names": names,
            "z_up_positions_verified": positions
            == ((0.0, 0.0, 0.0), (0.0, 0.0, 4.0), (0.0, 0.0, 4.0)),
            "labels_verified": labels == ("Root", "Spine", "Spine"),
            "selection_preserved": selection_preserved,
            "duplicate_create_blocked": duplicate_blocked,
            "duplicate_left_hierarchy_unchanged": joints_unchanged,
            "single_undo_removed_joints": undo_removed_joints,
            "container_survived_undo": container_survived,
            "settings_survived_undo": settings_survived,
            "unrelated_node_survived": marker_survived,
            "upper_body_preview_ready": upper_preview.ready,
            "upper_body_preview_did_not_modify_scene": upper_preview_clean,
            "upper_body_joint_count": len(upper_names),
            "upper_body_spine2_branches_verified": upper_spine2_children
            == {"Neck", "ClavicleLeft", "ClavicleRight"},
            "upper_body_labels_verified": upper_labels_verified,
            "upper_body_selection_preserved": upper_selection_preserved,
            "upper_body_duplicate_create_blocked": upper_duplicate_blocked,
            "upper_body_duplicate_left_hierarchy_unchanged": upper_duplicate_unchanged,
            "upper_body_single_undo_removed_joints": upper_undo_removed_joints,
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
