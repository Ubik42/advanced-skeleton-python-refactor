"""Maya scene port for SoftMod custom controls and influenced meshes."""
from __future__ import annotations

from dataclasses import replace

from adv_py.application.custom_controller import CustomControllerState
from adv_py.core.character_registry import (
    REGISTRY_NAME, CharacterChannel, encode_registration,
)
from adv_py.core.custom_controller import (
    CustomControlKind, CustomControllerPlan, DeformJointCandidate,
    SoftModRegion, WeightedVertex,
)
from adv_py.core.custom_control_weights import (
    ClusterWeightTransfer, SoftModProbe, cluster_weights_from_probe,
)

from .maya_face import MayaFaceHost


class MayaCustomControllerHost(MayaFaceHost):
    def __init__(self, *, namespace: str | None = None,
                 face: bool = False) -> None:
        super().__init__(namespace=namespace)
        self.face = face

    def _custom_system(self) -> str:
        from maya import cmds

        name = self.scene_address("FaceCustomSystem" if self.face
                                  else "CustomSystem")
        if cmds.objExists(name):
            return self._unique(name, "transform")
        motion_name = "FaceMotionSystem" if self.face else "MotionSystem"
        if cmds.objExists(self.scene_address(motion_name)):
            return cmds.createNode("transform", name=name,
                parent=self._unique(motion_name, "transform"))
        return cmds.createNode("transform", name=name)

    def _prepare_custom_source(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        if not plan.middle:
            return
        source = self._unique(plan.region.deformer, "softMod")
        handle = self._unique(plan.region.source_handle, "transform")
        cmds.setAttr(source + ".falloffCenterX", 0.0)
        for shape in cmds.listRelatives(handle, shapes=True,
                                        fullPath=True) or []:
            if cmds.objExists(shape + ".originX"):
                cmds.setAttr(shape + ".originX", 0.0)

    def _attach_to_custom_parent(self, attach: str, parent: str,
                                 local: bool) -> None:
        from maya import cmds

        if local:
            cmds.delete(cmds.orientConstraint(parent, attach))
        cmds.parentConstraint(parent, attach, maintainOffset=True)

    def _register_custom_nodes(self, paths: tuple[str, ...],
                               control: str, base: str | None = None) -> None:
        from maya import cmds

        if not cmds.objExists(self.scene_address(REGISTRY_NAME)):
            if self.face:
                return
            raise ValueError("Body 自定义控制器缺少角色登记")
        previous = self.read_character_registration()
        local = (self._cmds.identity.to_local if self.namespace is not None
                 else lambda path: path)
        nodes = tuple(self._registry_node(local(path)) for path in paths)
        controls = (("control", control),)
        if base:
            controls = (("base", base),) + controls
        channels = tuple(CharacterChannel(
            f"custom.{control.rsplit('|', 1)[-1].rsplit(':', 1)[-1]}."
            f"{role}.{channel}{axis}", local(path), channel + axis)
            for role, path in controls
            for channel in ("translate", "rotate", "scale")
            for axis in "XYZ")
        updated = replace(previous, nodes=previous.nodes + nodes,
                          channels=previous.channels + channels)
        self.write_character_registration_extension(previous, updated)

    def _probe_softmod(self, region: SoftModRegion) -> ClusterWeightTransfer:
        """Measure effective falloff, not the stored geometry-filter mask."""
        from maya import cmds
        from maya.api import OpenMaya as om

        mesh = self._mesh(region.mesh)
        handle = self._unique(region.source_handle, "transform")
        source = self._unique(region.deformer, "softMod")
        selection = om.MSelectionList()
        selection.add(mesh)
        mesh_fn = om.MFnMesh(selection.getDagPath(0))
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        disabled = {}
        original_y = float(cmds.getAttr(handle + ".translateY"))
        source_state = int(cmds.getAttr(source + ".nodeState"))
        try:
            cmds.setAttr(source + ".nodeState", 0)
            for node in history:
                if node == source or not cmds.objExists(node + ".nodeState"):
                    continue
                if cmds.objectType(node, isAType="geometryFilter"):
                    disabled[node] = int(cmds.getAttr(node + ".nodeState"))
                    cmds.setAttr(node + ".nodeState", 1)
            rest = tuple((float(point.x), float(point.y), float(point.z))
                         for point in mesh_fn.getPoints(om.MSpace.kWorld))
            cmds.setAttr(handle + ".translateY", original_y + 1.0)
            moved = tuple((float(point.x), float(point.y), float(point.z))
                          for point in mesh_fn.getPoints(om.MSpace.kWorld))
            return cluster_weights_from_probe(SoftModProbe(rest, moved))
        finally:
            cmds.setAttr(handle + ".translateY", original_y)
            cmds.setAttr(source + ".nodeState", source_state)
            for node, state in disabled.items():
                cmds.setAttr(node + ".nodeState", state)

    def _skin_for_mesh(self, mesh: str) -> str:
        from maya import cmds

        skins = tuple(dict.fromkeys(cmds.ls(
            cmds.listHistory(mesh, pruneDagObjects=True) or [],
            type="skinCluster") or []))
        if len(skins) != 1:
            raise ValueError("Skin Control 要求目标网格恰好有一个 SkinCluster")
        return self._unique(skins[0], "skinCluster")

    def _soft_selection_weights(self, region: SoftModRegion
                                ) -> tuple[WeightedVertex, ...]:
        """Sample Maya's soft selection with the source falloff curve."""
        from maya import cmds
        from maya import OpenMaya as om

        mesh = self._mesh(region.mesh)
        shape = (cmds.listRelatives(mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh") or [None])[0]
        selected = cmds.ls(selection=True, long=True) or []
        enabled = cmds.softSelect(query=True, softSelectEnabled=True)
        falloff = cmds.softSelect(query=True, softSelectFalloff=True)
        distance = cmds.softSelect(query=True, softSelectDistance=True)
        curve_before = cmds.softSelect(query=True, softSelectCurve=True)
        sampler = cmds.createNode("closestPointOnMesh")
        try:
            cmds.connectAttr(shape + ".outMesh", sampler + ".inMesh")
            cmds.connectAttr(shape + ".worldMatrix[0]",
                             sampler + ".inputMatrix")
            cmds.setAttr(sampler + ".inPosition", *region.center,
                         type="double3")
            nearest = int(cmds.getAttr(sampler + ".closestVertexIndex"))
            cmds.select("%s.vtx[%d]" % (mesh, nearest), replace=True)
            options = dict(softSelectEnabled=True,
                           softSelectFalloff=region.falloff_mode,
                           softSelectDistance=region.falloff_radius)
            if region.falloff_curve:
                options["softSelectCurve"] = ",".join(
                    "%s,%s,%d" % (value, position, interpolation)
                    for value, position, interpolation in region.falloff_curve)
            cmds.softSelect(edit=True, **options)
            rich = om.MRichSelection()
            om.MGlobal.getRichSelection(rich)
            selection = om.MSelectionList()
            rich.getSelection(selection)
            iterator = om.MItSelectionList(selection,
                                           om.MFn.kMeshVertComponent)
            dag = om.MDagPath()
            component = om.MObject()
            weights = {}
            while not iterator.isDone():
                iterator.getDagPath(dag, component)
                dag.pop()
                if dag.fullPathName() == mesh:
                    fn = om.MFnSingleIndexedComponent(component)
                    for offset in range(fn.elementCount()):
                        weights[int(fn.element(offset))] = float(
                            fn.weight(offset).influence())
                iterator.next()
            if not weights:
                raise ValueError("Soft Selection 未返回目标网格顶点权重")
            return tuple(WeightedVertex(index, weight)
                         for index, weight in sorted(weights.items()))
        finally:
            cmds.delete(sampler)
            restore = dict(softSelectEnabled=enabled,
                           softSelectFalloff=falloff,
                           softSelectDistance=distance)
            if curve_before:
                restore["softSelectCurve"] = curve_before
            cmds.softSelect(edit=True, **restore)
            cmds.select(selected, replace=True) if selected else cmds.select(
                clear=True)

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

    def resolve_custom_mesh(self, mesh: str) -> str:
        return self._mesh(mesh)

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

    def _cluster_meshes(self, deformer: str) -> tuple[str, ...]:
        from maya import cmds

        shapes = cmds.cluster(deformer, query=True, geometry=True) or []
        meshes = []
        for shape in shapes:
            matches = cmds.ls(shape, long=True) or []
            if len(matches) != 1:
                raise ValueError("Cluster 影响对象不存在或不唯一")
            node = matches[0]
            if cmds.nodeType(node) == "mesh":
                node = (cmds.listRelatives(node, parent=True,
                                           fullPath=True) or [None])[0]
            meshes.append(self._mesh(node))
        return tuple(sorted(meshes))

    def _skin_meshes(self, deformer: str) -> tuple[str, ...]:
        from maya import cmds

        shapes = cmds.skinCluster(deformer, query=True, geometry=True) or []
        meshes = []
        for shape in shapes:
            matches = cmds.ls(shape, long=True) or []
            if len(matches) != 1:
                raise ValueError("SkinCluster 影响对象不存在或不唯一")
            node = matches[0]
            if cmds.nodeType(node) == "mesh":
                node = (cmds.listRelatives(node, parent=True,
                                           fullPath=True) or [None])[0]
            meshes.append(self._mesh(node))
        return tuple(sorted(meshes))

    def _skin_joint_meshes(self, joint: str) -> tuple[str, ...]:
        from maya import cmds

        meshes = set()
        for skin in cmds.ls(type="skinCluster") or []:
            indices = cmds.getAttr(skin + ".matrix", multiIndices=True) or []
            connected = []
            for index in indices:
                connected.extend(cmds.listConnections(
                    skin + ".matrix[%d]" % index, source=True,
                    destination=False, type="joint") or [])
            if any(joint in (cmds.ls(item, long=True,
                                     type="joint") or []) for item in connected):
                meshes.update(self._skin_meshes(skin))
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
        handles = cmds.listConnections(source + ".matrix", source=True,
                                       destination=False, type="transform") or []
        if len(handles) != 1:
            raise ValueError("SoftMod 须有唯一的源操作柄")
        handle = self._unique(handles[0], "transform")
        curve = tuple(
            (float(cmds.getAttr(source + ".falloffCurve[%d].falloffCurve_FloatValue" % i)),
             float(cmds.getAttr(source + ".falloffCurve[%d].falloffCurve_Position" % i)),
             int(cmds.getAttr(source + ".falloffCurve[%d].falloffCurve_Interp" % i)))
            for i in (cmds.getAttr(source + ".falloffCurve", multiIndices=True) or []))
        return SoftModRegion(source, mesh, center, count, tuple(
            WeightedVertex(index, float(value))
            for index, value in enumerate(values)),
            handle, float(cmds.getAttr(source + ".falloffRadius")),
            int(cmds.getAttr(source + ".falloffMode")), curve)

    def deform_joint_candidates(self, mesh: str
                                ) -> tuple[DeformJointCandidate, ...]:
        from maya import cmds

        self._mesh(mesh)
        candidates = []
        if cmds.objExists(self.scene_address(REGISTRY_NAME)):
            registration = self.read_character_registration()
            for item in registration.body:
                path = self._unique(self.scene_address(item.path), "joint")
                center = tuple(float(value) for value in cmds.xform(
                    path, query=True, worldSpace=True, translation=True))
                candidates.append(DeformJointCandidate(path, center))
        elif not self.face:
            raise ValueError("Body 自定义控制器要求已登记角色")
        if self.face and cmds.objExists(self.scene_address(
                "FaceDeformationSystem")):
            root = self._unique("FaceDeformationSystem", "transform")
            for path in cmds.listRelatives(root, allDescendents=True,
                                           fullPath=True, type="joint") or []:
                if path in {item.path for item in candidates}:
                    continue
                center = tuple(float(value) for value in cmds.xform(
                    path, query=True, worldSpace=True, translation=True))
                candidates.append(DeformJointCandidate(path, center))
        if self.face and cmds.objExists(self.scene_address("FaceFitSkeleton")):
            fit = self._unique("FaceFitSkeleton", "transform")
            if cmds.objExists(fit + ".HeadJoint"):
                head_name = cmds.getAttr(fit + ".HeadJoint")
                if head_name and cmds.objExists(self.scene_address(head_name)):
                    path = self._unique(head_name, "joint")
                    if path not in {item.path for item in candidates}:
                        center = tuple(float(value) for value in cmds.xform(
                            path, query=True, worldSpace=True,
                            translation=True))
                        candidates.insert(0, DeformJointCandidate(path, center))
        return tuple(candidates)

    def preflight_custom_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        source = self._unique(plan.region.deformer, "softMod")
        handle = self._unique(plan.region.source_handle, "transform")
        mesh = self._mesh(plan.region.mesh)
        parent = self._unique(plan.parent_joint, "joint")
        if mesh not in self._softmod_meshes(source):
            raise ValueError("SoftMod 与区域网格不匹配")
        if (cmds.referenceQuery(source, isNodeReferenced=True)
                or cmds.referenceQuery(handle, isNodeReferenced=True)
                or cmds.referenceQuery(parent, isNodeReferenced=True)):
            raise ValueError("自定义控制要求本地可写的 SoftMod 和父关节")
        if int(cmds.polyEvaluate(mesh, vertex=True)) != plan.region.vertex_count:
            raise ValueError("SoftMod 区域顶点数已变化")
        incoming = cmds.listConnections(source + ".matrix", source=True,
                                        destination=False, type="transform") or []
        if len(incoming) != 1 or self._unique(incoming[0], "transform") != handle:
            raise ValueError("SoftMod 源操作柄已变化")
        if plan.kind is CustomControlKind.SKIN:
            skin = self._skin_for_mesh(mesh)
            if cmds.referenceQuery(skin, isNodeReferenced=True):
                raise ValueError("Skin Control 要求本地可写的 SkinCluster")

    def create_custom_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        self._require_transaction()
        self.preflight_custom_controller(plan)
        self._transaction_changed = True
        self._prepare_custom_source(plan)
        if plan.kind is CustomControlKind.SKIN:
            self._create_skin_controller(plan)
            return
        if plan.kind is CustomControlKind.CLUSTER:
            self._create_cluster_controller(plan)
            return
        parent = self._unique(plan.parent_joint, "joint")
        mesh = self._mesh(plan.region.mesh)
        source = self._unique(plan.region.deformer, "softMod")
        source_handle = self._unique(plan.region.source_handle, "transform")
        custom_system = self._custom_system()
        attach = cmds.createNode("transform", name=self.scene_address(
            plan.auxiliary_name("attach")), parent=custom_system)
        cmds.xform(attach, worldSpace=True, translation=plan.region.center)
        self._attach_to_custom_parent(attach, parent, plan.local)
        offset = cmds.createNode("transform", name=self.scene_address(
            plan.offset_name), parent=attach)
        radius = max(0.1, plan.region.falloff_radius * 0.25)
        base = cmds.curve(name=self.scene_address(plan.base_control_name),
                          degree=1,
                          point=[(0, radius * 2.5, 0),
                                 (0, -radius * 2.5, 0), (0, 0, 0),
                                 (radius * 2.5, 0, 0),
                                 (-radius * 2.5, 0, 0)])
        base = cmds.parent(base, offset, relative=True)[0]
        control = cmds.sphere(name=self.scene_address(plan.control_name),
                              radius=radius, constructionHistory=False)[0]
        control = cmds.parent(control, base, relative=True)[0]
        created = cmds.softMod(mesh, name=self.scene_address(
            plan.deformer_name))
        if len(created) != 2:
            raise RuntimeError("创建 SoftMod 未返回变形器和操作柄")
        deformer = self._unique(created[0], "softMod")
        new_handle = self._unique(created[1], "transform")
        cmds.setAttr(deformer + ".falloffRadius", plan.region.falloff_radius)
        cmds.setAttr(deformer + ".falloffMode", plan.region.falloff_mode)
        for index, (value, position, interpolation) in enumerate(
                plan.region.falloff_curve):
            plug = deformer + ".falloffCurve[%d]." % index
            cmds.setAttr(plug + "falloffCurve_FloatValue", value)
            cmds.setAttr(plug + "falloffCurve_Position", position)
            cmds.setAttr(plug + "falloffCurve_Interp", interpolation)
        for item in plan.region.weights:
            if item.weight != 1.0:
                cmds.setAttr(deformer + ".weightList[0].weights[%d]" %
                             item.index, item.weight)
        cmds.setAttr(deformer + ".falloffCenter",
                     *plan.region.center, type="double3")
        locator = cmds.spaceLocator(name=self.scene_address(
            plan.auxiliary_name("locator")))[0]
        locator = cmds.parent(locator, base, relative=True)[0]
        cmds.setAttr(locator + ".visibility", False)
        shape = (cmds.listRelatives(locator, shapes=True,
                                    fullPath=True) or [None])[0]
        cmds.connectAttr(shape + ".worldPosition[0]",
                         deformer + ".falloffCenter", force=True)
        for plug in (deformer + ".matrix", deformer + ".softModXforms"):
            for source_plug in (cmds.listConnections(
                    plug, source=True, destination=False, plugs=True) or []):
                cmds.disconnectAttr(source_plug, plug)
        cmds.delete(new_handle)
        cmds.connectAttr(attach + ".worldMatrix[0]",
                         deformer + ".matrix", force=True)
        cmds.connectAttr(base + ".worldInverseMatrix[0]",
                         deformer + ".postMatrix", force=True)
        cmds.connectAttr(base + ".worldMatrix[0]",
                         deformer + ".preMatrix", force=True)
        matrix = cmds.createNode("multMatrix", name=self.scene_address(
            plan.auxiliary_name("matrix")))
        cmds.connectAttr(control + ".worldMatrix[0]",
                         matrix + ".matrixIn[0]")
        cmds.connectAttr(control + ".parentInverseMatrix[0]",
                         matrix + ".matrixIn[1]")
        cmds.connectAttr(matrix + ".matrixSum",
                         deformer + ".softModXforms.weightedMatrix")
        cmds.addAttr(control, longName="falloffRadius", attributeType="double",
                     defaultValue=1.0, keyable=True)
        cmds.addAttr(control, longName="falloffMode", attributeType="enum",
                     enumName="volume:surface:",
                     defaultValue=plan.region.falloff_mode, keyable=True)
        cmds.connectAttr(control + ".falloffMode",
                         deformer + ".falloffMode", force=True)
        radius_factor = cmds.createNode("multiplyDivide", name=self.scene_address(
            plan.auxiliary_name("radius_factor")))
        radius_scale = cmds.createNode("multiplyDivide", name=self.scene_address(
            plan.auxiliary_name("radius_scale")))
        cmds.connectAttr(control + ".falloffRadius",
                         radius_factor + ".input1X")
        cmds.setAttr(radius_factor + ".input2X", plan.region.falloff_radius)
        cmds.connectAttr(radius_factor + ".outputX",
                         radius_scale + ".input1X")
        cmds.connectAttr(attach + ".scaleX", radius_scale + ".input2X")
        cmds.connectAttr(radius_scale + ".outputX",
                         deformer + ".falloffRadius", force=True)
        cmds.addAttr(control, longName="advPyCustomControlKind",
                     dataType="string")
        cmds.setAttr(control + ".advPyCustomControlKind", plan.kind.value,
                     type="string", lock=True)
        cmds.addAttr(control, longName="advPyCustomControlWeightCount",
                     attributeType="long")
        cmds.setAttr(control + ".advPyCustomControlWeightCount",
                     sum(item.weight > 0.0 for item in plan.region.weights),
                     lock=True)
        cmds.addAttr(control, longName="advPyCustomControlDeformer",
                     attributeType="message")
        cmds.connectAttr(deformer + ".message",
                         control + ".advPyCustomControlDeformer")
        cmds.addAttr(control, longName="advPyCustomControlParent",
                     attributeType="message")
        cmds.connectAttr(parent + ".message",
                         control + ".advPyCustomControlParent")
        cmds.delete(source_handle)
        if cmds.objExists(source):
            cmds.delete(source)
        self._register_custom_nodes((attach, offset, base, control),
                                    control, base)

    def _create_skin_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        self._transaction_changed = True
        mesh = self._mesh(plan.region.mesh)
        skin = self._skin_for_mesh(mesh)
        weights = self._soft_selection_weights(plan.region)
        parent = self._unique(plan.parent_joint, "joint")
        joint = cmds.createNode("joint", name=self.scene_address(
            plan.joint_name), parent=parent)
        cmds.xform(joint, worldSpace=True, translation=plan.region.center)
        cmds.setAttr(joint + ".segmentScaleCompensate", False)
        cmds.addAttr(joint, longName="skinControlJoint",
                     attributeType="bool", defaultValue=True)
        cmds.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                     dataType="string")
        cmds.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                     "custom-skin-v1", type="string", lock=True)
        system = self._custom_system()
        attach = cmds.createNode("transform", name=self.scene_address(
            plan.auxiliary_name("attach")), parent=system)
        cmds.xform(attach, worldSpace=True, translation=plan.region.center)
        self._attach_to_custom_parent(attach, parent, plan.local)
        offset = cmds.createNode("transform", name=self.scene_address(
            plan.offset_name), parent=attach)
        scale = max(0.1, plan.region.falloff_radius / 4.0) / 2.0
        corners = [(-1, 1, 1), (-1, 1, -1), (1, 1, -1),
                   (1, 1, 1), (-1, 1, 1), (-1, -1, 1),
                   (1, -1, 1), (1, -1, -1), (-1, -1, -1),
                   (-1, -1, 1), (-1, -1, -1), (-1, 1, -1),
                   (1, 1, -1), (1, -1, -1), (1, -1, 1), (1, 1, 1)]
        control = cmds.curve(name=self.scene_address(plan.control_name),
                             degree=1, point=[tuple(scale * axis for axis in p)
                                              for p in corners])
        control = cmds.parent(control, offset, relative=True)[0]
        cmds.parentConstraint(control, joint, maintainOffset=False)
        cmds.addAttr(control, longName="skinControl",
                     attributeType="bool", defaultValue=True)
        cmds.skinCluster(skin, edit=True, addInfluence=joint,
                         weight=0.0, lockWeights=False)
        matrix_indices = cmds.getAttr(skin + ".matrix", multiIndices=True) or []
        influence_index = None
        for index in matrix_indices:
            linked = cmds.listConnections(skin + ".matrix[%d]" % index,
                                          source=True, destination=False,
                                          type="joint") or []
            if len(linked) == 1 and self._unique(linked[0], "joint") == joint:
                influence_index = int(index)
                break
        if influence_index is None:
            raise RuntimeError("新关节未登记到 SkinCluster 影响矩阵")
        for item in weights:
            cmds.setAttr(skin + ".weightList[%d].weights[%d]" %
                         (item.index, influence_index), item.weight)
        influences = cmds.skinCluster(skin, query=True, influence=True) or []
        locks = {}
        try:
            for influence in influences:
                path = self._unique(influence, "joint")
                plug = path + ".lockInfluenceWeights"
                locks[path] = bool(cmds.getAttr(plug))
                cmds.setAttr(plug, path == joint)
            cmds.skinPercent(skin, mesh, normalize=True)
        finally:
            for path, locked in locks.items():
                cmds.setAttr(path + ".lockInfluenceWeights", locked)
        cmds.addAttr(control, longName="advPyCustomControlKind",
                     dataType="string")
        cmds.setAttr(control + ".advPyCustomControlKind", plan.kind.value,
                     type="string", lock=True)
        cmds.addAttr(control, longName="advPyCustomControlWeightCount",
                     attributeType="long")
        cmds.setAttr(control + ".advPyCustomControlWeightCount",
                     sum(item.weight > 0 for item in weights), lock=True)
        cmds.addAttr(control, longName="advPyCustomControlDeformer",
                     attributeType="message")
        cmds.connectAttr(skin + ".message",
                         control + ".advPyCustomControlDeformer")
        cmds.addAttr(control, longName="advPyCustomControlJoint",
                     attributeType="message")
        cmds.connectAttr(joint + ".message",
                         control + ".advPyCustomControlJoint")
        cmds.addAttr(control, longName="advPyCustomControlParent",
                     attributeType="message")
        cmds.connectAttr(parent + ".message",
                         control + ".advPyCustomControlParent")
        cmds.delete(self._unique(plan.region.source_handle, "transform"))
        if cmds.objExists(plan.region.deformer):
            cmds.delete(plan.region.deformer)
        self._register_custom_nodes((attach, offset, control, joint), control)

    def _create_cluster_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        self._transaction_changed = True
        transfer = self._probe_softmod(plan.region)
        parent = self._unique(plan.parent_joint, "joint")
        mesh = self._mesh(plan.region.mesh)
        custom_system = self._custom_system()
        attach = cmds.createNode("transform", name=self.scene_address(
            plan.auxiliary_name("attach")), parent=custom_system)
        cmds.xform(attach, worldSpace=True, translation=plan.region.center)
        self._attach_to_custom_parent(attach, parent, plan.local)
        offset = cmds.createNode("transform", name=self.scene_address(
            plan.offset_name), parent=attach)
        control = cmds.sphere(name=self.scene_address(plan.control_name),
                              radius=max(0.1, plan.region.falloff_radius / 4.0),
                              constructionHistory=False)[0]
        control = cmds.parent(control, offset, relative=True)[0]
        created = cmds.cluster(mesh, name=self.scene_address(
            plan.deformer_name))
        if len(created) != 2:
            raise RuntimeError("创建 Cluster 未返回变形器和操作柄")
        deformer = self._unique(created[0], "cluster")
        handle = cmds.rename(self._unique(created[1], "transform"),
                             self.scene_address(plan.auxiliary_name("handle")))
        cmds.xform(handle, worldSpace=True, translation=plan.region.center)
        cmds.parent(handle, custom_system)
        cmds.parentConstraint(control, handle, maintainOffset=False)
        cmds.setAttr(handle + ".visibility", False)
        for item in transfer.weights:
            cmds.percent(deformer, "%s.vtx[%d]" % (mesh, item.index),
                         value=item.weight)
        cmds.addAttr(control, longName="advPyCustomControlKind",
                     dataType="string")
        cmds.setAttr(control + ".advPyCustomControlKind", plan.kind.value,
                     type="string", lock=True)
        cmds.addAttr(control, longName="advPyCustomControlWeightCount",
                     attributeType="long")
        cmds.setAttr(control + ".advPyCustomControlWeightCount",
                     sum(item.weight > 0 for item in transfer.weights),
                     lock=True)
        cmds.addAttr(control, longName="advPyCustomControlDeformer",
                     attributeType="message")
        cmds.connectAttr(deformer + ".message",
                         control + ".advPyCustomControlDeformer")
        cmds.addAttr(control, longName="advPyCustomControlParent",
                     attributeType="message")
        cmds.connectAttr(parent + ".message",
                         control + ".advPyCustomControlParent")
        cmds.addAttr(control, longName="advPyClusterAttachmentVertex",
                     attributeType="long")
        cmds.setAttr(control + ".advPyClusterAttachmentVertex",
                     transfer.attachment_vertex, lock=True)
        cmds.delete(self._unique(plan.region.source_handle, "transform"))
        if cmds.objExists(plan.region.deformer):
            cmds.delete(plan.region.deformer)
        self._register_custom_nodes((attach, offset, control), control)

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
            destination=False,
            type="softMod" if kind is CustomControlKind.SOFT_MOD
            else "cluster" if kind is CustomControlKind.CLUSTER
            else "skinCluster") or []
        if len(links) != 1:
            raise ValueError("自定义控制器缺少唯一变形器连接")
        deformer = self._unique(links[0],
                                "softMod" if kind is CustomControlKind.SOFT_MOD
                                else "cluster" if kind is CustomControlKind.CLUSTER
                                else "skinCluster")
        base = (cmds.listRelatives(path, parent=True,
                                  fullPath=True) or [None])[0]
        if not base:
            raise ValueError("自定义控制器缺少父层")
        if kind is CustomControlKind.SOFT_MOD:
            offset = (cmds.listRelatives(base, parent=True,
                                        fullPath=True) or [None])[0]
            if not offset:
                raise ValueError("自定义控制器缺少偏移层")
        else:
            offset, base = base, None
        attach = (cmds.listRelatives(offset, parent=True,
                                    fullPath=True) or [None])[0]
        parents = cmds.listConnections(
            path + ".advPyCustomControlParent", source=True,
            destination=False, type="joint") or []
        if not attach or len(parents) != 1:
            raise ValueError("自定义控制器缺少附着层或父关节")
        parent = self._unique(parents[0], "joint")
        local = (self._cmds.identity.to_local if self.namespace is not None
                 else lambda node: node)
        has_registry = cmds.objExists(self.scene_address(REGISTRY_NAME))
        registered = ({node.path for node in
                       self.read_character_registration().nodes}
                      if has_registry else set())
        expected = {local(attach), local(offset), local(path)}
        if base:
            expected.add(local(base))
        face_path = any(segment.rsplit(":", 1)[-1] == "FaceCustomSystem"
                        for segment in path.split("|") if segment)
        if (has_registry and not expected <= registered
                or not has_registry and not face_path):
            raise ValueError("自定义控制器未登记到角色")
        joint = None
        if kind is CustomControlKind.SKIN:
            joints = cmds.listConnections(
                path + ".advPyCustomControlJoint", source=True,
                destination=False, type="joint") or []
            if len(joints) != 1:
                raise ValueError("Skin Control 缺少唯一影响关节")
            joint = self._unique(joints[0], "joint")
            if has_registry and local(joint) not in registered:
                raise ValueError("Skin Control 影响关节未登记到角色")
        return CustomControllerState(
            kind, offset, path, base, parent,
            self._softmod_meshes(deformer) if kind is CustomControlKind.SOFT_MOD
            else self._cluster_meshes(deformer)
            if kind is CustomControlKind.CLUSTER
            else self._skin_joint_meshes(joint),
            joint, deformer,
            int(cmds.getAttr(path + ".advPyCustomControlWeightCount")))

    def preflight_custom_extension(self, kind: CustomControlKind,
                                   deformer: str, joint: str | None,
                                   mesh: str) -> None:
        from maya import cmds

        if kind is CustomControlKind.SKIN:
            if not joint:
                raise ValueError("Skin Control 缺少影响关节")
            source_joint = self._unique(joint, "joint")
            target = self._mesh(mesh)
            if target in self._skin_joint_meshes(source_joint):
                raise ValueError("网格已由该 Skin Control 影响")
            if (cmds.referenceQuery(source_joint, isNodeReferenced=True)
                    or cmds.referenceQuery(target, isNodeReferenced=True)):
                raise ValueError("Skin 影响关节和目标网格须为本地可写节点")
            skins = cmds.ls(cmds.listHistory(target,
                                            pruneDagObjects=True) or [],
                            type="skinCluster") or []
            if len(set(skins)) > 1:
                raise ValueError("目标网格存在多个 SkinCluster，须指定目标层")
            if skins and cmds.referenceQuery(skins[0],
                                              isNodeReferenced=True):
                raise ValueError("目标 SkinCluster 须为本地可写节点")
            return
        source = self._unique(deformer, "softMod" if kind is CustomControlKind.SOFT_MOD
                              else "cluster")
        target = self._mesh(mesh)
        current = (self._softmod_meshes(source)
                   if kind is CustomControlKind.SOFT_MOD
                   else self._cluster_meshes(source))
        if target in current:
            raise ValueError("网格已经属于变形器影响集合")
        if (cmds.referenceQuery(source, isNodeReferenced=True)
                or cmds.referenceQuery(target, isNodeReferenced=True)):
            raise ValueError("变形器和新增网格须为本地可写节点")

    def add_custom_influenced_mesh(self, kind: CustomControlKind,
                                   deformer: str, joint: str | None,
                                   mesh: str) -> None:
        from maya import cmds

        self._require_transaction()
        self.preflight_custom_extension(kind, deformer, joint, mesh)
        self._transaction_changed = True
        if kind is CustomControlKind.SKIN:
            target = self._mesh(mesh)
            source_joint = self._unique(joint, "joint")
            skins = cmds.ls(cmds.listHistory(target,
                                            pruneDagObjects=True) or [],
                            type="skinCluster") or []
            if skins:
                cmds.skinCluster(skins[0], edit=True,
                                 addInfluence=source_joint,
                                 weight=0.0, lockWeights=False)
            else:
                cmds.skinCluster(source_joint, target,
                                 maximumInfluences=3)
        elif kind is CustomControlKind.SOFT_MOD:
            cmds.softMod(deformer, edit=True, geometry=mesh)
        else:
            cmds.cluster(deformer, edit=True, geometry=mesh)

    def open_cluster_weight_paint(self, deformer: str) -> None:
        from maya import cmds, mel

        cluster = self._unique(deformer, "cluster")
        sets = cmds.listConnections(cluster + ".message",
                                    source=False, destination=True,
                                    type="objectSet") or []
        if len(sets) != 1:
            raise ValueError("Cluster 缺少唯一变形器集合")
        cmds.select(sets[0], replace=True)
        mel.eval('artAttrToolScript 4 "cluster";')
        mel.eval('artSetToolAndSelectAttr("artAttrCtx", '
                 '"cluster.%s.weights");' % cluster)
        mel.eval("toolPropertyWindow;")

    def resolve_mirror_cluster_control(self, name: str) -> str:
        return self._unique(name, "transform")

    def mirror_cluster_weights(self, source: str, target: str,
                               mesh: str, side: str) -> None:
        from maya import cmds

        self._require_transaction()
        source = self._unique(source, "cluster")
        target = self._unique(target, "cluster")
        mesh = self._mesh(mesh)
        if (side not in ("L", "R") or source == target
                or mesh not in self._cluster_meshes(source)
                or mesh not in self._cluster_meshes(target)):
            raise ValueError("Cluster 镜像源、目标或侧别无效")
        shape = (cmds.listRelatives(mesh, shapes=True,
                                    noIntermediate=True, fullPath=True,
                                    type="mesh") or [None])[0]
        count = int(cmds.polyEvaluate(mesh, vertex=True))
        samples = []
        for index in range(count):
            vertex = "%s.vtx[%d]" % (mesh, index)
            values = cmds.percent(source, vertex, query=True, value=True) or []
            weight = float(values[0]) if values else 0.0
            if weight <= 0:
                continue
            position = cmds.xform(vertex, query=True,
                                  worldSpace=True, translation=True)
            if ((side == "R" and position[0] > -0.001)
                    or (side == "L" and position[0] < 0.001)):
                continue
            samples.append((weight, position))
        if not samples:
            raise ValueError("源侧 Cluster 没有可镜像的顶点权重")
        sampler = cmds.createNode("closestPointOnMesh")
        try:
            cmds.connectAttr(shape + ".outMesh", sampler + ".inMesh")
            cmds.connectAttr(shape + ".worldMatrix[0]",
                             sampler + ".inputMatrix")
            mapped = {}
            for weight, position in samples:
                cmds.setAttr(sampler + ".inPosition", -position[0],
                             position[1], position[2], type="double3")
                index = int(cmds.getAttr(sampler + ".closestVertexIndex"))
                mapped[index] = max(weight, mapped.get(index, 0.0))
            self._transaction_changed = True
            cmds.percent(target, mesh, value=0.0)
            for index, weight in mapped.items():
                cmds.percent(target, "%s.vtx[%d]" % (mesh, index),
                             value=weight)
        finally:
            cmds.delete(sampler)

    def custom_control_exists(self, control: str) -> bool:
        from maya import cmds

        return bool(cmds.objExists(control))

    def preflight_delete_custom_control(self,
                                        state: CustomControllerState) -> None:
        from maya import cmds

        nodes = [state.control, state.offset, state.parent_joint]
        if state.base_control:
            nodes.append(state.base_control)
        if state.joint:
            nodes.append(state.joint)
        if state.deformer:
            nodes.append(state.deformer)
        for node in nodes:
            if not cmds.objExists(node) or cmds.referenceQuery(
                    node, isNodeReferenced=True):
                raise ValueError("自定义控制器包含缺失或引用节点：" + node)
        if state.kind is CustomControlKind.SKIN:
            for mesh in state.influenced_meshes:
                if cmds.referenceQuery(mesh, isNodeReferenced=True):
                    raise ValueError("Skin Control 影响网格须为本地可写节点")

    def delete_custom_control(self, state: CustomControllerState) -> None:
        from maya import cmds

        self._require_transaction()
        self.preflight_delete_custom_control(state)
        self._transaction_changed = True
        attach = (cmds.listRelatives(state.offset, parent=True,
                                    fullPath=True) or [None])[0]
        if not attach:
            raise ValueError("自定义控制器缺少附着层")
        if cmds.objExists(self.scene_address(REGISTRY_NAME)):
            before = self.read_character_registration()
            local = (self._cmds.identity.to_local if self.namespace is not None
                     else lambda path: path)
            attach_local = local(attach)
            removed = {node.path for node in before.nodes
                       if node.path == attach_local
                       or node.path.startswith(attach_local + "|")}
            if state.joint:
                removed.add(local(state.joint))
            after = replace(before,
                            nodes=tuple(node for node in before.nodes
                                        if node.path not in removed),
                            channels=tuple(channel for channel in before.channels
                                           if channel.node not in removed))
            if len(after.nodes) == len(before.nodes):
                raise ValueError("自定义控制器不在角色登记中")
            self._validate_character_registration(after)
            registry = self.scene_address(REGISTRY_NAME)
            document = registry + ".advPyRegistryDocument"
            members = registry + ".members"
            cmds.setAttr(document, lock=False)
            cmds.setAttr(document, encode_registration(after), type="string")
            cmds.setAttr(document, lock=True)
            cmds.setAttr(members, lock=False)
            for index in cmds.getAttr(members, multiIndices=True) or []:
                destination = members + "[%d]" % index
                for source in cmds.listConnections(
                        destination, source=True, destination=False,
                        plugs=True) or []:
                    cmds.disconnectAttr(source, destination)
            for index, member in enumerate(after.nodes):
                cmds.connectAttr(self.scene_address(member.path) + ".message",
                                 members + "[%d]" % index)
            cmds.setAttr(members, lock=True)
        if state.kind is CustomControlKind.SKIN:
            joint = self._unique(state.joint, "joint")
            for skin in cmds.ls(type="skinCluster") or []:
                if not any(mesh in self._skin_meshes(skin)
                           for mesh in state.influenced_meshes):
                    continue
                indices = cmds.getAttr(skin + ".matrix",
                                       multiIndices=True) or []
                linked = [item for index in indices for item in
                          (cmds.listConnections(
                              skin + ".matrix[%d]" % index,
                              source=True, destination=False,
                              type="joint") or [])]
                if joint not in [path for item in linked
                                 for path in (cmds.ls(item, long=True,
                                                      type="joint") or [])]:
                    continue
                if len(indices) == 1:
                    cmds.delete(skin)
                else:
                    cmds.skinCluster(skin, edit=True, removeInfluence=joint)
            cmds.delete(joint)
        else:
            deformer = self._unique(state.deformer,
                                    "softMod" if state.kind is
                                    CustomControlKind.SOFT_MOD else "cluster")
            cmds.delete(deformer)
            if state.kind is CustomControlKind.CLUSTER:
                stem, side = state.control.rsplit("|", 1)[-1].rsplit(
                    ":", 1)[-1].rsplit("_", 1)
                handle = self.scene_address("Cluster" + stem + "_" + side
                                            + "Handle")
                if cmds.objExists(handle):
                    cmds.delete(handle)
            else:
                stem, side = state.control.rsplit("|", 1)[-1].rsplit(
                    ":", 1)[-1].rsplit("_", 1)
                for role in ("SoftModMultMatrix", "MainScaleForSoftModMPD1",
                             "MainScaleForSoftModMPD2"):
                    helper = self.scene_address(stem + role + "_" + side)
                    if cmds.objExists(helper):
                        cmds.delete(helper)
        cmds.delete(attach)
        if cmds.objExists(self.scene_address(REGISTRY_NAME)):
            self.read_character_registration()
