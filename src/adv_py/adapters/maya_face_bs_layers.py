"""Original conversion template, joint and additional Skin layers."""
from contextlib import nullcontext


class MayaFaceBSLayersMixin:
    @staticmethod
    def _original_bs_geo_tag(geometry, *, first_colon=False):
        leaf = geometry.rsplit("|", 1)[-1].lstrip(":")
        return leaf.replace(":", "_", 1) if first_colon else leaf.replace(":", "_")

    def _original_bs_clean_duplicate(self, geometry, name, parent):
        c = self._cmds
        raw = getattr(c, "raw", c)
        c.duplicate(geometry, name=name)
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"):
            c.setAttr(name + "." + attr, lock=False)
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
        if c.objExists("Main.jointVis"):
            c.connectAttr("Main.jointVis", "FaceJoint_M.v")
        c.createNode("transform", name="DeformationLayers", parent="FaceDeformationSystem")
        for layer in ("TemplateLayer", "FaceJointsLayer"):
            c.createNode("transform", name=layer, parent="DeformationLayers")
            c.setAttr(layer + ".v", False)
        for geometry in source["all_head"]:
            suffix = "_" + self._original_bs_geo_tag(geometry, first_colon=True)
            bs = "asFaceBS" if geometry == source["geometry"] else "asFaceBS" + suffix
            skin = self._original_pupil_skin(self.scene_address(geometry), exclude_prefix=False)
            template = self._original_bs_clean_duplicate(geometry, "TemplateLayer" + suffix, "TemplateLayer")
            layer = "FaceJointsLayer" + suffix
            c.duplicate(template, name=layer)
            c.parent(layer, "FaceJointsLayer")
            influences = raw.listConnections(skin + ".matrix", source=True, destination=False, type="joint") or []
            with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
                raw.skinCluster([*influences, self.scene_address(layer)], toSelectedBones=True,
                    maximumInfluences=3, dropoffRate=4, removeUnusedInfluence=False,
                    name=self.scene_address(layer + "SC"))
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
        lookup = {self._original_bs_geo_tag(mesh, first_colon=True): mesh for mesh in source["all_head"]}
        for child in c.listRelatives(layer + "Layer", children=True, type="transform") or []:
            tag = self._original_restore_leaf(child).replace("TemplateLayer_", "", 1)
            renamed = c.rename(child, layer + "Layer_" + tag)
            shape = c.listRelatives("FaceJointsLayer_" + tag, shapes=True)[0]
            bs = c.listConnections(shape, source=False, destination=True, type="blendShape")[0]
            geometry = lookup[tag]
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
        children = c.listRelatives("UpMidLoLayer", children=True, type="transform") or []
        joints = ["upperFaceJoint_M", "middleFaceJoint_M", "lowerFaceJoint_M", "FaceJoint_M"]
        for mesh in children:
            influences = [self.scene_address(joint) for joint in joints]
            if self._original_restore_leaf(mesh) == main:
                influences += raw.listConnections(self.scene_address(source["skin"]) + ".matrix", source=True, destination=False, type="joint") or []
            with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
                raw.skinCluster([*influences, self.scene_address(mesh)], toSelectedBones=True,
                    maximumInfluences=3, dropoffRate=4, removeUnusedInfluence=False,
                    name=self.scene_address(self._original_restore_leaf(mesh) + "SC"))
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
        for stem in ("upper", "lower"):
            y = c.xform(stem + "Face_M", query=True, worldSpace=True, translation=True)[1]
            c.select(main, replace=True)
            raw.polySelectConstraint(mode=3, type=1, distance=3,
                distancebound=(y, 9999) if stem == "upper" else (0, y),
                distanceaxis=(0, 1, 0), distancepoint=(0, 0, 0))
            vertices = raw.ls(selection=True, flatten=True) or []
            try:
                c.skinPercent(main + "SC", vertices, transformValue=((stem + "FaceJoint_M", 1),))
            except RuntimeError:
                if stem == "upper":
                    raise
        raw.polySelectConstraint(mode=0)
        for stem in ("upper", "lower"):
            self.smooth_original_face_flood(main + "SC", raw.ls(self.scene_address(main) + ".vtx[*]", flatten=True) or [], stem + "FaceJoint_M", "middleFaceJoint_M", 10)
        c.skinCluster(main + "SC", edit=True, removeUnusedInfluence=True)
        for mesh in children:
            if self._original_restore_leaf(mesh) != main:
                self._cage_copy_selected((main,), (mesh,))
        raw.skinCluster(self.scene_address(source["skin"]), edit=True, selectInfluenceVerts=self.scene_address(head))
        all_vertices = set(raw.ls(self.scene_address(geometry) + ".vtx[*]", flatten=True) or [])
        remaining = all_vertices - set(raw.ls(selection=True, flatten=True) or [])
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
