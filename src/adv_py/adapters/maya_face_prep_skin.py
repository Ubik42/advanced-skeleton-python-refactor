"""asFacePrep cleanup and native Skin regeneration, 31312–31519.

These are shared preparation stages, including the original fixed wrap
options. Prefix capture and restoration of an existing rig remain separate.
"""
from contextlib import nullcontext


class MayaFacePrepSkinMixin:
    def prepare_original_face_skin(self, source):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        geometry = self.scene_address(source["geometry"])
        skin = self.scene_address(source["skin"])
        # Original removes only unconnected intermediate mesh shapes.
        for shape in raw.listRelatives(geometry, shapes=True, fullPath=True) or []:
            if not raw.getAttr(shape + ".intermediateObject"):
                continue
            connected = any(raw.nodeType(node) not in ("shadingEngine", "objectSet")
                            for node in raw.listConnections(shape) or [])
            if not connected:
                raw.delete(shape)
        for command, flags in (("evaluator", {"name": "cache", "enable": False}),
                               ("cacheEvaluator", {"flushCache": "destroy"})):
            try:
                getattr(raw, command)(**flags)
            except RuntimeError:
                pass  # MEL catchQuiet for Maya versions without cache support.
        raw.setAttr(skin + ".skinningMethod", 0)
        for node in ("upperTempSoftModHandle1", "lowerTempSoftModHandle1",
                     "upperTempSoftModHandle2", "lowerTempSoftModHandle2"):
            if c.objExists(node):
                c.delete(node)
        source["skin"] = self.regenerate_original_face_skin(source["geometry"], source["skin"])
        # asSetFixedWrapOptions intentionally persists these Maya options.
        for option, value in (("autoWeightThreshold", 1), ("exclusiveBind", 0), ("renderInfl", 1)):
            raw.optionVar(intValue=(option, value))
        raw.optionVar(stringValue=("falloffMode", "volume"))

    def regenerate_original_face_skin(self, geometry, skin):
        """Copy to a temporary Skin, recreate the original, copy weights back."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        mesh = self.scene_address(geometry)
        skin_path = self.scene_address(skin)
        influences = raw.listConnections(skin_path + ".matrix", source=True, destination=False, type="joint") or []
        namespace = c._creation_namespace if hasattr(c, "_creation_namespace") else nullcontext
        with namespace():
            duplicate = raw.duplicate(mesh, name=self.scene_address("newSkinClusterLayer"), returnRootsOnly=True)[0]
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"):
            raw.setAttr(duplicate + "." + attr, lock=False)
        raw.sets(duplicate, edit=True, forceElement=":initialShadingGroup")
        for shape in raw.listRelatives(duplicate, shapes=True, fullPath=True) or []:
            if raw.getAttr(shape + ".intermediateObject"):
                raw.delete(shape)
        with namespace():
            temporary = raw.skinCluster([duplicate, *influences], toSelectedBones=True,
                                        maximumInfluences=3, dropoffRate=4, removeUnusedInfluence=False,
                                        name=self.scene_address("newSkinClusterSC"))[0]
        raw.select((mesh, duplicate), replace=True)
        raw.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint", influenceAssociation="closestJoint")
        raw.delete(skin_path)
        with namespace():
            regenerated = raw.skinCluster([mesh, *influences], toSelectedBones=True,
                                          maximumInfluences=3, dropoffRate=4, removeUnusedInfluence=False,
                                          name=skin_path)[0]
        raw.select((duplicate, mesh), replace=True)
        raw.copySkinWeights(noMirror=True, surfaceAssociation="closestPoint", influenceAssociation="closestJoint")
        raw.delete(duplicate)
        # Some Maya releases leave the deleted mesh's temporary Skin alive.
        if raw.objExists(temporary):
            raw.delete(temporary)
        if c.objExists("asFaceDeltaMush"):
            try:
                raw.reorderDeformers(self.scene_address("asFaceDeltaMush"), regenerated, mesh)
            except RuntimeError:
                pass
        fit = self._fit(required=True)
        if not c.objExists(fit + ".SkinCluster"):
            c.addAttr(fit, longName="SkinCluster", dataType="string")
        c.setAttr(fit + ".SkinCluster", regenerated, type="string")
        return regenerated

    def finish_original_face_preparation(self, source):
        """asFacePrep 31523–31625, after prefix capture/Skin regeneration."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        self.ensure_face_advanced_base(source["head"], source["geometry"], source["all_head"])
        scale = source["scale"] / 14.4300
        for node in ("OnFacecontrols", "ConstrainedSetup"):
            c.setAttr(node + ".s", scale, scale, scale, type="float3")
        self.ensure_original_face_joint(source["head"], source["scale"])
        for node in raw.listHistory(self.scene_address(source["geometry"])) or []:
            if raw.nodeType(node) == "skinCluster":
                source["skin"] = node
            if raw.nodeType(node) == "deltaMush":
                raw.setAttr(node + ".envelope", 0)
        fit = self._fit(required=True)
        c.setAttr(fit + ".SkinCluster", source["skin"], type="string")
        for part, name in (("UpperTeeth", "upperTeethSet"), ("LowerTeeth", "lowerTeethSet")):
            c.sets(empty=True, name=name)
            c.sets(name, add="FaceBuildingSets")
            vertices = self.read_original_face_parts(part)
            if vertices:
                raw.sets(vertices, add=self.scene_address(name))
        if c.objExists("DeformSet"):
            for joint in c.sets("DeformSet", query=True) or []:
                if c.objExists(joint + ".lockInfluenceWeights") and c.getAttr(joint + ".lockInfluenceWeights"):
                    c.setAttr(joint + ".lockInfluenceWeights", False)
        self.ensure_original_face_orientation()
        maximum = 0
        if all(c.objExists(fit + "." + name) for name in ("GameEngine", "UseMaxInf", "MaxInf")):
            if c.getAttr(fit + ".GameEngine") and c.getAttr(fit + ".UseMaxInf"):
                maximum = int(c.getAttr(fit + ".MaxInf", asString=True))
        if maximum:
            # Original Prep sets FOUR even when the selected MaxInf differs;
            # later Finish performs the final requested influence reduction.
            raw.skinCluster(self.scene_address(source["geometry"]), edit=True, maximumInfluences=4)
            raw.setAttr(self.scene_address(source["skin"]) + ".maxInfluences", 4)
            raw.setAttr(self.scene_address(source["skin"]) + ".maintainMaxInfluences", True)
        c.select(clear=True)
