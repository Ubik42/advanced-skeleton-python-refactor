"""Maya SubWrap cage, wrap deformers, attachment and component sets."""
from __future__ import annotations

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
        if creating:
            if not c.objExists(self._name("skinCage")):
                raise ValueError('"skinCage" not found; create SkinCage first')
            if c.objExists(self._name("skinSub")):
                raise ValueError('"skinSub" already exists')

    def create_cage(self) -> None:
        c = self.cmds
        selected = c.ls(selection=True) or []
        cages = self._name("Cages")
        if not c.objExists(cages):
            cages = c.createNode("transform", name=cages,
                                 parent=self._name("Geometry"),
                                 skipSelect=True)
        proxy = c.createNode("polySmoothProxy", name=self._name(
            "subWrapPolySmoothProxy"))
        sub = c.polyCube(name=self._name("skinSub"), width=1, height=1,
                         depth=1, subdivisionsX=1, subdivisionsY=1,
                         subdivisionsZ=1, axis=(0, 1, 0), createUVs=4,
                         constructionHistory=False)[0]
        sub = c.parent(sub, cages)[0]
        c.connectAttr(self._shape(self._name("skinCage")) + ".outMesh",
                      proxy + ".inputPolymesh")
        c.connectAttr(proxy + ".output", self._shape(sub) + ".inMesh")
        c.select(sub, replace=True)
        layer = c.createDisplayLayer(name=self._name("SkinSub"), number=1, noRecurse=True)
        c.setAttr(layer + ".displayType", 2)
        c.setAttr(layer + ".color", 30)
        original = self._name("SkinCage")
        c.setAttr(original + ".displayType", 1)
        c.select(selected, replace=True) if selected else c.select(clear=True)

    def delete_cage(self) -> None:
        c = self.cmds
        for leaf in ("skinSub", "SkinSub"):
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

    def _reverse_visibility(self) -> str:
        c = self.cmds
        main = self._name("Main")
        if not c.objExists(main + ".wrapDeform"):
            c.addAttr(main, longName="wrapDeform", attributeType="bool",
                      defaultValue=True, keyable=True)
            c.setAttr(main + ".wrapDeform", keyable=False, channelBox=True)
        reverse = self._name("wrapDeformReverse")
        if not c.objExists(reverse):
            reverse = c.createNode("reverse", name=reverse)
            c.connectAttr(main + ".wrapDeform", reverse + ".inputX")
        return reverse

    def wrap_mesh(self, mesh: str) -> None:
        self.wrap_meshes((mesh,))

    def wrap_meshes(self, meshes: tuple[str, ...]) -> None:
        """asWrapSkin creates the batch first, then configures all source wraps.

        wrapValues is shared across the final loop: a missing mesh attribute
        retains the preceding wrap's value, rather than resetting its default.
        """
        from maya import mel
        from .maya_face_deformer_sets import original_face_deformer_sets
        c = self.cmds
        reverse = self._reverse_visibility()
        for mesh in meshes:
            c.select(mesh, replace=True)
            c.select(self._name("skinSub"), add=True)
            with original_face_deformer_sets(c):
                mel.eval('doWrapArgList 7 {"1","0","1","2","1","1","1","0"};')
        wraps = c.listConnections(self._name("skinSub") + ".worldMesh", type="wrap") or []
        values = list(_WRAP_DEFAULTS)
        for index, old in enumerate(wraps):
            wrap = c.rename(old, self._name("subWrap" + str(index + 1)))
            mesh = c.listConnections(wrap + ".outputGeometry")[0]
            c.setAttr(wrap + ".nodeState", 1)
            for index, attr in enumerate(_WRAP_ATTRS):
                if c.objExists(mesh + "." + attr):
                    values[index] = c.getAttr(mesh + "." + attr)
                c.setAttr(wrap + "." + attr, values[index])
            for attr, value in (("dropoff", 4), ("smoothness", 0), ("inflType", 2)):
                c.setAttr(self._name("skinSub") + "." + attr, value)
            c.connectAttr(reverse + ".output.outputX", wrap + ".nodeState")
        c.select(clear=True)

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
        if not c.objExists(self._name("skinSub")):
            raise ValueError("skinSub not found; create SubWrap first")
        stored = c.getAttr(cage + ".subWrapped") or ""
        meshes = tuple(mesh for mesh in stored.split(";")
                       if mesh and c.objExists(mesh))
        return meshes

    def detach_all(self) -> tuple[str, ...]:
        """asSkinSubDetach preserves final downstream mesh and deletion order.

        The original deletes the whole subWrap array inside its loop. Do not
        quietly turn that into per-wrap deletion while claiming source fidelity.
        Multiple wraps require native validation against this source behavior.
        """
        c = self.cmds
        wraps = self._sub_wrap_nodes()
        records = []
        mesh = ""
        for wrap in wraps:
            for node in c.listHistory(wrap + ".outputGeometry", future=True) or []:
                if c.nodeType(node) == "mesh":
                    mesh = c.listRelatives(node, parent=True)[0]
            records.append(mesh)
            for attr in _WRAP_ATTRS:
                if not c.objExists(mesh + "." + attr):
                    c.addAttr(mesh, longName=attr, attributeType="double")
                c.setAttr(mesh + "." + attr, c.getAttr(wrap + "." + attr))
            c.delete(list(wraps))
        cage = self._name("skinCage")
        if not c.objExists(cage + ".subWrapped"):
            c.addAttr(cage, longName="subWrapped", dataType="string")
        c.setAttr(cage + ".subWrapped", "".join(mesh + ";" for mesh in records), type="string")
        return tuple(records)

    def selected_vertices(self) -> tuple[str, ...]:
        return tuple(self.cmds.ls(selection=True, flatten=True,
                                  long=True) or ())

    def _deformer_set(self, node: str) -> str:
        return self.cmds.listConnections(node + ".message")[0]

    def exclude_vertices(self, vertices: tuple[str, ...]) -> None:
        """asWrapExlude: final Wrap/Skin history, native smoothing and inversion."""
        c = self.cmds
        from maya import mel
        mesh = self._mesh(vertices[0])
        wraps = self._wraps(vertices[0])
        if not wraps:
            raise ValueError("No wrap deformer on selected object")
        wrap = wraps[-1]
        skin = self._skin(vertices[0])
        had_skin = bool(skin)
        c.select(list(vertices), replace=True)
        if not had_skin:
            from adv_py.core.skin_cage import plan_skin_cage_copy
            from .maya_original_skin_operations import smooth_skin_on_selected
            plan = plan_skin_cage_copy((mesh,), vertices)
            self.preflight_copy(plan)
            for target in plan:
                self.copy_weights(target)
            objects = c.ls(selection=True, objectsOnly=True)
            target = c.listRelatives(objects[0], parent=True)[0]
            c.select(target, replace=True)
            smooth_skin_on_selected(self.namespace, cmds=c, transactional=False)
            c.select(list(vertices), replace=True)
        skin = self._skin(vertices[0])
        wrap_set, skin_set = self._deformer_set(wrap), self._deformer_set(skin)
        c.sets(remove=wrap_set)
        selected = c.ls(selection=True) or []
        objects = c.ls(selection=True, objectsOnly=True) or []
        c.select(objects[0] + ".vtx[0:999999]", replace=True)
        c.select(selected, deselect=True)
        c.sets(remove=skin_set)
        if not had_skin:
            objects = c.ls(selection=True, objectsOnly=True) or []
            c.select(objects[0], replace=True)
            mel.eval("removeUnusedInfluences;")
        c.select(list(vertices), replace=True)

    def vertices_excluded(self, vertices: tuple[str, ...]) -> bool:
        c = self.cmds
        mesh = self._mesh(vertices[0])
        wraps = self._wraps(mesh)
        skin = self._skin(mesh)
        if not wraps or not skin:
            return False
        wrap_set = self._deformer_set(wraps[-1])
        skin_set = self._deformer_set(skin)
        return all(not c.sets(vertex, isMember=wrap_set)
                   and c.sets(vertex, isMember=skin_set)
                   for vertex in vertices)
