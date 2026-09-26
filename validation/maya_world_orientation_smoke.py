from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def vectors_match(left, right, tolerance=1e-5):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaFitJointHost
        from adv_py.application import (
            CreateFitSkeleton,
            CreateMinimalFitTemplate,
            EditFitJointMetadata,
            OrientWorldFitJoints,
        )
        from adv_py.core import (
            FitJointPatch,
            FitOrientationRequest,
            FitOrientationValidationError,
        )
        from adv_py.product.maya_panel_controller import MayaPanelController

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="y", rotateView=False)
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply(
            "PortableWorldOrientation",
            display_radius=2.5,
        ).state.path
        CreateMinimalFitTemplate(host).apply(container, segment_length=4.0)
        root = f"{container}|Root"
        spine1 = f"{root}|Spine1"
        cmds.setAttr(f"{spine1}.translateZ", 2.0)
        marker = cmds.createNode(
            "transform",
            name="PortableWorldOrientationSelection",
            skipSelect=True,
        )
        cmds.select(marker, replace=True)
        EditFitJointMetadata(host).apply(
            (root,),
            FitJointPatch.from_values(
                world_orient_up="xDown",
                world_orient_forward="zForward",
            ),
        )

        use_case = OrientWorldFitJoints(host)
        request = FitOrientationRequest((root,))
        before = host.capture_fit_orientation(container)
        before_state = next(item for item in before.joints if item.joint == root)
        before_positions = {
            node.path: node.world_position for node in before.hierarchy.joints
        }
        cmds.file(modified=False)
        preview = use_case.plan(request, container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        expected_axes = (
            (0.0, -1.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        planned_axes_match = len(preview.changes) == 1 and all(
            vectors_match(current, expected)
            for current, expected in zip(
                preview.changes[0].desired_world_axes,
                expected_axes,
            )
        )

        result = use_case.apply(request, container)
        after_state = next(item for item in result.verified.joints if item.joint == root)
        world_axes_match = all(
            vectors_match(current, expected)
            for current, expected in zip(after_state.world_axes, expected_axes)
        )
        positions_preserved = all(
            vectors_match(node.world_position, before_positions[node.path])
            for node in result.verified.hierarchy.joints
        )
        rotate_zero = vectors_match(after_state.rotation, (0.0, 0.0, 0.0))
        metadata_preserved = result.verified.metadata == before.metadata
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        idempotent = not use_case.plan(request, container).changes

        cmds.undo()
        restored = host.capture_fit_orientation(container)
        restored_state = next(item for item in restored.joints if item.joint == root)
        single_undo_restored = (
            vectors_match(restored_state.joint_orient, before_state.joint_orient)
            and all(
                vectors_match(current, previous)
                for current, previous in zip(
                    restored_state.world_axes,
                    before_state.world_axes,
                )
            )
        )
        metadata_survived_undo = restored.metadata == before.metadata

        panel_controller = MayaPanelController()
        cmds.setAttr(f"{root}.jointOrientX", restored_state.joint_orient[0] + 10.)
        panel_world_changes = panel_controller.fit_orient(
            ":", ("Root",), container, world=True)
        panel_world_state = next(item for item in
            host.capture_fit_orientation(container).joints if item.joint == root)
        panel_world_axes_match = all(
            vectors_match(current, expected)
            for current, expected in zip(panel_world_state.world_axes, expected_axes)
        )
        cmds.undo()
        panel_world_undo = vectors_match(
            next(item for item in host.capture_fit_orientation(container).joints
                 if item.joint == root).joint_orient,
            (restored_state.joint_orient[0] + 10.,
             restored_state.joint_orient[1], restored_state.joint_orient[2]),
        )
        cmds.setAttr(f"{root}.jointOrient", *restored_state.joint_orient)

        EditFitJointMetadata(host).apply(
            (root,),
            FitJointPatch.from_values(world_orient_forward="free"),
        )
        cmds.file(modified=False)
        free_before = host.capture_fit_orientation(container)
        free_before_positions = {
            node.path: node.world_position for node in free_before.hierarchy.joints
        }
        free_preview = use_case.plan(request, container)
        free_preview_clean = not bool(cmds.file(query=True, modified=True))
        free_expected_axes = (
            (0.0, -1.0, 0.0),
            (0.0, 0.0, 1.0),
            (-1.0, 0.0, 0.0),
        )
        free_planned_axes_match = len(free_preview.changes) == 1 and all(
            vectors_match(current, expected)
            for current, expected in zip(
                free_preview.changes[0].desired_world_axes,
                free_expected_axes,
            )
        )
        free_result = use_case.apply(request, container)
        free_state = next(item for item in free_result.verified.joints if item.joint == root)
        free_world_axes_match = all(
            vectors_match(current, expected)
            for current, expected in zip(free_state.world_axes, free_expected_axes)
        )
        free_positions_preserved = all(
            vectors_match(node.world_position, free_before_positions[node.path])
            for node in free_result.verified.hierarchy.joints
        )
        free_idempotent = not use_case.plan(request, container).changes
        cmds.undo()
        free_undo_restored = all(
            vectors_match(current, previous)
            for current, previous in zip(
                next(
                    item
                    for item in host.capture_fit_orientation(container).joints
                    if item.joint == root
                ).world_axes,
                next(
                    item for item in free_before.joints if item.joint == root
                ).world_axes,
            )
        )

        cmds.addAttr(
            container,
            longName="worldmatch",
            attributeType="bool",
            defaultValue=True,
            keyable=True,
        )
        cmds.file(modified=False)
        world_match_blocked = False
        try:
            use_case.apply(request, container)
        except FitOrientationValidationError:
            world_match_blocked = True
        world_match_preflight_clean = not bool(cmds.file(query=True, modified=True))

        container_survived = cmds.objExists(container)
        marker_survived = cmds.objExists(marker)
        cmds.delete(container, marker)
        remaining = cmds.ls("PortableWorldOrientation*", long=True) or []
        passed = all(
            (
                preview_clean,
                planned_axes_match,
                world_axes_match,
                positions_preserved,
                rotate_zero,
                metadata_preserved,
                selection_preserved,
                idempotent,
                single_undo_restored,
                metadata_survived_undo,
                panel_world_changes == 1,
                panel_world_axes_match,
                panel_world_undo,
                free_preview_clean,
                free_planned_axes_match,
                free_world_axes_match,
                free_positions_preserved,
                free_idempotent,
                free_undo_restored,
                world_match_blocked,
                world_match_preflight_clean,
                container_survived,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "world_fit_orientation",
            "preview_did_not_modify_scene": preview_clean,
            "planned_axes_match": planned_axes_match,
            "world_axes_match": world_axes_match,
            "world_positions_preserved": positions_preserved,
            "rotate_channels_zero": rotate_zero,
            "metadata_preserved": metadata_preserved,
            "selection_preserved": selection_preserved,
            "repeat_plan_is_noop": idempotent,
            "single_undo_restored_orientation": single_undo_restored,
            "metadata_survived_undo": metadata_survived_undo,
            "panel_world_changes": panel_world_changes,
            "panel_world_axes_match": panel_world_axes_match,
            "panel_world_single_undo": panel_world_undo,
            "free_preview_did_not_modify_scene": free_preview_clean,
            "free_planned_axes_match": free_planned_axes_match,
            "free_world_axes_match": free_world_axes_match,
            "free_world_positions_preserved": free_positions_preserved,
            "free_repeat_plan_is_noop": free_idempotent,
            "free_single_undo_restored_orientation": free_undo_restored,
            "world_match_blocked": world_match_blocked,
            "world_match_preflight_did_not_modify_scene": world_match_preflight_clean,
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
