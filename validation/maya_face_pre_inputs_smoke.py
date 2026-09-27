"""Exercise Face / Pre polygon Mask, Face and All Head in Maya."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds

from adv_py.adapters.maya_face_pre import MayaFacePreHost
from adv_py.application.face_pre import FacePreRole, RecordFacePreInput
from adv_py.product.maya_panel_controller import MayaPanelController


def main():
    with TemporaryDirectory(prefix="advpy-face-pre-") as folder:
        scene = Path(folder) / "face-pre.mb"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.select(clear=True)
        head = cmds.joint(name="Head_M", position=(0, 3, 0))
        face = cmds.polySphere(name="FaceMesh", radius=1,
                               subdivisionsX=12, subdivisionsY=8,
                               constructionHistory=False)[0]
        cmds.xform(face, worldSpace=True, translation=(0, 3, .5))
        hair = cmds.polyCube(name="HairMesh", width=2, height=.4,
                             depth=1.4, constructionHistory=False)[0]
        cmds.xform(hair, worldSpace=True, translation=(0, 4, .2))
        controller = MayaPanelController()
        cmds.select(face, replace=True)
        try:
            controller.face_pre_record_mask(":")
        except ValueError:
            pass
        else:
            raise AssertionError("Mask must reject whole-object selection")
        cmds.select(face + ".f[0:11]", replace=True)
        bounds = cmds.exactWorldBoundingBox(face + ".f[0:11]")
        mesh, count, scale = controller.face_pre_record_mask(":")
        assert mesh == "|FaceMesh" and count == 12 and scale > 0
        host = MayaFacePreHost()
        assert host.read_face_mask() == (mesh, tuple(range(12)), scale)
        fit = cmds.ls("FaceFitSkeleton", long=True, type="transform")[0]
        assert len(cmds.listRelatives(fit, shapes=True,
                                      type="nurbsCurve") or []) == 4
        base = cmds.xform(fit + "|FaceFitSkeletonShape.cv[0]", query=True,
                          worldSpace=True, translation=True)
        upper = cmds.xform(fit + "|FaceFitSkeletonHeightShape.cv[0]", query=True,
                           worldSpace=True, translation=True)
        assert abs(base[1] - bounds[1]) < 1e-5
        assert abs(upper[1] - bounds[4]) < 1e-5
        for name, y in (("FaceFitSkeletonShape", bounds[1]),
                        ("FaceFitSkeletonHeightShape", bounds[4]),
                        ("FaceFitSkeletonCircleShape", bounds[1]),
                        ("FaceFitSkeletonHeightCircleShape", bounds[4])):
            shape = fit + "|" + name
            box = cmds.exactWorldBoundingBox(shape)
            half_width = (bounds[3] - bounds[0]) / 2
            expected = (-half_width, y, bounds[2],
                        half_width, y, bounds[5])
            assert max(abs(a - b) for a, b in zip(box, expected)) < 1e-4, (
                name, box, expected)
        cmds.select(hair, replace=True)
        try:
            controller.face_pre_record_objects(":", "Face", head)
        except ValueError:
            pass
        else:
            raise AssertionError("Face must match Mask mesh")
        cmds.select(face, replace=True)
        assert controller.face_pre_record_objects(":", "Face", head) == (mesh,)
        assert len(cmds.ls(type="skinCluster") or []) == 1
        cmds.select(hair, replace=True)
        try:
            controller.face_pre_record_objects(":", "AllHead", head)
        except ValueError:
            pass
        else:
            raise AssertionError("All Head must contain Face")
        cmds.select(face, hair, replace=True)
        assert controller.face_pre_record_objects(":", "AllHead", head) == (
            "|FaceMesh", "|HairMesh")
        assert len(cmds.ls(type="skinCluster") or []) == 2
        cmds.undo()
        assert host.read_face_objects(FacePreRole.ALL_HEAD) == ()
        assert len(cmds.ls(type="skinCluster") or []) == 1
        cmds.redo()
        assert host.read_face_objects(FacePreRole.ALL_HEAD) == (
            "|FaceMesh", "|HairMesh")
        assert len(cmds.ls(type="skinCluster") or []) == 2
        eye = cmds.polySphere(name="EyeRight", radius=.25,
                              subdivisionsX=8, subdivisionsY=8,
                              constructionHistory=False)[0]
        cmds.xform(eye, worldSpace=True, translation=(-.5, 3.2, 1.2))
        eye_bounds = cmds.exactWorldBoundingBox(eye)
        eye_fit = controller.face_fit_eye_ball(":", "|EyeRight", head)
        position = cmds.xform(eye_fit, query=True, worldSpace=True,
                              translation=True)
        assert max(abs(position[axis] -
            (eye_bounds[axis] + eye_bounds[axis + 3]) / 2)
            for axis in range(3)) < 1e-5
        diameter = eye_bounds[4] - eye_bounds[1]
        assert abs(cmds.getAttr(eye_fit + ".scaleY") - diameter) < 1e-5
        assert cmds.objExists("FitEyeSphere")
        cmds.undo()
        assert not cmds.objExists("FitEyeBall")
        cmds.redo()
        assert cmds.objExists("FitEyeBall")
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(scene), open=True, force=True,
                  executeScriptNodes=False)
        reopened = MayaFacePreHost()
        assert reopened.read_face_mask() == (mesh, tuple(range(12)), scale)
        assert reopened.read_face_objects(FacePreRole.FACE) == (mesh,)
        assert reopened.read_face_objects(FacePreRole.ALL_HEAD) == (
            "|FaceMesh", "|HairMesh")
        assert len(cmds.ls(type="skinCluster") or []) == 2
        assert reopened.read_eye_ball_fit().endswith("|FitEyeBall")
        assert controller.face_pre_reselect(":", "Mask") == 12
        assert len(cmds.ls(selection=True, flatten=True) or []) == 12
        assert controller.face_pre_reselect(":", "AllHead") == 2
        assert len(cmds.ls(selection=True) or []) == 2
        print("Face Pre Mask, Face, All Head Maya smoke: OK", flush=True)


if __name__ == "__main__":
    main()
