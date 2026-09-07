from __future__ import annotations
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone

def close(a, b, tolerance=1e-3): return all(abs(x-y) <= tolerance for x, y in zip(a, b))

def main(output):
    started = time.perf_counter(); maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BuildBodyArmIkControls, BuildBodyArmMechanisms, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton
        cmds.file(new=True, force=True); cmds.undoInfo(state=True); cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableArmIkSelection", skipSelect=True)
        host = MayaBodyBuildHost(); container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit = host.capture_fit_orientation(container); cmds.select(marker, replace=True)
        mechanisms = BuildBodyArmMechanisms(host).apply(container).snapshot
        use_case = BuildBodyArmIkControls(host); cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=2.0)
        preview_clean = not cmds.file(query=True, modified=True)
        result = use_case.apply(container, control_radius=2.0)
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        right = next(s for s in result.snapshot.limbs if s.side.value == "R")
        wrist_driver = next(j.path for j in mechanisms.joints if j.path.endswith("AdvPy_WristIKDriver_R"))
        body_wrist = next(j.path for j in body.joints if j.name == "Wrist_R")
        body_elbow = next(j.path for j in body.joints if j.name == "Elbow_R")
        body_before = cmds.xform(body_wrist, query=True, worldSpace=True, translation=True)
        elbow_position = cmds.xform(body_elbow, query=True, worldSpace=True, translation=True)
        target = tuple(wrist + (elbow - wrist) * 0.25 for wrist, elbow in zip(right.wrist_position, elbow_position))
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.xform(right.wrist_control_path, worldSpace=True, translation=target)
        solved = close(cmds.xform(wrist_driver, query=True, worldSpace=True, translation=True), target)
        body_isolated = close(cmds.xform(body_wrist, query=True, worldSpace=True, translation=True), body_before)
        cmds.xform(right.wrist_control_path, worldSpace=True, translation=right.wrist_position)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        removed = not cmds.objExists(preview.ik.root_path) and all(not cmds.objExists(s.handle_name) for s in preview.ik.limbs)
        mechanisms_survived = cmds.objExists("|AdvPy_ArmMechanisms")
        body_survived = len(host.capture_body_skeleton("Root_M").joints) == 30
        fit_survived = host.capture_fit_orientation(container) == fit
        cmds.undo(); mechanisms_removed = not cmds.objExists("|AdvPy_ArmMechanisms")
        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls("Root_M", "FitSkeleton", "AdvPy_ArmIKControls", "AdvPy_ArmMechanisms", marker, long=True) or []
        checks = dict(preview_ready=preview.ready, preview_clean=preview_clean, two_sides=len(result.snapshot.limbs)==2, selection_preserved=selection_preserved, ik_target_reached=solved, body_isolated=body_isolated, single_undo_removed_ik=removed, mechanisms_survived_ik_undo=mechanisms_survived, body_survived=body_survived, fit_survived=fit_survived, second_undo_removed_mechanisms=mechanisms_removed, cleanup=not remaining)
        passed = all(checks.values())
        payload = {"host":"maya", "version":str(cmds.about(version=True)), "pid":os.getpid(), "slice":"body_bilateral_rp_ik_controls", **checks, "remaining_nodes":remaining, "duration_seconds":round(time.perf_counter()-started,3), "status":"passed" if passed else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        return 0 if passed else 1
    finally: maya.standalone.uninitialize()

if __name__ == "__main__": raise SystemExit(main(Path(sys.argv[1])))
