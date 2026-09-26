"""Maya adapter for paired eye controls and referenced eye geometry."""
from __future__ import annotations

from adv_py.application.face_eye_rig import FaceEyeRigResult
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face import MayaFaceHost


class MayaFaceEyeHost(MayaFaceHost):
    def preflight_face_eye_head(self, head_joint: str) -> None:
        matches = self._cmds.ls(head_joint, long=True, type="joint") or []
        if matches != [head_joint]:
            raise FitSkeletonValidationError("Head 关节路径不存在或不唯一")
        if self._cmds.referenceQuery(head_joint, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能在只读引用的 Head 关节下构建眼部控制")

    def selected_eye_mesh(self) -> str:
        c = self._cmds
        selected = c.ls(selection=True, long=True, objectsOnly=True) or []
        if len(selected) != 1:
            raise ValueError("请只选择一件眼球网格")
        node = selected[0]
        if c.nodeType(node) == "mesh":
            node = (c.listRelatives(node, parent=True, fullPath=True) or [None])[0]
        shapes = c.listRelatives(node, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or [] if node else []
        if len(shapes) != 1:
            raise ValueError("所选对象需要唯一可见多边形网格")
        return node

    def create_face_eye_rig(self, head_joint: str, right_eye: str,
                            left_eye: str) -> FaceEyeRigResult:
        self._require_transaction()
        c = self._cmds
        selection = c.ls(selection=True, long=True) or []
        bounds = [c.exactWorldBoundingBox(mesh)
                  for mesh in (right_eye, left_eye)]
        centers = [tuple((box[axis] + box[axis + 3]) / 2.0
                         for axis in range(3)) for box in bounds]
        radii = [max(box[3] - box[0], box[4] - box[1],
                     box[5] - box[2]) / 2.0 for box in bounds]
        if any(radius <= 1e-6 for radius in radii):
            raise FitSkeletonValidationError("眼球网格包围盒无效")
        self._transaction_changed = True
        try:
            group = c.createNode("transform", name="AdvPy_FaceEyes",
                                 parent=head_joint)
            average = tuple((centers[0][axis] + centers[1][axis]) / 2.0
                            for axis in range(3))
            distance = max(radii) * 4.0
            global_control = c.circle(name="AdvPy_EyeAim",
                normal=(0, 0, 1), radius=max(radii) * 1.5,
                constructionHistory=False)[0]
            c.parent(global_control, group, absolute=True)
            c.xform(global_control, worldSpace=True,
                    translation=(average[0], average[1], average[2] + distance))
            controls = []
            joints = []
            for side, center, radius in zip(("R", "L"), centers, radii):
                c.select(clear=True)
                joint = c.joint(name="AdvPy_Eye_" + side,
                                position=center)
                c.parent(joint, group, absolute=True)
                c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                          dataType="string")
                c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                          "face-eye-v1", type="string", lock=True)
                control = c.circle(name="AdvPy_EyeAim_" + side,
                    normal=(0, 0, 1), radius=radius * .65,
                    constructionHistory=False)[0]
                c.parent(control, global_control, absolute=True)
                c.xform(control, worldSpace=True,
                    translation=(center[0], center[1], center[2] + distance))
                c.aimConstraint(control, joint, aimVector=(0, 0, 1),
                    upVector=(0, 1, 0), worldUpType="objectrotation",
                    worldUpObject=head_joint, maintainOffset=False)
                controls.append((c.ls(control, long=True,
                                      type="transform") or [])[0])
                joints.append((c.ls(joint, long=True, type="joint") or [])[0])
            c.addAttr(group, longName="advPyRightEyeMesh", dataType="string")
            c.setAttr(group + ".advPyRightEyeMesh", right_eye, type="string")
            c.addAttr(group, longName="advPyLeftEyeMesh", dataType="string")
            c.setAttr(group + ".advPyLeftEyeMesh", left_eye, type="string")
            return FaceEyeRigResult(
                (c.ls(group, long=True, type="transform") or [])[0],
                (c.ls(global_control, long=True, type="transform") or [])[0],
                controls[0], controls[1], joints[0], joints[1],
                ("AdvPy_EyeSkin_R", "AdvPy_EyeSkin_L"))
        finally:
            c.select(selection, replace=True) if selection else c.select(clear=True)
