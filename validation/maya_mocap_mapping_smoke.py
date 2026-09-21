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

        from adv_py.adapters import MayaBodyBuildHost, MayaMocapMappingReader
        from adv_py.application import (
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            InspectMocapBodyMapping,
            save_mocap_mapping_preset,load_mocap_mapping_preset,
        )
        from adv_py.core import MocapJointMapping,MocapMappingPreset

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
        marker = cmds.createNode("transform", name="MocapMappingSelection", skipSelect=True)
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
        use_case = InspectMocapBodyMapping(MayaMocapMappingReader())
        before_nodes = tuple(cmds.ls(long=True) or [])
        before_selection = tuple(cmds.ls(selection=True, long=True) or [])
        before_time = float(cmds.currentTime(query=True))
        before_modified = bool(cmds.file(query=True, modified=True))
        before_undo = str(cmds.undoInfo(query=True, undoName=True) or "")

        inspection = use_case.execute("|TakeA:Hips", mappings)
        plan = inspection.require_valid()
        read_only_preserved = (
            tuple(cmds.ls(long=True) or []) == before_nodes
            and tuple(cmds.ls(selection=True, long=True) or []) == before_selection
            and abs(float(cmds.currentTime(query=True)) - before_time) < 1e-9
            and bool(cmds.file(query=True, modified=True)) == before_modified
            and str(cmds.undoInfo(query=True, undoName=True) or "") == before_undo
        )

        reversed_mapping = (
            mappings[0],
            MocapJointMapping("Spine", "Head_M"),
            mappings[2],
            mappings[3],
            MocapJointMapping("Head", "Spine1_M"),
        )
        invalid = use_case.execute("|TakeA:Hips", reversed_mapping)
        invalid_codes = {issue.code for issue in invalid.issues}
        output.parent.mkdir(parents=True,exist_ok=True)
        preset=MocapMappingPreset('Take A five-joint test',mappings,30)
        preset_path=output.with_name('mapping-preset.json')
        save_mocap_mapping_preset(preset,preset_path)
        loaded=load_mocap_mapping_preset(preset_path)
        preset_plan=use_case.execute('|TakeA:Hips',loaded.mappings,
                                     expected_body_joint_count=loaded.expected_body_joint_count).require_valid()
        checks = {
            "owned_body_detected": len(body.joints) == 30,
            "explicit_mapping_valid": inspection.valid,
            "five_entries_resolved": len(plan.entries) == 5,
            "source_namespace_preserved": plan.source_namespace == "TakeA",
            "clip_range_preserved": (
                plan.start_time == 1.0 and plan.end_time == 20.0
            ),
            "root_paths_resolved": (
                plan.entries[0].source_path == "|TakeA:Hips"
                and plan.entries[0].target_path == "|Root_M"
                and plan.entries[0].transfer_translation
                and plan.entries[0].transfer_rotation
            ),
            "animated_attributes_resolved": (
                plan.entries[0].animated_attributes == ("rotateY", "translateX")
                and plan.entries[1].animated_attributes == ("rotateX",)
                and plan.entries[-1].animated_attributes == ()
            ),
            "reversed_topology_detected": "topology_mismatch" in invalid_codes,
            "inspection_is_read_only": read_only_preserved,
            "preset_round_trip_resolves_same_mapping": loaded==preset and preset_plan==plan,
        }

        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (
            cmds.ls("Root_M", "FitSkeleton", "TakeA:*", long=True) or []
        )
        passed = all(checks.values())
        result = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "mocap_body_mapping",
            **checks,
            "body_joint_count": len(body.joints),
            "mapping_count": len(plan.entries),
            "start_time": plan.start_time,
            "end_time": plan.end_time,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
