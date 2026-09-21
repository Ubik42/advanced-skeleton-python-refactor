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

        from adv_py.adapters import MayaBodyBuildHost,MayaMocapSourceReader,MayaMocapClipHost
        from adv_py.application import (
            BakeBodyExportSkeleton,
            BuildBodyExportSkeleton,
            BuildBodyRootMotion,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            ExportBodyFbx,
            InspectMocapSource,
            ImportMocapFbx,
        )
        from adv_py.core import (
            BodyFbxEncoding,
            BodyFbxCurvePolicy,
            BodyFbxExportProfile,
            BodyFbxFileVersion,
            BodyFbxLinearUnit,
            BodyFbxNamingProfile,
            FitUpAxis,
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
        original_undo_name = str(cmds.undoInfo(query=True, undoName=True) or "")
        with tempfile.TemporaryDirectory(prefix="advpy-fbx-") as directory:
            destination = Path(directory) / "synthetic-character.fbx"
            result = ExportBodyFbx(host).apply(
                destination,
                start_frame=1,
                end_frame=5,
                source_container=container,
            )
            converted_destination = Path(directory) / "synthetic-character-y-up-m.fbx"
            converted_profile = BodyFbxExportProfile(
                BodyFbxFileVersion.FBX_2018,
                FitUpAxis.Y,
                BodyFbxLinearUnit.METER,
                BodyFbxEncoding.ASCII,
            )
            converted_result = ExportBodyFbx(host).apply(
                converted_destination,
                start_frame=1,
                end_frame=5,
                source_container=container,
                profile=converted_profile,
            )
            named_destination=Path(directory)/'engine-named-character.fbx'
            named_profile=BodyFbxNamingProfile('EngineRoot',
                (('Root_M','pelvis'),('Spine1_M','spine_01'),('Head_M','head')))
            named_result=ExportBodyFbx(host).apply(named_destination,start_frame=1,end_frame=5,
                source_container=container,naming_profile=named_profile)
            reduced_destination=Path(directory)/'linear-reduced-character.fbx'
            reduced_profile=BodyFbxExportProfile(
                BodyFbxFileVersion.FBX_2020, FitUpAxis.Z,
                BodyFbxLinearUnit.CENTIMETER, BodyFbxEncoding.BINARY,
                BodyFbxCurvePolicy.LOSSLESS_LINEAR,
            )
            reduced_result=ExportBodyFbx(host).apply(
                reduced_destination,start_frame=1,end_frame=5,
                source_container=container,profile=reduced_profile)
            checks = {
                "live_body_dependencies_detected": bool(live_dependencies),
                "explicit_31_node_selection": result.plan.selection.node_count == 31,
                "published_names_are_canonical": (
                    result.plan.selection.published_root_path == "|RootMotion"
                    and not any(
                        "AdvPy_EXP_" in path or ":" in path
                        for path in result.plan.selection.published_paths
                    )
                ),
                "zero_body_dependencies": not result.plan.body_dependency_plugs,
                "binary_fbx_written": (
                    result.artifact.encoding == "binary"
                    and result.artifact.format_version == 7700
                    and result.artifact.byte_count == destination.stat().st_size
                    and len(result.artifact.content_sha256) == 64
                ),
                "linear_reduction_applied": (
                    reduced_result.applied_profile.curve_policy == 'lossless_linear'
                    and reduced_result.applied_profile.removed_linear_keys > 0
                    and reduced_result.artifact.byte_count < result.artifact.byte_count
                ),
                "default_profile_applied": (
                    result.applied_profile.file_version == "FBX202000"
                    and result.applied_profile.up_axis.lower() == "z"
                    and abs(result.applied_profile.scale_factor - 1.0) < 1e-9
                    and result.applied_profile.encoding == "binary"
                ),
                "explicit_ascii_profile_applied": (
                    converted_result.artifact.encoding == "ascii"
                    and converted_result.artifact.format_version == 7500
                    and converted_result.applied_profile.file_version == "FBX201800"
                    and converted_result.applied_profile.up_axis.lower() == "y"
                    and abs(converted_result.applied_profile.scale_factor - 100.0) < 1e-9
                    and converted_result.applied_profile.encoding == "ascii"
                ),
                "selection_preserved": (cmds.ls(selection=True, long=True) or []) == original_selection,
                "current_time_preserved": abs(float(cmds.currentTime(query=True)) - original_time) < 1e-6,
                "modified_state_preserved": bool(cmds.file(query=True, modified=True)) == original_modified,
                "undo_top_preserved": str(
                    cmds.undoInfo(query=True, undoName=True) or ""
                ) == original_undo_name,
                "plugin_version_recorded": bool(result.plugin_version),
                "original_scene_paths_restored": (
                    len(cmds.ls("AdvPy_EXP_*", long=True, type="joint") or []) == 30
                    and (cmds.ls("AdvPy_GameRootMotion", long=True, type="joint") or [])
                    == ["|AdvPy_GameRootMotion"]
                    and not (cmds.ls("|RootMotion", long=True) or [])
                ),
                "bake_metadata_restored": (
                    host.capture_baked_body_export_skeleton(result.plan.bake)
                    == result.plan.baked
                ),
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

            def imported_pose(path):
                cmds.file(new=True, force=True)
                cmds.file(str(path), i=True, type='FBX', ignoreVersion=True,
                          mergeNamespacesOnClash=False, options='fbx')
                joints=tuple(sorted(cmds.ls(type='joint',long=True) or []))
                poses=[]
                for frame in range(1,6):
                    cmds.currentTime(frame,edit=True,update=True)
                    poses.append(tuple(tuple(float(value) for value in
                        cmds.xform(joint,query=True,worldSpace=True,matrix=True))
                        for joint in joints))
                key_count=sum(len(cmds.keyframe(joint,attribute=attribute,
                    query=True,timeChange=True) or []) for joint in joints
                    for attribute in ('translateX','translateY','translateZ',
                                      'rotateX','rotateY','rotateZ',
                                      'scaleX','scaleY','scaleZ'))
                return joints,tuple(poses),key_count
            full_joints,full_poses,full_keys=imported_pose(destination)
            reduced_joints,reduced_poses,reduced_keys=imported_pose(reduced_destination)
            max_pose_error=max(abs(left-right) for full_frame,reduced_frame in
                zip(full_poses,reduced_poses) for full_joint,reduced_joint in
                zip(full_frame,reduced_frame) for left,right in zip(full_joint,reduced_joint))
            checks['reduced_fbx_reimports_with_same_joint_poses']=(
                full_joints==reduced_joints and reduced_keys<full_keys
                and max_pose_error<1e-5)

            cmds.file(new=True, force=True)
            cmds.file(
                str(converted_destination),
                i=True,
                type="FBX",
                ignoreVersion=True,
                mergeNamespacesOnClash=False,
                options="fbx",
            )
            imported_joints = cmds.ls(type="joint", long=True) or []
            root_motion = cmds.ls("RootMotion", long=True, type="joint") or []
            export_joints = [
                path for path in imported_joints if path != "|RootMotion"
            ]
            root_motion_keys = cmds.keyframe(
                "RootMotion.translateX", query=True, timeChange=True
            ) or []
            shoulder_keys = cmds.keyframe(
                "Shoulder_R.rotateX", query=True, timeChange=True
            ) or []
            checks.update({
                "fresh_import_has_31_joints": len(imported_joints) == 31,
                "fresh_import_has_one_root_motion": (
                    len(root_motion) == 1
                    and not (cmds.listRelatives(root_motion[0], parent=True) or [])
                ),
                "fresh_import_has_30_export_joints": len(export_joints) == 30,
                "fresh_import_names_are_canonical": (
                    (cmds.ls("|RootMotion|Root_M", long=True, type="joint") or [])
                    == ["|RootMotion|Root_M"]
                    and not (cmds.ls("AdvPy_EXP_*", long=True) or [])
                    and not any(":" in path for path in imported_joints)
                ),
                "internal_metadata_not_exported": not any(
                    cmds.objExists(f"|RootMotion|Root_M.{attribute}")
                    for attribute in (
                        "advPyOwner",
                        "advPyArtifactKind",
                        "advPySchemaVersion",
                        "advPySourceBodyRoot",
                        "advPyExportJointCount",
                        "advPyBakeSchemaVersion",
                        "advPyBakeStartFrame",
                        "advPyBakeEndFrame",
                        "advPyBakeSampleBy",
                    )
                ),
                "fresh_import_animation_range": (
                    tuple(round(float(value)) for value in root_motion_keys) == (1, 2, 3, 4, 5)
                    and tuple(round(float(value)) for value in shoulder_keys) == (1, 2, 3, 4, 5)
                ),
                "no_fit_body_or_control_leakage": not any(
                    cmds.ls(pattern, long=True) or []
                    for pattern in ("FitSkeleton", "|Root_M", "*_CTRL", "AdvPy_CharacterControls")
                ),
            })
            imported_source=InspectMocapSource(MayaMocapSourceReader()).execute('|RootMotion')
            checks['imported_fbx_is_mocap_source']=imported_source.valid
            if not imported_source.valid:
                print('MOCAP_IMPORT_ISSUES',[(issue.code,issue.message) for issue in imported_source.issues],flush=True)
            take_time=float(cmds.currentTime(query=True))
            take_selection=cmds.ls(selection=True,long=True) or []
            cmds.createNode('transform',name='PreImportUndoMarker',skipSelect=True)
            external=ImportMocapFbx(MayaMocapClipHost()).apply(named_destination,namespace='ExternalTake')
            checks['isolated_external_fbx_source']=(external.summary.namespace=='ExternalTake'
                and external.summary.joint_count==31 and external.summary.start_time==1.
                and external.summary.end_time==5.
                and abs(float(cmds.currentTime(query=True))-take_time)<1e-8
                and (cmds.ls(selection=True,long=True) or [])==take_selection)
            from dataclasses import replace
            sample_time,sample_matrices=external.clip.samples[0]
            invalid_matrix=list(sample_matrices[0]);invalid_matrix[12]+=1.
            invalid_samples=((sample_time,(tuple(invalid_matrix),)+sample_matrices[1:]),)+external.clip.samples[1:]
            failed_clip=replace(external.clip,samples=invalid_samples)
            try:MayaMocapClipHost().create_mocap_clip('FaultTake',failed_clip)
            except Exception:failed_import_rolled_back=(not cmds.ls('FaultTake:*')
                and bool(cmds.ls('|ExternalTake:EngineRoot',long=True,type='joint')))
            else:failed_import_rolled_back=False
            checks['invalid_external_clip_rolls_back']=failed_import_rolled_back
            cmds.undo()
            checks['external_import_single_undo']=(not cmds.ls('|ExternalTake:EngineRoot',long=True)
                                                   and bool(cmds.ls('PreImportUndoMarker')))
            cmds.undo()
            checks['previous_undo_history_preserved']=not cmds.ls('PreImportUndoMarker')
            cmds.redo();cmds.redo()
            checks['external_import_redo_restores_source']=(
                bool(cmds.ls('|ExternalTake:EngineRoot',long=True,type='joint'))
                and InspectMocapSource(MayaMocapSourceReader()).execute('|ExternalTake:EngineRoot').valid)
            retained_scene=(output.parent/'isolated-mocap.ma').resolve()
            cmds.file(rename=str(retained_scene));cmds.file(save=True,type='mayaAscii',force=True)
            cmds.file(str(retained_scene),open=True,force=True)
            checks['external_import_reopens_as_source']=InspectMocapSource(
                MayaMocapSourceReader()).execute('|ExternalTake:EngineRoot').valid
            cmds.file(new=True,force=True)
            cmds.file(str(named_destination),i=True,type='FBX',ignoreVersion=True,
                      mergeNamespacesOnClash=False,options='fbx')
            checks['fresh_import_has_engine_names']=(
                named_result.plan.selection.published_root_path=='|EngineRoot'
                and (cmds.ls('|EngineRoot|pelvis|spine_01',long=True,type='joint') or [])==['|EngineRoot|pelvis|spine_01']
                and len(cmds.ls('head',long=True,type='joint') or [])==1
                and len(cmds.ls(type='joint') or [])==31)

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
            "converted_fbx_byte_count": converted_result.artifact.byte_count,
            "converted_fbx_sha256": converted_result.artifact.content_sha256,
            "reduced_fbx_byte_count": reduced_result.artifact.byte_count,
            "removed_linear_keys": reduced_result.applied_profile.removed_linear_keys,
            "full_reimport_key_count": full_keys,
            "reduced_reimport_key_count": reduced_keys,
            "reimport_max_pose_error": max_pose_error,
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
