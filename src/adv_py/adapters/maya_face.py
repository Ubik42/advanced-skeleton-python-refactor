"""Maya expression/viseme blendShape adapter."""
from __future__ import annotations

from hashlib import sha256
import json

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.face_shapes import FaceMeshSnapshot, FaceShapeKind
from adv_py.core.face_performance import FacePerformance
from adv_py.application.face_shapes import FaceBinding, FaceBuildPlan
from adv_py.application.face_performance import FacePerformancePlan
from adv_py.application.face_landmarks import FaceTargetGenerationPlan

from .maya_body import MayaBodyBuildHost


class MayaFaceHost(MayaBodyBuildHost):
    def face_target_path_available(self, path: str) -> bool:
        from maya import cmds

        return not cmds.objExists(self.scene_address(path))

    def create_face_target(self, plan: FaceTargetGenerationPlan) -> None:
        from maya import cmds

        self._require_transaction()
        if not self.face_target_path_available(plan.target.mesh):
            raise CharacterRegistryError("生成面部目标时路径已被占用")
        target = self.scene_address(plan.target.mesh)
        name = plan.target.mesh.rsplit("|", 1)[-1]
        selection = cmds.ls(selection=True, long=True) or []
        self._transaction_changed = True
        try:
            created = self._cmds.duplicate(plan.neutral.path, name=name,
                                           returnRootsOnly=True)
            if len(created) != 1 or (cmds.ls(self.scene_address(created[0]),
                                              long=True) or []) != [target]:
                raise RuntimeError("生成面部目标路径与计划不一致")
            self._cmds.delete(plan.target.mesh, constructionHistory=True)
            for index, point in enumerate(plan.points):
                if any(abs(a - b) > 1e-8 for a, b in
                       zip(point, plan.neutral.points[index])):
                    self._cmds.xform(f"{plan.target.mesh}.vtx[{index}]",
                                     objectSpace=True, translation=point)
            cmds.addAttr(target, longName="advPyFaceTargetProvenance",
                         dataType="string")
            cmds.setAttr(target + ".advPyFaceTargetProvenance",
                         plan.provenance, type="string", lock=True)
        finally:
            if selection:
                cmds.select(selection, replace=True)
            else:
                cmds.select(clear=True)

    def read_face_target_provenance(self, path: str) -> str:
        from maya import cmds

        target = self.scene_address(path)
        if (not cmds.objExists(target)
                or not cmds.attributeQuery("advPyFaceTargetProvenance",
                                           node=target, exists=True)):
            raise CharacterRegistryError("生成目标缺少来源记录")
        return cmds.getAttr(target + ".advPyFaceTargetProvenance")

    def read_face_manifest(self, control_path: str) -> tuple:
        from maya import cmds

        control = self.scene_address(control_path)
        if (not cmds.objExists(control) or
                not cmds.attributeQuery("advPyFaceSchemaVersion", node=control, exists=True) or
                cmds.getAttr(control + ".advPyFaceSchemaVersion") != 1):
            raise CharacterRegistryError("面部控制或清单版本无效")
        try:
            rows = json.loads(cmds.getAttr(control + ".advPyFaceManifest"))
            channels = tuple((name, FaceShapeKind(kind)) for name, kind in rows)
            if not channels or len({name for name, _ in channels}) != len(channels):
                raise ValueError()
            for name, _ in channels:
                if not cmds.attributeQuery(name, node=control, exists=True):
                    raise ValueError()
                destinations = cmds.listConnections(control + "." + name,
                    source=False, destination=True, plugs=True) or []
                if len(destinations) != 1 or cmds.nodeType(destinations[0].rsplit(".", 1)[0]) != "blendShape":
                    raise ValueError()
            return channels
        except (TypeError, ValueError, KeyError, RuntimeError) as error:
            raise CharacterRegistryError("面部控制清单或权重连接无效") from error

    def preflight_face_performance(self, control_path: str,
                                   performance: FacePerformance) -> None:
        from maya import cmds

        if cmds.currentUnit(query=True, time=True) != performance.time_unit:
            raise CharacterRegistryError("面部动画时间单位与场景不一致")
        if not cmds.undoInfo(query=True, state=True):
            raise CharacterRegistryError("面部动画写入需要启用 Maya 撤销")
        control = self.scene_address(control_path)
        if cmds.referenceQuery(control, isNodeReferenced=True):
            raise CharacterRegistryError("不能修改引用场景中的面部控制")
        if cmds.animLayer(query=True, root=True):
            raise CharacterRegistryError("面部动画写入不支持动画层")
        for name, _ in performance.channels:
            plug = control + "." + name
            if cmds.getAttr(plug, lock=True) or not cmds.getAttr(plug, keyable=True):
                raise CharacterRegistryError("面部通道不可写入：" + name)
            source = cmds.connectionInfo(plug, sourceFromDestination=True)
            if source:
                if not self._character_direct_animation(source):
                    raise CharacterRegistryError("面部通道有非角色动画驱动：" + name + " " + source)
                destinations = cmds.listConnections(source, source=False,
                    destination=True, plugs=True) or []
                destination = destinations[0] if len(destinations) == 1 else ""
                node, _, attribute = destination.rpartition(".")
                matches = cmds.ls(node, long=True) or []
                if len(destinations) != 1 or matches != [control] or attribute != name:
                    raise CharacterRegistryError("面部动画曲线被多个通道共享：" + name)

    def capture_face_curve_state(self, control_path: str,
                                 performance: FacePerformance) -> tuple:
        from maya import cmds

        control = self.scene_address(control_path)
        start, end = performance.frames[0], performance.frames[-1]
        rows = []
        for name, _ in performance.channels:
            plug = control + "." + name
            source = cmds.connectionInfo(plug, sourceFromDestination=True) or ""
            times = tuple(cmds.keyframe(plug, query=True, timeChange=True) or ())
            values = tuple(cmds.keyframe(plug, query=True, valueChange=True) or ())
            incoming = tuple(cmds.keyTangent(plug, query=True, inTangentType=True) or ())
            outgoing = tuple(cmds.keyTangent(plug, query=True, outTangentType=True) or ())
            if not (len(times) == len(values) == len(incoming) == len(outgoing)):
                raise CharacterRegistryError("面部动画曲线快照不完整：" + name)
            guards = tuple(float(cmds.getAttr(plug, time=frame))
                           for frame in (start - 1, end + 1))
            rows.append((source, tuple(zip(times, values, incoming, outgoing)), guards))
        return tuple(rows)

    def write_face_performance(self, plan: FacePerformancePlan) -> None:
        self._require_transaction()
        if self.capture_face_curve_state(plan.control_path, plan.performance) != plan.curve_state:
            raise CharacterRegistryError("面部动画曲线在写入前发生变化")
        self._transaction_changed = True
        start, end = plan.performance.frames[0], plan.performance.frames[-1]
        for index, (name, _) in enumerate(plan.performance.channels):
            _, old_keys, guards = plan.curve_state[index]
            old_times = {row[0] for row in old_keys}
            for frame, value in zip((start - 1, end + 1), guards):
                if frame not in old_times:
                    self._cmds.setKeyframe(plan.control_path, attribute=name,
                                           time=frame, value=value)
            for frame, values in plan.performance.samples:
                self._cmds.setKeyframe(plan.control_path, attribute=name,
                    time=frame, value=values[index], inTangentType="linear",
                    outTangentType="linear")

    def sample_face_performance(self, control_path: str,
                                performance: FacePerformance) -> tuple:
        from maya import cmds

        control = self.scene_address(control_path)
        return tuple((frame, tuple(float(cmds.getAttr(control + "." + name,
            time=frame)) for name, _ in performance.channels))
            for frame, _ in performance.samples)

    def verify_face_curve_boundary(self, plan: FacePerformancePlan) -> None:
        from maya import cmds

        start, end = plan.performance.frames[0], plan.performance.frames[-1]
        current = self.capture_face_curve_state(plan.control_path, plan.performance)
        for index, (_, old_keys, guards) in enumerate(plan.curve_state):
            name = plan.performance.channels[index][0]
            _, new_keys, new_guards = current[index]
            outside = lambda rows: tuple(row for row in rows if row[0] < start or row[0] > end)
            old_outside = outside(old_keys)
            new_by_time = {row[0]: row for row in outside(new_keys)}
            if any(new_by_time.get(row[0]) != row for row in old_outside):
                raise RuntimeError("面部片段外原有关键帧发生变化：" + name)
            if any(abs(a - b) > 1e-8 for a, b in zip(guards, new_guards)):
                raise RuntimeError("面部片段边界值发生变化：" + name)

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
