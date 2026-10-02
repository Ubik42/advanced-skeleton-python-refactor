"""Maya host for live, selected-face Control Mesh shapes."""
from __future__ import annotations

from contextlib import contextmanager
import re

from adv_py.core.control_mesh import ControlMeshItem, ControlMeshSource
from adv_py.core.control_mesh_color import (
    ControlMeshColorItem, ControlMeshColorSource, SHADER_COLORS,
)
from adv_py.core.ik_control_mesh import IKControlCurve, IKControlMeshItem
from adv_py.core.control_mesh_delete import (
    ControlMeshDeleteItem, ControlMeshDeleteSource,
)


class MayaControlMeshHost:
    def __init__(self, namespace: str = '') -> None:
        from maya import cmds
        from maya.api import OpenMaya

        self.cmds = cmds
        self.om = OpenMaya
        self._in_transaction = False
        self.namespace=namespace.strip(':')

    def _capture_namespace(self, global_control):
        leaf=global_control.rsplit('|',1)[-1]
        self.namespace=leaf.rsplit(':',1)[0] if ':' in leaf else ''

    def _mesh(self, shape: str):
        path = self.om.MSelectionList().add(shape).getDagPath(0)
        return self.om.MFnMesh(path), path

    def _face_content(self, shape: str, faces: tuple[int, ...], *, object_space=False):
        mesh, dag = self._mesh(shape)
        points = mesh.getPoints(self.om.MSpace.kObject if object_space else self.om.MSpace.kWorld)
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

    def _mirror_faces(self, shape: str, faces: tuple[int, ...], control: str) -> tuple[int, ...]:
        c=self.cmds
        # The source samples world X-reflected positions against outMesh,
        # including ConvertSelectionToVertices' treatment of the last control.
        converted=c.polyListComponentConversion(
            [shape+f'.f[{face}]' for face in faces]+[control],toVertex=True)
        vertices=c.ls(converted,flatten=True) or []
        enabled=bool(c.undoInfo(query=True,state=True))
        sampler=None
        c.undoInfo(stateWithoutFlush=False)
        try:
            sampler=c.createNode('closestPointOnMesh',name='AdvPy_ControlMeshClosestSampler',skipSelect=True)
            c.connectAttr(shape+'.outMesh',sampler+'.inMesh')
            mirrored=set()
            for vertex in vertices:
                point=c.xform(vertex,query=True,worldSpace=True,translation=True)
                c.setAttr(sampler+'.inPosition',-point[0],point[1],point[2],type='float3')
                mirrored.add(int(c.getAttr(sampler+'.closestVertexIndex')))
        finally:
            if sampler and c.objExists(sampler):c.delete(sampler)
            c.undoInfo(stateWithoutFlush=enabled)
        mesh,_=self._mesh(shape)
        return tuple(face for face in range(mesh.numPolygons)
                     if set(mesh.getPolygonVertices(face))<=mirrored)

    def capture_control_mesh_source(
        self, global_control: str, mirror: bool,
    ) -> ControlMeshSource:
        c = self.cmds
        self._capture_namespace(global_control)
        selected = c.ls(selection=True, flatten=True, long=True) or []
        if len(selected) < 2 or "." in selected[-1]:
            raise ValueError("请先选一件网格的面，最后选择目标控制器")
        control = selected[-1]
        if c.nodeType(control) not in ('transform','joint'):
            raise ValueError("最后选择的对象必须是控制器 Transform 或 Joint")
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
        if mirror:
            other_leaf = leaf[:-2] + ('_R' if leaf.endswith('_L') else '_L')
            # Registered Python controls carry physical FK names; translate
            # their identity to the same source left/right FK role first.
            from .maya_geometry_cut_up import MayaGeometryCutUpHost
            from .maya_geometry_control_mapping import SourceGeometryControlMapping
            mapping=SourceGeometryControlMapping(MayaGeometryCutUpHost(self.namespace))
            for joint,fk in mapping.bindings.items():
                if fk.rsplit('|',1)[-1]==leaf and joint.endswith(('_R','_L')):
                    other_joint=joint[:-1]+('L' if joint.endswith('_R') else 'R')
                    other_leaf=mapping.fk(other_joint) or other_leaf
                    break
            matches = [node for node in c.ls(other_leaf,long=True) or []
                       if c.nodeType(node) in ('transform','joint')]
            if len(matches) == 1:
                opposite = matches[0]
                mirror_faces = self._mirror_faces(shape, faces, control)
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
        from .maya_geometry_cut_up import MayaGeometryCutUpHost
        from adv_py.core.geometry_cut_up import plan_cut_up_mesh
        c=self.cmds
        self._capture_namespace(global_control)
        leaf=global_control.rsplit('|',1)[-1]
        namespace=leaf.rsplit(':',1)[0] if ':' in leaf else ''
        host=MayaGeometryCutUpHost(namespace)
        sources=[]
        for row in host.capture_cut_up_inputs(cut_up=False):
            plan=plan_cut_up_mesh(*row)
            shape=c.listRelatives(plan.mesh,shapes=True,noIntermediate=True,type='mesh',fullPath=True)[0]
            for piece in plan.pieces:
                control=c.ls(piece.joint,long=True)[0]
                sources.append(ControlMeshSource(shape,control,global_control,piece.faces,plan.face_count))
        return tuple(sources)

    def existing_control_mesh_names(self) -> frozenset[str]:
        return frozenset(self.cmds.ls(long=False) or [])

    def preflight_control_mesh(self, item: ControlMeshItem) -> None:
        c = self.cmds
        if (not c.objExists(item.mesh_shape)
                or c.nodeType(item.mesh_shape) != "mesh"
                or not c.objExists(item.control)
                or c.nodeType(item.control) not in ('transform','joint')
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
            from .maya_fit_geometry import MayaFitGeometryHost
            with MayaFitGeometryHost(self.namespace).namespace_scope():
                yield
                remaining = [name for name in selected if c.objExists(name)]
                if remaining:c.select(remaining,replace=True)
                else:c.select(clear=True)
        except Exception:
            c.undoInfo(closeChunk=True)
            c.undo()
            raise
        else:
            c.undoInfo(closeChunk=True)
        finally:
            self._in_transaction = False

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
        for curve in curves[:1]:
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
        c.connectAttr(item.mesh_shape + ".outMesh",
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
        else:
            c.delete(shape+'.f[0]')
            deletion=c.listConnections(shape+'.inMesh',source=True,destination=False)[0]
            c.setAttr(deletion+'.nodeState',1)
        deletion=c.listConnections(shape+'.inMesh',source=True,destination=False)[0]
        c.rename(deletion,item.control.rsplit('|',1)[-1]+'MCDeleteComponent')
        control_leaf=item.control.rsplit('|',1)[-1]
        namespace=control_leaf.rsplit(':',1)[0]+':' if ':' in control_leaf else ''
        face_set=namespace+'FaceControlSet'
        if c.objExists(face_set) and c.sets(item.control,isMember=face_set) and control_leaf.endswith('_R'):
            normals=c.polyNormal(shape,normalMode=0,userNormalMode=0,constructionHistory=False) or []
            if normals and c.objExists(normals[0]):
                normal=c.rename(normals[0],control_leaf+'MCDeleteComponent')
                c.setAttr(normal+'.isHistoricallyInteresting',0)
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
        def same_source(destination, expected):
            actual=c.connectionInfo(destination,sourceFromDestination=True)
            if not actual:return False
            node,attribute=actual.split('.',1);wanted,wanted_attribute=expected.split('.',1)
            return attribute==wanted_attribute and c.ls(node,long=True)==c.ls(wanted,long=True)
        if (not c.objExists(geometry)
                or c.nodeType(geometry) != "transformGeometry"
                or not same_source(shape+'.visibility',item.global_control+'.ctrlMeshVis')
                or not same_source(geometry+'.inputGeometry',item.mesh_shape+'.outMesh')
                or not same_source(geometry+'.transform',item.control+'.worldInverseMatrix[0]')
                or int(c.polyEvaluate(shape, face=True)) != len(item.faces)):
            return False
        # transformGeometry uses float mesh storage. Validate the source faces
        # with a geometric tolerance instead of exact rounded tuple ordering.
        remaining=list(self._face_content(shape,tuple(range(len(item.faces)))))
        for vertices,material in self._face_content(item.mesh_shape,item.faces,object_space=True):
            match=None
            for index,(other,assigned) in enumerate(remaining):
                if assigned!=material or len(vertices)!=len(other):continue
                unmatched=list(other)
                for point in vertices:
                    nearest=min(range(len(unmatched)),key=lambda i:sum((a-b)**2 for a,b in zip(point,unmatched[i])))
                    if max(abs(a-b) for a,b in zip(point,unmatched[nearest]))>1e-5:break
                    unmatched.pop(nearest)
                else:match=index;break
            if match is None:return False
            remaining.pop(match)
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

    def capture_ik_control_curves(
        self, global_control: str,
    ) -> tuple[tuple[IKControlCurve, ...], float]:
        c = self.cmds
        if not c.objExists(global_control) or c.nodeType(global_control) != "transform":
            raise ValueError("IK Control Mesh 缺少角色总控")
        leaf = global_control.rsplit("|", 1)[-1]
        prefix = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
        sets = c.ls(prefix + "ControlSet", type="objectSet") or []
        if len(sets) != 1:
            raise ValueError("IK Control Mesh 需要唯一 ControlSet")
        members = c.sets(sets[0], query=True) or []
        sources = []
        for member in members:
            matches = c.ls(member, long=True, type="transform") or []
            if len(matches) != 1:
                raise ValueError("ControlSet 控制器不存在或名称不唯一：" + member)
            control = matches[0]
            name = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if ((name.startswith("FK") and not name.startswith("FKIK"))
                    or ("FK_" in name and "FKIK" not in name)
                    or name.endswith("FK")):
                continue
            for curve in c.listRelatives(
                    control, shapes=True, fullPath=True,
                    noIntermediate=True, type="nurbsCurve") or []:
                form = int(c.getAttr(curve + ".form"))
                spans = int(c.getAttr(curve + ".spans"))
                cv_count = (spans if form == 2 else
                            int(c.getAttr(curve + ".controlPoints", size=True)))
                if cv_count < 2:
                    continue
                points = tuple(tuple(float(value) for value in
                                     c.pointPosition(f"{curve}.cv[{index}]",
                                                     world=True))
                               for index in range(cv_count))
                plug = curve + ".visibility"
                previous = c.connectionInfo(
                    plug, sourceFromDestination=True) or None
                sources.append(IKControlCurve(
                    control, curve, global_control, points,
                    form == 2, int(c.getAttr(curve + ".overrideColor")),
                    previous))
        fit = c.ls(prefix + "FitSkeleton", type="transform") or []
        scale = 1.0
        if len(fit) > 1:
            raise ValueError("IK Control Mesh 的 FitSkeleton 名称不唯一")
        if fit:
            joints = c.listRelatives(fit[0], allDescendents=True,
                                     fullPath=True, type="joint") or []
            max_y = max((float(c.xform(joint, query=True,
                                        worldSpace=True, translation=True)[1])
                         for joint in joints), default=0.0)
            if max_y > 0.0:
                scale = max(max_y / 17.176163, 0.01)
        return tuple(sources), scale

    def preflight_ik_control_mesh(self, item: IKControlMeshItem) -> None:
        c = self.cmds
        if (not c.objExists(item.control)
                or not c.objExists(item.curve)
                or not c.objExists(item.global_control)
                or c.objExists(item.shape_name)
                or (item.visibility_source and
                    (c.objExists(item.shape_name + "CurveMPD") or
                     c.objExists(item.shape_name + "MeshMPD")))
                or c.referenceQuery(item.control, isNodeReferenced=True)
                or c.getAttr(item.curve + ".visibility", lock=True)):
            raise ValueError("IK Control Mesh 控制器、曲线或目标名称不可用")
        parents = c.listRelatives(item.curve, allParents=True,
                                  fullPath=True) or []
        if parents != [item.control]:
            raise ValueError("IK Control Mesh 曲线必须直属目标控制器且不能实例化")
        for name in ("ctrlCurveVis", "ctrlMeshVis"):
            if c.attributeQuery(name, node=item.global_control, exists=True):
                if c.getAttr(item.global_control + "." + name, type=True) != "bool":
                    raise ValueError("角色总控可见性属性类型错误：" + name)

    def create_ik_control_mesh(self, item: IKControlMeshItem) -> None:
        if not self._in_transaction:
            raise RuntimeError("IK Control Mesh 创建必须位于事务内")
        c = self.cmds
        om = self.om
        for name in ("ctrlCurveVis", "ctrlMeshVis"):
            if not c.attributeQuery(name, node=item.global_control, exists=True):
                c.addAttr(item.global_control, longName=name,
                          attributeType="bool", defaultValue=True,
                          keyable=True)
                c.setAttr(item.global_control + "." + name,
                          keyable=False, channelBox=True)
        matrix_values = c.getAttr(item.control + ".worldInverseMatrix[0]")[0]
        inverse = om.MMatrix(matrix_values)
        points = [om.MPoint(*vertex) * inverse for vertex in item.vertices]
        counts = [len(face) for face in item.faces]
        indices = [index for face in item.faces for index in face]
        parent = om.MSelectionList().add(item.control).getDependNode(0)
        mesh_object = om.MFnMesh().create(points, counts, indices,
                                          parent=parent)
        shape = om.MFnDagNode(mesh_object).fullPathName()
        shape = c.rename(shape, item.shape_name)
        for attribute in ("castsShadows", "receiveShadows", "motionBlur",
                          "primaryVisibility", "smoothShading",
                          "visibleInReflections", "visibleInRefractions"):
            c.setAttr(shape + "." + attribute, False)
        c.sets(shape, edit=True,
               forceElement=item.shader or "initialShadingGroup")
        if item.visibility_source:
            curve_mpd = c.createNode("multiplyDivide",
                                     name=item.shape_name + "CurveMPD")
            mesh_mpd = c.createNode("multiplyDivide",
                                    name=item.shape_name + "MeshMPD")
            c.connectAttr(item.visibility_source,
                          curve_mpd + ".input1X")
            c.connectAttr(item.visibility_source,
                          mesh_mpd + ".input1X")
            c.connectAttr(item.global_control + ".ctrlCurveVis",
                          curve_mpd + ".input2X")
            c.connectAttr(item.global_control + ".ctrlMeshVis",
                          mesh_mpd + ".input2X")
            c.connectAttr(curve_mpd + ".outputX",
                          item.curve + ".visibility", force=True)
            c.connectAttr(mesh_mpd + ".outputX",
                          shape + ".visibility", force=True)
        else:
            c.connectAttr(item.global_control + ".ctrlCurveVis",
                          item.curve + ".visibility", force=True)
            c.connectAttr(item.global_control + ".ctrlMeshVis",
                          shape + ".visibility", force=True)

    def capture_ik_control_mesh(self, item: IKControlMeshItem) -> bool:
        c = self.cmds
        matches = c.ls(item.shape_name, long=True, type="mesh") or []
        if len(matches) != 1:
            return False
        shape = matches[0]
        if ((c.listRelatives(shape, parent=True, fullPath=True) or [])
                != [item.control]
                or int(c.polyEvaluate(shape, face=True)) != len(item.faces)):
            return False
        curve_vis = (item.shape_name + "CurveMPD.outputX"
                     if item.visibility_source else
                     item.global_control + ".ctrlCurveVis")
        mesh_vis = (item.shape_name + "MeshMPD.outputX"
                    if item.visibility_source else
                    item.global_control + ".ctrlMeshVis")
        if (c.connectionInfo(item.curve + ".visibility",
                             sourceFromDestination=True) != curve_vis
                or c.connectionInfo(shape + ".visibility",
                                    sourceFromDestination=True) != mesh_vis):
            return False
        if item.visibility_source:
            for suffix in ("Curve", "Mesh"):
                node = item.shape_name + suffix + "MPD"
                if (not c.objExists(node)
                        or c.nodeType(node) != "multiplyDivide"
                        or c.connectionInfo(node + ".input1X",
                            sourceFromDestination=True)
                        != item.visibility_source):
                    return False
        mesh, dag = self._mesh(shape)
        shaders, assignments = mesh.getConnectedShaders(dag.instanceNumber())
        expected_shader = item.shader or "initialShadingGroup"
        materials = tuple(self.om.MFnDependencyNode(shader).name()
                          for shader in shaders)
        return (all(0 <= int(slot) < len(materials)
                    and materials[int(slot)] == expected_shader
                    for slot in assignments)
                and all(not bool(c.getAttr(shape + "." + attribute))
                        for attribute in ("castsShadows", "receiveShadows",
                                          "motionBlur", "primaryVisibility",
                                          "smoothShading", "visibleInReflections",
                                          "visibleInRefractions")))

    def capture_control_mesh_delete_sources(
        self, global_control: str, selected_only: bool,
    ) -> tuple[ControlMeshDeleteSource, ...]:
        c = self.cmds
        leaf = global_control.rsplit("|", 1)[-1]
        prefix = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
        control_sets = c.ls(prefix + "ControlSet", type="objectSet") or []
        if len(control_sets) != 1:
            raise ValueError("Control Mesh 删除需要唯一 ControlSet")
        members = c.sets(control_sets[0], query=True) or []
        controls = []
        for member in members:
            matches = c.ls(member, long=True, type="transform") or []
            if len(matches) != 1:
                raise ValueError("ControlSet 控制器不唯一：" + member)
            controls.append(matches[0])
        if selected_only:
            selection = c.ls(selection=True, long=True, objectsOnly=True) or []
            if not selection:
                raise ValueError("请先选择要删除 Control Mesh 的控制器")
            foreign = set(selection) - set(controls)
            if foreign:
                raise ValueError("所选对象不属于当前角色 ControlSet")
            controls = [control for control in controls if control in selection]
        sources = []
        for control in controls:
            control_leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            shapes = tuple(shape for shape in (
                c.listRelatives(control, shapes=True, fullPath=True,
                                noIntermediate=True, type="mesh") or [])
                if re.fullmatch(re.escape(control_leaf) + r"MeshCtrl\d*",
                                shape.rsplit("|", 1)[-1].rsplit(":", 1)[-1]))
            if not shapes:
                continue
            helpers = set()
            for shape in shapes:
                name = shape.rsplit("|", 1)[-1]
                for suffix in ("CurveMPD", "MeshMPD"):
                    candidate = name + suffix
                    if c.objExists(candidate):
                        if c.nodeType(candidate) != "multiplyDivide":
                            raise ValueError("Control Mesh 辅助节点类型冲突：" + candidate)
                        helpers.add(candidate)
                upstream = c.connectionInfo(
                    shape + ".inMesh", sourceFromDestination=True)
                if upstream:
                    node = upstream.split(".", 1)[0]
                    expected = control.rsplit("|", 1)[-1] + "MCTransformGeometry"
                    if (c.nodeType(node) == "transformGeometry"
                            and node.rsplit(":", 1)[-1].startswith(
                                expected.rsplit(":", 1)[-1])):
                        helpers.add(node)
            visibility = []
            for curve in c.listRelatives(
                    control, shapes=True, fullPath=True,
                    noIntermediate=True, type="nurbsCurve") or []:
                source = c.connectionInfo(
                    curve + ".visibility", sourceFromDestination=True)
                if not source:
                    continue
                initial = source
                visited = set()
                while source and source.split(".", 1)[0] in helpers:
                    node = source.split(".", 1)[0]
                    if node in visited or not node.endswith("CurveMPD"):
                        raise ValueError("Control Mesh 曲线显隐连接存在循环或冲突")
                    visited.add(node)
                    source = c.connectionInfo(
                        node + ".input1X", sourceFromDestination=True)
                if visited:
                    visibility.append((curve, source or None))
                elif initial == global_control + ".ctrlCurveVis":
                    visibility.append((curve, None))
            sources.append(ControlMeshDeleteSource(
                control, shapes, tuple(sorted(helpers)), tuple(visibility)))
        return tuple(sources)

    def preflight_control_mesh_deletion(
        self, item: ControlMeshDeleteItem,
    ) -> None:
        c = self.cmds
        for node in (item.control,) + item.shapes + item.helpers:
            if (not c.objExists(node)
                    or c.referenceQuery(node, isNodeReferenced=True)):
                raise ValueError("Control Mesh 删除目标不存在或处于引用中：" + node)
        for curve, source in item.curve_visibility:
            if (not c.objExists(curve)
                    or c.getAttr(curve + ".visibility", lock=True)
                    or (source is not None and not c.objExists(
                        source.split(".", 1)[0]))):
                raise ValueError("Control Mesh 曲线显隐无法恢复：" + curve)

    def delete_control_meshes(self, item: ControlMeshDeleteItem) -> None:
        if not self._in_transaction:
            raise RuntimeError("Control Mesh 删除必须位于事务内")
        c = self.cmds
        for curve, source in item.curve_visibility:
            plug = curve + ".visibility"
            if source:
                c.connectAttr(source, plug, force=True)
            else:
                incoming = c.connectionInfo(plug, sourceFromDestination=True)
                if incoming:
                    c.disconnectAttr(incoming, plug)
                c.setAttr(plug, True)
        c.delete(list(item.shapes))
        if item.helpers:
            c.delete(list(item.helpers))

    def capture_control_mesh_deletion(
        self, item: ControlMeshDeleteItem,
    ) -> bool:
        c = self.cmds
        if any(c.objExists(node) for node in item.shapes + item.helpers):
            return False
        return all((c.connectionInfo(
            curve + ".visibility", sourceFromDestination=True) or None)
                   == source for curve, source in item.curve_visibility)
