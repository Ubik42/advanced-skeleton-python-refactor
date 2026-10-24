"""Original conversion template, joint and additional Skin layers."""
from .maya_face_body_roles import face_body_main
from .maya_original_skin_history import bind_original_skin, remove_unused_for_skin


from .maya_original_transform_channels import lock_original_transform_channels

class MayaFaceBSLayersMixin:
    @staticmethod
    def _original_bs_geo_tag(geometry, *, first_colon=False):
        leaf = geometry.rsplit("|", 1)[-1].lstrip(":")
        return leaf.replace(":", "_", 1) if first_colon else leaf.replace(":", "_")

    def _original_bs_clean_duplicate(self, geometry, name, parent):
        c = self._cmds
        raw = getattr(c, "raw", c)
        c.duplicate(geometry, name=name)
        lock_original_transform_channels(c, name)
        c.parent(name, parent)
        raw.sets(self.scene_address(name), edit=True, forceElement=":initialShadingGroup")
        children = c.listRelatives(name, children=True, type="transform") or []
        if children:
            c.delete(children)
        for shape in c.listRelatives(name, shapes=True, fullPath=True) or []:
            if c.getAttr(shape + ".intermediateObject"):
                c.delete(shape)
        for shape in c.listRelatives(name, shapes=True, fullPath=True) or []:
            pairs = c.listConnections(shape, source=False, destination=True, plugs=True,
                                      connections=True, type="objectSet") or []
            for index in range(0, len(pairs), 2):
                if "Area." in pairs[index + 1]:
                    c.disconnectAttr(pairs[index], pairs[index + 1])
        return name

    def prepare_original_face_bs_layers(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        c.setAttr("FaceDeformationSystem.v", lock=False)
        c.setAttr("FaceDeformationSystem.v", True)
        for child in c.listRelatives("FaceDeformationSystem", children=True, type="transform") or []:
            if not c.getAttr(child + ".v", lock=True):
                c.setAttr(child + ".v", False, lock=True)
        c.parent("FaceJoint_M", "FaceDeformationSystem")
        c.setAttr("FaceJoint_M.v", lock=False)
        if c.objExists(face_body_main(self)+".jointVis"):
            c.connectAttr(face_body_main(self)+".jointVis", "FaceJoint_M.v")
        c.createNode("transform", name="DeformationLayers", parent="FaceDeformationSystem")
        for layer in ("TemplateLayer", "FaceJointsLayer"):
            c.createNode("transform", name=layer, parent="DeformationLayers")
            c.setAttr(layer + ".v", False)
        for geometry in source["all_head"]:
            suffix = "_" + self._original_bs_geo_tag(geometry, first_colon=True)
            bs = "asFaceBS" if geometry == source["geometry"] else "asFaceBS" + suffix
            skin = self.original_face_bs_skin(geometry)
            template = self._original_bs_clean_duplicate(geometry, "TemplateLayer" + suffix, "TemplateLayer")
            layer = "FaceJointsLayer" + suffix
            c.duplicate(template, name=layer)
            c.parent(layer, "FaceJointsLayer")
            influences = raw.listConnections(skin + ".matrix", source=True, destination=False, type="joint") or []
            bind_original_skin(c, (*influences, layer), layer + "SC",
                               namespace=self.namespace)
            self._cage_copy_selected((geometry,), (layer,))
            for joint in c.listConnections(layer + "SC.matrix") or []:
                raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", bool(c.sets(joint, isMember="FaceAllSet")))
            if c.objExists("upperFaceJoint_M"):
                for stem in ("upper", "middle", "lower"):
                    c.setAttr(stem + "FaceJoint_M.liw", False)
            c.skinCluster(layer + "SC", edit=True, dropoffRate=4, lockWeights=False, weight=0, addInfluence="FaceJoint_M")
            try:
                c.skinPercent(layer + "SC", layer, transformValue=(("FaceJoint_M", 1),))
            except RuntimeError:
                pass
            if c.objExists("upperFaceJoint_M"):
                for stem in ("upper", "middle", "lower"):
                    # Literal source name is upperJoint_M, not upperFaceJoint_M.
                    joint = stem + "Joint_M"
                    if c.objExists(joint):
                        c.skinCluster(layer + "SC", edit=True, removeInfluence=joint)
            self._original_face_bs_front(geometry, bs)
            self._original_face_bs_add_target(geometry, bs, layer)
            if suffix:
                c.aliasAttr("FaceJointsLayer", bs + ".weight[0]")
        if c.objExists("upperSideReverse_R"):
            self.create_original_face_bs_skin_layer("UpMidLo", source)

    def create_original_face_bs_skin_layer(self, layer, source):
        """asFaceCreateSkinLayer, source 42708–42746."""
        c = self._cmds
        c.duplicate("TemplateLayer", name=layer + "Layer")
        result = []
        raw = getattr(c, "raw", c)
        for child in c.listRelatives(layer + "Layer", children=True, type="transform", fullPath=True) or []:
            tag = self._original_restore_leaf(child).replace("TemplateLayer_", "", 1)
            renamed = c.rename(child, layer + "Layer_" + tag)
            shape = c.listRelatives("FaceJointsLayer_" + tag, shapes=True)[0]
            bs = c.listConnections(shape, source=False, destination=True, type="blendShape")[0]
            # asFaceCreateSkinLayer follows the BlendShape's future history,
            # taking the first mesh's parent rather than inferring an output
            # from the template name or the original All Head registration.
            geometry = ""
            for node in raw.listHistory(self.scene_address(bs), future=True) or []:
                if raw.nodeType(node) == "mesh":
                    geometry = self._original_bs_physical_address(
                        raw.listRelatives(node, parent=True, fullPath=True)[0])
                    break
            self._original_face_bs_add_target(geometry, bs, renamed)
            c.setAttr(bs + "." + self._original_restore_leaf(renamed), 1)
            result.append(renamed)
        return tuple(result)

    def rebuild_original_face_bs_up_mid_lo(self, source):
        """Original Mixed UpMidLo Skin separation, 43590–43694."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        geometry, head = source["geometry"], source["head"]
        main = "UpMidLoLayer_" + self._original_bs_geo_tag(geometry, first_colon=True)
        for side in ("_R", "_L", "_M"):
            for stem in ("upper", "middle", "lower"):
                group = stem + "SideReverse" + side
                children = c.listRelatives(group, children=True, type="transform") or []
                if children:
                    c.parent(children, "SideReverse" + side)
                c.delete(group)
        c.parent("EyeOffset_R", "EyeOffset_L", "EyeControls")
        # MEL 43560 switches to the visible UpMidLo meshes before native
        # Skin painting. The paint context must operate on this layer.
        self.show_original_face_layer_in_transaction("UpMidLo")
        children = c.listRelatives("UpMidLoLayer", children=True, type="transform") or []
        joints = ["upperFaceJoint_M", "middleFaceJoint_M", "lowerFaceJoint_M", "FaceJoint_M"]
        for mesh in children:
            influences = [self.scene_address(joint) for joint in joints]
            if self._original_restore_leaf(mesh) == main:
                influences += raw.listConnections(self.scene_address(source["skin"]) + ".matrix", source=True, destination=False, type="joint") or []
            bind_original_skin(c, (*influences, mesh),
                self._original_restore_leaf(mesh) + "SC", namespace=self.namespace)
            c.skinPercent(self._original_restore_leaf(mesh) + "SC", mesh, transformValue=(("middleFaceJoint_M", 1),))
        self._cage_copy_selected((geometry,), (main,))
        influences = c.listConnections(main + "SC.matrix", source=True, destination=False, type="joint") or []
        for joint in influences:
            raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", True)
        raw.setAttr(self.scene_address(head) + ".lockInfluenceWeights", False)
        try:
            c.skinPercent(main + "SC", main, transformValue=(("middleFaceJoint_M", 1),))
        except RuntimeError:
            pass
        for joint in influences:
            raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", False)
        for joint in joints[:3]:
            raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", True)
        try:
            c.skinPercent(main + "SC", main, transformValue=(("FaceJoint_M", 1),))
        except RuntimeError:
            pass
        for joint in influences:
            raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", True)
        for joint in joints[:3]:
            raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", False)
        c.select(main, replace=True)
        for stem in ("upper", "lower"):
            y = c.xform(stem + "Face_M", query=True, worldSpace=True, translation=True)[1]
            raw.polySelectConstraint(mode=3, type=1, dist=3,
                distbound=(y, 9999) if stem == "upper" else (0, y),
                distaxis=(0, 1, 0), distpoint=(0, 0, 0))
            vertices = raw.ls(selection=True, flatten=True) or []
            try:
                c.skinPercent(main + "SC", vertices, transformValue=((stem + "FaceJoint_M", 1),))
            except RuntimeError:
                if stem == "upper":
                    raise
        raw.polySelectConstraint(mode=0)
        # Source 43604 selects the whole mesh before its two paint floods.
        for stem in ("upper", "lower"):
            self.smooth_original_face_flood(main + "SC", (main,), stem + "FaceJoint_M", "middleFaceJoint_M", 10)
        remove_unused_for_skin(raw, self.scene_address(main + "SC"))
        for mesh in children:
            if self._original_restore_leaf(mesh) != main:
                self._cage_copy_selected((main,), (mesh,))
        raw.skinCluster(self.scene_address(source["skin"]), edit=True, selectInfluenceVerts=self.scene_address(head))
        all_vertices = raw.ls(self.scene_address(geometry) + ".vtx[*]", flatten=True) or []
        selected = set(raw.ls(selection=True, flatten=True) or [])
        remaining = [vertex for vertex in all_vertices if vertex not in selected]
        if remaining:
            c.skinPercent(main + "SC", [main + "." + vertex.split(".", 1)[1] for vertex in remaining], transformValue=(("FaceJoint_M", 1),))
        for part in ("RightEye", "LeftEye"):
            if not c.objExists("squashEyeFfd1Set_R"):
                continue
            for mesh in self.read_original_face_parts(part):
                if "." not in mesh:
                    layer = "UpMidLoLayer_" + self._original_bs_geo_tag(mesh, first_colon=True)
                    c.skinPercent(layer + "SC", layer, transformValue=(("upperFaceJoint_M", 1),))
        self.show_original_face_layer_in_transaction("Normal")
