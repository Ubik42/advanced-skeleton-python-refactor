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
        from adv_py.application import BuildFaceBlendShapes, GenerateFaceTarget, ReplaceRegisteredSpineCharacter
        from adv_py.core import FaceLandmark, FaceShapeKind, FaceTarget

        if inspect_scene is not None:
            cmds.file(str(folder / inspect_scene), open=True, force=True)
            face = MayaFaceHost(namespace="source")
            registration = face.read_character_registration()
            controls = cmds.ls("source:AdvPy_FaceControls", long=True) or []
            good = (len(registration.spine.body_joints) == 7 and
                    not cmds.namespace(exists="target") and len(controls) == 1 and
                    cmds.objExists("source:FaceSkin") and
                    cmds.objExists("source:AdvPy_FaceBlendShape") and
                    all(cmds.objExists(name) for name in
                        ("source:SmileTarget", "source:VisemeATarget")) and
                    abs(cmds.getAttr(controls[0] + ".smile_R", time=5) - 1.) < 1e-6 and
                    abs(cmds.getAttr(controls[0] + ".viseme_A", time=10) - 1.) < 1e-6)
            print(json.dumps({"cli_reopen_face_valid": good}), flush=True)
            return 0 if good else 1

        cmds.file(str(folder / "full-spine-replacement-before.ma"), open=True, force=True)
        cmds.undoInfo(state=True)
        face = MayaFaceHost(namespace="source")
        registration = face.read_character_registration()
        head = next(j.path for j in registration.body if j.path.rsplit("|", 1)[-1] == "Head_M")
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
        targets = (face.scene_address(smile.mesh), face.scene_address(viseme.mesh))
        for frame, values in ((0, (.15, 0.)), (1, (0., 0.)),
                              (5, (1., .4)), (10, (.2, 1.)),
                              (20, (.25, 0.))):
            for attr, value in zip(("smile_R", "viseme_A"), values):
                cmds.setKeyframe(control, attribute=attr, time=frame, value=value)
        identities = {node: (cmds.ls(node, uuid=True) or [None])[0]
                      for node in (neutral, "source:FaceSkin", control,
                                   deformer, *targets)}
        before = {}
        for frame in (1, 5, 10):
            cmds.currentTime(frame, edit=True)
            before[frame] = tuple(cmds.xform("|source:FaceNeutral.vtx[0]",
                query=True, worldSpace=True, translation=True))
        cmds.currentTime(1, edit=True)
        source_scene = folder / "face-topology-before.ma"
        cmds.file(rename=str(source_scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        (folder / "face-topology-input.json").write_text(json.dumps({
            "control": control, "targets": targets}, ensure_ascii=False),
            encoding="utf8")
        replacement = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace="target"))
        args = ("source", "target", (("source:SourceSkin", "|source:SourceMesh"),
                                     ("source:FaceSkin", "|source:FaceNeutral")))
        kwargs = dict(start_frame=1, end_frame=10, extensions=(control,),
                      retained_assets=targets, max_mesh_error=.2)
        replacement.apply_many(*args, **kwargs)

        def check():
            active = MayaFaceHost(namespace="source")
            new_reg = active.read_character_registration()
            new_control = cmds.ls(identities[control], long=True) or []
            new_head = next(j.path for j in new_reg.body
                            if j.path.rsplit("|", 1)[-1] == "Head_M")
            same_uuids = all(bool(cmds.ls(uuid, long=True))
                             for uuid in identities.values())
            parent = (cmds.listRelatives(new_control[0], parent=True,
                      fullPath=True) or [None])[0] if new_control else None
            current = {}
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                for frame in (1, 5, 10):
                    cmds.currentTime(frame, edit=True)
                    current[frame] = tuple(cmds.xform("|source:FaceNeutral.vtx[0]",
                        query=True, worldSpace=True, translation=True))
            finally:
                cmds.undoInfo(stateWithoutFlush=True)
            mesh_error = max(abs(a-b) for frame in before
                             for a,b in zip(before[frame], current[frame]))
            return dict(spine_joints=len(new_reg.spine.body_joints),
                        namespace_removed=not cmds.namespace(exists="target"),
                        identities_preserved=same_uuids,
                        face_control_on_new_head=(parent == active.scene_address(new_head)
                            or bool(parent and (cmds.listRelatives(parent, parent=True,
                                fullPath=True) or [None])[0] == active.scene_address(new_head))),
                        face_values_preserved=bool(new_control) and all(
                            abs(cmds.getAttr(new_control[0] + ".smile_R", time=frame) - value) < 1e-6
                            for frame, value in ((0, .15), (5, 1.), (20, .25))),
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
        report = dict(passed=passed, undo=undo, undo_details=undo_details,
                      redo=redo, reopened=reopened)
        (folder / "face-topology-replacement.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if (undo and all(x == passed for x in (redo, reopened)) and
                     passed["spine_joints"] == 7 and passed["namespace_removed"] and
                     passed["identities_preserved"] and passed["face_control_on_new_head"] and
                     passed["face_values_preserved"] and passed["deformation_live"]) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(),
                          sys.argv[2] if len(sys.argv) > 2 else None))
