from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-3):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def position(cmds, path):
    return cmds.xform(path, query=True, worldSpace=True, translation=True)


def constraint_has_half_weights(cmds, constraint, command):
    aliases = command(constraint, query=True, weightAliasList=True) or []
    return len(aliases) == 2 and close(
        tuple(cmds.getAttr(f"{constraint}.{alias}") for alias in aliases),
        (0.5, 0.5),
    )


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyLegBlend,
            BuildBodyLegFkMechanismControls,
            BuildBodyLegIkControls,
            BuildBodyLegMechanisms,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableLegBlendSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit = host.capture_fit_orientation(container)
        cmds.select(marker, replace=True)
        mechanisms = BuildBodyLegMechanisms(host).apply(container).snapshot
        fk = BuildBodyLegFkMechanismControls(host).apply(container)

        use_case = BuildBodyLegBlend(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        blend = use_case.apply(container)
        ik = BuildBodyLegIkControls(host).apply(container)

        right_plug = f"{blend.snapshot.settings_path}.legIkFk_R"
        left_plug = f"{blend.snapshot.settings_path}.legIkFk_L"
        right_fk_control = next(
            state.control_path for state in fk.snapshot.controls
            if state.control_path.endswith("AdvPy_HipFK_R")
        )
        right_ik_control = next(
            state.ankle_control_path for state in ik.snapshot.limbs
            if state.side.value == "R"
        )
        right_fk_ankle = next(
            state.path for state in mechanisms.joints
            if state.path.endswith("AdvPy_AnkleFKDriver_R")
        )
        right_ik_ankle = next(
            state.path for state in mechanisms.joints
            if state.path.endswith("AdvPy_AnkleIKDriver_R")
        )
        right_body_ankle = next(
            state.path for state in body.joints if state.name == "Ankle_R"
        )
        right_body_knee = next(
            state.path for state in body.joints if state.name == "Knee_R"
        )
        left_body_ankle = next(
            state.path for state in body.joints if state.name == "Ankle_L"
        )
        bind_right = position(cmds, right_body_ankle)
        bind_left = position(cmds, left_body_ankle)

        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{right_fk_control}.rotateZ", 20.0)
        fk_drives_body = (
            close(position(cmds, right_body_ankle), position(cmds, right_fk_ankle))
            and not close(position(cmds, right_body_ankle), bind_right)
            and close(position(cmds, right_ik_ankle), bind_right)
        )
        cmds.setAttr(f"{right_fk_control}.rotateZ", 0.0)

        cmds.setAttr(right_plug, 1.0)
        knee = position(cmds, right_body_knee)
        target = tuple(
            ankle + (knee_value - ankle) * 0.25
            for ankle, knee_value in zip(bind_right, knee)
        )
        cmds.xform(right_ik_control, worldSpace=True, translation=target)
        ik_drives_body = (
            close(position(cmds, right_ik_ankle), target)
            and close(position(cmds, right_body_ankle), target)
            and close(position(cmds, right_fk_ankle), bind_right)
        )
        left_independent = (
            close(position(cmds, left_body_ankle), bind_left)
            and close((cmds.getAttr(left_plug),), (0.0,))
        )

        cmds.setAttr(right_plug, 0.5)
        right_side = next(
            side for side in preview.blend.sides if side.side.value == "R"
        )
        orient_half = all(
            constraint_has_half_weights(
                cmds,
                joint.constraint_name,
                cmds.orientConstraint,
            )
            for joint in right_side.joints
        )
        point_half = all(
            constraint_has_half_weights(
                cmds,
                joint.translation_constraint_name,
                cmds.pointConstraint,
            )
            for joint in right_side.joints
            if joint.translation_constraint_name
        )
        cmds.setAttr(right_plug, 0.0)
        cmds.xform(right_ik_control, worldSpace=True, translation=bind_right)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "eight_rotation_constraints": sum(
                len(side.joints) for side in blend.snapshot.sides
            ) == 8,
            "four_translation_constraints": sum(
                joint.translation_constraint_name is not None
                for side in blend.snapshot.sides
                for joint in side.joints
            ) == 4,
            "fk_drives_body": fk_drives_body,
            "ik_drives_body": ik_drives_body,
            "half_rotation_weights": orient_half,
            "half_translation_weights": point_half,
            "left_side_independent": left_independent,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }

        cmds.undo()
        checks["ik_single_undo"] = not cmds.objExists("|AdvPy_LegIKControls")
        cmds.undo()
        checks["blend_single_undo"] = (
            not cmds.objExists("|AdvPy_LegSettings")
            and all(
                not cmds.objExists(joint.constraint_name)
                for side in preview.blend.sides
                for joint in side.joints
            )
        )
        checks["fk_controls_survived"] = cmds.objExists("|AdvPy_LegFKControls")
        checks["mechanisms_survived"] = cmds.objExists("|AdvPy_LegMechanisms")
        checks["body_survived"] = len(
            host.capture_body_skeleton("Root_M").joints
        ) == 30
        checks["fit_survived"] = host.capture_fit_orientation(container) == fit

        cmds.undo()
        cmds.undo()
        checks["unrelated_node_survived"] = cmds.objExists(marker)
        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_Leg*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_fk_ik_rotation_translation_blend",
            **checks,
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
