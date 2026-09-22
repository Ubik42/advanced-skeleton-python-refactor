"""Maya expression/viseme blendShape adapter."""
from __future__ import annotations

from hashlib import sha256
import json

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.face_shapes import FaceMeshSnapshot
from adv_py.application.face_shapes import FaceBinding, FaceBuildPlan

from .maya_body import MayaBodyBuildHost


class MayaFaceHost(MayaBodyBuildHost):
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot:
        from maya import cmds
        from maya.api import OpenMaya as om

        actual = self.scene_address(path)
        matches = cmds.ls(actual, long=True, type="transform") or []
        if len(matches) != 1:
            raise CharacterRegistryError("面部网格 Transform 缺失或歧义：" + path)
        shapes = cmds.listRelatives(matches[0], shapes=True, noIntermediate=True,
                                    fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise CharacterRegistryError("面部目标必须有且只有一个可见 mesh shape：" + path)
        selection = om.MSelectionList()
        selection.add(shapes[0])
        fn = om.MFnMesh(selection.getDagPath(0))
        counts, vertices = fn.getVertices()
        topology = sha256(repr((tuple(counts), tuple(vertices))).encode("ascii")).hexdigest()
        points = tuple((float(point.x), float(point.y), float(point.z))
                       for point in fn.getPoints(om.MSpace.kObject))
        return FaceMeshSnapshot(path, len(points), topology, points)

    def face_names_available(self, control_path: str, deformer_name: str) -> bool:
        from maya import cmds
        return (not cmds.objExists(self.scene_address(control_path))
                and not cmds.objExists(self.scene_address(deformer_name)))

    def build_face_shapes(self, plan: FaceBuildPlan) -> None:
        from maya import cmds

        self._require_transaction()
        if not self.face_names_available(plan.control_path, plan.deformer_name):
            raise CharacterRegistryError("面部构建名称在执行前被占用")
        c = self._cmds
        selection = cmds.ls(selection=True, long=True) or []
        self._transaction_changed = True
        try:
            control_name = plan.control_path.rsplit("|", 1)[-1]
            created_control = c.createNode("transform", name=control_name,
                                           parent=plan.head_joint, skipSelect=True)
            if (c.ls(created_control, long=True, type="transform") or []) != [plan.control_path]:
                raise RuntimeError("面部控制路径与计划不一致")
            control = plan.control_path
            c.addAttr(control, longName="advPyFaceSchemaVersion", attributeType="long")
            c.setAttr(control + ".advPyFaceSchemaVersion", 1, lock=True)
            manifest = json.dumps(tuple((target.name, target.kind.value)
                for target, _ in plan.targets), separators=(",", ":"))
            c.addAttr(control, longName="advPyFaceManifest", dataType="string")
            c.setAttr(control + ".advPyFaceManifest", manifest,
                      type="string", lock=True)
            meshes = tuple(target.mesh for target, _ in plan.targets)
            created = c.blendShape(*meshes, plan.neutral.path,
                                   name=plan.deformer_name, frontOfChain=True)
            if len(created) != 1 or created[0] != plan.deformer_name:
                raise RuntimeError("面部 BlendShape 创建结果与计划不一致")
            for index, (target, _) in enumerate(plan.targets):
                c.addAttr(control, longName=target.name, attributeType="double",
                          minValue=0., maxValue=1., defaultValue=0., keyable=True)
                weight = f"{plan.deformer_name}.weight[{index}]"
                cmds.aliasAttr(target.name, self.scene_address(weight))
                c.connectAttr(f"{control}.{target.name}", weight, force=False)
        finally:
            if selection:
                cmds.select(selection, replace=True)
            else:
                cmds.select(clear=True)

    def capture_face_binding(self, plan: FaceBuildPlan) -> FaceBinding:
        from maya import cmds

        control = self.scene_address(plan.control_path)
        deformer = self.scene_address(plan.deformer_name)
        if (not cmds.objExists(control) or cmds.nodeType(deformer) != "blendShape"
                or cmds.getAttr(control + ".advPyFaceSchemaVersion") != 1):
            raise RuntimeError("面部控制或 BlendShape 结构缺失")
        expected_manifest = json.dumps(tuple((target.name, target.kind.value)
            for target, _ in plan.targets), separators=(",", ":"))
        if cmds.getAttr(control + ".advPyFaceManifest") != expected_manifest:
            raise RuntimeError("面部目标语义清单读回不一致")
        aliases = cmds.aliasAttr(deformer, query=True) or []
        alias_map = {aliases[index + 1]: aliases[index]
                     for index in range(0, len(aliases), 2)}
        rows = []
        for index, (target, _) in enumerate(plan.targets):
            weight = f"{deformer}.weight[{index}]"
            source = cmds.connectionInfo(weight, sourceFromDestination=True)
            if source:
                source_node, source_attribute = source.rsplit(".", 1)
                source_matches = cmds.ls(source_node, long=True) or []
                source = (source_matches[0] + "." + source_attribute
                          if len(source_matches) == 1 else source)
            alias = alias_map.get(f"weight[{index}]", alias_map.get(f"w[{index}]"))
            if source != f"{control}.{target.name}" or alias != target.name:
                raise RuntimeError("面部控制属性未连接到声明的 BlendShape 权重："
                    + repr((source, alias, control, target.name)))
            rows.append((target.name, target.kind.value,
                         f"{plan.deformer_name}.weight[{index}]"))
        neutral = self.capture_face_mesh(plan.neutral.path)
        if neutral.vertex_count != plan.neutral.vertex_count:
            raise RuntimeError("面部构建改变了中性网格拓扑")
        maximum = 0.
        for target, _ in plan.targets:
            plug = f"{control}.{target.name}"
            source = cmds.connectionInfo(plug, sourceFromDestination=True)
            if source:
                times = cmds.keyframe(plug, query=True, timeChange=True) or []
                values = cmds.keyframe(plug, query=True, valueChange=True) or []
                if not times or len(times) != len(values):
                    raise RuntimeError("面部控制动画曲线缺少可采样关键帧")
                frame = times[max(range(len(values)), key=lambda index: values[index])]
                with self._character_sampling_time() as seek:
                    seek(frame)
                    active = self.capture_face_mesh(plan.neutral.path)
            else:
                original = float(cmds.getAttr(plug))
                try:
                    cmds.setAttr(plug, 1.)
                    active = self.capture_face_mesh(plan.neutral.path)
                finally:
                    cmds.setAttr(plug, original)
            maximum = max(maximum, *(abs(a - b)
                for left, right in zip(neutral.points, active.points)
                for a, b in zip(left, right)))
        return FaceBinding(plan.control_path, plan.deformer_name,
                           tuple(rows), maximum)
