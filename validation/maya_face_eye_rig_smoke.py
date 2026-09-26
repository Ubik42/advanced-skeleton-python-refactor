"""Build eye controls on a registered Body with two referenced eyeballs."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.adapters.maya_face_eye import MayaFaceEyeHost
from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
from adv_py.application import (BuildBodyCharacterRig,
    BuildOrientedBodySkeleton, BuildVariableBodySourceFit,
    CreateFitSkeleton, RegisterBodyCharacter)
from adv_py.application.face_eye_rig import BuildFaceEyeRig
from adv_py.application.preparation_reference import ReferencePreparationModel
from adv_py.core.variable_body_fit import variable_axial_description
from adv_py.product.maya_panel_controller import MayaPanelController


def point(mesh):
    return tuple(cmds.pointPosition(mesh + ".vtx[0]", world=True))


def main() -> None:
    with TemporaryDirectory(prefix="advpy-face-eyes-") as folder:
        folder = Path(folder)
        model = folder / "eyes.mb"
        scene = folder / "eye-rig.mb"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        host = MayaFaceEyeHost()
        CreateFitSkeleton(host).apply()
        BuildVariableBodySourceFit(host).apply(spine_segments=4)
        BuildOrientedBodySkeleton(host).apply()
        rig = BuildBodyCharacterRig(host).apply(
            include_torso=True, include_spine_ik=True,
            include_control_spaces=True,
            axial_description=variable_axial_description(4))
        registration = RegisterBodyCharacter(host).apply(rig)
        before_roles = MayaPanelController().characters()
        head = next(joint.path for joint in registration.body
                    if joint.path.rsplit("|", 1)[-1] == "Head_M")
        head_pos = cmds.xform(head, query=True, worldSpace=True,
                              translation=True)
        for name, side in (("EyeRight", -1), ("EyeLeft", 1)):
            cmds.polySphere(name=name, radius=.25, subdivisionsX=8,
                            subdivisionsY=6, constructionHistory=False)
            cmds.xform(name, worldSpace=True, translation=(
                head_pos[0] + side * .55, head_pos[1] + .1,
                head_pos[2] + .75))
        cmds.select("EyeRight", "EyeLeft", replace=True)
        cmds.file(str(model), exportSelected=True, type="mayaBinary", force=True)
        cmds.delete("EyeRight", "EyeLeft")
        ReferencePreparationModel(MayaPreparationReferenceHost()).execute(model)
        right, left = "|model:EyeRight", "|model:EyeLeft"

        def fault(stage):
            if stage == "skins-bound":
                raise RuntimeError("injected")
        try:
            BuildFaceEyeRig(MayaFaceEyeHost()).apply(
                head, right, left, on_stage=fault)
        except RuntimeError as error:
            assert str(error) == "injected", error
        else:
            raise AssertionError("Eye rig failure must roll back")
        assert not cmds.objExists("AdvPy_FaceEyes")
        assert not cmds.ls("AdvPy_EyeSkin_*", type="skinCluster")
        result = MayaPanelController().face_eye_build(":", head, right, left)
        after_roles = MayaPanelController().characters()
        assert any(row.namespace == ":" and row.registered for row in before_roles), before_roles
        assert any(row.namespace == ":" and row.registered for row in after_roles), after_roles
        assert len(result.skins) == 2
        assert len(cmds.ls("AdvPy_EyeSkin_*", type="skinCluster") or []) == 2
        before_right, before_left = point(right), point(left)
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(result.right_control + ".translateX", .5)
        right_only, left_still = point(right), point(left)
        assert abs(right_only[0] - before_right[0]) > 1e-4
        assert max(abs(a - b) for a, b in zip(left_still, before_left)) < 1e-6
        cmds.setAttr(result.right_control + ".translateX", 0)
        cmds.setAttr(result.global_control + ".translateX", .5)
        both_right, both_left = point(right), point(left)
        assert abs(both_right[0] - before_right[0]) > 1e-4
        assert abs(both_left[0] - before_left[0]) > 1e-4
        cmds.setAttr(result.global_control + ".translateX", 0)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        assert not cmds.objExists("AdvPy_FaceEyes")
        assert not cmds.ls("AdvPy_EyeSkin_*", type="skinCluster")
        cmds.redo()
        assert cmds.objExists("AdvPy_FaceEyes")
        assert len(cmds.ls("AdvPy_EyeSkin_*", type="skinCluster") or []) == 2
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(scene), open=True, force=True,
                  executeScriptNodes=False)
        assert len(cmds.ls("AdvPy_EyeSkin_*", type="skinCluster") or []) == 2
        assert cmds.referenceQuery("model:EyeRight", isNodeReferenced=True)
        assert cmds.objExists("AdvPy_EyeAim")
        assert any(row.namespace == ":" and row.registered
                   for row in MayaPanelController().characters())
        cmds.setKeyframe("AdvPy_EyeAim.translateX", time=1, value=0)
        cmds.setKeyframe("AdvPy_EyeAim.translateX", time=5, value=.8)
        expected = {}
        for frame in (1, 5):
            cmds.currentTime(frame, edit=True)
            expected[frame] = (point(right), point(left))
        exported = folder / "eyes.fbx"
        publication = MayaPanelController().publish_fbx(
            ":", exported, 1, 5, include_skins=True)
        assert publication.bytes_written > 0 and exported.is_file()
        assert len(cmds.ls("AdvPy_EyeSkin_*", type="skinCluster") or []) == 2
        cmds.file(new=True, force=True)
        cmds.file(str(exported), i=True, type="FBX", ignoreVersion=True,
                  executeScriptNodes=False)
        assert len(cmds.ls(type="skinCluster") or []) == 2
        for name in ("AdvPy_Eye_R", "AdvPy_Eye_L"):
            assert len(cmds.ls(name, type="joint", long=True) or []) == 1
        maximum_error = 0.0
        for frame in (1, 5):
            cmds.currentTime(frame, edit=True)
            actual = (point("EyeRight"), point("EyeLeft"))
            maximum_error = max(maximum_error, *(abs(a - b)
                for source, target in zip(expected[frame], actual)
                for a, b in zip(source, target)))
        assert maximum_error < .01, maximum_error
        print("Face eye controls and skinned FBX roundtrip: OK",
              maximum_error, flush=True)


if __name__ == "__main__":
    main()
