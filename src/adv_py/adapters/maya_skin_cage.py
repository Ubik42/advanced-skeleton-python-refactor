"""Maya implementation of the original SkinCage copy/delete/reuse actions."""
from __future__ import annotations

from contextlib import contextmanager

from adv_py.core.skin_cage import SKIN_CAGE_NODES, SkinCageCopyTarget


class MayaSkinCageHost:
    def __init__(self, namespace: str = "") -> None:
        from maya import cmds
        self.cmds = cmds
        self.namespace = namespace.strip(":")
        self._source_skin = ""
        self._source_mesh = ""
        self._influences: tuple[str, ...] = ()
        self._selection: tuple[str, ...] = ()

    def _name(self, leaf: str) -> str:
        return self.namespace + ":" + leaf if self.namespace else leaf

    @contextmanager
    def transaction(self, label: str):
        c = self.cmds
        c.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        finally:
            c.undoInfo(closeChunk=True)

    def _skin(self, mesh: str) -> str:
        c = self.cmds
        skins = [node for node in c.listHistory(mesh, pruneDagObjects=True) or ()
                 if c.nodeType(node) == "skinCluster"]
        if len(skins) > 1:
            raise ValueError("网格存在多个 skinCluster，请先明确变形链：" + mesh)
        return skins[0] if skins else ""

    def _mesh(self, node: str) -> str:
        c = self.cmds
        shape = node.split(".", 1)[0]
        if c.nodeType(shape) == "mesh":
            parents = c.listRelatives(shape, parent=True, fullPath=True) or []
            if len(parents) != 1:
                raise ValueError("网格 Shape 没有唯一父节点：" + shape)
            return parents[0]
        if c.nodeType(shape) != "transform" or not c.listRelatives(
                shape, shapes=True, noIntermediate=True, type="mesh"):
            raise ValueError("选择项不是多边形网格：" + node)
        return (c.ls(shape, long=True) or [shape])[0]

    def capture_copy_input(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        c = self.cmds
        self._selection = tuple(c.ls(selection=True, flatten=True, long=True) or ())
        if not self._selection:
            raise ValueError("请选择要复制 SkinCage 权重的网格或顶点")
        components = tuple(item for item in self._selection if "." in item)
        if components and len(components) != len(self._selection):
            raise ValueError("请只选择网格对象，或只选择同一网格的顶点")
        if components and any(".vtx[" not in item for item in components):
            raise ValueError("组件复制目前只接受网格顶点")
        meshes = tuple(dict.fromkeys(self._mesh(item) for item in self._selection))
        return meshes, components

    def preflight_copy(self, targets: tuple[SkinCageCopyTarget, ...]) -> None:
        c = self.cmds
        self._source_mesh = self._name("skinCage")
        self._source_skin = self._name("skinClusterSkinCage")
        if not c.objExists(self._source_mesh) or not c.objExists(self._source_skin):
            raise ValueError("当前角色没有完整 SkinCage；需先创建笼体")
        if self._skin(self._source_mesh) != self._source_skin:
            raise ValueError("SkinCage 的蒙皮连接与原版结构不一致")
        self._influences = tuple(c.skinCluster(
            self._source_skin, query=True, influence=True) or ())
        if not self._influences:
            raise ValueError("SkinCage 蒙皮没有变形关节")
        for target in targets:
            if target.mesh == (c.ls(self._source_mesh, long=True) or [""])[0]:
                raise ValueError("不能把 SkinCage 权重复制回笼体本身")
            self._skin(target.mesh)

    def copy_weights(self, target: SkinCageCopyTarget) -> None:
        c = self.cmds
        skin = self._skin(target.mesh)
        if skin:
            current = set(c.skinCluster(skin, query=True, influence=True) or ())
            for joint in self._influences:
                if joint not in current:
                    c.skinCluster(skin, edit=True, addInfluence=joint,
                                  weight=0.0, lockWeights=False)
        else:
            skin = c.skinCluster(list(self._influences), target.mesh,
                                 toSelectedBones=True, maximumInfluences=3,
                                 dropoffRate=4.0)[0]
        try:
            c.select(self._source_mesh, replace=True)
            c.select(list(target.components) if target.components else
                     target.mesh, add=True)
            c.copySkinWeights(noMirror=True,
                              surfaceAssociation="closestPoint",
                              influenceAssociation="closestJoint")
            c.setAttr(skin + ".skinningMethod",
                      c.getAttr(self._source_skin + ".skinningMethod"))
            c.skinCluster(skin, edit=True, removeUnusedInfluence=True)
        finally:
            c.select(list(self._selection), replace=True)

    def capture_copy(self, target: SkinCageCopyTarget) -> bool:
        return bool(self._skin(target.mesh))

    def delete_cage(self) -> tuple[str, ...]:
        c = self.cmds
        existing = tuple(self._name(leaf) for leaf in SKIN_CAGE_NODES
                         if c.objExists(self._name(leaf)))
        if existing:
            c.delete(list(existing))
        if any(c.objExists(node) for node in existing):
            raise RuntimeError("SkinCage 删除后仍有残留节点")
        return existing

    def print_reuse_commands(self, *, transforms: bool = True,
                             shapes: bool = True, catch: bool = False) -> int:
        c = self.cmds
        root = self._name("MeshCurves")
        if not c.objExists(root):
            raise ValueError("当前角色没有 MeshCurves")
        commands = []
        if transforms:
            for constraint in c.listRelatives(
                    root, allDescendents=True, type="constraint",
                    fullPath=True) or ():
                for attr in c.listAttr(constraint, userDefined=True) or ():
                    value = c.getAttr(constraint + "." + attr)
                    if isinstance(value, (int, float)):
                        commands.append(f"setAttr {constraint}.{attr} {value}")
        for curve in c.listRelatives(root, allDescendents=True,
                                     type="transform", fullPath=True) or ():
            shape = c.listRelatives(curve, shapes=True,
                                    noIntermediate=True, type="nurbsCurve") or []
            if not shape or not c.getAttr(curve + ".visibility"):
                continue
            if transforms:
                pos = c.xform(curve, query=True, objectSpace=True,
                              translation=True)
                rot = c.xform(curve, query=True, objectSpace=True,
                              rotation=True)
                scale = c.xform(curve, query=True, objectSpace=True,
                                scale=True)
                commands.append("xform -os -t {} {} {} -ro {} {} {} -s {} {} {} {}".format(
                    *pos, *rot, *scale, curve))
            if shapes:
                count = int(c.getAttr(shape[0] + ".spans")) + int(
                    c.getAttr(shape[0] + ".degree"))
                for index in range(count):
                    xyz = c.getAttr(f"{shape[0]}.controlPoints[{index}]")[0]
                    if any(xyz):
                        commands.append("setAttr {}.controlPoints[{}] {} {} {}".format(
                            shape[0], index, *xyz))
        for command in commands:
            print("catch (`" + command + "`);" if catch
                  else command + ";")
        return len(commands)
