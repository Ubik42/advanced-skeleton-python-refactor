"""Maya scene port for SoftMod custom controls and influenced meshes."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import replace
import json

from adv_py.application.custom_controller import CustomControllerState
from adv_py.core.character_registry import (
    REGISTRY_NAME, CharacterChannel, encode_registration,
)
from adv_py.core.custom_controller import (
    CustomControlKind, CustomControllerPlan, DeformJointCandidate,
    SoftModRegion, WeightedVertex, original_parent_distance_key,
)

from .maya_face import MayaFaceHost


class MayaCustomControllerHost(MayaFaceHost):
    def __init__(self, *, namespace: str | None = None,
                 face: bool = False) -> None:
        super().__init__(namespace=namespace)
        self.face = face

    def _capture_face_owned_nodes(self) -> frozenset[str] | None:
        """Track later custom controls in the FaceSetup ownership boundary."""
        if not self.face:
            return None
        from maya import cmds

        face_set = self.scene_address("FaceAllSet")
        if not cmds.objExists(face_set):
            return None
        return frozenset(identifier for path in cmds.ls(long=True) or ()
                         for identifier in (cmds.ls(path, uuid=True) or ()))

    def _register_face_owned_nodes(self,
                                   before: frozenset[str] | None) -> None:
        if before is None:
            return
        from maya import cmds

        face_set = self.scene_address("FaceAllSet")
        if not cmds.objExists(face_set):
            raise RuntimeError("创建 Face 自定义控制器时 FaceAllSet 已消失")
        new_nodes = []
        for path in cmds.ls(long=True) or ():
            ids = cmds.ls(path, uuid=True) or ()
            if (len(ids) != 1 or ids[0] in before or
                    cmds.nodeType(path) in ("skinCluster", "mesh",
                                            "objectSet", "shadingEngine",
                                            "lambert", "blinn", "phong",
                                            "surfaceShader")):
                continue
            if cmds.referenceQuery(path, isNodeReferenced=True):
                raise RuntimeError("Face 自定义控制产生了引用节点：" + path)
            new_nodes.append(path)
        created = set(new_nodes)
        new_nodes = [path for path in new_nodes if not (
            path.startswith("|") and any(
                path.startswith(parent + "|")
                for parent in created if parent != path))]
        if new_nodes:
            cmds.sets(tuple(new_nodes), add=face_set)
            recorded = {identifier
                        for member in cmds.sets(face_set, query=True) or ()
                        for identifier in (cmds.ls(member, uuid=True) or ())}
            expected = {identifier for path in new_nodes
                        for identifier in (cmds.ls(path, uuid=True) or ())}
            if not expected <= recorded:
                raise RuntimeError("Face 自定义控制节点未登记到 FaceAllSet")

    def softmod_target_mesh(self, deformer: str) -> str:
        from .maya_original_custom_pose import original_softmod_mesh
        return original_softmod_mesh(self, deformer)

    def softmod_pose_center(self, deformer: str) -> tuple[float, float, float]:
        from maya import cmds

        self._require_transaction()
        source = self._unique(deformer, "softMod")
        handles = cmds.listConnections(source + ".matrix", source=True,
                                       destination=False,
                                       type="transform") or []
        if len(handles) != 1:
            raise ValueError("SoftMod 缺少唯一操作柄")
        handle = self._unique(handles[0], "transform")
        translation = cmds.getAttr(handle + ".translate")[0]
        self._transaction_changed = True
        try:
            cmds.setAttr(handle + ".translate", 0, 0, 0, type="float3")
            return tuple(float(value) for value in cmds.xform(
                handle, query=True, worldSpace=True, pivots=True)[:3])
        finally:
            cmds.setAttr(handle + ".translate", *translation, type="float3")

    def mirrored_parent_joint(self, parent: str) -> str:
        leaf = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if not leaf.endswith("_R"):
            return self._unique_custom_parent(parent)
        return self._unique_custom_parent(leaf[:-1] + "L")

    def create_mirrored_softmod(
            self, plan: CustomControllerPlan,
            posed_center: tuple[float, float, float]) -> str:
        """Build the temporary mirrored SoftMod used by ADV's recursive pass."""
        from maya import cmds

        self._require_transaction()
        if plan.side != "_R":
            raise ValueError("自动镜像仅从右侧创建左侧控制器")
        names = (self.scene_address("CustomControlMirrorSoftMod"),
                 self.scene_address("CustomControlMirrorSoftModHandle"))
        if any(cmds.objExists(name) for name in names):
            raise ValueError("自动镜像的临时 SoftMod 名称已占用")
        self._transaction_changed = True
        source_mesh = self._mesh(plan.region.mesh)
        reflected = (-posed_center[0], posed_center[1], posed_center[2])
        bbox = cmds.xform(source_mesh, query=True, boundingBox=True)
        target = source_mesh
        if bbox[3] < reflected[0]:
            sampler_name = self.scene_address("closestSampler")
            if cmds.objExists(sampler_name):cmds.delete(sampler_name)
            sampler = cmds.createNode("closestPointOnMesh", name=sampler_name)
            try:
                cmds.setAttr(sampler + ".inPosition", *reflected, type="double3")
                minimum_distance = 999.0
                for shape in cmds.ls(type="mesh", noIntermediate=True,
                                     long=True) or []:
                    mesh = (cmds.listRelatives(shape, parent=True,
                        fullPath=True) or [None])[0]
                    if not mesh:
                        continue
                    cmds.connectAttr(shape + ".outMesh",
                                     sampler + ".inMesh", force=True)
                    cmds.connectAttr(shape + ".worldMatrix[0]",
                                     sampler + ".inputMatrix", force=True)
                    from math import dist
                    position = cmds.getAttr(sampler + ".position")[0]
                    distance = dist(reflected, position)
                    if distance < minimum_distance:
                        minimum_distance = distance
                        target = self._mesh(mesh)
            finally:
                cmds.delete(sampler)
        from .maya_face_deformer_sets import original_face_deformer_sets
        with getattr(self._cmds, "_creation_namespace", nullcontext)(), original_face_deformer_sets(self._cmds):
            created = cmds.softMod(target, name=names[0], falloffMode=1, falloffAroundSelection=False)
        if len(created) != 2:
            raise RuntimeError("镜像 SoftMod 未返回变形器和操作柄")
        source = self._unique(created[0], "softMod")
        handle = cmds.rename(self._unique(created[1], "transform"),
                             names[1])
        build_center = (-plan.region.center[0], plan.region.center[1],
                        plan.region.center[2])
        for shape in cmds.listRelatives(handle, shapes=True,
                                        fullPath=True) or []:
            if cmds.objExists(shape + ".origin"):
                cmds.setAttr(shape + ".origin", *build_center, type="float3")
        cmds.xform(handle, pivots=build_center)
        cmds.setAttr(source + ".falloffCenter", *build_center, type="float3")
        cmds.setAttr(source + ".falloffRadius", plan.region.falloff_radius)
        cmds.setAttr(source + ".falloffMode", plan.region.falloff_mode)
        for index, (value, position, interpolation) in enumerate(
                plan.region.falloff_curve):
            plug = source + ".falloffCurve[%d]." % index
            cmds.setAttr(plug + "falloffCurve_FloatValue", value)
            cmds.setAttr(plug + "falloffCurve_Position", position)
            cmds.setAttr(plug + "falloffCurve_Interp", interpolation)
        return source

    def _custom_system(self) -> str:
        from maya import cmds

        name = self.scene_address("FaceCustomSystem" if self.face
                                  else "CustomSystem")
        if cmds.objExists(name):
            system = self._unique(name, "transform")
        else:
            motion_name = "FaceMotionSystem" if self.face else "MotionSystem"
            if cmds.objExists(self.scene_address(motion_name)):
                system = cmds.createNode("transform", name=name,
                    parent=self._unique(motion_name, "transform"))
            else:
                system = cmds.createNode("transform", name=name)
        if self.face:
            control_box = self.scene_address("ctrlBox")
            source = control_box + ".CustomCtrlVis"
            if cmds.objExists(source):
                self._connect_custom_system(source, system + ".visibility")
        else:
            main = next((self.scene_address(name)
                         for name in ("Main", "AdvPy_Global")
                         if cmds.objExists(self.scene_address(name))), None)
            if main is not None:
                source = main + ".customVis"
                if not cmds.objExists(source):
                    cmds.addAttr(main, longName="customVis",
                                 attributeType="bool", defaultValue=True,
                                 keyable=True)
                    cmds.setAttr(source, keyable=False, channelBox=True)
                self._connect_custom_system(source, system + ".visibility")
            scale = self.scene_address("MainScaleMultiplyDivide")
            if cmds.objExists(scale + ".output"):
                self._connect_custom_system(scale + ".output",
                                            system + ".scale")
        return system

    @staticmethod
    def _connect_custom_system(source: str, destination: str) -> None:
        from maya import cmds

        if cmds.isConnected(source, destination):
            return
        incoming = cmds.listConnections(destination, source=True,
                                        destination=False,
                                        plugs=True) or []
        if incoming:
            raise ValueError("CustomSystem 已由其他节点驱动：" + destination)
        cmds.connectAttr(source, destination)

    @contextmanager
    def build_pose_session(self, deformer: str):
        from .maya_original_custom_pose import build_pose_session
        with build_pose_session(self, deformer):
            yield

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

    def _ensure_custom_partial_parent(self, parent: str) -> str:
        """Custom Control uses the same asCreatePartialJoints source graph.

        Its caller already owns the build-pose session and undo chunk. Do not
        manufacture a separate midpoint constraint graph or open a nested chunk.
        """
        from .maya_partial_joints import MayaPartialJointsHost
        from adv_py.core.partial_joints import plan_create_partial_joints

        self._require_transaction()
        parent = self._unique_custom_parent(parent)
        if self._cmds.nodeType(parent) != "joint":return parent
        helper = MayaPartialJointsHost(namespace=self.namespace)
        candidates = helper.capture_partial_candidates()
        candidate = next((row for row in candidates if row.joint == parent), None)
        if candidate is None:
            return parent
        leaf = helper._leaf(parent)
        stem, separator, side = leaf.rpartition("_")
        if not separator or not candidate.parent or not candidate.child_count:
            return parent
        import re
        if re.search(r"Part[0-9]", leaf):
            return parent
        partial = helper._node(stem + "Partial_" + side)
        if helper._cmds.objExists(partial):
            return self._unique(partial, "joint")
        plan = plan_create_partial_joints(
            candidates, (parent,), use_opm=helper.partial_uses_opm())
        helper._transaction_active = True
        try:
            for spec in plan.specs:
                helper.create_partial_joint(spec)
        finally:
            helper._transaction_active = False
            self._transaction_changed |= helper._transaction_changed
        return self._unique(partial, "joint")

    def _register_custom_nodes(self, paths: tuple[str, ...],
                               control: str, base: str | None = None) -> None:
        from maya import cmds

        # Native parenting returns shortest unique names. Registry documents
        # store complete DAG paths and UUIDs after the graph has settled.
        paths = tuple(self._unique_custom_parent(path) for path in paths)
        control = self._unique(control, "transform")
        base = self._unique(base, "transform") if base else None
        self._update_custom_build_pose(control, base=base, add=True)
        control_set = self.scene_address("FaceControlSet" if self.face
                                         else "ControlSet")
        if not cmds.objExists(control_set) and self.face:
            raise ValueError("Face 自定义控制器缺少 FaceControlSet")
        if cmds.objExists(control_set):
            cmds.sets([node for node in (control, base) if node],
                      add=control_set)
        if self.face:
            return
        if not cmds.objExists(self.scene_address(REGISTRY_NAME)):
            # Original ADV rigs carry sets and buildPose, not this port's
            # optional registry. Do not impose a new conversion prerequisite.
            return
        previous = self.read_character_registration()
        local = (self._cmds.identity.to_local if self.namespace is not None
                 else lambda path: path)
        registered = {node.path for node in previous.nodes}
        nodes = tuple(self._registry_node(local(path)) for path in dict.fromkeys(paths)
                      if local(path) not in registered)
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

    def _update_custom_build_pose(self, control: str, *,
                                  base: str | None = None,
                                  add: bool) -> None:
        """Maintain the original buildPose custom-channel reset command."""
        from maya import cmds

        node = self.scene_address("faceBuildPose" if self.face else "buildPose")
        if not cmds.objExists(node):
            return
        plug = node + ".udExtraAttr"
        if not cmds.objExists(plug):
            if not add:
                return
            cmds.addAttr(node, longName="udExtraAttr", dataType="string")
        script = cmds.getAttr(plug) or ""
        metadata = control + ".advPyBuildPoseCommand"
        if add:
            command = ('xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 '
                       '"%s";' % control)
            for attribute in cmds.listAttr(control, userDefined=True,
                                           keyable=True) or []:
                value = cmds.getAttr(control + "." + attribute)
                if isinstance(value, (int, float, bool)):
                    command += ('setAttr "%s.%s" %s;' %
                                (control, attribute, int(value) if
                                 isinstance(value, bool) else value))
            if base:
                command += ('xform -os -t 0 0 0 -ro 0 0 0 -s 1 1 1 '
                            '"%s";' % base)
        else:
            if not cmds.objExists(metadata):
                return
            command = cmds.getAttr(metadata) or ""
        if add:
            if command in script:
                raise ValueError("控制器已经写入 buildPose 附加命令")
            script += command
            cmds.addAttr(control, longName="advPyBuildPoseCommand",
                         dataType="string")
            cmds.setAttr(metadata, command, type="string", lock=True)
            values = []
            for node in (control, *((base,) if base else ())):
                for kind, neutral in (("translate", 0.0),
                                      ("rotate", 0.0), ("scale", 1.0)):
                    for axis in "XYZ":
                        attribute = kind + axis
                        value_plug = node + "." + attribute
                        if cmds.getAttr(value_plug, settable=True):
                            values.append((node, attribute, neutral))
                if node == control:
                    for attribute in cmds.listAttr(
                            node, userDefined=True, keyable=True) or []:
                        value = cmds.getAttr(node + "." + attribute)
                        if isinstance(value, (int, float, bool)):
                            values.append((node, attribute, float(value)))
            cmds.addAttr(control, longName="advPyBuildPoseValues",
                         dataType="string")
            cmds.setAttr(control + ".advPyBuildPoseValues",
                         json.dumps(values, separators=(",", ":")),
                         type="string", lock=True)
        else:
            script = script.replace(command, "", 1)
        cmds.setAttr(plug, script, type="string")

    def _skin_for_mesh(self, mesh: str,
                       requested: str | None = None) -> str:
        from maya import cmds

        skins = tuple(dict.fromkeys(cmds.ls(
            cmds.listHistory(mesh, pruneDagObjects=True, interestLevel=2) or [],
            type="skinCluster") or []))
        if requested == "*new":
            return "*new"
        if requested is not None:
            chosen = self._unique(requested, "skinCluster")
            if chosen not in {self._unique(item, "skinCluster")
                              for item in skins}:
                raise ValueError("指定 SkinCluster 不属于目标网格")
            return chosen
        if not skins:
            raise ValueError("目标网格没有 SkinCluster；新建分层时使用 *new")
        # asGetSkinCluster retains the last native history match.
        return self._unique(skins[-1], "skinCluster")

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

        # Maya selection and deformer history may address either the transform
        # or its shape. Preserve the selected DAG instance when resolving it.
        address = path if path.startswith(("|", ":")) or ":" in path else self.scene_address(path)
        nodes = cmds.ls(address, long=True) or []
        if len(nodes) == 1 and cmds.nodeType(nodes[0]) == "mesh":
            parents = cmds.listRelatives(nodes[0], parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise ValueError("目标网格 Shape 缺少唯一父级")
            path = parents[0]
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
        from .maya_original_custom_pose import original_softmod_mesh
        mesh = original_softmod_mesh(self, source)
        count = int(cmds.polyEvaluate(mesh, vertex=True))
        geometries = cmds.softMod(source, query=True, geometry=True) or []
        indices = cmds.softMod(source, query=True, geometryIndices=True) or []
        if len(geometries) != len(indices):
            raise ValueError("SoftMod 输出几何与索引数量不一致")
        matches = [index for geometry, index in zip(geometries, indices)
                   if self._mesh(geometry) == mesh]
        if len(matches) != 1:
            raise ValueError("SoftMod 选定输出网格缺少唯一索引")
        geometry_index = matches[0]
        selection = om.MSelectionList()
        selection.add(source)
        fn = oma.MFnWeightGeometryFilter(selection.getDependNode(0))
        components = om.MFnSingleIndexedComponent().create(
            om.MFn.kMeshVertComponent)
        om.MFnSingleIndexedComponent(components).addElements(range(count))
        values = fn.getWeights(int(geometry_index), components)
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

    def deform_joint_candidates(self, mesh: str, *, include_preferred: bool = True
                                ) -> tuple[DeformJointCandidate, ...]:
        """asGetDeformJointsByDistance / asCCLayout's original candidate list."""
        from maya import cmds

        self._mesh(mesh)
        deformation = self.scene_address("DeformationSystem")
        paths = (cmds.listRelatives(deformation, allDescendents=True,
                    fullPath=True, type="joint") or [] if cmds.objExists(deformation)
                 else cmds.ls(type="joint", long=True) or [])
        candidates = []
        for path in paths:
            leaf = path.rsplit("|", 1)[-1]
            if leaf.endswith("_L") or "Partial_" in leaf or "Fix" in leaf:
                continue
            center = tuple(float(value) for value in cmds.xform(
                path, query=True, worldSpace=True, translation=True))
            candidates.append(DeformJointCandidate(path, center))
        preferred = self.preferred_custom_parent() if include_preferred else None
        if preferred and preferred not in {item.path for item in candidates}:
            center = tuple(float(value) for value in cmds.xform(
                preferred, query=True, worldSpace=True, translation=True))
            candidates.insert(0, DeformJointCandidate(preferred, center))
        return tuple(candidates)

    def _unique_custom_parent(self, node: str) -> str:
        from maya import cmds
        paths = cmds.ls(self.scene_address(node), long=True) or []
        if len(paths) != 1 or cmds.nodeType(paths[0]) not in ("joint", "transform"):
            raise ValueError("自定义控制父节点须为唯一的 Transform 或 Joint")
        return paths[0]

    def custom_parent_candidate(self, node: str) -> DeformJointCandidate:
        from maya import cmds
        path = self._unique_custom_parent(node)
        center = tuple(float(value) for value in cmds.xform(
            path, query=True, worldSpace=True, translation=True))
        return DeformJointCandidate(path, center)

    def custom_parent_candidates(self, region, candidates, preferred=None):
        """Reproduce asCCLayout's ordered end-joint removals, then promotion."""
        from maya import cmds
        rows = sorted(candidates, key=lambda row:
                      original_parent_distance_key(row, region.center))
        # MEL mutates the list in its index loop. Do not turn this into a
        # blanket filter: removal changes which following item is visited.
        index = 0
        while index < len(rows):
            row = rows[index]
            if (not cmds.listRelatives(row.path, children=True, type="joint")
                    and not cmds.attributeQuery("control", node=row.path, exists=True)
                    and len(rows) > 1):
                rows.pop(index)
            index += 1
        if preferred:
            preferred = self._unique_custom_parent(preferred)
            rows = [row for row in rows if row.path != preferred]
            rows.insert(0, self.custom_parent_candidate(preferred))
        return tuple(rows)

    def preferred_custom_parent(self) -> str | None:
        from maya import cmds

        preferred = None
        fit_name = self.scene_address("FaceFitSkeleton")
        if self.face and cmds.objExists(fit_name + ".HeadJoint"):
            head = cmds.getAttr(fit_name + ".HeadJoint")
            if head:preferred = self._unique_custom_parent(head)
        selected = cmds.ls(selection=True, type="transform", long=True) or []
        if len(selected) > 1:
            preferred = self._unique_custom_parent(selected[1])
        return preferred

    def custom_parent_for_source(self, deformer: str) -> str:
        """Choose the dialog's parent in the input pose, before UV/build pose."""
        from types import SimpleNamespace
        from maya import cmds
        preferred = self.preferred_custom_parent()
        source = self._unique(deformer, "softMod")
        mesh = self.softmod_target_mesh(source)
        handles = cmds.listConnections(source + ".matrix", source=True,
                                       destination=False, type="transform") or []
        if len(handles) != 1:raise ValueError("SoftMod 缺少唯一操作柄")
        handle = self._unique(handles[0], "transform")
        shapes = cmds.listRelatives(handle, shapes=True, fullPath=True) or []
        origins = [shape for shape in shapes if cmds.objExists(shape + ".origin")]
        if len(origins) != 1:raise ValueError("SoftMod 缺少唯一原点")
        region = SimpleNamespace(center=tuple(cmds.getAttr(origins[0] + ".origin")[0]))
        candidates = self.custom_parent_candidates(
            region, self.deform_joint_candidates(mesh), preferred)
        if not candidates:raise ValueError("自定义控制器缺少可用父节点")
        return candidates[0].path

    def preflight_custom_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        source = self._unique(plan.region.deformer, "softMod")
        handle = self._unique(plan.region.source_handle, "transform")
        mesh = self._mesh(plan.region.mesh)
        parent = self._unique_custom_parent(plan.parent_joint)
        if plan.partial_parent and self.face:
            raise ValueError("Face Custom Control 不支持 50% Parent")
        if self.face and (not cmds.objExists(self.scene_address(
                "FaceControlSet")) or not cmds.objExists(self.scene_address(
                    "faceBuildPose"))):
            raise ValueError("Face Custom Control 要求已构建 FaceControlSet 和 faceBuildPose")
        game_engine = self.scene_address(
            "FaceFitSkeleton.GameEngine" if self.face
            else "FitSkeleton.gameEngine")
        if not self.face:
            from adv_py.core.body_game_engine import (
                BodyGameEnginePolicy, BodyOperation)

            operation = {
                CustomControlKind.SKIN: BodyOperation.SKIN_CONTROL,
                CustomControlKind.CLUSTER: BodyOperation.CLUSTER_CONTROL,
                CustomControlKind.SOFT_MOD: BodyOperation.SOFT_MOD_CONTROL,
            }[plan.kind]
            enabled = bool(cmds.objExists(game_engine)
                           and cmds.getAttr(game_engine))
            BodyGameEnginePolicy(enabled).require(operation)
        elif (plan.kind is not CustomControlKind.SKIN
              and cmds.objExists(game_engine)
              and bool(cmds.getAttr(game_engine))):
            raise ValueError("Face 游戏引擎模式仅允许 Skin Control")
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
            skin = self._skin_for_mesh(mesh, plan.skin_cluster)
            if (skin != "*new"
                    and cmds.referenceQuery(skin, isNodeReferenced=True)):
                raise ValueError("Skin Control 要求本地可写的 SkinCluster")

    def create_custom_controller(self, plan: CustomControllerPlan) -> None:
        from maya import cmds

        self._require_transaction()
        self.preflight_custom_controller(plan)
        face_before = self._capture_face_owned_nodes()
        self._transaction_changed = True
        self._prepare_custom_source(plan)
        if plan.kind is CustomControlKind.SKIN:
            self._create_skin_controller(plan)
            self._register_face_owned_nodes(face_before)
            return
        if plan.kind is CustomControlKind.CLUSTER:
            self._create_cluster_controller(plan)
            self._register_face_owned_nodes(face_before)
            return
        from .maya_original_custom_deformers import create_softmod
        create_softmod(self, plan)
        self._register_face_owned_nodes(face_before)

    def _create_skin_controller(self, plan: CustomControllerPlan) -> None:
        from .maya_original_custom_skin import create
        create(self, plan)

    def _create_cluster_controller(self, plan: CustomControllerPlan) -> None:
        from .maya_original_custom_deformers import create_cluster
        create_cluster(self, plan)

    def capture_custom_controller(self, plan: CustomControllerPlan
                                  ) -> CustomControllerState:
        return self.capture_custom_control(plan.control_name)

    def capture_custom_control(self, control: str) -> CustomControllerState:
        from maya import cmds

        path = self._unique(control, "transform")
        kind_plug = path + ".advPyCustomControlKind"
        original = not cmds.objExists(kind_plug)
        leaf = path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if original:
            # Original custom controls have native type flags, .parent and
            # source-named deformers, without Python registration metadata.
            flags = (("softModControl", CustomControlKind.SOFT_MOD),
                     ("clusterControl", CustomControlKind.CLUSTER),
                     ("skinControl", CustomControlKind.SKIN))
            kinds = [value for attr, value in flags if cmds.objExists(path + "." + attr)
                     and cmds.getAttr(path + "." + attr)]
            if len(kinds) != 1 or not cmds.objExists(path + ".parent") or not any(
                    part.rsplit(":", 1)[-1] in ("CustomSystem", "FaceCustomSystem")
                    for part in path.split("|")):
                raise ValueError("所选节点不是原版自定义控制器")
            kind = kinds[0]
            stem, side = leaf.rsplit("_", 1)
            if kind is CustomControlKind.SKIN:
                source_joint = self._unique("Joint" + leaf, "joint")
                links = cmds.listConnections(source_joint + ".worldMatrix[0]",
                    source=False, destination=True, type="skinCluster") or []
                links = list(dict.fromkeys(links))[:1]
            else:
                links = [self._unique(stem + "SoftMod_" + side, "softMod")
                         if kind is CustomControlKind.SOFT_MOD else
                         self._unique("Cluster" + leaf, "cluster")]
        else:
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
        elif kind is CustomControlKind.CLUSTER:
            subtract = base
            offset = (cmds.listRelatives(subtract, parent=True,
                                        fullPath=True) or [None])[0]
            if not offset:
                raise ValueError("Cluster Control 缺少偏移层")
            base = None
        else:
            offset, base = base, None
        attach = (offset if kind is CustomControlKind.SOFT_MOD else
                  (cmds.listRelatives(offset, parent=True,
                                      fullPath=True) or [None])[0])
        parents = ([cmds.getAttr(path + ".parent")] if original else
                   cmds.listConnections(path + ".advPyCustomControlParent",
                       source=True, destination=False) or [])
        if not attach or len(parents) != 1:
            raise ValueError("自定义控制器缺少附着层或父关节")
        parent = self._unique_custom_parent(parents[0])
        local = (self._cmds.identity.to_local if self.namespace is not None
                 else lambda node: node)
        has_registry = (not self.face and cmds.objExists(
            self.scene_address(REGISTRY_NAME)))
        registered = ({node.path for node in
                       self.read_character_registration().nodes}
                      if has_registry else set())
        expected = {local(attach), local(offset), local(path)}
        if base:
            expected.add(local(base))
        if kind is CustomControlKind.CLUSTER:
            group = (cmds.listRelatives(attach, parent=True,
                                       fullPath=True) or [None])[0]
            if (not group or group.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                    != "ClusterControlGrp" + path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]):
                raise ValueError("Cluster Control 缺少控制组")
            expected.update((local(subtract), local(group)))
        if self.face:
            face_path = any(segment.rsplit(":", 1)[-1] == "FaceCustomSystem"
                            for segment in path.split("|") if segment)
            face_set = self.scene_address("FaceControlSet")
            if (not face_path or not cmds.objExists(face_set)
                    or not cmds.sets(path, isMember=face_set)):
                raise ValueError("自定义控制器未加入 FaceControlSet")
        elif has_registry and not original and not expected <= registered:
            raise ValueError("自定义控制器未登记到 Body 角色")
        joint = None
        if kind is CustomControlKind.SKIN:
            joints = ([source_joint] if original else cmds.listConnections(
                path + ".advPyCustomControlJoint", source=True,
                destination=False, type="joint") or [])
            if len(joints) != 1:
                raise ValueError("Skin Control 缺少唯一影响关节")
            joint = self._unique(joints[0], "joint")
            if has_registry and not original and local(joint) not in registered:
                raise ValueError("Skin Control 影响关节未登记到角色")
            if self._is_layered_custom_skin(path, joint):
                joint_offset = (cmds.listRelatives(joint, parent=True,
                    fullPath=True) or [None])[0]
                offset_leaf = (joint_offset.rsplit("|", 1)[-1]
                               .rsplit(":", 1)[-1] if joint_offset else "")
                if (not offset_leaf.startswith("JointOffset")
                        or has_registry and local(joint_offset) not in registered):
                    raise ValueError("分层 Skin Control 缺少关节偏移层")
        return CustomControllerState(
            kind, offset, path, base, parent,
            self._softmod_meshes(deformer) if kind is CustomControlKind.SOFT_MOD
            else self._cluster_meshes(deformer)
            if kind is CustomControlKind.CLUSTER
            else self._skin_joint_meshes(joint),
            joint, deformer,
            (int(cmds.getAttr(path + ".advPyCustomControlWeightCount"))
             if not original else self._original_custom_weight_count(kind, deformer, joint)))

    def _original_custom_weight_count(self, kind, deformer, joint):
        """Read native weights for source controls without port metadata."""
        from maya import cmds
        from maya.api import OpenMaya as om, OpenMayaAnim as oma
        selection = om.MSelectionList(); selection.add(deformer)
        if kind is CustomControlKind.SKIN:
            fn = oma.MFnSkinCluster(selection.getDependNode(0))
            influence = om.MSelectionList(); influence.add(joint)
            logical = fn.indexForInfluenceObject(influence.getDagPath(0))
            physical = next(i for i, path in enumerate(fn.influenceObjects())
                            if fn.indexForInfluenceObject(path) == logical)
            meshes = self._skin_meshes(deformer)
        else:
            fn = oma.MFnWeightGeometryFilter(selection.getDependNode(0))
            meshes = self._softmod_meshes(deformer) if kind is CustomControlKind.SOFT_MOD else self._cluster_meshes(deformer)
        count = 0
        for mesh in meshes:
            geometry = om.MSelectionList(); geometry.add(mesh)
            dag = geometry.getDagPath(0); dag.extendToShape()
            component = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
            om.MFnSingleIndexedComponent(component).addElements(range(cmds.polyEvaluate(mesh, vertex=True)))
            weights = (fn.getWeights(dag, component, physical) if kind is CustomControlKind.SKIN
                       else fn.getWeights(dag, component))
            count += sum(value > 0. for value in weights)
        return count

    @staticmethod
    def _is_layered_custom_skin(control, joint):
        from maya import cmds
        plug = control + ".advPyLayeredSkin"
        if cmds.objExists(plug):
            return bool(cmds.getAttr(plug))
        parents = cmds.listRelatives(joint, parent=True, fullPath=True) or []
        return bool(parents and parents[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1].startswith("JointOffset"))

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
                                            pruneDagObjects=True, interestLevel=2) or [],
                            type="skinCluster") or []
            if skins and cmds.referenceQuery(skins[-1],
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
                                            pruneDagObjects=True, interestLevel=2) or [],
                            type="skinCluster") or []
            if skins:
                cmds.skinCluster(skins[-1], edit=True,
                                 addInfluence=source_joint,
                                 weight=0.0, lockWeights=False)
            else:
                from .maya_original_skin_history import new_original_skin_clusters
                cmds.select(source_joint, target, replace=True)
                new_original_skin_clusters(commands=cmds, namespace=self.namespace)
        else:
            from .maya_face_deformer_sets import original_deformer_set
            cmds.sets(mesh, add=original_deformer_set(cmds, deformer))

    def open_cluster_weight_paint(self, deformer: str) -> None:
        from maya import cmds, mel

        cluster = self._unique(deformer, "cluster")
        from .maya_face_deformer_sets import original_deformer_set
        cmds.select(original_deformer_set(cmds, cluster), replace=True)
        cmds.select(cmds.ls(selection=True, objectsOnly=True) or [], replace=True)
        mel.eval('artAttrToolScript 4 "cluster";')
        mel.eval('artSetToolAndSelectAttr("artAttrCtx", '
                 '"cluster.%s.weights");' % cluster)
        mel.eval("toolPropertyWindow;")

    def resolve_mirror_cluster_control(self, name: str) -> str:
        return self._unique(name, "transform")

    def mirror_cluster_weights(self, source: str, target: str,
                               mesh: str, side: str) -> None:
        from .maya_original_custom_mirror import mirror_cluster_weights
        mirror_cluster_weights(self, source, target, mesh, side)

    def custom_control_exists(self, control: str) -> bool:
        from maya import cmds

        return bool(cmds.objExists(control))

    def paired_custom_control(self, control: str) -> str | None:
        from maya import cmds

        leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if not leaf.endswith(("_L", "_R")):
            return None
        opposite = leaf[:-1] + ("R" if leaf.endswith("_L") else "L")
        matches = cmds.ls(self.scene_address(opposite), long=True,
                          type="transform") or []
        if len(matches) > 1:
            raise ValueError("同名对侧控制器不唯一")
        return matches[0] if matches else None

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
        self._update_custom_build_pose(state.control, add=False)
        attach = (cmds.listRelatives(state.offset, parent=True,
                                    fullPath=True) or [None])[0]
        if not attach:
            raise ValueError("自定义控制器缺少附着层")
        delete_root = (state.offset if state.kind is CustomControlKind.SOFT_MOD
                       or state.kind is CustomControlKind.SKIN
                       and attach.rsplit("|", 1)[-1].rsplit(":", 1)[-1].startswith("ParentConstraintTo")
                       else attach)
        if state.kind is CustomControlKind.CLUSTER:
            delete_root = (cmds.listRelatives(attach, parent=True,
                                             fullPath=True) or [None])[0]
            if not delete_root:
                raise ValueError("Cluster Control 缺少控制组")
        if not self.face and cmds.objExists(self.scene_address(REGISTRY_NAME)):
            before = self.read_character_registration()
            local = (self._cmds.identity.to_local if self.namespace is not None
                     else lambda path: path)
            attach_local = local(delete_root)
            removed = {node.path for node in before.nodes
                       if node.path == attach_local
                       or node.path.startswith(attach_local + "|")}
            if state.joint:
                removed.add(local(state.joint))
                if self._is_layered_custom_skin(state.control, state.joint):
                    joint_offset = (cmds.listRelatives(
                        state.joint, parent=True, fullPath=True) or [None])[0]
                    if joint_offset:
                        removed.add(local(joint_offset))
            after = replace(before,
                            nodes=tuple(node for node in before.nodes
                                        if node.path not in removed),
                            channels=tuple(channel for channel in before.channels
                                           if channel.node not in removed))
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
            layered = self._is_layered_custom_skin(state.control, joint)
            joint_offset = ((cmds.listRelatives(joint, parent=True,
                fullPath=True) or [None])[0] if layered else None)
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
            if joint_offset and cmds.objExists(joint_offset):
                cmds.delete(joint_offset)
            if layered:
                leaf = state.control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                stem, side = leaf.rsplit("_", 1)
                matrix = self.scene_address(stem + "JointMM_" + side)
                if cmds.objExists(matrix):
                    cmds.delete(matrix)
        else:
            deformer = self._unique(state.deformer,
                                    "softMod" if state.kind is
                                    CustomControlKind.SOFT_MOD else "cluster")
            cmds.delete(deformer)
            if state.kind is CustomControlKind.CLUSTER:
                stem, side = state.control.rsplit("|", 1)[-1].rsplit(
                    ":", 1)[-1].rsplit("_", 1)
                for role in ("OffsetDM", "PlusMinusAverage", "MMT", "DMT",
                             "MMR", "DMR", "CurveFromMeshEdge",
                             "PointOnCurveInfo"):
                    helper = self.scene_address(role + stem + "_" + side)
                    if cmds.objExists(helper):
                        cmds.delete(helper)
            else:
                stem, side = state.control.rsplit("|", 1)[-1].rsplit(
                    ":", 1)[-1].rsplit("_", 1)
                for role in ("SoftModMultMatrix", "MainScaleForSoftModMPD1",
                             "MainScaleForSoftModMPD2"):
                    helper = self.scene_address(stem + role + "_" + side)
                    if cmds.objExists(helper):
                        cmds.delete(helper)
        cmds.delete(delete_root)
        from adv_py.core.original_build_pose_cleanup import original_build_pose_commands
        pose = self.scene_address("faceBuildPose" if self.face else "buildPose")
        for attribute in ("udAttr", "udExtraAttr"):
            plug = pose + "." + attribute
            if cmds.objExists(plug):
                text = original_build_pose_commands(cmds.getAttr(plug) or "",
                    lambda token: cmds.objExists(token.strip('"')))
                cmds.setAttr(plug, text, type="string")
        if not self.face and cmds.objExists(self.scene_address(REGISTRY_NAME)):
            self.read_character_registration()
