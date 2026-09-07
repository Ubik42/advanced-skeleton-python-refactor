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
            OrientSimpleFitChain,
        )
        from adv_py.core import (
            FitOrientationRequest,
            FitOrientationChildSelection,
            FitOrientationValidationError,
            FitWorldAxis,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        host = MayaFitJointHost()
        container = CreateFitSkeleton(host).apply(
            "PortableFitOrientation",
            display_radius=2.5,
        ).state.path
        CreateMinimalFitTemplate(host).apply(container, segment_length=4.0)
        marker = cmds.createNode(
            "transform",
            name="PortableOrientationSelection",
            skipSelect=True,
        )
        cmds.select(marker, replace=True)
        use_case = OrientSimpleFitChain(host)
        request = FitOrientationRequest(("Root", "Spine1"))

        spine1 = "|PortableFitOrientation|Root|Spine1"
        cmds.setAttr(f"{spine1}.jointOrientZ", lock=True)
        cmds.file(modified=False)
        locked_blocked = False
        try:
            use_case.apply(FitOrientationRequest(("Spine1",)), container)
        except FitOrientationValidationError:
            locked_blocked = True
        locked_preflight_clean = not bool(cmds.file(query=True, modified=True))
        cmds.setAttr(f"{spine1}.jointOrientZ", lock=False)

        root = "|PortableFitOrientation|Root"
        cmds.addAttr(
            root,
            longName="worldOrientUp",
            attributeType="enum",
            enumName="xUp:yUp:zUp:xDown:yDown:zDown",
            defaultValue=3,
            keyable=True,
        )
        cmds.addAttr(
            root,
            longName="worldOrientForward",
            attributeType="enum",
            enumName=(
                "xForward:yForward:zForward:xBackward:yBackward:zBackward:free"
            ),
            defaultValue=2,
            keyable=True,
        )
        cmds.file(modified=False)
        world_policy_blocked = False
        try:
            use_case.apply(FitOrientationRequest(("Root",)), container)
        except FitOrientationValidationError:
            world_policy_blocked = True
        world_policy_preflight_clean = not bool(cmds.file(query=True, modified=True))
        cmds.deleteAttr(f"{root}.worldOrientForward")
        cmds.deleteAttr(f"{root}.worldOrientUp")

        before = host.capture_fit_orientation(container)
        before_positions = tuple(
            node.world_position for node in before.hierarchy.joints
        )
        cmds.file(modified=False)
        preview = use_case.plan(request, container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(request, container)
        after_positions = tuple(
            node.world_position for node in result.verified.hierarchy.joints
        )
        positions_preserved = all(
            all(abs(a - b) <= 1e-5 for a, b in zip(current, previous))
            for current, previous in zip(after_positions, before_positions)
        )
        secondary_fallback = all(
            change.secondary_world_axis is FitWorldAxis.Y
            for change in preview.changes
        )
        rotates_zero = all(
            all(abs(value) <= 1e-5 for value in state.rotation)
            for state in result.verified.joints
        )
        end_unchanged = result.verified.joints[-1].joint_orient == (
            0.0,
            0.0,
            0.0,
        )
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        repeat_plan = use_case.plan(request, container)
        idempotent = not repeat_plan.changes

        cmds.undo()
        restored = all(
            all(abs(value) <= 1e-5 for value in state.joint_orient)
            for state in host.capture_fit_orientation(container).joints
        )
        container_survived = cmds.objExists(container)
        marker_survived = cmds.objExists(marker)

        root = "|PortableFitOrientation|Root"
        clavicle = cmds.createNode(
            "joint",
            name="Clavicle",
            parent=root,
            skipSelect=True,
        )
        cmds.setAttr(
            f"{clavicle}.translate", 3.0, 0.0, 2.0, type="double3"
        )
        clavicle_end = cmds.createNode(
            "joint",
            name="ClavicleEnd",
            parent=clavicle,
            skipSelect=True,
        )
        cmds.setAttr(
            f"{clavicle_end}.translate", 2.0, 0.0, 0.0, type="double3"
        )
        cmds.setAttr(
            f"{clavicle}.jointOrient", 10.0, 0.0, 0.0, type="double3"
        )
        cmds.select(marker, replace=True)
        cmds.file(modified=False)
        branch_without_selection_blocked = False
        try:
            use_case.apply(FitOrientationRequest(("Root",)), container)
        except FitOrientationValidationError:
            branch_without_selection_blocked = True
        branch_preflight_clean = not bool(cmds.file(query=True, modified=True))

        branch_before = host.capture_fit_orientation(container)
        branch_positions = {
            node.path: node.world_position for node in branch_before.hierarchy.joints
        }
        branch_orients = {
            state.joint: state.joint_orient for state in branch_before.joints
        }
        branch_request = FitOrientationRequest(
            ("Root",),
            (FitOrientationChildSelection("Root", "Clavicle"),),
        )
        branch_preview = use_case.plan(branch_request, container)
        branch_result = use_case.apply(branch_request, container)
        branch_selected_child = (
            len(branch_preview.changes) == 1
            and branch_preview.changes[0].child.endswith("|Clavicle")
        )
        branch_positions_preserved = all(
            all(abs(a - b) <= 1e-5 for a, b in zip(
                node.world_position,
                branch_positions[node.path],
            ))
            for node in branch_result.verified.hierarchy.joints
        )
        branch_child_orients_preserved = all(
            state.joint_orient == branch_orients[state.joint]
            for state in branch_result.verified.joints
            if state.joint != root
        )
        branch_selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        branch_idempotent = not use_case.plan(branch_request, container).changes
        cmds.undo()
        branch_restored_snapshot = host.capture_fit_orientation(container)
        branch_undo_restored = all(
            state.joint_orient == branch_orients[state.joint]
            for state in branch_restored_snapshot.joints
        )

        cmds.delete(container, marker)
        remaining = cmds.ls("PortableFitOrientation*", long=True) or []
        remaining += cmds.ls("PortableOrientationSelection", long=True) or []
        passed = all(
            (
                locked_blocked,
                locked_preflight_clean,
                world_policy_blocked,
                world_policy_preflight_clean,
                len(preview.changes) == 2,
                preview_clean,
                positions_preserved,
                secondary_fallback,
                rotates_zero,
                end_unchanged,
                selection_preserved,
                idempotent,
                restored,
                container_survived,
                marker_survived,
                branch_without_selection_blocked,
                branch_preflight_clean,
                branch_selected_child,
                branch_positions_preserved,
                branch_child_orients_preserved,
                branch_selection_preserved,
                branch_idempotent,
                branch_undo_restored,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "simple_fit_chain_orientation",
            "locked_joint_orient_blocked": locked_blocked,
            "locked_preflight_did_not_modify_scene": locked_preflight_clean,
            "world_orient_policy_recognized_and_blocked": world_policy_blocked,
            "world_orient_preflight_did_not_modify_scene": world_policy_preflight_clean,
            "preview_change_count": len(preview.changes),
            "preview_did_not_modify_scene": preview_clean,
            "world_positions_preserved": positions_preserved,
            "parallel_up_fallback_verified": secondary_fallback,
            "rotate_channels_remained_zero": rotates_zero,
            "end_joint_orient_unchanged": end_unchanged,
            "selection_preserved": selection_preserved,
            "repeat_plan_is_noop": idempotent,
            "single_undo_restored_joint_orient": restored,
            "container_survived_undo": container_survived,
            "unrelated_node_survived": marker_survived,
            "branch_without_selection_blocked": branch_without_selection_blocked,
            "branch_preflight_did_not_modify_scene": branch_preflight_clean,
            "branch_selected_child_used": branch_selected_child,
            "branch_world_positions_preserved": branch_positions_preserved,
            "all_branch_child_orients_preserved": branch_child_orients_preserved,
            "branch_selection_preserved": branch_selection_preserved,
            "branch_repeat_plan_is_noop": branch_idempotent,
            "branch_single_undo_restored_orientation": branch_undo_restored,
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
