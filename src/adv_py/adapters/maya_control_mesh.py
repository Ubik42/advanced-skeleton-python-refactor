"""Maya host for live, selected-face Control Mesh shapes."""
from __future__ import annotations

from contextlib import contextmanager

from adv_py.core.control_mesh import ControlMeshItem, ControlMeshSource


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
