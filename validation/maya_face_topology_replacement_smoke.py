"""Self-generated Face controls and deformers across a 4-to-6 spine takeover."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, inspect_scene: str | None = None) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaFaceHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        from adv_py.application import BuildFaceBlendShapes, GenerateFaceTarget, ReplaceRegisteredSpineCharacter
        from adv_py.core import FaceLandmark, FaceShapeKind, FaceTarget

        if inspect_scene is not None:
            cmds.file(str(folder / inspect_scene), open=True, force=True)
            face = MayaFaceHost(namespace="source")
            registration = face.read_character_registration()
            controls = cmds.ls("source:AdvPy_FaceControls", long=True) or []
            followers = cmds.ls("source:FaceFollower", long=True) or []
            drivers = cmds.ls("source:FaceDriver", long=True) or []
            gains = cmds.ls("source:FaceGain", long=True) or []
            shared = cmds.ls("external:SharedFaceScale", long=True) or []
            props = cmds.ls("source:FingerProp", long=True) or []
            spine_props = cmds.ls("source:SpineProp", long=True) or []
            spine_parent = (cmds.listRelatives(spine_props[0], parent=True,
                fullPath=True) or [None])[0] if spine_props else None
            good = (len(registration.spine.body_joints) == 7 and
                    not cmds.namespace(exists="target") and
                    len(controls) == len(followers) == len(drivers) == len(gains)
                    == len(shared)
                    == len(props) == len(spine_props) == 1 and
                    cmds.objExists("source:FaceSkin") and
                    cmds.objExists("source:AdvPy_FaceBlendShape") and
                    all(cmds.objExists(name) for name in
                        ("source:SmileTarget", "source:VisemeATarget")) and
                    abs(cmds.getAttr(controls[0] + ".smile_R", time=5) - 1.) < 1e-6 and
                    abs(cmds.getAttr(controls[0] + ".viseme_A", time=10) - 1.) < 1e-6 and
                    abs(cmds.getAttr(followers[0] + ".translateX", time=5) - .75) < 1e-6 and
                    bool(cmds.lockNode(shared[0], query=True, lock=True)[0]) and
                    abs(cmds.getAttr(props[0] + ".translateZ", time=10) - 1.) < 1e-6 and
                    bool(spine_parent) and (cmds.listRelatives(spine_parent,
                        parent=True, fullPath=True) or [None])[0]
                        == face.scene_address(registration.spine.body_joints[4]))
            print(json.dumps({"cli_reopen_face_valid": good}), flush=True)
            return 0 if good else 1

        cmds.file(str(folder / "full-spine-replacement-before.ma"), open=True, force=True)
        cmds.undoInfo(state=True)
        face = MayaFaceHost(namespace="source")
        registration = face.read_character_registration()
        head = next(j.path for j in registration.body if j.path.rsplit("|", 1)[-1] == "Head_M")
        finger = next(n.path for n in registration.nodes
                      if n.path.rsplit("|", 1)[-1] == "AdvPy_Index1FK_L")
        neutral = cmds.polyPlane(name="source:FaceNeutral", width=2, height=2,
                                 subdivisionsX=1, subdivisionsY=1)[0]
        smile = FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|SmileTarget")
        viseme = FaceTarget("viseme_A", FaceShapeKind.VISEME, "|VisemeATarget")
        GenerateFaceTarget(face).apply("|FaceNeutral", smile,
            (FaceLandmark(0, (.5, 0., .2), 3.),))
        GenerateFaceTarget(face).apply("|FaceNeutral", viseme,
            (FaceLandmark(2, (0., .4, .3), .25),))
        cmds.skinCluster(face.scene_address(head), neutral,
                         name="source:FaceSkin", toSelectedBones=True)
        built = BuildFaceBlendShapes(face).apply("|FaceNeutral", (smile, viseme))
        control = face.scene_address(built.plan.control_path)
        deformer = face.scene_address(built.plan.deformer_name)
        follower = cmds.createNode("transform", name="source:FaceFollower",
                                   parent=control)
        driver = cmds.createNode("multiplyDivide", name="source:FaceDriver")
        gain = cmds.createNode("multiplyDivide", name="source:FaceGain")
        cmds.namespace(addNamespace="external")
        shared = cmds.createNode("multiplyDivide", name="external:SharedFaceScale")
        cmds.setAttr(driver + ".input2X", 1.)
        cmds.setAttr(gain + ".input2X", 1.)
        cmds.setAttr(shared + ".input1X", .75)
        cmds.setAttr(shared + ".input2X", 1.)
        cmds.connectAttr(control + ".smile_R", driver + ".input1X")
        cmds.connectAttr(driver + ".outputX", gain + ".input1X")
        cmds.connectAttr(shared + ".outputX", gain + ".input2X", force=True)
        cmds.connectAttr(gain + ".outputX", follower + ".translateX")
        cmds.lockNode(shared, lock=True)
        prop = cmds.createNode("transform", name="source:FingerProp",
                               parent=face.scene_address(finger))
        prop = (cmds.ls(prop, long=True) or [prop])[0]
        spine_prop = cmds.createNode("transform", name="source:SpineProp",
                                    parent=face.scene_address(registration.spine.body_joints[3]))
        spine_prop = (cmds.ls(spine_prop, long=True) or [spine_prop])[0]
        cmds.setAttr(spine_prop + ".translateY", .2)
        cmds.setKeyframe(prop, attribute="translateZ", time=1, value=0.)
        cmds.setKeyframe(prop, attribute="translateZ", time=10, value=1.)
        prop_curve = (cmds.listConnections(prop + ".translateZ",
            source=True, destination=False, type="animCurve") or [None])[0]
        targets = (face.scene_address(smile.mesh), face.scene_address(viseme.mesh))
        for frame, values in ((0, (.15, 0.)), (1, (0., 0.)),
                              (5, (1., .4)), (10, (.2, 1.)),
                              (20, (.25, 0.))):
            for attr, value in zip(("smile_R", "viseme_A"), values):
                cmds.setKeyframe(control, attribute=attr, time=frame, value=value)
        promotion_host = MayaOriginalSpinePromotionHost()
        graph_exact = set(promotion_host.expand_original_spine_retained_graph(
            "source", (driver,))) == {driver, gain}
        try:
            promotion_host.expand_original_spine_retained_graph(
                "source", ("source:AdvPy_SplineArc",))
        except ValueError:
            old_rig_graph_root_rejected = True
        else:
            old_rig_graph_root_rejected = False
        identities = {node: (cmds.ls(node, uuid=True) or [None])[0]
                      for node in (neutral, "source:FaceSkin", control,
                                   deformer, follower, driver, gain, shared, prop, prop_curve,
                                   spine_prop, *targets)}
        before = {}
        prop_before = {}
        spine_prop_before = {}
        for frame in (1, 5, 10):
            cmds.currentTime(frame, edit=True)
            before[frame] = tuple(cmds.xform("|source:FaceNeutral.vtx[0]",
                query=True, worldSpace=True, translation=True))
            prop_before[frame] = tuple(cmds.xform(prop, query=True,
                worldSpace=True, matrix=True))
            spine_prop_before[frame] = tuple(cmds.xform(spine_prop, query=True,
                worldSpace=True, matrix=True))
        cmds.currentTime(1, edit=True)
        source_scene = folder / "face-topology-before.ma"
        cmds.file(rename=str(source_scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        (folder / "face-topology-input.json").write_text(json.dumps({
            "control": control, "prop": prop, "spine_prop": spine_prop,
            "targets": targets,
            "driver": driver, "gain": gain}, ensure_ascii=False),
            encoding="utf8")
        replacement = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace="target"))
        args = ("source", "target", (("source:SourceSkin", "|source:SourceMesh"),
                                     ("source:FaceSkin", "|source:FaceNeutral")))
        kwargs = dict(start_frame=1, end_frame=10,
                      extensions=(control, prop, spine_prop),
                      retained_assets=targets, retained_graph_roots=(driver,),
                      max_mesh_error=.2)
        try:
            replacement.apply_many(*args, **{
                key: value for key, value in kwargs.items()
                if key != "retained_graph_roots"})
        except ValueError as error:
            undeclared_driver_rejected = ("附件输入需要独占的原生动画曲线" in str(error) and
                cmds.namespace(exists="target") and
                bool(cmds.ls(identities[driver], long=True)) and
                len(face.read_character_registration().spine.body_joints) == 5)
        else:
            undeclared_driver_rejected = False
        class FailedPromotionHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_promotion(self, plan):
                super().apply_original_spine_promotion(plan)
                raise RuntimeError("Injected failure after Face promotion")

        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                return FailedPromotionHost()

        try:
            ReplaceRegisteredSpineCharacter(
                FailedHost(namespace="target")).apply_many(*args, **kwargs)
        except RuntimeError as error:
            rollback = ("Injected failure after Face promotion" in str(error) and
                cmds.namespace(exists="target") and
                len(MayaBodyBuildHost(namespace="source")
                    .read_character_registration().spine.body_joints) == 5 and
                all(bool(cmds.ls(uuid, long=True)) for uuid in identities.values()) and
                abs(cmds.getAttr(control + ".smile_R", time=5) - 1.) < 1e-6)
        else:
            rollback = False
        replacement.apply_many(*args, **kwargs)

        def check():
            active = MayaFaceHost(namespace="source")
            new_reg = active.read_character_registration()
            new_control = cmds.ls(identities[control], long=True) or []
            new_follower = cmds.ls(identities[follower], long=True) or []
            new_driver = cmds.ls(identities[driver], long=True) or []
            new_gain = cmds.ls(identities[gain], long=True) or []
            new_shared = cmds.ls(identities[shared], long=True) or []
            new_prop = cmds.ls(identities[prop], long=True) or []
            new_spine_prop = cmds.ls(identities[spine_prop], long=True) or []
            new_head = next(j.path for j in new_reg.body
                            if j.path.rsplit("|", 1)[-1] == "Head_M")
            new_finger = next(n.path for n in new_reg.nodes
                if n.path.rsplit("|", 1)[-1] == "AdvPy_Index1FK_L")
            same_uuids = all(bool(cmds.ls(uuid, long=True))
                             for uuid in identities.values())
            parent = (cmds.listRelatives(new_control[0], parent=True,
                      fullPath=True) or [None])[0] if new_control else None
            prop_parent = (cmds.listRelatives(new_prop[0], parent=True,
                fullPath=True) or [None])[0] if new_prop else None
            spine_prop_parent = (cmds.listRelatives(new_spine_prop[0], parent=True,
                fullPath=True) or [None])[0] if new_spine_prop else None
            current = {}
            prop_current = {}
            spine_prop_current = {}
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                for frame in (1, 5, 10):
                    cmds.currentTime(frame, edit=True)
                    current[frame] = tuple(cmds.xform("|source:FaceNeutral.vtx[0]",
                        query=True, worldSpace=True, translation=True))
                    prop_current[frame] = tuple(cmds.xform(new_prop[0], query=True,
                        worldSpace=True, matrix=True))
                    spine_prop_current[frame] = tuple(cmds.xform(new_spine_prop[0],
                        query=True, worldSpace=True, matrix=True))
            finally:
                cmds.undoInfo(stateWithoutFlush=True)
            mesh_error = max(abs(a-b) for frame in before
                             for a,b in zip(before[frame], current[frame]))
            prop_error = max(abs(a-b) for frame in prop_before
                             for a,b in zip(prop_before[frame], prop_current[frame]))
            spine_prop_error = max(abs(a-b) for frame in spine_prop_before
                for a,b in zip(spine_prop_before[frame], spine_prop_current[frame]))
            return dict(spine_joints=len(new_reg.spine.body_joints),
                        namespace_removed=not cmds.namespace(exists="target"),
                        identities_preserved=same_uuids,
                        face_control_on_new_head=(parent == active.scene_address(new_head)
                            or bool(parent and (cmds.listRelatives(parent, parent=True,
                                fullPath=True) or [None])[0] == active.scene_address(new_head))),
                        finger_prop_on_new_control=(prop_parent == active.scene_address(new_finger)
                            or bool(prop_parent and (cmds.listRelatives(prop_parent,
                                parent=True, fullPath=True) or [None])[0]
                                == active.scene_address(new_finger))),
                        finger_prop_max_matrix_error=prop_error,
                        spine_prop_on_arc_joint=bool(spine_prop_parent and
                            (cmds.listRelatives(spine_prop_parent, parent=True,
                                fullPath=True) or [None])[0] == active.scene_address(
                                    new_reg.spine.body_joints[4])),
                        spine_prop_max_matrix_error=spine_prop_error,
                        face_values_preserved=bool(new_control) and all(
                            abs(cmds.getAttr(new_control[0] + ".smile_R", time=frame) - value) < 1e-6
                            for frame, value in ((0, .15), (5, 1.), (20, .25))),
                        internal_driver_preserved=bool(new_control and new_follower
                            and new_driver and new_gain and new_shared) and
                            (cmds.ls(cmds.connectionInfo(new_follower[0] + ".translateX",
                                sourceFromDestination=True).split('.', 1)[0], uuid=True)
                                or [None])[0] == identities[gain] and
                            (cmds.ls(cmds.connectionInfo(new_gain[0] + ".input1X",
                                sourceFromDestination=True).split('.', 1)[0], uuid=True)
                                or [None])[0] == identities[driver] and
                            (cmds.ls(cmds.connectionInfo(new_driver[0] + ".input1X",
                                sourceFromDestination=True).split('.', 1)[0], uuid=True)
                                or [None])[0] == identities[control] and
                            (cmds.ls(cmds.connectionInfo(new_gain[0] + ".input2X",
                                sourceFromDestination=True).split('.', 1)[0], uuid=True)
                                or [None])[0] == identities[shared] and
                            bool(cmds.lockNode(new_shared[0], query=True, lock=True)[0]) and
                            abs(cmds.getAttr(new_follower[0] + ".translateX", time=5) - .75) < 1e-6,
                        deformation_live=mesh_error < .2 and
                            max(abs(a-b) for a,b in zip(current[1], current[5])) > .1,
                        face_mesh_max_error_cm=mesh_error)

        passed = check()
        cmds.undo()
        undo_details = dict(target_namespace=cmds.namespace(exists="target"),
            spine_joints=len(MayaBodyBuildHost(namespace="source")
                    .read_character_registration().spine.body_joints),
            face_control=bool(cmds.ls(identities[control], long=True)))
        undo = (undo_details["target_namespace"] and
                undo_details["spine_joints"] == 5 and undo_details["face_control"])
        cmds.redo()
        redo = check()
        scene = folder / "face-topology-replaced.ma"
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(str(scene), open=True, force=True)
        reopened = check()
        report = dict(passed=passed, graph_exact=graph_exact,
                      old_rig_graph_root_rejected=old_rig_graph_root_rejected,
                      undeclared_driver_rejected=undeclared_driver_rejected,
                      rollback=rollback, undo=undo, undo_details=undo_details,
                      redo=redo, reopened=reopened)
        (folder / "face-topology-replacement.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if (graph_exact and old_rig_graph_root_rejected and
                     undeclared_driver_rejected and rollback and undo and
                     all(x == passed for x in (redo, reopened)) and
                     passed["spine_joints"] == 7 and passed["namespace_removed"] and
                     passed["identities_preserved"] and passed["face_control_on_new_head"] and
                     passed["finger_prop_on_new_control"] and
                     passed["finger_prop_max_matrix_error"] < 1e-4 and
                     passed["spine_prop_on_arc_joint"] and
                     passed["spine_prop_max_matrix_error"] < 1e-4 and
                     passed["face_values_preserved"] and passed["internal_driver_preserved"] and
                     passed["deformation_live"]) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(),
                          sys.argv[2] if len(sys.argv) > 2 else None))
