"""Preflight an original Fit scene; optional build edits only unsaved memory."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


def main(scene: Path, report: Path, isolated_build: bool = False,
         isolated_skin: bool = False, isolated_export: bool = False) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.body_skeleton import BuildBodySkeleton
        from adv_py.application.oriented_body_skeleton import BuildOrientedBodySkeleton
        from adv_py.application.body_character_rig import BuildBodyCharacterRig
        from adv_py.application.skin_bind import BindSkin
        from adv_py.application.body_root_motion import BuildBodyRootMotion
        from adv_py.application.body_export_skeleton import (
            BuildBodyExportSkeleton, BakeBodyExportSkeleton)
        from adv_py.application.body_fbx_export import ExportBodyFbx
        from adv_py.core.joint_labels import JointLabel
        from adv_py.application.fit_symmetry import PlanFitSymmetry

        if not scene.is_file() or scene.suffix.lower() not in (".ma", ".mb"):
            raise ValueError("输入必须是已有的 Maya 场景文件")
        cmds.file(new=True, force=True)
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fit = cmds.ls("FitSkeleton", type="transform", long=True) or []
        result = {"source": scene.name, "fit_containers": fit,
                  "fit_joint_count": 0, "metadata": {}, "plan": {}}
        if len(fit) == 1:
            host = MayaBodyBuildHost()
            hierarchy = host.capture_fit_hierarchy(fit[0])
            result["fit_joint_count"] = len(hierarchy.joints)
            for node in hierarchy.joints:
                try:
                    meta = host.read_fit_joint_metadata(node.path)
                    result["metadata"][node.short_name] = {
                        "no_mirror": meta.no_mirror,
                        "no_mirror_left": meta.no_mirror_left,
                        "label": getattr(host.read_joint_label(node.path),
                                         "text", None),
                    }
                except Exception as exc:
                    result["metadata"][node.short_name] = {
                        "error": f"{type(exc).__name__}: {exc}"}
            try:
                plan = PlanFitSymmetry(host).execute(fit[0])
                result["plan"] = {"status": "ready",
                                  "instance_count": len(plan.instances),
                                  "output_names": [item.output_name
                                                   for item in plan.instances]}
            except Exception as exc:
                result["plan"] = {"status": "failed",
                                  "error": f"{type(exc).__name__}: {exc}"}
            try:
                build = BuildBodySkeleton(host).plan(fit[0])
                result["body_build"] = {
                    "ready": build.ready,
                    "missing_labels": [path.rsplit("|", 1)[-1]
                                       for path in build.missing_labels],
                    "name_collisions": list(build.name_collisions),
                    "spec_count": len(build.specs),
                }
            except Exception as exc:
                result["body_build"] = {
                    "error": f"{type(exc).__name__}: {exc}"}
            if isolated_build:
                # The source file stays untouched. Only this unsaved in-memory
                # scene loses the existing rig so names can be built afresh.
                mesh_copy = None
                if isolated_skin:
                    shapes = cmds.ls(type="mesh", long=True,
                                     noIntermediate=True) or []
                    if len(shapes) != 1:
                        raise ValueError("原版网格不是唯一的可见 mesh")
                    source_mesh = (cmds.listRelatives(
                        shapes[0], parent=True, fullPath=True) or [""])[0]
                    mesh_copy = cmds.duplicate(
                        source_mesh, name="AdvPy_SamMesh",
                        returnRootsOnly=True)[0]
                    mesh_copy = cmds.parent(mesh_copy, world=True)[0]
                    cmds.delete(mesh_copy, constructionHistory=True)
                    mesh_copy = (cmds.ls(mesh_copy, long=True) or [""])[0]
                group = (cmds.listRelatives(fit[0], parent=True,
                                            fullPath=True) or [""])[0]
                scene_siblings = (cmds.listRelatives(
                    group, children=True, fullPath=True) or ()) if group else (
                        cmds.ls(assemblies=True, long=True) or ())
                siblings = [path for path in scene_siblings
                            if path != fit[0]]
                cmds.delete(siblings)
                fit_before = {node.short_name: node.world_position
                              for node in hierarchy.joints}
                try:
                    with host.transaction("标注原版 Fit 副本"):
                        for node in hierarchy.joints:
                            if host.read_joint_label(node.path) is None:
                                host.set_joint_label(
                                    node.path, JointLabel.parse(node.short_name))
                    built = BuildOrientedBodySkeleton(host).apply(fit[0])
                    current_fit = host.capture_fit_hierarchy(fit[0])
                    result["isolated_build"] = {
                        "status": "passed",
                        "body_count": len(built.snapshot.joints),
                        "fit_unchanged": fit_before == {
                            node.short_name: node.world_position
                            for node in current_fit.joints},
                    }
                    try:
                        character = BuildBodyCharacterRig(host).plan(
                            fit[0], include_torso=True)
                        result["isolated_build"]["character_plan"] = {
                            "ready": character.ready,
                            "blockers": list(character.blockers),
                        }
                        if character.ready:
                            rig = BuildBodyCharacterRig(host).apply(
                                fit[0], include_torso=True)
                            result["isolated_build"]["character_rig"] = {
                                "status": "passed",
                                "body_count": len(rig.body.joints),
                                "hand_controls": rig.hand is not None,
                                "fit_unchanged": fit_before == {
                                    node.short_name: node.world_position
                                    for node in host.capture_fit_hierarchy(
                                        fit[0]).joints},
                            }
                            if rig.hand is not None:
                                hand_failures = []
                                for item in rig.hand.snapshot.controls:
                                    driven = item.driven_joint
                                    baseline = tuple(cmds.xform(
                                        driven, query=True, worldSpace=True,
                                        matrix=True))
                                    cmds.setAttr(f"{item.control_path}.rotateX", 12.0)
                                    posed = tuple(cmds.xform(
                                        driven, query=True, worldSpace=True,
                                        matrix=True))
                                    cmds.undo()
                                    restored = tuple(cmds.xform(
                                        driven, query=True, worldSpace=True,
                                        matrix=True))
                                    changed = max(abs(a - b) for a, b in zip(
                                        baseline, posed)) > 1e-4
                                    undone = max(abs(a - b) for a, b in zip(
                                        baseline, restored)) < 1e-4
                                    if not changed or not undone:
                                        hand_failures.append({
                                            "control": item.control_path,
                                            "joint": driven,
                                            "changed": changed,
                                            "undo_restored": undone,
                                        })
                                result["isolated_build"]["all_hand_controls"] = {
                                    "count": len(rig.hand.snapshot.controls),
                                    "failures": hand_failures,
                                }
                                if mesh_copy is not None:
                                    influences = tuple(
                                        state.path for state in rig.body.joints)
                                    bound = BindSkin(host).apply(
                                        mesh_copy, influences,
                                        skin_name="AdvPy_SamBodySkin")
                                    result["isolated_build"]["skin"] = {
                                        "status": "passed",
                                        "mesh": mesh_copy,
                                        "influence_count": len(
                                            bound.snapshot.influence_paths),
                                        "vertex_count": cmds.polyEvaluate(
                                            mesh_copy, vertex=True),
                                    }
                                    vertex = f"{mesh_copy}.vtx[0]"
                                    neutral_vertex = tuple(cmds.pointPosition(
                                        vertex, world=True))
                                    global_control = (
                                        "|AdvPy_CharacterControls|"
                                        "AdvPy_GlobalOffset|AdvPy_Global")
                                    cmds.setAttr(
                                        f"{global_control}.translateX", 2.0)
                                    moved_vertex = tuple(cmds.pointPosition(
                                        vertex, world=True))
                                    cmds.undo()
                                    restored_vertex = tuple(cmds.pointPosition(
                                        vertex, world=True))
                                    result["isolated_build"]["skin"].update({
                                        "global_motion": abs(
                                            moved_vertex[0] - neutral_vertex[0]),
                                        "undo_restored": max(abs(a - b)
                                            for a, b in zip(neutral_vertex,
                                                            restored_vertex)) < 1e-4,
                                    })
                                control = next(item for item in
                                    rig.hand.snapshot.controls
                                    if item.control_path.rsplit("|", 1)[-1]
                                    == "AdvPy_Index1FK_R")
                                joint = control.driven_joint
                                before = tuple(cmds.xform(
                                    joint, query=True, worldSpace=True,
                                    matrix=True))
                                cmds.setAttr(f"{control.control_path}.rotateX", 15.0)
                                moved = tuple(cmds.xform(
                                    joint, query=True, worldSpace=True,
                                    matrix=True))
                                cmds.undo()
                                undone = tuple(cmds.xform(
                                    joint, query=True, worldSpace=True,
                                    matrix=True))
                                cmds.redo()
                                redone = tuple(cmds.xform(
                                    joint, query=True, worldSpace=True,
                                    matrix=True))
                                def near(left, right):
                                    return max(abs(a - b) for a, b in zip(
                                        left, right)) < 1e-4
                                with tempfile.TemporaryDirectory() as temporary:
                                    output = Path(temporary) / "sam-fit-built.mb"
                                    if isolated_export:
                                        for frame, angle in ((1, 0.0),
                                                             (3, 15.0),
                                                             (5, 30.0)):
                                            cmds.setKeyframe(
                                                control.control_path,
                                                attribute="rotateX",
                                                time=frame, value=angle)
                                        cmds.currentTime(1, edit=True,
                                                         update=True)
                                        frame_one = tuple(cmds.xform(
                                            joint, query=True,
                                            worldSpace=True, matrix=True))
                                        cmds.currentTime(5, edit=True,
                                                         update=True)
                                        frame_five = tuple(cmds.xform(
                                            joint, query=True,
                                            worldSpace=True, matrix=True))
                                        cmds.currentTime(3, edit=True,
                                                         update=True)
                                        result["isolated_build"]["animation"] = {
                                            "frame_1_vs_5_changed": not near(
                                                frame_one, frame_five),
                                        }
                                        BuildBodyRootMotion(host).apply(
                                            source_container=fit[0])
                                        export = BuildBodyExportSkeleton(
                                            host).apply(
                                                source_container=fit[0])
                                        baked = BakeBodyExportSkeleton(
                                            host).apply(
                                                start_frame=1, end_frame=5,
                                                source_container=fit[0])
                                        destination = (Path(temporary) /
                                                       "sam-export.fbx")
                                        published = ExportBodyFbx(host).apply(
                                            destination, start_frame=1,
                                            end_frame=5,
                                            source_container=fit[0])
                                        result["isolated_build"]["export"] = {
                                            "status": "passed",
                                            "export_joint_count": len(
                                                export.plan.export_skeleton.joints),
                                            "sample_count": len(baked.samples),
                                            "fbx_bytes": destination.stat().st_size,
                                            "plugin_version":
                                                published.plugin_version,
                                        }
                                    cmds.file(rename=str(output))
                                    cmds.file(save=True, type="mayaBinary")
                                    cmds.file(str(output), open=True, force=True,
                                              executeScriptNodes=False)
                                    reopened = tuple(cmds.xform(
                                        joint, query=True, worldSpace=True,
                                        matrix=True))
                                    if isolated_export:
                                        cmds.currentTime(1, edit=True,
                                                         update=True)
                                        reopened_one = tuple(cmds.xform(
                                            joint, query=True,
                                            worldSpace=True, matrix=True))
                                        cmds.currentTime(5, edit=True,
                                                         update=True)
                                        reopened_five = tuple(cmds.xform(
                                            joint, query=True,
                                            worldSpace=True, matrix=True))
                                        result["isolated_build"]["animation"][
                                            "reopen_frames_match"] = (
                                                near(frame_one, reopened_one)
                                                and near(frame_five,
                                                         reopened_five))
                                    if mesh_copy is not None:
                                        skin_nodes = cmds.ls(
                                            "AdvPy_SamBodySkin",
                                            type="skinCluster") or []
                                        result["isolated_build"]["skin"][
                                            "reopen_influence_count"] = (
                                            len(cmds.skinCluster(
                                                skin_nodes[0], query=True,
                                                influence=True) or [])
                                            if len(skin_nodes) == 1 else 0)
                                    cmds.file(new=True, force=True)
                                    if isolated_export:
                                        cmds.file(
                                            str(destination), i=True,
                                            type="FBX", ignoreVersion=True,
                                            mergeNamespacesOnClash=False,
                                            options="fbx")
                                        imported_joints = cmds.ls(
                                            type="joint", long=True) or []
                                        imported_finger = cmds.ls(
                                            "IndexFinger1_R", type="joint",
                                            long=True) or []
                                        if len(imported_finger) == 1:
                                            cmds.currentTime(
                                                1, edit=True, update=True)
                                            imported_one = tuple(cmds.xform(
                                                imported_finger[0], query=True,
                                                worldSpace=True, matrix=True))
                                            cmds.currentTime(
                                                5, edit=True, update=True)
                                            imported_five = tuple(cmds.xform(
                                                imported_finger[0], query=True,
                                                worldSpace=True, matrix=True))
                                        result["isolated_build"]["export"].update({
                                            "reimport_joint_count": len(
                                                imported_joints),
                                            "reimport_finger_animated": (
                                                len(imported_finger) == 1
                                                and not near(imported_one,
                                                             imported_five)),
                                        })
                                        cmds.file(new=True, force=True)
                                result["isolated_build"]["hand_drive"] = {
                                    "joint": joint.rsplit("|", 1)[-1],
                                    "control_count": len(
                                        rig.hand.snapshot.controls),
                                    "changed": not near(before, moved),
                                    "undo_restored": near(before, undone),
                                    "redo_restored": near(moved, redone),
                                    "reopen_restored": near(moved, reopened),
                                }
                    except Exception as exc:
                        result["isolated_build"]["character_rig"] = {
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}"}
                except Exception as exc:
                    result["isolated_build"] = {
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}"}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        if isolated_build:
            built = result.get("isolated_build", {})
            drive = built.get("hand_drive", {})
            if (built.get("status") != "passed"
                    or built.get("body_count") != result.get(
                        "plan", {}).get("instance_count")
                    or not built.get("fit_unchanged")
                    or built.get("character_rig", {}).get("status") != "passed"
                    or drive.get("control_count") != 30
                    or built.get("all_hand_controls", {}).get("count") != 30
                    or built.get("all_hand_controls", {}).get("failures")
                    or not all(drive.get(key) for key in (
                        "changed", "undo_restored", "redo_restored",
                        "reopen_restored"))):
                return 1
            if isolated_skin and (built.get("skin", {}).get("status") != "passed"
                                  or built["skin"].get("influence_count") !=
                                  built.get("body_count")
                                  or abs(built["skin"].get(
                                      "global_motion", 0.0) - 2.0) > 1e-3
                                  or not built["skin"].get("undo_restored")
                                  or built["skin"].get(
                                      "reopen_influence_count") !=
                                      built.get("body_count")):
                return 1
            if isolated_export and (
                    not built.get("animation", {}).get(
                        "frame_1_vs_5_changed")
                    or not built.get("animation", {}).get(
                        "reopen_frames_match")
                    or built.get("export", {}).get("status") != "passed"
                    or built["export"].get("export_joint_count") !=
                        built.get("body_count")
                    or built["export"].get("reimport_joint_count") !=
                        built.get("body_count") + 1
                    or not built["export"].get(
                        "reimport_finger_animated")
                    or built["export"].get("fbx_bytes", 0) < 1000):
                return 1
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    export_mode = "--isolated-export" in sys.argv[3:]
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          any(flag in sys.argv[3:] for flag in (
                              "--isolated-build", "--isolated-skin",
                              "--isolated-export")),
                          "--isolated-skin" in sys.argv[3:] or export_mode,
                          export_mode))
