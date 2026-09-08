from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def run_axis(cmds, axis):
    from adv_py.adapters import MayaBodyBuildHost
    from adv_py.application import BuildBodyRootMotion
    from adv_py.core import audit_body_root_motion, oriented_body_provenance

    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    cmds.upAxis(axis=axis.lower(), rotateView=False)
    marker = cmds.createNode(
        "transform",
        name=f"RootMotion{axis}Selection",
        skipSelect=True,
    )
    host = MayaBodyBuildHost()
    container = cmds.createNode("transform", name="FitSkeleton", skipSelect=True)
    root = cmds.createNode("joint", name="Root_M", skipSelect=True)
    provenance = oriented_body_provenance("|FitSkeleton", 1)
    with host.transaction("创建 Root Motion 自生成验证 Body"):
        host.write_body_provenance("|Root_M", provenance)
    body = host.capture_body_skeleton("Root_M")
    before = host.capture_body_skeleton("Root_M")
    cmds.select(marker, replace=True)

    result = BuildBodyRootMotion(host).apply(source_container="|FitSkeleton")
    plan = result.plan.root_motion
    selection_preserved = (cmds.ls(selection=True) or []) == [marker]

    source_translate = (3.0, 4.0, 5.0)
    source_rotate = (11.0, 22.0, 33.0)
    cmds.undoInfo(stateWithoutFlush=False)
    cmds.setAttr(f"{body.root}.translate", *source_translate, type="double3")
    cmds.setAttr(f"{body.root}.rotate", *source_rotate, type="double3")
    cmds.dgdirty(allPlugs=True)
    current = host.capture_body_root_motion(plan)
    expected_translate = (
        (3.0, 0.0, 5.0) if axis == "Y" else (3.0, 4.0, 0.0)
    )
    expected_rotation = (
        (0.0, 22.0, 0.0) if axis == "Y" else (0.0, 0.0, 33.0)
    )
    source_drives_planar_yaw = (
        close(current.translation, expected_translate)
        and close(current.rotation, expected_rotation)
    )
    audit_passes_after_motion = not audit_body_root_motion(plan, current)
    body_hierarchy_preserved = (
        host.capture_body_skeleton("Root_M").root == before.root
        and len(host.capture_body_skeleton("Root_M").joints) == len(before.joints)
    )

    cmds.undoInfo(stateWithoutFlush=True)
    cmds.undo()
    root_motion_removed = not any(
        cmds.ls(name, long=True) or [] for name in plan.node_names
    )
    body_survived = bool(cmds.ls("Root_M", long=True, type="joint") or [])
    fit_survived = bool(cmds.ls("FitSkeleton", long=True) or [])
    marker_survived = cmds.objExists(marker)

    cmds.delete("|Root_M", container, marker)
    remaining = cmds.ls(
        "Root_M",
        "FitSkeleton",
        "AdvPy_GameRootMotion*",
        marker,
        long=True,
    ) or []
    return {
        "up_axis": axis,
        "joint_count": len(before.joints),
        "translation_axes": list(plan.translation_axes),
        "rotation_axis": plan.rotation_axis,
        "source_drives_planar_yaw": source_drives_planar_yaw,
        "audit_passes_after_motion": audit_passes_after_motion,
        "body_hierarchy_preserved": body_hierarchy_preserved,
        "selection_preserved": selection_preserved,
        "single_undo_removed_root_motion": root_motion_removed,
        "body_survived_undo": body_survived,
        "fit_survived_undo": fit_survived,
        "marker_survived_undo": marker_survived,
        "cleanup": not remaining,
    }


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        axes = [run_axis(cmds, axis) for axis in ("Y", "Z")]
        passed = all(
            value
            for result in axes
            for key, value in result.items()
            if key not in {"up_axis", "joint_count", "translation_axes", "rotation_axis"}
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_game_root_motion",
            "axes": axes,
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
