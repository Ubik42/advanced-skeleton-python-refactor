"""Transfer original ADV eyelid Skin to an equal-topology Python face rig."""
from __future__ import annotations

from array import array
from math import dist
import re

from adv_py.core.dense_skin_transfer import DenseSkinWeights
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_eyelid_rig import MayaFaceEyeLidRigHost


_LID = re.compile(r"^((?:upper|lower)Lid(?:Main|Outer))(\d+)(_[RL])$")
_AUX = re.compile(r"^lowerLidOuterJoint_([RL])$")


def _base(name: str) -> str:
    return name.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


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
        """Graft ADV eyelid influences from a visible equal-topology source."""
        from maya import cmds as raw
        from maya.api import OpenMaya as om

        c = self._cmds
        motion = (c.ls("FaceMotionSystem", long=True,
                       type="transform") or [])
        if len(motion) != 1 or not c.attributeQuery(
                "advPyFaceMesh", node=motion[0], exists=True):
            raise FitSkeletonValidationError("目标场景尚未建立 Python 眼睑绑定")
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
        target_by_base = {_base(name): name for name in before.influence_names}
        if len(target_by_base) != len(before.influence_names) or "Head_M" not in target_by_base:
            raise FitSkeletonValidationError("目标影响关节名称不唯一或缺少 Head_M")
        lid_targets = {name: target for name, target in target_by_base.items()
                       if _LID.fullmatch(name)}
        if not lid_targets:
            raise FitSkeletonValidationError("目标 Skin 没有眼睑分段关节")
        source_map = []
        auxiliary = {}
        approximated = 0
        source_lid_names = set()
        for index, joint in enumerate(source_joints):
            name = _base(joint)
            match = _LID.fullmatch(name)
            if match:
                if name in source_lid_names:
                    raise FitSkeletonValidationError(
                        "来源眼睑影响关节重名：" + name)
                source_lid_names.add(name)
                target = lid_targets.get(name)
                if target is None:
                    candidates = [(abs(int(_LID.fullmatch(other).group(2)) -
                                       int(match.group(2))), other)
                                  for other in lid_targets
                                  if (other.startswith(match.group(1)) and
                                      other.endswith(match.group(3)))]
                    if not candidates:
                        raise FitSkeletonValidationError(
                            "目标缺少眼睑分段：" + name)
                    target = lid_targets[min(candidates)[1]]
                    approximated += 1
                source_map.append((index, target))
            elif _AUX.fullmatch(name):
                side = _AUX.fullmatch(name).group(1)
                if side in auxiliary:
                    raise FitSkeletonValidationError("原版外围关节重名")
                auxiliary[side] = (index, joint)
        if not source_map:
            raise FitSkeletonValidationError("来源不是已绑定的原版眼睑 Skin")
        roots = c.ls("FaceJoint_M", long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("目标 FaceJoint_M 缺失或不唯一")
        for side in auxiliary:
            if c.objExists("lowerLidOuterJoint_" + side):
                raise FitSkeletonValidationError("目标外围关节已存在")
            if not c.objExists("ctrlLowerEyeLidOuter_" + side + "MotionSum"):
                raise FitSkeletonValidationError("目标下 Outer 驱动缺失")
        selected = c.ls(selection=True, long=True) or []
        with self.transaction("迁移原版眼睑 Skin"):
            self._transaction_changed = True
            for side, (_, source_joint) in auxiliary.items():
                name = "lowerLidOuterJoint_" + side
                pivot = raw.xform(source_joint, query=True,
                                  worldSpace=True, translation=True)
                c.select(clear=True)
                joint = c.joint(name=name)
                joint = c.parent(joint, roots[0], absolute=True)[0]
                c.xform(joint, worldSpace=True, translation=pivot)
                addition = c.createNode("plusMinusAverage",
                                        name=name + "MotionSum")
                c.setAttr(addition + ".input3D[0]", *pivot, type="double3")
                c.connectAttr("ctrlLowerEyeLidOuter_" + side +
                              "MotionSum.output3D", addition + ".input3D[1]")
                c.connectAttr(addition + ".output3D", joint + ".translate")
                c.skinCluster(target_skin, edit=True,
                              addInfluence=joint, weight=0.)
            target = self.capture_dense_skin(target_skin)
            target_index = {name: i for i, name in
                            enumerate(target.influence_names)}
            target_by_base = {_base(name): name for name in target.influence_names}
            source_map.extend((index, target_by_base[
                "lowerLidOuterJoint_" + side])
                for side, (index, _) in auxiliary.items())
            width = len(target.influence_names)
            old_width = len(before.influence_names)
            old_index = {name: i for i, name in
                         enumerate(before.influence_names)}
            old = memoryview(before.values).cast("d")
            values = array("d", [0.] * (before.vertex_count * width))
            lid_columns = {target_index[name] for _, name in source_map}
            non_lid = [(target_index[name], old_index[name])
                       for name in before.influence_names
                       if target_index[name] not in lid_columns]
            head_index = target_index[target_by_base["Head_M"]]
            for vertex in range(before.vertex_count):
                mass = 0.
                for source_index, name in source_map:
                    amount = max(0., source_values[
                        vertex * len(source_joints) + source_index])
                    values[vertex * width + target_index[name]] += amount
                    mass += amount
                if mass > 1. + 1e-5:
                    raise FitSkeletonValidationError(
                        f"原版顶点 {vertex} 的眼睑权重超过 1")
                remaining = max(0., 1. - mass)
                old_remaining = sum(max(0., old[
                    vertex * old_width + index]) for _, index in non_lid)
                if old_remaining > 1e-8:
                    for new_index, source_index in non_lid:
                        values[vertex * width + new_index] = (
                            remaining * max(0., old[
                                vertex * old_width + source_index]) /
                            old_remaining)
                else:
                    values[vertex * width + head_index] += remaining
            self.apply_dense_skin(DenseSkinWeights(target_skin,
                before.vertex_count, target.influence_names,
                values.tobytes()))
            blend = array("d", source_blend)
            if source_method == 0:
                blend = array("d", [0.] * before.vertex_count)
            elif source_method == 1:
                blend = array("d", [1.] * before.vertex_count)
            self.apply_skin_blend_weights(target_skin, blend)
            c.setAttr(target_skin + ".skinningMethod", 2)
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return {"source_mesh": source_path, "target_mesh": target_mesh,
                "vertex_count": before.vertex_count,
                "mapped_segment_influences": len(source_map) - len(auxiliary),
                "approximated_segments": approximated,
                "auxiliary_joints": tuple("lowerLidOuterJoint_" + side
                                          for side in sorted(auxiliary)),
                "maximum_rest_position_error_cm": round(position_error, 8)}
