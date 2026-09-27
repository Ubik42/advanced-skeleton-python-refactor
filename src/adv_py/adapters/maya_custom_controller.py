"""Maya scene port for SoftMod custom controls and influenced meshes."""
from __future__ import annotations

from dataclasses import replace

from adv_py.application.custom_controller import CustomControllerState
from adv_py.core.character_registry import CharacterChannel
from adv_py.core.custom_controller import (
    CustomControlKind, CustomControllerPlan, DeformJointCandidate,
    SoftModRegion, WeightedVertex,
)

from .maya_face import MayaFaceHost


class MayaCustomControllerHost(MayaFaceHost):
    def _unique(self, path: str, node_type: str) -> str:
        from maya import cmds

        address = (path if path.startswith(("|", ":")) or ":" in path
                   else self.scene_address(path))
        matches = cmds.ls(address, long=True,
                          type=node_type) or []
        if len(matches) != 1:
            raise ValueError("场景节点不存在或名称不唯一：" + path)
        return matches[0]

    def _mesh(self, path: str) -> str:
        from maya import cmds

        mesh = self._unique(path, "transform")
        shapes = cmds.listRelatives(mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh") or []
        if len(shapes) != 1 or int(cmds.polyEvaluate(mesh, vertex=True)) < 1:
            raise ValueError("自定义控制要求单一非空多边形网格")
        return mesh

    def _softmod_meshes(self, deformer: str) -> tuple[str, ...]:
        from maya import cmds

        shapes = cmds.softMod(deformer, query=True, geometry=True) or []
        meshes = []
        for shape in shapes:
            matches = cmds.ls(shape, long=True) or []
            if len(matches) != 1:
                raise ValueError("SoftMod 影响对象不存在或不唯一")
            node = matches[0]
            if cmds.nodeType(node) == "mesh":
                node = (cmds.listRelatives(node, parent=True,
                                           fullPath=True) or [None])[0]
            meshes.append(self._mesh(node))
        if len(meshes) != len(set(meshes)):
            raise ValueError("SoftMod 影响对象重复")
        return tuple(sorted(meshes))

    def capture_softmod_region(self, deformer: str) -> SoftModRegion:
        from maya import cmds
        from maya.api import OpenMaya as om
        from maya.api import OpenMayaAnim as oma

        source = self._unique(deformer, "softMod")
        meshes = self._softmod_meshes(source)
        if len(meshes) != 1:
            raise ValueError("创建自定义控制时 SoftMod 须只影响一件网格")
        mesh = meshes[0]
        count = int(cmds.polyEvaluate(mesh, vertex=True))
        indices = cmds.softMod(source, query=True, geometryIndices=True) or []
        if len(indices) != 1:
            raise ValueError("SoftMod 网格索引不唯一")
        selection = om.MSelectionList()
        selection.add(source)
        fn = oma.MFnWeightGeometryFilter(selection.getDependNode(0))
        components = om.MFnSingleIndexedComponent().create(
            om.MFn.kMeshVertComponent)
        om.MFnSingleIndexedComponent(components).addElements(range(count))
        values = fn.getWeights(int(indices[0]), components)
        if len(values) != count:
            raise ValueError("SoftMod 顶点权重读取不完整")
        center = tuple(float(value) for value in cmds.softMod(
            source, query=True, falloffCenter=True))
        return SoftModRegion(source, mesh, center, count, tuple(
            WeightedVertex(index, float(value))
            for index, value in enumerate(values) if float(value) > 0.0))

    def deform_joint_candidates(self, mesh: str
                                ) -> tuple[DeformJointCandidate, ...]:
        from maya import cmds

        self._mesh(mesh)
        registration = self.read_character_registration()
        candidates = []
        for item in registration.body:
            path = self._unique(self.scene_address(item.path), "joint")
            center = tuple(float(value) for value in cmds.xform(
                path, query=True, worldSpace=True, translation=True))
            candidates.append(DeformJointCandidate(path, center))
        return tuple(candidates)

    def preflight_custom_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        if plan.kind is not CustomControlKind.SOFT_MOD:
            raise NotImplementedError(
                "Skin／Cluster 控制的原版权重转换尚未接入 Maya")
        source = self._unique(plan.region.deformer, "softMod")
        mesh = self._mesh(plan.region.mesh)
        parent = self._unique(plan.parent_joint, "joint")
        if mesh not in self._softmod_meshes(source):
            raise ValueError("SoftMod 与区域网格不匹配")
        if (cmds.referenceQuery(source, isNodeReferenced=True)
                or cmds.referenceQuery(parent, isNodeReferenced=True)):
            raise ValueError("自定义控制要求本地可写的 SoftMod 和父关节")
        if int(cmds.polyEvaluate(mesh, vertex=True)) != plan.region.vertex_count:
            raise ValueError("SoftMod 区域顶点数已变化")

    def create_custom_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        self._require_transaction()
        self.preflight_custom_controller(plan)
        self._transaction_changed = True
        parent = self._unique(plan.parent_joint, "joint")
        offset = cmds.createNode("transform", name=self.scene_address(
            plan.offset_name), parent=parent, skipSelect=True)
        cmds.xform(offset, worldSpace=True, translation=plan.region.center)
        radius = max(0.1, float(cmds.softMod(
            plan.region.deformer, query=True, falloffRadius=True)) * 0.25)
        normal = ((0.0, 0.0, 1.0) if cmds.upAxis(query=True, axis=True) == "z"
                  else (0.0, 1.0, 0.0))
        base = cmds.circle(name=self.scene_address(plan.base_control_name),
                           normal=normal, radius=radius * 1.3,
                           constructionHistory=False)[0]
        base = cmds.parent(base, offset)[0]
        cmds.xform(base, worldSpace=True, translation=plan.region.center)
        control = cmds.circle(name=self.scene_address(plan.control_name),
                              normal=normal, radius=radius,
                              constructionHistory=False)[0]
        control = cmds.parent(control, base)[0]
        cmds.xform(control, worldSpace=True, translation=plan.region.center)
        cmds.softMod(plan.region.deformer, edit=True,
                     weightedNode=(base, control))
        cmds.addAttr(control, longName="advPyCustomControlKind",
                     dataType="string")
        cmds.setAttr(control + ".advPyCustomControlKind", plan.kind.value,
                     type="string", lock=True)
        cmds.addAttr(control, longName="advPyCustomControlWeightCount",
                     attributeType="long")
        cmds.setAttr(control + ".advPyCustomControlWeightCount",
                     len(plan.region.weights), lock=True)
        cmds.addAttr(control, longName="advPyCustomControlDeformer",
                     attributeType="message")
        cmds.connectAttr(plan.region.deformer + ".message",
                         control + ".advPyCustomControlDeformer")
        previous = self.read_character_registration()
        local = (self._cmds.identity.to_local if self.namespace is not None
                 else lambda path: path)
        nodes = tuple(self._registry_node(local(path))
                      for path in (offset, base, control))
        channels = tuple(
            CharacterChannel(
                f"custom.{plan.control_name}.{role}.{channel}{axis}",
                local(path), channel + axis)
            for role, path in (("base", base), ("control", control))
            for channel in ("translate", "rotate", "scale")
            for axis in "XYZ")
        updated = replace(previous,
                          nodes=previous.nodes + nodes,
                          channels=previous.channels + channels)
        self.write_character_registration_extension(previous, updated)

    def capture_custom_controller(self, plan: CustomControllerPlan
                                  ) -> CustomControllerState:
        return self.capture_custom_control(plan.control_name)

    def capture_custom_control(self, control: str) -> CustomControllerState:
        from maya import cmds

        path = self._unique(control, "transform")
        kind_plug = path + ".advPyCustomControlKind"
        if not cmds.objExists(kind_plug):
            raise ValueError("所选节点不是本工程自定义控制器")
        kind = CustomControlKind(cmds.getAttr(kind_plug))
        links = cmds.listConnections(
            path + ".advPyCustomControlDeformer", source=True,
            destination=False, type="softMod") or []
        if len(links) != 1:
            raise ValueError("自定义控制器缺少唯一 SoftMod 连接")
        deformer = self._unique(links[0], "softMod")
        base = (cmds.listRelatives(path, parent=True,
                                  fullPath=True) or [None])[0]
        if not base:
            raise ValueError("自定义控制器缺少底座")
        offset = (cmds.listRelatives(base, parent=True,
                                    fullPath=True) or [None])[0]
        if not offset:
            raise ValueError("自定义控制器缺少偏移层")
        parent = (cmds.listRelatives(offset, parent=True,
                                    fullPath=True) or [None])[0]
        if not parent:
            raise ValueError("自定义控制器缺少变形关节父级")
        local = (self._cmds.identity.to_local if self.namespace is not None
                 else lambda node: node)
        registered = {node.path for node in
                      self.read_character_registration().nodes}
        if not {local(offset), local(base), local(path)} <= registered:
            raise ValueError("自定义控制器未登记到角色")
        return CustomControllerState(
            kind, offset, path, base, parent,
            self._softmod_meshes(deformer), None, deformer,
            int(cmds.getAttr(path + ".advPyCustomControlWeightCount")))

    def preflight_softmod_extension(self, deformer: str, mesh: str) -> None:
        from maya import cmds

        source = self._unique(deformer, "softMod")
        target = self._mesh(mesh)
        if target in self._softmod_meshes(source):
            raise ValueError("网格已经属于 SoftMod 影响集合")
        if (cmds.referenceQuery(source, isNodeReferenced=True)
                or cmds.referenceQuery(target, isNodeReferenced=True)):
            raise ValueError("SoftMod 和新增网格须为本地可写节点")

    def add_softmod_influenced_mesh(self, deformer: str, mesh: str) -> None:
        from maya import cmds

        self._require_transaction()
        self.preflight_softmod_extension(deformer, mesh)
        self._transaction_changed = True
        cmds.softMod(deformer, edit=True, geometry=mesh)
