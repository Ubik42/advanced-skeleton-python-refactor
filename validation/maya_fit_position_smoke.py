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
            CreateMinimalFitTemplate,
            EditFitJointPositions,
        )
        from adv_py.core import (
            FitJointPositionEdit,
            FitJointPositionPatch,
            FitPositionValidationError,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply(
            "PortableFitPosition",
            display_radius=2.5,
        ).state.path
        CreateMinimalFitTemplate(host).apply(container, segment_length=4.0)
        marker = cmds.createNode(
            "transform",
            name="PortablePositionSelection",
            skipSelect=True,
        )
        cmds.select(marker, replace=True)
        editor = EditFitJointPositions(host)

        root_center_blocked = False
        cmds.file(modified=False)
        try:
            editor.apply(
                FitJointPositionPatch(
                    (FitJointPositionEdit("Root", (0.5, 0.0, 0.0)),)
                ),
                container,
            )
        except FitPositionValidationError:
            root_center_blocked = True
        root_preflight_clean = not bool(cmds.file(query=True, modified=True))

        spine1 = "|PortableFitPosition|Root|Spine1"
        cmds.setAttr(f"{spine1}.tz", lock=True)
        cmds.file(modified=False)
        locked_axis_blocked = False
        try:
            editor.apply(
                FitJointPositionPatch(
                    (FitJointPositionEdit("Spine1", (0.0, 0.0, 5.0)),)
                ),
                container,
            )
        except FitPositionValidationError:
            locked_axis_blocked = True
        locked_preflight_clean = not bool(cmds.file(query=True, modified=True))
        cmds.setAttr(f"{spine1}.tz", lock=False)

        patch = FitJointPositionPatch(
            (
                FitJointPositionEdit("Spine1", (0.0, 0.0, 5.0)),
                FitJointPositionEdit("Spine2", (0.0, 0.0, 3.0)),
            )
        )
        cmds.file(modified=False)
        preview = editor.plan(patch, container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = editor.apply(patch, container)
        positions_applied = tuple(
            node.local_position
            for node in result.verified_hierarchy.joints
            if node.short_name in ("Spine1", "Spine2")
        ) == ((0.0, 0.0, 5.0), (0.0, 0.0, 3.0))
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        hierarchy_unchanged = tuple(
            node.short_name for node in result.verified_hierarchy.joints
        ) == ("Root", "Spine1", "Spine2")

        cmds.undo()
        restored = (
            cmds.getAttr(f"{spine1}.tz") == 4.0
            and cmds.getAttr("|PortableFitPosition|Root|Spine1|Spine2.tz") == 4.0
        )
        container_survived = cmds.objExists(container)
        marker_survived = cmds.objExists(marker)

        cmds.delete(container, marker)
        remaining = cmds.ls("PortableFitPosition*", long=True) or []
        remaining += cmds.ls("PortablePositionSelection", long=True) or []
        passed = all(
            (
                root_center_blocked,
                root_preflight_clean,
                locked_axis_blocked,
                locked_preflight_clean,
                len(preview.changes) == 2,
                preview_clean,
                positions_applied,
                selection_preserved,
                hierarchy_unchanged,
                restored,
                container_survived,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_joint_position_edit",
            "root_center_preflight_blocked": root_center_blocked,
            "root_preflight_did_not_modify_scene": root_preflight_clean,
            "locked_axis_preflight_blocked": locked_axis_blocked,
            "locked_preflight_did_not_modify_scene": locked_preflight_clean,
            "preview_change_count": len(preview.changes),
            "preview_did_not_modify_scene": preview_clean,
            "positions_applied": positions_applied,
            "selection_preserved": selection_preserved,
            "hierarchy_unchanged": hierarchy_unchanged,
            "single_undo_restored_positions": restored,
            "container_survived_undo": container_survived,
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
