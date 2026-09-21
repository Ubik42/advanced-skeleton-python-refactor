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

        from adv_py.adapters import MayaBodyBuildHost, MayaMocapConnectionHost
        from adv_py.application import (
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            ConnectMocapBody,
            CreateFitSkeleton,
            DisconnectMocapBody,
        )
        from adv_py.core import MocapJointMapping
        from adv_py.adapters.maya_mocap import MayaMocapBakeHost
        from adv_py.application.mocap_bake import BakeMocapBody
        from adv_py.core.mocap_bake import verify_mocap_bake_samples
        from adv_py.core.mocap_mapping import MocapMappingValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        body_host = MayaBodyBuildHost()
        container = CreateFitSkeleton(body_host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(body_host).apply(container)
        body = BuildOrientedBodySkeleton(body_host).apply(container).snapshot

        cmds.namespace(add="TakeA")
        hips = cmds.createNode("joint", name="TakeA:Hips", skipSelect=True)
        spine = cmds.createNode("joint", name="TakeA:Spine", parent=hips, skipSelect=True)
        chest = cmds.createNode("joint", name="TakeA:Chest", parent=spine, skipSelect=True)
        neck = cmds.createNode("joint", name="TakeA:Neck", parent=chest, skipSelect=True)
        cmds.createNode("joint", name="TakeA:Head", parent=neck, skipSelect=True)
        marker = cmds.createNode("transform", name="MocapConnectionSelection", skipSelect=True)
        for frame, hips_x, hips_yaw, spine_pitch in (
            (1, 0.0, 0.0, 0.0),
            (10, 5.0, 35.0, 12.0),
            (20, 12.0, 80.0, -8.0),
        ):
            cmds.setKeyframe(hips, attribute="translateX", time=frame, value=hips_x)
            cmds.setKeyframe(hips, attribute="rotateY", time=frame, value=hips_yaw)
            cmds.setKeyframe(spine, attribute="rotateX", time=frame, value=spine_pitch)
        cmds.currentTime(10, edit=True, update=True)
        cmds.select(marker, replace=True)

        mappings = (
            MocapJointMapping("Hips", "Root_M", True, True),
            MocapJointMapping("Spine", "Spine1_M"),
            MocapJointMapping("Chest", "Chest_M"),
            MocapJointMapping("Neck", "Neck_M"),
            MocapJointMapping("Head", "Head_M"),
        )
        host = MayaMocapBakeHost()
        connected = ConnectMocapBody(host).execute("|TakeA:Hips", mappings)
        selection = tuple(cmds.ls(selection=True, long=True) or [])
        source_before = host.capture_mocap_source("|TakeA:Hips")
        curves_before = set(cmds.ls(type="animCurve") or [])
        options = dict(start_frame=2, end_frame=20, sample_by=2)
        use_case = BakeMocapBody(host)
        undo_before = cmds.undoInfo(query=True, undoName=True)
        modified_before = cmds.file(query=True, modified=True)
        nodes_before = set(cmds.ls(long=True) or [])
        plan = use_case.plan("|TakeA:Hips", mappings, **options)
        expected = host.sample_mocap_body(plan)
        checks = {
            "plan_and_sampling_preserve_undo": cmds.undoInfo(query=True, undoName=True) == undo_before,
            "plan_and_sampling_preserve_nodes": set(cmds.ls(long=True) or []) == nodes_before,
            "plan_and_sampling_preserve_modified": cmds.file(query=True, modified=True) == modified_before,
            "sampling_preserves_time": cmds.currentTime(query=True) == 10,
        }
        cmds.setAttr("Root_M.translateX", lock=True)
        try:
            use_case.execute("|TakeA:Hips", mappings, **options)
            checks["locked_target_rejected"] = False
        except MocapMappingValidationError:
            checks["locked_target_rejected"] = all(cmds.objExists(s.name) for s in plan.connection.constraints)
        finally:
            cmds.setAttr("Root_M.translateX", lock=False)

        foreign = cmds.createNode("transform", name="ForeignConsumer", skipSelect=True)
        cmds.connectAttr(plan.connection.constraints[0].name + ".constraintTranslateX", foreign + ".translateX")
        try:
            use_case.execute("|TakeA:Hips", mappings, **options)
            checks["external_consumer_rejected"] = False
        except MocapMappingValidationError:
            checks["external_consumer_rejected"] = cmds.isConnected(
                plan.connection.constraints[0].name + ".constraintTranslateX", foreign + ".translateX")
        cmds.delete(foreign)

        class FailedReadbackHost(MayaMocapBakeHost):
            def verify_mocap_keys(self, plan, samples):
                super().verify_mocap_keys(plan, samples)
                raise MocapMappingValidationError("Injected postcheck failure")

        try:
            BakeMocapBody(FailedReadbackHost()).execute("|TakeA:Hips", mappings, **options)
            checks["failure_rolled_back"] = False
        except MocapMappingValidationError:
            checks["failure_rolled_back"] = (
                all(cmds.objExists(s.name) for s in plan.connection.constraints)
                and set(cmds.ls(type="animCurve") or []) == curves_before
                and cmds.currentTime(query=True) == 10)
        verify_mocap_bake_samples(plan, expected, host.sample_mocap_body(plan))
        samples = use_case.execute("|TakeA:Hips", mappings, **options)
        host.verify_mocap_keys(plan, samples)
        verify_mocap_bake_samples(plan, expected, host.sample_mocap_body(plan))
        checks["sampled_poses_and_keys_match"] = True
        checks["constraints_removed"] = not host.find_mocap_name_collisions(plan.connection)
        checks["eighteen_direct_curves"] = len(set(cmds.ls(type="animCurve") or []) - curves_before) == 18
        checks["time_preserved_after_bake"] = cmds.currentTime(query=True) == 10
        checks["selection_preserved"] = tuple(cmds.ls(selection=True, long=True) or []) == selection
        checks["source_unchanged"] = host.capture_mocap_source("|TakeA:Hips") == source_before
        cmds.undo()
        checks["single_undo_restores_constraints"] = all(cmds.objExists(s.name) for s in plan.connection.constraints)
        checks["single_undo_removes_keys"] = set(cmds.ls(type="animCurve") or []) == curves_before
        checks["undo_preserves_time"] = cmds.currentTime(query=True) == 10
        verify_mocap_bake_samples(plan, expected, host.sample_mocap_body(plan))
        cmds.redo()
        host.verify_mocap_keys(plan, samples)
        verify_mocap_bake_samples(plan, expected, host.sample_mocap_body(plan))
        checks["redo_restores_bake"] = not host.find_mocap_name_collisions(plan.connection)
        cmds.delete(hips)
        verify_mocap_bake_samples(plan, expected, host.sample_mocap_body(plan))
        checks["playback_independent_of_source"] = True
        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (cmds.ls("Root_M", "FitSkeleton", "TakeA:*", long=True) or [])
        result = {
            "host": "maya", "version": str(cmds.about(version=True)), "pid": os.getpid(),
            "slice": "mocap_body_bake", **checks, "sample_count": len(samples),
            "channel_count": len(plan.channels), "key_count": len(samples) * len(plan.channels),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if all(checks.values()) else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
