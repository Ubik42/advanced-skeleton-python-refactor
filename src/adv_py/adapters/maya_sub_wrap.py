"""Maya SubWrap cage, wrap deformers, attachment and component sets."""
from __future__ import annotations

from contextlib import contextmanager

from .maya_skin_cage import MayaSkinCageHost


_WRAP_ATTRS = ("falloffMode", "exclusiveBind", "autoWeightThreshold",
               "weightThreshold", "maxDistance")
_WRAP_DEFAULTS = (0, 0, 1, 0, 0)


class MayaSubWrapHost(MayaSkinCageHost):
    def _shape(self, mesh: str) -> str:
        shapes = self.cmds.listRelatives(
            mesh, shapes=True, noIntermediate=True, fullPath=True,
            type="mesh") or []
        if len(shapes) != 1:
            raise ValueError("SubWrap 需要唯一的多边形网格 Shape：" + mesh)
        return shapes[0]

    def _wraps(self, mesh: str) -> tuple[str, ...]:
        c = self.cmds
        return tuple(node for node in (c.listHistory(
            mesh, pruneDagObjects=True) or ()) if c.nodeType(node) == "wrap")

    def preflight_cage(self, *, creating: bool) -> None:
        c = self.cmds
        for leaf in ("skinCage", "Geometry"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("SubWrap 缺少原版节点：" + leaf)
        present = c.objExists(self._name("skinSub"))
        if creating and present:
            raise ValueError("SubWrap 笼体已存在")
        if not creating and not present:
            raise ValueError("SubWrap 笼体不存在")
        if creating:
            for leaf in ("subWrapPolySmoothProxy", "SkinSub"):
                if c.objExists(self._name(leaf)):
                    raise ValueError("SubWrap 有残留节点：" + leaf)

    def create_cage(self) -> None:
        c = self.cmds
        cages = self._name("Cages")
        if not c.objExists(cages):
            cages = c.createNode("transform", name=cages,
                                 parent=self._name("Geometry"),
                                 skipSelect=True)
        proxy = c.createNode("polySmoothProxy", name=self._name(
            "subWrapPolySmoothProxy"))
        sub = c.polyCube(name=self._name("skinSub"), width=1, height=1,
                         depth=1, subdivisionsX=1, subdivisionsY=1,
                         subdivisionsZ=1, constructionHistory=False)[0]
        sub = c.parent(sub, cages)[0]
        c.connectAttr(self._shape(self._name("skinCage")) + ".outMesh",
                      proxy + ".inputPolymesh", force=True)
        c.connectAttr(proxy + ".output", self._shape(sub) + ".inMesh",
                      force=True)
        layer = c.createDisplayLayer(empty=True, name=self._name("SkinSub"))
        c.editDisplayLayerMembers(layer, sub)
        c.setAttr(layer + ".displayType", 2)
        c.setAttr(layer + ".color", 30)
        original = self._name("SkinCage")
        if c.objExists(original):
            c.setAttr(original + ".displayType", 1)

    def delete_cage(self) -> None:
        c = self.cmds
        if self._sub_wrap_nodes():
            self.detach_all()
        for leaf in ("skinSub", "SkinSub", "subWrapPolySmoothProxy"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)

    def cage_present(self) -> bool:
        c = self.cmds
        sub = self._name("skinSub")
        proxy = self._name("subWrapPolySmoothProxy")
        layer = self._name("SkinSub")
        if not c.objExists(sub):
            return False
        shape = self._shape(sub)
        return (c.objExists(proxy) and c.objExists(layer)
                and c.isConnected(proxy + ".output", shape + ".inMesh"))

    def selected_meshes(self) -> tuple[str, ...]:
        c = self.cmds
        selection = c.ls(selection=True, long=True) or []
        return tuple(dict.fromkeys(self._mesh(node) for node in selection))

    def preflight_wrap(self, meshes: tuple[str, ...]) -> None:
        c = self.cmds
        for leaf in ("skinSub", "Main"):
            if not c.objExists(self._name(leaf)):
                raise ValueError("SubWrap 包裹缺少原版节点：" + leaf)
        for mesh in meshes:
            self._shape(mesh)
            if self._wraps(mesh):
                raise ValueError("网格已有 Wrap 变形器：" + mesh)

    @contextmanager
    def _legacy_component_sets(self):
        c = self.cmds
        key = "deformationUseComponentTags"
        exists = c.optionVar(exists=key)
        old = c.optionVar(query=key) if exists else None
        if old:
            c.optionVar(intValue=(key, 0))
        try:
            yield
        finally:
            if old:
                c.optionVar(intValue=(key, old))

    def _reverse_visibility(self) -> str:
        c = self.cmds
        main = self._name("Main")
        if not c.attributeQuery("wrapDeform", node=main, exists=True):
            c.addAttr(main, longName="wrapDeform", attributeType="bool",
                      defaultValue=True, keyable=True)
        reverse = self._name("wrapDeformReverse")
        if not c.objExists(reverse):
            reverse = c.createNode("reverse", name=reverse)
        if not c.isConnected(main + ".wrapDeform", reverse + ".inputX"):
            c.connectAttr(main + ".wrapDeform", reverse + ".inputX",
                          force=True)
        return reverse

    def _next_wrap_name(self) -> str:
        index = 1
        while self.cmds.objExists(self._name(f"subWrap{index}")):
            index += 1
        return self._name(f"subWrap{index}")

    def wrap_mesh(self, mesh: str) -> None:
        from maya import mel

        c = self.cmds
        before = set(self._wraps(mesh))
        original = c.ls(selection=True, long=True) or []
        try:
            with self._legacy_component_sets():
                c.select(mesh, replace=True)
                c.select(self._name("skinSub"), add=True)
                mel.eval('doWrapArgList 7 { "1","0","1", "2", "1", "1", "1", "0" }')
        finally:
            c.select(original, replace=True) if original else c.select(clear=True)
        created = [node for node in self._wraps(mesh) if node not in before]
        if len(created) != 1:
            raise RuntimeError("Maya 未为网格创建唯一 Wrap：" + mesh)
        wrap = c.rename(created[0], self._next_wrap_name())
        reverse = self._reverse_visibility()
        for attr, default in zip(_WRAP_ATTRS, _WRAP_DEFAULTS):
            value = (c.getAttr(mesh + "." + attr) if c.attributeQuery(
                attr, node=mesh, exists=True) else default)
            c.setAttr(wrap + "." + attr, value)
        for attr, value in (("dropoff", 4), ("smoothness", 0),
                            ("inflType", 2)):
            sub = self._name("skinSub")
            if c.attributeQuery(attr, node=sub, exists=True):
                c.setAttr(sub + "." + attr, value)
        c.connectAttr(reverse + ".outputX", wrap + ".nodeState",
                      force=True)

    def mesh_wrapped(self, mesh: str) -> bool:
        c = self.cmds
        return any(self._leaf(node).startswith("subWrap") for node
                   in self._wraps(mesh))

    def _leaf(self, node: str) -> str:
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _sub_wrap_nodes(self) -> tuple[str, ...]:
        c = self.cmds
        prefix = self.namespace + ":" if self.namespace else ""
        result = []
        for node in c.ls(type="wrap") or ():
            short = node.rsplit("|", 1)[-1]
            if ((short.startswith(prefix + "subWrap") if prefix else
                 ":" not in short and short.startswith("subWrap"))):
                result.append(node)
        return tuple(result)

    def detached_meshes(self) -> tuple[str, ...]:
        c = self.cmds
        cage = self._name("skinCage")
        if not c.objExists(cage) or not c.attributeQuery(
                "subWrapped", node=cage, exists=True):
            raise ValueError("SkinCage 没有已解除的 SubWrap 网格记录")
        stored = c.getAttr(cage + ".subWrapped") or ""
        meshes = tuple(dict.fromkeys(mesh for mesh in stored.split(";")
                                     if mesh and c.objExists(mesh)))
        return meshes

    def detach_all(self) -> tuple[str, ...]:
        c = self.cmds
        records = []
        for wrap in self._sub_wrap_nodes():
            shapes = c.deformer(wrap, query=True, geometry=True) or []
            if len(shapes) != 1:
                raise ValueError("SubWrap 变形器缺少唯一目标网格：" + wrap)
            mesh = self._mesh(shapes[0])
            records.append(mesh)
            for attr in _WRAP_ATTRS:
                if not c.attributeQuery(attr, node=mesh, exists=True):
                    c.addAttr(mesh, longName=attr, attributeType="double")
                c.setAttr(mesh + "." + attr, c.getAttr(wrap + "." + attr))
            c.delete(wrap)
        cage = self._name("skinCage")
        if not c.attributeQuery("subWrapped", node=cage, exists=True):
            c.addAttr(cage, longName="subWrapped", dataType="string")
        c.setAttr(cage + ".subWrapped", ";".join(records) + (
            ";" if records else ""), type="string")
        return tuple(records)

    def selected_vertices(self) -> tuple[str, ...]:
        return tuple(self.cmds.ls(selection=True, flatten=True,
                                  long=True) or ())

    def _deformer_set(self, node: str) -> str:
        c = self.cmds
        sets = c.listConnections(node + ".message", type="objectSet") or []
        if len(sets) != 1:
            raise ValueError("变形器缺少唯一组件集合：" + node)
        return sets[0]

    def exclude_vertices(self, vertices: tuple[str, ...]) -> None:
        c = self.cmds
        meshes = {self._mesh(vertex) for vertex in vertices}
        if len(meshes) != 1:
            raise ValueError("一次只能排除同一网格的顶点")
        mesh = next(iter(meshes))
        wraps = self._wraps(mesh)
        if len(wraps) != 1:
            raise ValueError("所选网格需要唯一的 Wrap 变形器")
        skin = self._skin(mesh)
        if not skin:
            from adv_py.application.skin_cage import CopySkinCageWeights
            c.select(list(vertices), replace=True)
            CopySkinCageWeights(MayaSkinCageHost(self.namespace)).execute()
            skin = self._skin(mesh)
        wrap_set = self._deformer_set(wraps[0])
        skin_set = self._deformer_set(skin)
        c.sets(list(vertices), remove=wrap_set)
        count = int(c.polyEvaluate(mesh, vertex=True))
        excluded = {int(vertex.rsplit("[", 1)[1].rstrip("]"))
                    for vertex in vertices}
        others = [mesh + f".vtx[{index}]" for index in range(count)
                  if index not in excluded]
        if others:
            c.sets(others, remove=skin_set)

    def vertices_excluded(self, vertices: tuple[str, ...]) -> bool:
        c = self.cmds
        mesh = self._mesh(vertices[0])
        wraps = self._wraps(mesh)
        skin = self._skin(mesh)
        if len(wraps) != 1 or not skin:
            return False
        wrap_set = self._deformer_set(wraps[0])
        skin_set = self._deformer_set(skin)
        return all(not c.sets(vertex, isMember=wrap_set)
                   and c.sets(vertex, isMember=skin_set)
                   for vertex in vertices)
