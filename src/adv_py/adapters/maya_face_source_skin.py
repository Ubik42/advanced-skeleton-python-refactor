"""Transfer original ADV eyelid Skin to an equal-topology Python face rig."""
from __future__ import annotations

from array import array

from adv_py.application.face_source_skin import (
    FaceSourceSkinCapture, TransferOriginalEyeLidSkin,
)
from adv_py.core.face_source_skin_mapping import FaceSourceSkinMapping, face_influence_base
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_eyelid_rig import MayaFaceEyeLidRigHost


def _mesh_skin(cmds, mesh_name: str):
    from maya.api import OpenMaya as om
    from maya.api import OpenMayaAnim as oma

    matches = cmds.ls(mesh_name, long=True, type="transform") or []
    if len(matches) != 1:
        raise FitSkeletonValidationError("原版头部网格缺失或不唯一")
    shapes = cmds.listRelatives(matches[0], shapes=True,
                                noIntermediate=True, fullPath=True,
                                type="mesh") or []
    if len(shapes) != 1:
        raise FitSkeletonValidationError("原版头部需要唯一网格形状")
    skins = [node for node in cmds.listHistory(shapes[0]) or ()
             if cmds.nodeType(node) == "skinCluster"]
    if len(skins) != 1:
        raise FitSkeletonValidationError("原版头部需要唯一 Skin")
    selection = om.MSelectionList()
    selection.add(matches[0])
    dag = selection.getDagPath(0)
    mesh = om.MFnMesh(dag)
    selection = om.MSelectionList()
    selection.add(skins[0])
    skin = oma.MFnSkinCluster(selection.getDependNode(0))
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.addElements(range(mesh.numVertices))
    weights, width = skin.getWeights(dag, component)
    influences = tuple(path.fullPathName()
                       for path in skin.influenceObjects())
    if width != len(influences):
        raise RuntimeError("来源 Skin 权重维度不符")
    points = tuple(tuple(float(point[axis]) for axis in range(3))
                   for point in mesh.getPoints(om.MSpace.kWorld))
    blend = tuple(float(value) for value in
                  skin.getBlendWeights(dag, component))
    return (matches[0], skins[0], points, array("d", weights),
            influences, blend, int(cmds.getAttr(skins[0] + ".skinningMethod")))


class MayaFaceSourceSkinHost(MayaFaceEyeLidRigHost):
    def transfer_original_eye_lid_skin(self, source_mesh: str) -> dict:
        return TransferOriginalEyeLidSkin(self).execute(source_mesh)

    def capture_face_source_skin(
        self, source_mesh: str,
    ) -> FaceSourceSkinCapture:
        from maya import cmds as raw
        from maya.api import OpenMaya as om

        c = self._cmds
        motion = (c.ls("FaceMotionSystem", long=True,
                       type="transform") or [])
        if len(motion) != 1 or not c.attributeQuery(
                "advPyFaceMesh", node=motion[0], exists=True):
            raise FitSkeletonValidationError("目标场景尚未建立 Python 眼睑绑定")
        simpler_eyelid = (c.attributeQuery(
            "advPySimplerEyeLid", node=motion[0], exists=True)
            and bool(c.getAttr(motion[0] + ".advPySimplerEyeLid")))
        target_mesh = c.getAttr(motion[0] + ".advPyFaceMesh")
        target_shape = (c.listRelatives(target_mesh, shapes=True,
                        noIntermediate=True, fullPath=True,
                        type="mesh") or [])
        if len(target_shape) != 1:
            raise FitSkeletonValidationError("目标 Face 网格形状缺失")
        target_skins = [node for node in c.listHistory(target_shape[0]) or ()
                        if c.nodeType(node) == "skinCluster"]
        if len(target_skins) != 1:
            raise FitSkeletonValidationError("目标 Face 网格需要唯一 Skin")
        target_skin = target_skins[0]
        source = _mesh_skin(raw, source_mesh)
        source_path, _, source_points, source_values, source_joints, source_blend, source_method = source
        if source_path == target_mesh or source_method not in (0, 1, 2):
            raise FitSkeletonValidationError("来源必须是独立的原版 Face Skin")
        selection = om.MSelectionList()
        selection.add(target_mesh)
        target_fn = om.MFnMesh(selection.getDagPath(0))
        if target_fn.numVertices != len(source_points):
            raise FitSkeletonValidationError("原版与目标头部顶点数不同")
        target_points = target_fn.getPoints(om.MSpace.kWorld)
        position_error = max(max(abs(a[axis] - b[axis])
            for axis in range(3)) for a, b in zip(source_points, target_points))
        if position_error > 1e-4:
            raise FitSkeletonValidationError(
                f"原版与目标头部当前形态不一致：{position_error:.6f} cm")
        before = self.capture_dense_skin(target_skin)
        target_by_base = {face_influence_base(name): name
                          for name in before.influence_names}
        if len(target_by_base) != len(before.influence_names) or "Head_M" not in target_by_base:
            raise FitSkeletonValidationError("目标影响关节名称不唯一或缺少 Head_M")
        return FaceSourceSkinCapture(
            source_path, target_mesh, target_skin, source_joints,
            source_values, source_blend, source_method, before,
            simpler_eyelid, position_error,
            tuple(c.ls(selection=True, long=True) or ()))

    def preflight_face_source_auxiliaries(
        self, capture: FaceSourceSkinCapture,
        mapping: FaceSourceSkinMapping,
    ) -> None:
        c = self._cmds
        roots = c.ls("FaceJoint_M", long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("目标 FaceJoint_M 缺失或不唯一")
        target_by_base = {face_influence_base(name): name
                          for name in capture.before.influence_names}
        for side, _ in mapping.auxiliary_sources:
            joint_name = "lowerLidOuterJoint_" + side
            if capture.simpler_eyelid:
                joint = c.ls(joint_name, long=True, type="joint") or []
                if (len(joint) != 1
                        or joint_name not in target_by_base
                        or not c.attributeQuery(
                            "advPyAuxiliaryInfluenceKind", node=joint[0],
                            exists=True)
                        or c.getAttr(joint[0] +
                            ".advPyAuxiliaryInfluenceKind") !=
                            "face-lower-outer-v1"):
                    raise FitSkeletonValidationError(
                        "简化眼睑目标外围关节未完成")
            else:
                if c.objExists(joint_name):
                    raise FitSkeletonValidationError("目标外围关节已存在")
                if not c.objExists(
                    "ctrlLowerEyeLidOuter_" + side + "MotionSum"):
                    raise FitSkeletonValidationError("目标下 Outer 驱动缺失")

    def create_face_source_auxiliary(
        self, side: str, source_joint: str, target_skin: str,
    ) -> None:
        from maya import cmds as raw

        self._require_transaction()
        c = self._cmds
        roots = c.ls("FaceJoint_M", long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("目标 FaceJoint_M 缺失或不唯一")
        name = "lowerLidOuterJoint_" + side
        pivot = raw.xform(source_joint, query=True,
                          worldSpace=True, translation=True)
        c.select(clear=True)
        joint = c.joint(name=name)
        joint = c.parent(joint, roots[0], absolute=True)[0]
        c.xform(joint, worldSpace=True, translation=pivot)
        addition = c.createNode("plusMinusAverage", name=name + "MotionSum")
        c.setAttr(addition + ".input3D[0]", *pivot, type="double3")
        c.connectAttr("ctrlLowerEyeLidOuter_" + side +
                      "MotionSum.output3D", addition + ".input3D[1]")
        c.connectAttr(addition + ".output3D", joint + ".translate")
        c.skinCluster(target_skin, edit=True, addInfluence=joint, weight=0.)
        self._transaction_changed = True

    def set_face_source_skinning_method(self, skin_name: str) -> None:
        self._require_transaction()
        self._cmds.setAttr(skin_name + ".skinningMethod", 2)
        self._transaction_changed = True

    def restore_face_source_selection(self, selected: tuple[str, ...]) -> None:
        c = self._cmds
        c.select(selected, replace=True) if selected else c.select(clear=True)
