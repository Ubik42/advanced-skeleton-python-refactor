"""Maya host for live, selected-face Control Mesh shapes."""
from __future__ import annotations

from contextlib import contextmanager
import re

from adv_py.core.control_mesh import ControlMeshItem, ControlMeshSource
from adv_py.core.control_mesh_color import (
    ControlMeshColorItem, ControlMeshColorSource, SHADER_COLORS,
)


class MayaControlMeshHost:
    def __init__(self) -> None:
        from maya import cmds
        from maya.api import OpenMaya

        self.cmds = cmds
        self.om = OpenMaya
        self._in_transaction = False

    def _mesh(self, shape: str):
        path = self.om.MSelectionList().add(shape).getDagPath(0)
        return self.om.MFnMesh(path), path

    def _face_content(self, shape: str, faces: tuple[int, ...]):
        mesh, dag = self._mesh(shape)
        points = mesh.getPoints(self.om.MSpace.kWorld)
        shaders, assignments = mesh.getConnectedShaders(
            dag.instanceNumber())
        materials = tuple(self.om.MFnDependencyNode(shader).name()
                          for shader in shaders)
        rows = []
        for face in faces:
            vertices = tuple(sorted(
                tuple(round(float(value), 6) for value in
                      (points[index].x, points[index].y,
                       points[index].z))
                for index in mesh.getPolygonVertices(face)))
            slot = int(assignments[face])
            rows.append((vertices,
                         materials[slot] if 0 <= slot < len(materials)
                         else None))
        return tuple(sorted(rows, key=repr))

    def _mirror_faces(self, shape: str, faces: tuple[int, ...]
                      ) -> tuple[int, ...]:
        mesh, _ = self._mesh(shape)
        points = mesh.getPoints(self.om.MSpace.kWorld)
        selected_vertices = set()
        for face in faces:
            selected_vertices.update(mesh.getPolygonVertices(face))
        mirrored_vertices = set()
        for vertex in selected_vertices:
            point = points[vertex]
            reflected = self.om.MPoint(-point.x, point.y, point.z)
            _, near_face = mesh.getClosestPoint(
                reflected, self.om.MSpace.kWorld)
            candidates = mesh.getPolygonVertices(near_face)
            mirrored_vertices.add(min(candidates, key=lambda index:
                (points[index].x - reflected.x) ** 2
                + (points[index].y - reflected.y) ** 2
                + (points[index].z - reflected.z) ** 2))
        return tuple(index for index in range(mesh.numPolygons)
                     if set(mesh.getPolygonVertices(index))
                     <= mirrored_vertices)

    def capture_control_mesh_source(
        self, global_control: str, mirror: bool,
    ) -> ControlMeshSource:
        c = self.cmds
        selected = c.ls(selection=True, flatten=True, long=True) or []
        if len(selected) < 2 or "." in selected[-1]:
            raise ValueError("请先选一件网格的面，最后选择目标控制器")
        control = selected[-1]
        if c.nodeType(control) != "transform":
            raise ValueError("最后选择的对象必须是控制器 Transform")
        components = selected[:-1]
        if any(".f[" not in component for component in components):
            raise ValueError("控制器之前只能选择多边形面")
        owners = {component.rsplit(".f[", 1)[0]
                  for component in components}
        if len(owners) != 1:
            raise ValueError("Control Mesh 一次只接受一件来源网格")
        owner = owners.pop()
        shape = (owner if c.nodeType(owner) == "mesh" else
                 (c.listRelatives(owner, shapes=True, fullPath=True,
                                  noIntermediate=True, type="mesh") or [None])[0])
        if not shape:
            raise ValueError("所选面缺少唯一多边形网格 Shape")
        mesh, _ = self._mesh(shape)
        faces = tuple(sorted({int(component.rsplit(".f[", 1)[1][:-1])
                              for component in components}))
        opposite = None
        mirror_faces = ()
        leaf = control.rsplit("|", 1)[-1]
        if mirror and leaf.endswith(("_R", "_L")):
            other_leaf = leaf[:-1] + ("L" if leaf.endswith("_R") else "R")
            matches = c.ls(other_leaf, long=True, type="transform") or []
            if len(matches) == 1:
                opposite = matches[0]
                mirror_faces = self._mirror_faces(shape, faces)
                if not mirror_faces:
                    raise ValueError("Control Mesh 镜像侧没有包含的网格面")
        return ControlMeshSource(shape, control, global_control,
                                 faces, mesh.numPolygons,
                                 opposite, mirror_faces)

    def _control_for_influence(self, joint: str,
                               controls: dict[str, str]) -> str | None:
        c = self.cmds
        current = joint
        for _ in range(100):
            leaf = current.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if "_" in leaf:
                stem, side = leaf.rsplit("_", 1)
                candidates = ("AdvPy_" + stem + "FK_" + side,
                              "AdvPy_Torso" + leaf + "FK",
                              "FK" + leaf, stem + "FK_" + side)
            else:
                candidates = ("FK" + leaf,)
            candidates += (leaf.replace("Joint", ""),)
            for candidate in candidates:
                if candidate in controls:
                    return controls[candidate]
            parent = c.listRelatives(current, parent=True,
                                     fullPath=True) or []
            if not parent or c.nodeType(parent[0]) != "joint":
                break
            current = parent[0]
        return None

    def capture_control_mesh_batch_sources(
        self, global_control: str, controls: tuple[str, ...],
    ) -> tuple[ControlMeshSource, ...]:
        from maya.api import OpenMayaAnim

        c = self.cmds
        selected = c.ls(selection=True, long=True) or []
        if not selected or any("." in item or c.nodeType(item)
                               != "transform" for item in selected):
            raise ValueError("批量 Control Mesh 需要选择已蒙皮网格对象")
        control_by_leaf = {}
        for control in controls:
            leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if leaf in control_by_leaf and control_by_leaf[leaf] != control:
                raise ValueError("已登记控制器短名称不唯一：" + leaf)
            control_by_leaf[leaf] = control
        sources = []
        for transform in selected:
            shapes = c.listRelatives(transform, shapes=True,
                                     fullPath=True,
                                     noIntermediate=True,
                                     type="mesh") or []
            if len(shapes) != 1:
                raise ValueError("所选对象缺少唯一多边形网格：" + transform)
            shape = shapes[0]
            mesh, dag = self._mesh(shape)
            clusters = tuple(dict.fromkeys(node for node in
                (c.listHistory(shape, pruneDagObjects=True) or [])
                if c.nodeType(node) == "skinCluster"))
            if len(clusters) != 1:
                raise ValueError("所选网格需要唯一 SkinCluster：" + transform)
            skin_node = self.om.MSelectionList().add(
                clusters[0]).getDependNode(0)
            skin = OpenMayaAnim.MFnSkinCluster(skin_node)
            influences = tuple(path.fullPathName()
                               for path in skin.influenceObjects())
            if not influences:
                raise ValueError("SkinCluster 没有影响关节：" + clusters[0])
            component = self.om.MFnSingleIndexedComponent().create(
                self.om.MFn.kMeshVertComponent)
            component_fn = self.om.MFnSingleIndexedComponent(component)
            component_fn.addElements(list(range(mesh.numVertices)))
            weights, influence_count = skin.getWeights(dag, component)
            if influence_count != len(influences):
                raise RuntimeError("SkinCluster 影响列表与权重数据不一致")
            groups: dict[str, list[int]] = {}
            for face in range(mesh.numPolygons):
                vertices = mesh.getPolygonVertices(face)
                sums = [sum(float(weights[vertex * influence_count + index])
                            for vertex in vertices
                            if weights[vertex * influence_count + index]
                            > 0.001)
                        for index in range(influence_count)]
                strongest = max(range(influence_count),
                                key=lambda index: sums[index])
                if sums[strongest] <= 0.0:
                    continue
                control = self._control_for_influence(
                    influences[strongest], control_by_leaf)
                if control:
                    groups.setdefault(control, []).append(face)
            for control, faces in groups.items():
                sources.append(ControlMeshSource(
                    shape, control, global_control,
                    tuple(faces), mesh.numPolygons))
        return tuple(sources)

    def existing_control_mesh_names(self) -> frozenset[str]:
        return frozenset(self.cmds.ls(long=False) or [])

    def preflight_control_mesh(self, item: ControlMeshItem) -> None:
        c = self.cmds
        if (not c.objExists(item.mesh_shape)
                or c.nodeType(item.mesh_shape) != "mesh"
                or not c.objExists(item.control)
                or c.nodeType(item.control) != "transform"
                or not c.objExists(item.global_control)
                or c.nodeType(item.global_control) != "transform"
                or c.objExists(item.shape_name)
                or c.objExists(item.transform_name)):
            raise ValueError("Control Mesh 来源、控制器或目标名称无效")
        mesh, _ = self._mesh(item.mesh_shape)
        if any(face >= mesh.numPolygons for face in item.faces):
            raise ValueError("Control Mesh 来源网格拓扑已变化")
        if len(c.listRelatives(item.mesh_shape, allParents=True,
                               fullPath=True) or []) != 1:
            raise ValueError("Control Mesh 来源网格不能是实例")
        if c.referenceQuery(item.control, isNodeReferenced=True):
            raise ValueError("Control Mesh 不能写入引用控制器")

    @contextmanager
    def transaction(self, label: str):
        c = self.cmds
        if self._in_transaction:
            raise RuntimeError("Control Mesh 不支持嵌套事务")
        if not c.undoInfo(query=True, state=True):
            raise ValueError("Control Mesh 需要开启 Maya Undo")
        self._in_transaction = True
        selected = c.ls(selection=True, long=True, flatten=True) or []
        c.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            c.undoInfo(closeChunk=True)
            c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)
        finally:
            self._in_transaction = False
            remaining = [name for name in selected if c.objExists(name)]
            if remaining:
                c.select(remaining, replace=True)
            else:
                c.select(clear=True)

    def _visibility(self, item: ControlMeshItem, shape: str) -> None:
        c = self.cmds
        for name in ("ctrlCurveVis", "ctrlMeshVis"):
            if not c.attributeQuery(name, node=item.global_control,
                                    exists=True):
                c.addAttr(item.global_control, longName=name,
                          attributeType="bool", defaultValue=True,
                          keyable=True)
                c.setAttr(item.global_control + "." + name,
                          keyable=False, channelBox=True)
        c.connectAttr(item.global_control + ".ctrlMeshVis",
                      shape + ".visibility", force=True)
        curves = c.listRelatives(item.control, shapes=True,
                                 fullPath=True,
                                 noIntermediate=True,
                                 type="nurbsCurve") or []
        for curve in curves:
            plug = curve + ".visibility"
            if (not c.connectionInfo(plug, isDestination=True)
                    and not c.getAttr(plug, lock=True)):
                c.connectAttr(item.global_control + ".ctrlCurveVis",
                              plug)

    def create_control_mesh(self, item: ControlMeshItem) -> None:
        if not self._in_transaction:
            raise RuntimeError("Control Mesh 创建必须位于事务内")
        c = self.cmds
        mesh, dag = self._mesh(item.mesh_shape)
        source_count = mesh.numPolygons
        shape = c.createNode("mesh", name=item.shape_name,
                             parent=item.control, skipSelect=True)
        c.setAttr(shape + ".isHistoricallyInteresting", 0)
        geometry = c.createNode("transformGeometry",
                                name=item.transform_name)
        c.setAttr(geometry + ".isHistoricallyInteresting", 0)
        c.setAttr(geometry + ".freezeNormals", True)
        c.connectAttr(item.control + ".worldInverseMatrix[0]",
                      geometry + ".transform")
        c.connectAttr(item.mesh_shape + ".worldMesh[0]",
                      geometry + ".inputGeometry")
        c.connectAttr(geometry + ".outputGeometry",
                      shape + ".inMesh")
        shaders, assignments = mesh.getConnectedShaders(
            dag.instanceNumber())
        for slot, shader in enumerate(shaders):
            engine = self.om.MFnDependencyNode(shader).name()
            members = [f"{shape}.f[{index}]"
                       for index, assigned in enumerate(assignments)
                       if int(assigned) == slot]
            for offset in range(0, len(members), 256):
                c.sets(members[offset:offset + 256], edit=True,
                       forceElement=engine)
        omitted = sorted(set(range(source_count)) - set(item.faces))
        if omitted:
            c.delete([f"{shape}.f[{face}]" for face in omitted])
        for attribute in ("castsShadows", "receiveShadows", "motionBlur",
                          "primaryVisibility", "smoothShading",
                          "visibleInReflections", "visibleInRefractions"):
            c.setAttr(shape + "." + attribute, False)
        self._visibility(item, shape)

    def capture_control_mesh(self, item: ControlMeshItem) -> bool:
        c = self.cmds
        shapes = c.ls(item.shape_name, long=True, type="mesh") or []
        if len(shapes) != 1:
            return False
        shape = shapes[0]
        parent = c.listRelatives(shape, parent=True, fullPath=True) or []
        if parent != [item.control]:
            return False
        geometry = item.transform_name
        if (not c.objExists(geometry)
                or c.nodeType(geometry) != "transformGeometry"
                or c.connectionInfo(shape + ".visibility",
                    sourceFromDestination=True)
                != item.global_control + ".ctrlMeshVis"
                or c.connectionInfo(geometry + ".inputGeometry",
                    sourceFromDestination=True)
                != item.mesh_shape + ".worldMesh[0]"
                or c.connectionInfo(geometry + ".transform",
                    sourceFromDestination=True)
                != item.control + ".worldInverseMatrix[0]"
                or int(c.polyEvaluate(shape, face=True)) != len(item.faces)):
            return False
        if self._face_content(shape, tuple(range(len(item.faces)))) != (
                self._face_content(item.mesh_shape, item.faces)):
            return False
        return all(not bool(c.getAttr(shape + "." + attribute))
                   for attribute in ("castsShadows", "receiveShadows",
                                     "motionBlur", "primaryVisibility",
                                     "smoothShading", "visibleInReflections",
                                     "visibleInRefractions"))

    def capture_control_mesh_color_sources(
        self, controls: tuple[str, ...],
    ) -> tuple[tuple[ControlMeshColorSource, ...], float]:
        c = self.cmds
        roots = [path for path in (c.ls(type="transform", long=True) or [])
                 if path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                 == "DeformationSystem"]
        namespaces = {control.rsplit("|", 1)[-1].rsplit(":", 1)[0]
                      if ":" in control.rsplit("|", 1)[-1] else ""
                      for control in controls}
        if len(namespaces) != 1:
            raise ValueError("Control Mesh 控制器跨越多个命名空间")
        namespace = namespaces.pop()
        roots = [path for path in roots
                 if ((path.rsplit("|", 1)[-1].rsplit(":", 1)[0]
                      if ":" in path.rsplit("|", 1)[-1] else "")
                     == namespace)]
        if len(roots) != 1:
            raise ValueError("Control Mesh 着色需要唯一 DeformationSystem")
        joints = c.listRelatives(roots[0], allDescendents=True,
                                 fullPath=True, type="joint") or []
        if not joints:
            raise ValueError("DeformationSystem 缺少变形关节")
        control_by_leaf = {}
        for control in controls:
            leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if leaf in control_by_leaf and control_by_leaf[leaf] != control:
                raise ValueError("控制器短名称不唯一：" + leaf)
            control_by_leaf[leaf] = control
        sources = []
        for joint in joints:
            control = self._control_for_influence(joint, control_by_leaf)
            if control is None:
                continue
            leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            shapes = c.listRelatives(control, shapes=True,
                                     fullPath=True,
                                     noIntermediate=True,
                                     type="mesh") or []
            for shape in shapes:
                shape_leaf = shape.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                if not re.fullmatch(re.escape(leaf) + r"MeshCtrl\d*",
                                    shape_leaf):
                    continue
                marker = shape + ".ControlMeshesExpanded"
                sources.append(ControlMeshColorSource(
                    joint, shape,
                    bool(c.getAttr(marker)) if c.objExists(marker)
                    else False))
        axis = 1 if c.upAxis(query=True, axis=True) == "y" else 2
        positions = [float(c.xform(joint, query=True, worldSpace=True,
                                   translation=True)[axis])
                     for joint in joints]
        height = max(positions) - min(positions)
        return tuple(sources), height

    def preflight_control_mesh_color(
        self, item: ControlMeshColorItem,
    ) -> None:
        c = self.cmds
        if (not c.objExists(item.mesh_shape)
                or c.nodeType(item.mesh_shape) != "mesh"
                or c.referenceQuery(item.mesh_shape,
                                    isNodeReferenced=True)):
            raise ValueError("Control Mesh 着色目标不存在或不可写")
        shader = item.shader.removesuffix("SG")
        if (c.objExists(shader)
                and c.nodeType(shader) != ("surfaceShader"
                    if shader == "asRedSS" else "lambert")):
            raise ValueError("原版颜色 Shader 名称被其他节点占用：" + shader)
        if c.objExists(item.shader) and c.nodeType(item.shader) != "shadingEngine":
            raise ValueError("原版颜色 ShadingGroup 名称被占用：" + item.shader)

    def ensure_control_mesh_shaders(self) -> None:
        if not self._in_transaction:
            raise RuntimeError("Control Mesh 着色必须位于事务内")
        c = self.cmds
        for group, rgb in SHADER_COLORS.items():
            shader = group.removesuffix("SG")
            if c.objExists(shader) and c.objExists(group):
                if (c.nodeType(shader) != ("surfaceShader"
                        if shader == "asRedSS" else "lambert")
                        or c.nodeType(group) != "shadingEngine"):
                    raise ValueError("原版颜色节点类型冲突：" + group)
                continue
            if c.objExists(shader) or c.objExists(group):
                raise ValueError("原版颜色节点仅创建了一半：" + group)
            kind = "surfaceShader" if shader == "asRedSS" else "lambert"
            c.shadingNode(kind, asShader=True, name=shader)
            c.sets(renderable=True, noSurfaceShader=True,
                   empty=True, name=group)
            c.connectAttr(shader + ".outColor",
                          group + ".surfaceShader", force=True)
            color_plug = (".outColor" if shader == "asRedSS"
                          else ".color")
            c.setAttr(shader + color_plug, *rgb, type="float3")

    def colorize_control_mesh(self, item: ControlMeshColorItem) -> None:
        if not self._in_transaction:
            raise RuntimeError("Control Mesh 着色必须位于事务内")
        c = self.cmds
        c.sets(item.mesh_shape, edit=True, forceElement=item.shader)
        if not item.already_expanded:
            mesh, _ = self._mesh(item.mesh_shape)
            if mesh.numVertices < 1:
                raise ValueError("Control Mesh 没有可扩展的顶点")
            c.moveVertexAlongDirection(
                f"{item.mesh_shape}.vtx[0:{mesh.numVertices - 1}]",
                normalDirection=item.expand_distance)
            c.addAttr(item.mesh_shape, longName="ControlMeshesExpanded",
                      attributeType="bool", defaultValue=True,
                      keyable=False)

    def capture_control_mesh_color(
        self, item: ControlMeshColorItem,
    ) -> bool:
        c = self.cmds
        if not (c.objExists(item.mesh_shape)
                and c.objExists(item.mesh_shape
                                + ".ControlMeshesExpanded")
                and bool(c.getAttr(item.mesh_shape
                                   + ".ControlMeshesExpanded"))):
            return False
        mesh, dag = self._mesh(item.mesh_shape)
        shaders, assignments = mesh.getConnectedShaders(
            dag.instanceNumber())
        materials = tuple(self.om.MFnDependencyNode(shader).name()
                          for shader in shaders)
        return (mesh.numPolygons > 0
                and all(0 <= int(slot) < len(materials)
                        and materials[int(slot)] == item.shader
                        for slot in assignments))
