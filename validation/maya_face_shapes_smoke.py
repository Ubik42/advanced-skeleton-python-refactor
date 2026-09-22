"""Generated expression and viseme targets on one registered Maya character."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import (
            ApplyFacePerformance, BuildBodyCharacterRig, BuildFaceBlendShapes, BuildOrientedBodySkeleton,
            BuildVariableBodySourceFit, CreateFitSkeleton, GenerateFaceTarget,
            RegisterBodyCharacter,
            RebuildBodyCharacter,
        )
        from adv_py.core import (FaceLandmark, FacePerformance, FaceShapeKind,
            FaceTarget, PhonemeCue, face_performance_from_json, face_performance_to_json,
            phoneme_cues_to_performance)
        from adv_py.core.variable_body_fit import variable_axial_description

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.namespace(addNamespace="hero")
        host = MayaFaceHost(namespace="hero")
        CreateFitSkeleton(host).apply()
        BuildVariableBodySourceFit(host).apply(spine_segments=4)
        BuildOrientedBodySkeleton(host).apply()
        rig = BuildBodyCharacterRig(host).apply(
            include_torso=True, include_spine_ik=True,
            include_control_spaces=True,
            axial_description=variable_axial_description(4),
        )
        registration = RegisterBodyCharacter(host).apply(rig)
        head = next(joint.path for joint in registration.body
                    if joint.path.rsplit("|", 1)[-1] == "Head_M")
        neutral = cmds.polyPlane(name="hero:FaceNeutral", width=2, height=2,
                                 subdivisionsX=1, subdivisionsY=1)[0]
        smile_spec = FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|SmileTarget")
        smile_marks = (FaceLandmark(0, (.5, 0., .2), 3.),)
        class FailedLandmarkHost(MayaFaceHost):
            def create_face_target(self, plan):
                super().create_face_target(plan)
                raise RuntimeError("Injected landmark target failure")
        try:
            GenerateFaceTarget(FailedLandmarkHost(namespace="hero")).apply(
                "|FaceNeutral", smile_spec, smile_marks)
        except RuntimeError as error:
            failed_landmark_rolled_back = (
                "Injected landmark target failure" in str(error)
                and not cmds.objExists("hero:SmileTarget"))
        else:
            failed_landmark_rolled_back = False
        smile_plan = GenerateFaceTarget(host).apply(
            "|FaceNeutral", smile_spec, smile_marks)
        smile = host.scene_address(smile_spec.mesh)
        cmds.undo()
        target_undo = not cmds.objExists(smile)
        cmds.redo()
        target_redo = (host.read_face_target_provenance(smile_spec.mesh)
                       == smile_plan.provenance
                       and all(abs(a - b) < 1e-6
                           for actual, expected in zip(
                               host.capture_face_mesh(smile_spec.mesh).points,
                               smile_plan.points)
                           for a, b in zip(actual, expected)))
        viseme_spec = FaceTarget("viseme_A", FaceShapeKind.VISEME,
                                 "|VisemeATarget")
        viseme_plan = GenerateFaceTarget(host).apply("|FaceNeutral",
            viseme_spec, (FaceLandmark(2, (0., .4, .3), .25),))
        viseme = host.scene_address(viseme_spec.mesh)
        cmds.skinCluster(host.scene_address(head), neutral,
                         name="hero:FaceSkin", toSelectedBones=True)
        marker = cmds.createNode("transform", name="FaceBuildSelection", skipSelect=True)
        cmds.select(marker, replace=True)
        original_selection = cmds.ls(selection=True, long=True) or []
        original_time = float(cmds.currentTime(query=True))
        targets = (
            smile_spec, viseme_spec,
        )
        unbuilt_scene = output.with_name(output.stem + "-unbuilt.ma")
        unbuilt_scene.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(rename=str(unbuilt_scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        wrong = cmds.polyCube(name="hero:WrongFaceTopology",
                              constructionHistory=False)[0]
        try:
            BuildFaceBlendShapes(host).plan("|FaceNeutral", (
                FaceTarget("wrong", FaceShapeKind.EXPRESSION,
                           "|WrongFaceTopology"),))
        except ValueError:
            wrong_topology_rejected = host.face_names_available(
                head + "|AdvPy_FaceControls", "AdvPy_FaceBlendShape")
        else:
            wrong_topology_rejected = False
        cmds.select(marker, replace=True)
        class FailedFaceHost(MayaFaceHost):
            def build_face_shapes(self, plan):
                super().build_face_shapes(plan)
                raise RuntimeError("Injected face build failure")

        before_failure = host.read_character_registration()
        try:
            BuildFaceBlendShapes(FailedFaceHost(namespace="hero")).apply(
                "|FaceNeutral", targets)
        except RuntimeError as error:
            failed_build_rolled_back = (
                "Injected face build failure" in str(error)
                and host.read_character_registration() == before_failure
                and host.face_names_available(
                    head + "|AdvPy_FaceControls", "AdvPy_FaceBlendShape")
            )
        else:
            failed_build_rolled_back = False
        result = BuildFaceBlendShapes(host).apply("|FaceNeutral", targets)
        control = host.scene_address(result.plan.control_path)
        deformer = host.scene_address(result.plan.deformer_name)
        checks = {
            "two_semantic_channels": len(result.binding.channels) == 2,
            "generated_targets_keep_provenance": (
                failed_landmark_rolled_back and target_undo and target_redo
                and host.read_face_target_provenance(viseme_spec.mesh)
                    == viseme_plan.provenance),
            "landmark_falloff_moves_unmarked_vertex": (
                .01 < smile_plan.points[1][0]
                    - smile_plan.neutral.points[1][0] < .5),
            "wrong_topology_rejected_before_build": wrong_topology_rejected,
            "failed_build_rolled_back": failed_build_rolled_back,
            "actual_mesh_deformation": result.binding.max_geometry_delta > .1,
            "control_follows_head": (cmds.listRelatives(control, parent=True,
                fullPath=True) or []) == [host.scene_address(head)],
            "selection_preserved": (cmds.ls(selection=True, long=True) or []) == original_selection,
            "time_preserved": abs(float(cmds.currentTime(query=True)) - original_time) < 1e-8,
            "registration_still_valid": host.read_character_registration() == registration,
            "blendshape_before_skin": (cmds.listHistory(neutral) or []).index(deformer)
                > (cmds.listHistory(neutral) or []).index("hero:FaceSkin"),
        }
        cmds.undo()
        checks["single_undo_removes_face_only"] = (
            host.face_names_available(result.plan.control_path,
                                      result.plan.deformer_name)
            and cmds.objExists(neutral)
            and host.read_character_registration() == registration)
        cmds.redo()
        checks["redo_restores_face"] = (
            host.capture_face_binding(result.plan).max_geometry_delta > .1)
        for frame, value in ((0, .15), (20, .25)):
            host._cmds.setKeyframe(result.plan.control_path,
                attribute="smile_R", time=frame, value=value)
        performance = FacePerformance(
            (("smile_R", FaceShapeKind.EXPRESSION),
             ("viseme_A", FaceShapeKind.VISEME)),
            cmds.currentUnit(query=True, time=True),
            ((1, (0., 0.)), (5, (1., .4)), (10, (.2, 1.))),
        )
        document = face_performance_to_json(performance)
        checks["portable_performance_roundtrip"] = (
            face_performance_from_json(document) == performance)
        old_keys = tuple(cmds.keyframe(control + ".smile_R", query=True,
                                   timeChange=True) or ())
        old_values = tuple(cmds.keyframe(control + ".smile_R", query=True,
                                     valueChange=True) or ())
        class FailedPerformanceHost(MayaFaceHost):
            def write_face_performance(self, plan):
                super().write_face_performance(plan)
                raise RuntimeError("Injected face performance failure")
        try:
            ApplyFacePerformance(FailedPerformanceHost(namespace="hero")).apply(
                result.plan.control_path, performance)
        except RuntimeError as error:
            checks["failed_performance_rolled_back"] = (
                "Injected face performance failure" in str(error)
                and tuple(cmds.keyframe(control + ".smile_R", query=True,
                    timeChange=True) or ()) == old_keys
                and tuple(cmds.keyframe(control + ".smile_R", query=True,
                    valueChange=True) or ()) == old_values
                and not cmds.keyframe(control + ".viseme_A", query=True,
                    timeChange=True))
        else:
            checks["failed_performance_rolled_back"] = False
        ApplyFacePerformance(host).apply(result.plan.control_path, performance)
        checks["clip_and_old_keys_coexist"] = (
            abs(cmds.getAttr(control + ".smile_R", time=0) - .15) < 1e-8
            and abs(cmds.getAttr(control + ".smile_R", time=20) - .25) < 1e-8
            and abs(cmds.getAttr(control + ".viseme_A", time=10) - 1.) < 1e-8)
        cmds.undo()
        checks["single_undo_restores_old_face_keys"] = (
            tuple(cmds.keyframe(control + ".smile_R", query=True,
                timeChange=True) or ()) == old_keys
            and not cmds.keyframe(control + ".viseme_A", query=True,
                timeChange=True))
        cmds.redo()
        checks["redo_restores_performance"] = (
            abs(cmds.getAttr(control + ".smile_R", time=5) - 1.) < 1e-8
            and abs(cmds.getAttr(control + ".viseme_A", time=10) - 1.) < 1e-8)
        clip_time = float(cmds.currentTime(query=True))
        try:
            cmds.currentTime(1)
            baseline = host.capture_face_mesh("|FaceNeutral").points
            cmds.currentTime(5)
            expressive = host.capture_face_mesh("|FaceNeutral").points
            cmds.currentTime(10)
            speaking = host.capture_face_mesh("|FaceNeutral").points
        finally:
            cmds.currentTime(clip_time)
        checks["sampled_frames_deform_mesh"] = (
            max(abs(a - b) for p, q in zip(baseline, expressive)
                for a, b in zip(p, q)) > .1
            and max(abs(a - b) for p, q in zip(baseline, speaking)
                for a, b in zip(p, q)) > .1)
        scene = output.with_suffix(".ma")
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(str(scene), open=True, force=True)
        reopened = MayaFaceHost(namespace="hero")
        reopened_control = reopened.scene_address(result.plan.control_path)
        checks["reopened_face_animation"] = (
            abs(cmds.getAttr(reopened_control + ".smile_R", time=5) - 1.) < 1e-8
            and abs(cmds.getAttr(reopened_control + ".viseme_A", time=10) - 1.) < 1e-8
            and reopened.capture_face_binding(result.plan).max_geometry_delta > .1
        )
        checks["reopened_registration"] = reopened.read_character_registration() == registration
        checks["generated_targets_survive_reopen"] = (
            GenerateFaceTarget(reopened).audit(smile_plan).vertex_count == 4
            and GenerateFaceTarget(reopened).audit(viseme_plan).vertex_count == 4)
        face_control_uuid = (cmds.ls(reopened_control, uuid=True) or [None])[0]
        deformer_uuid = (cmds.ls(reopened.scene_address(result.plan.deformer_name),
                                  uuid=True) or [None])[0]
        RebuildBodyCharacter(reopened).apply("FaceStage",
            extensions=(result.plan.control_path,))
        rebuilt = MayaFaceHost(namespace="hero")
        checks["rebuilt_character_layout"] = (
            rebuilt.read_character_registration().compatibility_digest
            == registration.compatibility_digest)
        checks["face_control_identity_preserved"] = (
            (cmds.ls(rebuilt.scene_address(result.plan.control_path),
                     uuid=True) or [None])[0] == face_control_uuid)
        checks["face_deformer_identity_preserved"] = (
            (cmds.ls(rebuilt.scene_address(result.plan.deformer_name),
                     uuid=True) or [None])[0] == deformer_uuid)
        checks["face_deformation_survives_rebuild"] = (
            rebuilt.capture_face_binding(result.plan).max_geometry_delta > .1)
        checks["generated_targets_survive_rebuild"] = (
            GenerateFaceTarget(rebuilt).audit(smile_plan).vertex_count == 4
            and GenerateFaceTarget(rebuilt).audit(viseme_plan).vertex_count == 4)
        smile_keys_before = tuple(cmds.keyframe(rebuilt.scene_address(
            result.plan.control_path) + ".smile_R", query=True,
            timeChange=True) or ())
        cue_clip = phoneme_cues_to_performance(
            performance.channels, performance.time_unit,
            (PhonemeCue("a", 30, 36),), (("a", "viseme_A"),))
        ApplyFacePerformance(rebuilt).apply(result.plan.control_path, cue_clip)
        checks["phoneme_clip_preserves_expression_animation"] = (
            cue_clip.channels == (("viseme_A", FaceShapeKind.VISEME),)
            and tuple(cmds.keyframe(rebuilt.scene_address(
                result.plan.control_path) + ".smile_R", query=True,
                timeChange=True) or ()) == smile_keys_before
            and abs(cmds.getAttr(rebuilt.scene_address(
                result.plan.control_path) + ".viseme_A", time=33) - 1.) < 1e-8)
        cue_time = float(cmds.currentTime(query=True))
        try:
            cmds.currentTime(28)
            quiet_points = rebuilt.capture_face_mesh("|FaceNeutral").points
            cmds.currentTime(33)
            spoken_points = rebuilt.capture_face_mesh("|FaceNeutral").points
        finally:
            cmds.currentTime(cue_time)
        checks["phoneme_clip_deforms_mesh"] = max(
            abs(a - b) for p, q in zip(quiet_points, spoken_points)
            for a, b in zip(p, q)) > .1
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(str(scene), open=True, force=True)
        checks["phoneme_clip_reopens"] = (
            abs(cmds.getAttr(MayaFaceHost(namespace="hero").scene_address(
                result.plan.control_path) + ".viseme_A", time=33) - 1.) < 1e-8)
        payload = {**checks, "joint_count": len(registration.body),
                   "max_geometry_delta": result.binding.max_geometry_delta,
                   "status": "passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
