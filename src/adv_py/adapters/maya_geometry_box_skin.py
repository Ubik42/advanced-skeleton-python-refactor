"""Maya BoxSkin combine, bind and closest-vertex weight transfer."""
from __future__ import annotations

from adv_py.core.geometry_box_skin import BoxSkinPair
from .maya_geometry_poly_boxes import MayaPolyBoxesHost
from .maya_original_skin_history import new_original_skin_clusters


from .maya_original_transform_channels import lock_original_transform_channels

class MayaBoxSkinHost(MayaPolyBoxesHost):
    def __init__(self, namespace: str = "") -> None:
        super().__init__(namespace)
        self._expected_weights: dict[int, str] = {}

    def box_skin_exists(self) -> bool:
        c = self.cmds
        return any(c.objExists(self._name(leaf)) for leaf in (
            "BoxSkin", "BoxSkinGeometry", "BoxSkinMesh",
            "BoxSkinMeshSkinCluster"))

    def preflight_box_skin(self, pairs: tuple[BoxSkinPair, ...]) -> None:
        c = self.cmds
        if not c.objExists(self._name("Geometry")):
            raise ValueError("BoxSkin 缺少 Geometry 组")
        deform = self._name("DeformSet")
        if not c.objExists(deform):
            raise ValueError("BoxSkin 缺少 DeformSet")
        for pair in pairs:
            if not c.objExists(self._name(pair.joint)):
                raise ValueError("BoxSkin 缺少变形关节：" + pair.joint)

    def create_box_skin(self, pairs: tuple[BoxSkinPair, ...]) -> int:
        c=self.cmds
        layer=c.createDisplayLayer(name=self._name('BoxSkin'),empty=True)
        c.setAttr(layer+'.color',3);c.setAttr(layer+'.displayType',2)
        group=c.createNode('transform',name=self._name('BoxSkinGeometry'),parent=self._name('Geometry'))
        boxes_layer=self._name('PolyBoxes')
        c.setAttr(boxes_layer+'.visibility',0)
        # Source traverses every mesh Shape, including intermediate originals.
        # A box with two Shapes is intentionally scaled twice, not once per
        # transform; retaining this detail also preserves vertex sampling.
        scale_sources=tuple(c.listRelatives(shape,parent=True,fullPath=True)[0]
            for shape in c.listRelatives(self._name('BoxesGeometry'),
                allDescendents=True,type='mesh',fullPath=True) or [])
        for box in scale_sources:
            try:c.scale(.95,1,1,box,relative=True)
            except RuntimeError:pass  # native catchQuiet on authored scales
        copies=[]
        for pair in pairs:
            box=self._name(pair.box)
            copy=c.duplicate(box)[0]
            copy=c.rename(copy,self._name(pair.box+'BoxSkin'))
            lock_original_transform_channels(c, copy)
            copy=c.parent(copy,group)[0]
            c.editDisplayLayerMembers(layer,copy,noRecurse=True)
            c.select(self._name(pair.joint),copy,replace=True)
            skins=new_original_skin_clusters(commands=c,namespace=self.namespace)
            c.rename(skins[0],self._name(pair.box+'SkinCluster'))
            c.refresh()
            copies.append(copy)
        # Source duplicates the already-bound individual meshes before
        # uniting them. The resulting mesh stays at world until sampling.
        c.select(c.listRelatives(group,children=True),replace=True)
        snapshots=c.duplicate()
        mesh=c.polyUnite(constructionHistory=False,mergeUVSets=False,
                         name=self._name('BoxSkinMesh'))[0]
        c.delete(snapshots)
        c.editDisplayLayerMembers(layer,mesh,noRecurse=True)
        deform=self._name('DeformSet')
        c.select(mesh,replace=True);c.select(deform,add=True)
        skins=new_original_skin_clusters(commands=c,namespace=self.namespace)
        skin=c.rename(skins[0],self._name('BoxSkinMeshSkinCluster'))
        c.select(c.listRelatives(group,children=True),mesh,replace=True)
        shape=c.listRelatives(mesh,shapes=True,noIntermediate=True,type='mesh')[0]
        c.createNode('closestPointOnMesh',name=self._name('closestSampler'))
        # The MEL procedure addresses this literal name after createNode.
        # Do not silently substitute an auto-numbered node on a name clash.
        sampler=self._name('closestSampler')
        expected={}
        try:
            c.connectAttr(shape+'.outMesh',sampler+'.inMesh',force=True)
            for pair in pairs:
                source=self._name(pair.box)
                for index in range(int(c.polyEvaluate(source,vertex=True))):
                    position=c.xform(source+f'.vtx[{index}]',query=True,worldSpace=True,translation=True)
                    c.setAttr(sampler+'.inPosition',*position,type='double3')
                    vertex=int(c.getAttr(sampler+'.closestVertexIndex'))
                    c.skinPercent(skin,mesh+f'.vtx[{vertex}]',
                                  transformValue=(self._name(pair.joint),1.))
                    expected[vertex]=pair.joint
            self._expected_weights=expected
        finally:
            c.delete(sampler)
        c.delete(c.listRelatives(group,children=True) or [])
        c.parent(mesh,group)
        # Do not replace the source's rounded reciprocal with 1/.95: its
        # small resulting scale drift is part of the original operation.
        for box in scale_sources:
            try:c.scale(1.052632,1,1,box,relative=True)
            except RuntimeError:pass
        c.select(clear=True)
        return int(c.polyEvaluate(mesh,vertex=True))

    def capture_box_skin(self, pairs: tuple[BoxSkinPair, ...],
                         vertex_count: int) -> bool:
        c = self.cmds
        group = self._name("BoxSkinGeometry")
        mesh = self._name("BoxSkinMesh")
        skin = self._name("BoxSkinMeshSkinCluster")
        layer = self._name("BoxSkin")
        if (not all(c.objExists(node) for node in (group, mesh, skin, layer))
                or c.nodeType(skin) != "skinCluster"
                or (c.listRelatives(mesh, parent=True) or []) != [group]
                or int(c.polyEvaluate(mesh, vertex=True)) != vertex_count
                or c.getAttr(layer + ".color") != 3
                or c.getAttr(layer + ".displayType") != 2):
            return False
        influences = {self._leaf(node) for node in
                      c.skinCluster(skin, query=True, influence=True) or ()}
        if not {pair.joint for pair in pairs}.issubset(influences):
            return False
        for vertex, joint in self._expected_weights.items():
            weight = c.skinPercent(
                skin, f"{mesh}.vtx[{vertex}]", query=True,
                transform=self._name(joint))
            if abs(float(weight) - 1.0) > 1e-4:
                return False
        return bool(self._expected_weights)

    def delete_box_skin(self) -> None:
        c = self.cmds
        for leaf in ("BoxSkin", "BoxSkinGeometry", "BoxSkinMesh"):
            node = self._name(leaf)
            if c.objExists(node):
                c.delete(node)
