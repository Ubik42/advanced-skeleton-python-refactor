from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BakeBodyExportSkeleton,
            BuildBodyExportSkeleton,
            BuildBodyRootMotion,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            ExportBodyFbx,
        )
        from adv_py.core import (
            plan_body_export_skeleton_bake,
            plan_body_fbx_export_selection,
        )
        from adv_py.core.fit_settings import FitSkeletonValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="FbxExportSelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        shoulder = "|Root_M|Spine1_M|Chest_M|Scapula_R|Shoulder_R"
        for frame, root_x, root_y, root_z, yaw, shoulder_x in (
            (1, 0.0, 0.0, 8.0, 0.0, 0.0),
            (3, 4.0, 6.0, 12.0, 30.0, 20.0),
            (5, 8.0, 12.0, 16.0, 60.0, 40.0),
        ):
            for axis, value in zip("XYZ", (root_x, root_y, root_z)):
                cmds.setKeyframe("|Root_M", attribute=f"translate{axis}", time=frame, value=value)
            cmds.setKeyframe("|Root_M", attribute="rotateZ", time=frame, value=yaw)
            cmds.setKeyframe(shoulder, attribute="rotateX", time=frame, value=shoulder_x)
        cmds.currentTime(3, edit=True, update=True)
        cmds.select(marker, replace=True)
        root_motion_result = BuildBodyRootMotion(host).apply(source_container=container)
        export_result = BuildBodyExportSkeleton(host).apply(source_container=container)
        live_bake_plan = plan_body_export_skeleton_bake(
            export_result.plan.export_skeleton,
            root_motion_result.plan.root_motion,
            start_frame=1,
            end_frame=5,
        )
        live_selection = plan_body_fbx_export_selection(live_bake_plan)
        live_dependencies = host.capture_body_export_dependency_plugs(
            body.root, live_selection.node_paths
        )
        BakeBodyExportSkeleton(host).apply(
            start_frame=1, end_frame=5, source_container=container
        )

        original_selection = cmds.ls(selection=True, long=True) or []
        original_time = float(cmds.currentTime(query=True))
        original_modified = bool(cmds.file(query=True, modified=True))
        with tempfile.TemporaryDirectory(prefix="advpy-fbx-") as directory:
            destination = Path(directory) / "synthetic-character.fbx"
            result = ExportBodyFbx(host).apply(
                destination,
                start_frame=1,
                end_frame=5,
                source_container=container,
            )
            checks = {
                "live_body_dependencies_detected": bool(live_dependencies),
                "explicit_31_node_selection": result.plan.selection.node_count == 31,
                "zero_body_dependencies": not result.plan.body_dependency_plugs,
                "binary_fbx_written": (
                    result.artifact.encoding == "binary"
                    and result.artifact.byte_count == destination.stat().st_size
                    and len(result.artifact.content_sha256) == 64
                ),
                "selection_preserved": (cmds.ls(selection=True, long=True) or []) == original_selection,
                "current_time_preserved": abs(float(cmds.currentTime(query=True)) - original_time) < 1e-6,
                "modified_state_preserved": bool(cmds.file(query=True, modified=True)) == original_modified,
                "plugin_version_recorded": bool(result.plugin_version),
            }
            try:
                ExportBodyFbx(host).apply(
                    destination,
                    start_frame=1,
                    end_frame=5,
                    source_container=container,
                )
                refused_overwrite = False
            except FitSkeletonValidationError:
                refused_overwrite = True
            checks["existing_target_refused"] = refused_overwrite

            cmds.file(new=True, force=True)
            cmds.file(
                str(destination),
                i=True,
                type="FBX",
                ignoreVersion=True,
                mergeNamespacesOnClash=False,
                options="fbx",
            )
            imported_joints = cmds.ls(type="joint", long=True) or []
            root_motion = cmds.ls("AdvPy_GameRootMotion", long=True, type="joint") or []
            export_joints = cmds.ls("AdvPy_EXP_*", long=True, type="joint") or []
            root_motion_keys = cmds.keyframe(
                "AdvPy_GameRootMotion.translateX", query=True, timeChange=True
            ) or []
            shoulder_keys = cmds.keyframe(
                "AdvPy_EXP_Shoulder_R.rotateX", query=True, timeChange=True
            ) or []
            checks.update({
                "fresh_import_has_31_joints": len(imported_joints) == 31,
                "fresh_import_has_one_root_motion": (
                    len(root_motion) == 1
                    and not (cmds.listRelatives(root_motion[0], parent=True) or [])
                ),
                "fresh_import_has_30_export_joints": len(export_joints) == 30,
                "fresh_import_animation_range": (
                    tuple(round(float(value)) for value in root_motion_keys) == (1, 2, 3, 4, 5)
                    and tuple(round(float(value)) for value in shoulder_keys) == (1, 2, 3, 4, 5)
                ),
                "no_fit_body_or_control_leakage": not any(
                    cmds.ls(pattern, long=True) or []
                    for pattern in ("FitSkeleton", "Root_M", "*_CTRL", "AdvPy_CharacterControls")
                ),
            })

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "fbx_plugin_version": result.plugin_version,
            "pid": os.getpid(),
            "slice": "body_fbx_export",
            **checks,
            "source_joint_count": len(body.joints),
            "imported_joint_count": len(imported_joints),
            "fbx_byte_count": result.artifact.byte_count,
            "fbx_sha256": result.artifact.content_sha256,
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
