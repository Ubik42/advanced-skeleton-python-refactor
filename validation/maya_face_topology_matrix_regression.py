"""Generated Face, Skin, DG and spine attachment takeover for 4↔8 spines."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import maya.standalone


def main(folder: Path, source_count: int, target_count: int) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaFaceHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.application import (BuildFaceBlendShapes, GenerateFaceTarget,
                                        ReplaceRegisteredSpineCharacter)
        from adv_py.core import FaceLandmark, FaceShapeKind, FaceTarget

        stem = f"spine-{source_count}-to-{target_count}-face"
        cmds.file(str(folder / f"spine-{source_count}-to-{target_count}-before.ma"),
                  open=True, force=True)
        cmds.undoInfo(state=True)
        face = MayaFaceHost(namespace="source")
        source = face.read_character_registration()
        head = next(row.path for row in source.body
                    if row.path.rsplit("|", 1)[-1] == "Head_M")
        neutral = cmds.polyPlane(name="source:FaceNeutral", width=2, height=2,
                                 subdivisionsX=1, subdivisionsY=1,
                                 constructionHistory=False)[0]
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
        follower = cmds.createNode("transform", name="source:FaceFollower",
                                   parent=control)
        driver = cmds.createNode("multiplyDivide", name="source:FaceDriver")
        cmds.setAttr(driver + ".input2X", .75)
        cmds.connectAttr(control + ".smile_R", driver + ".input1X")
        cmds.connectAttr(driver + ".outputX", follower + ".translateX")
        for frame, values in ((0, (.15, 0.)), (1, (0., 0.)),
                              (5, (1., .4)), (10, (.2, 1.)),
                              (20, (.25, 0.))):
            for attr, value in zip(("smile_R", "viseme_A"), values):
                cmds.setKeyframe(control, attribute=attr, time=frame, value=value)

        old_spine_index = round(source_count * .75)
        attachment = cmds.createNode("transform", name="source:SpineProp",
            parent=face.scene_address(source.spine.body_joints[old_spine_index]))
        attachment = cmds.ls(attachment, long=True)[0]
        cmds.setAttr(attachment + ".translateY", .2)
        identities = {node: cmds.ls(node, uuid=True)[0]
                      for node in (neutral, "source:FaceSkin", control, follower,
                                   driver, attachment, face.scene_address(smile.mesh),
                                   face.scene_address(viseme.mesh))}
        frames = (1, 5, 10)

        def sample(node: str) -> dict[int, tuple[float, ...]]:
            old_time = cmds.currentTime(query=True)
            undo = cmds.undoInfo(query=True, state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                values = {}
                for frame in frames:
                    cmds.currentTime(frame, edit=True)
                    values[frame] = tuple(cmds.xform(node, query=True,
                        worldSpace=True, matrix=True))
                return values
            finally:
                cmds.currentTime(old_time, edit=True)
                cmds.undoInfo(stateWithoutFlush=undo)

        attachment_before = sample(attachment)
        cmds.currentTime(1, edit=True)
        cmds.file(rename=str(folder / f"{stem}-before.ma"))
        cmds.file(save=True, type="mayaAscii", force=True)
        targets = (face.scene_address(smile.mesh), face.scene_address(viseme.mesh))
        service = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace="target"))
        result = service.apply_many("source", "target", (
            ("source:SourceSkin", "|source:SourceMesh"),
            ("source:FaceSkin", "|source:FaceNeutral")),
            start_frame=1, end_frame=10, max_mesh_error=.2,
            extensions=(control, attachment), retained_assets=targets,
            retained_graph_roots=(driver,))

        def check() -> dict[str, object]:
            active = MayaFaceHost(namespace="source")
            registration = active.read_character_registration()
            nodes = {node: cmds.ls(uuid, long=True) or []
                     for node, uuid in identities.items()}
            prop = nodes[attachment][0] if nodes[attachment] else ""
            parent = (cmds.listRelatives(prop, parent=True, fullPath=True)
                      or [None])[0] if prop else None
            grandparent = (cmds.listRelatives(parent, parent=True, fullPath=True)
                           or [None])[0] if parent else None
            expected_joint = active.scene_address(
                registration.spine.body_joints[round(target_count * .75)])
            current = sample(prop) if prop else {}
            matrix_error = max((abs(a-b) for frame in frames
                for a,b in zip(attachment_before[frame], current[frame])),
                default=float("inf"))
            new_control = nodes[control][0] if nodes[control] else ""
            new_follower = nodes[follower][0] if nodes[follower] else ""
            new_driver = nodes[driver][0] if nodes[driver] else ""
            return dict(spine_joints=len(registration.spine.body_joints),
                target_removed=not cmds.namespace(exists="target"),
                identities=all(nodes.values()),
                attachment_parent=grandparent == expected_joint,
                attachment_matrix_error=matrix_error,
                face_values=bool(new_control) and all(
                    abs(cmds.getAttr(new_control + ".smile_R", time=f) - v) < 1e-6
                    for f,v in ((0, .15), (5, 1.), (20, .25))),
                driver_connection=bool(new_follower and new_driver) and
                    cmds.connectionInfo(new_follower + ".translateX",
                        sourceFromDestination=True) == new_driver + ".outputX",
                follower_value=bool(new_follower) and abs(cmds.getAttr(
                    new_follower + ".translateX", time=5) - .75) < 1e-6,
                skins=all(cmds.objExists(name) for name in
                    ("source:SourceSkin", "source:FaceSkin")))

        def valid(state: dict[str, object]) -> bool:
            return (state["spine_joints"] == target_count + 1 and
                all(value for key, value in state.items()
                    if key not in ("spine_joints", "attachment_matrix_error")) and
                state["attachment_matrix_error"] < 1e-4)

        passed = check()
        cmds.undo()
        undo = (cmds.namespace(exists="target") and
                len(MayaBodyBuildHost(namespace="source")
                    .read_character_registration().spine.body_joints)
                == source_count + 1 and
                all(cmds.ls(uuid) for uuid in identities.values()))
        cmds.redo()
        redone = check()
        redo = valid(redone)
        output = folder / f"{stem}-replaced.ma"
        cmds.file(rename=str(output))
        cmds.file(save=True, type="mayaAscii", force=True)
        cmds.file(str(output), open=True, force=True)
        reopened_state = check()
        reopened = valid(reopened_state)
        report = dict(source=source_count, target=target_count,
                      result=dict(frames=result.frames, skins=result.skin_count,
                                  vertices=result.vertices),
                      passed=passed, undo=undo, redo=redone,
                      reopened=reopened_state)
        (folder / f"{stem}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if (valid(passed) and undo and redo and reopened and
            result.skin_count == 2 and result.vertices == 8) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]),
                          int(sys.argv[3])))
