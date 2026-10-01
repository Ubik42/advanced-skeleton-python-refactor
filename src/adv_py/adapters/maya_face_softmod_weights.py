"""Original SoftMod/rich-selection to Skin weights (73763, 73884).

Weights use actual influence logical indices and Maya's native falloff. No
radial approximation replaces Maya surface-distance soft selection.
"""
from contextlib import nullcontext


class MayaFaceSoftModWeightsMixin:
    def _original_softmod_influence_index(self, skin, joint):
        from maya.api import OpenMaya as om, OpenMayaAnim as oma
        selection = om.MSelectionList()
        selection.add(self.scene_address(skin))
        fn = oma.MFnSkinCluster(selection.getDependNode(0))
        selection = om.MSelectionList()
        selection.add(self.scene_address(joint))
        return int(fn.indexForInfluenceObject(selection.getDagPath(0)))

    def set_original_face_joint_weights(self, joint, geometry, skin, numbers, weights):
        """asSkinWeightSet: direct sparse plug write followed by two normalizes."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        index = self._original_softmod_influence_index(skin, joint)
        for number, weight in zip(numbers, weights):
            raw.setAttr(self.scene_address(skin) + f".weightList[{number}].weights[{index}]", weight)
        for lock in (True, False):
            raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", lock)
            try:
                raw.skinPercent(self.scene_address(skin), self.scene_address(geometry), normalize=True)
            except RuntimeError:
                pass

    def weight_original_face_by_softmod(self, joint, geometry, skin, radius, falloff_mode=1):
        """Native rich-selection branch of asSkinWeightBySoftMod."""
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        selection = tuple(raw.ls(selection=True) or [])
        if c.objExists("tempSoftModCopy") or self._original_restore_leaf(joint).startswith("LipPullJoint_"):
            return self._weight_original_face_by_softmod_delta(joint, geometry, skin, radius, falloff_mode)
        from maya.api import OpenMaya as om
        position = c.xform(joint, query=True, worldSpace=True, translation=True)
        if c.objExists("closestSampler2"):
            c.delete("closestSampler2")
        sampler = c.createNode("closestPointOnMesh", name="closestSampler2")
        raw.connectAttr(self.scene_address(geometry) + ".outMesh", self.scene_address(sampler) + ".inMesh", force=True)
        c.setAttr(sampler + ".inPosition", *position)
        number = int(c.getAttr(sampler + ".closestVertexIndex"))
        raw.select(self.scene_address(geometry) + f".vtx[{number}]", replace=True)
        c.delete(sampler)
        raw.softSelect(softSelectReset=True)
        raw.softSelect(edit=True, softSelectEnabled=True, softSelectFalloff=falloff_mode, softSelectDistance=radius)
        if c.objExists("convertingSoftMod"):
            soft = c.getAttr("convertingSoftMod.softMod")
            values = []
            for index in range(int(c.getAttr(soft + ".falloffCurve", size=True))):
                for attr in ("FloatValue", "Position", "Interp"):
                    values.append(str(c.getAttr(soft + f".falloffCurve[{index}].falloffCurve_" + attr)))
            raw.softSelect(edit=True, softSelectCurve=",".join(values))
        index = self._original_softmod_influence_index(skin, joint)
        rich = om.MGlobal.getRichSelection().getSelection()
        iterator = om.MItSelectionList(rich, om.MFn.kMeshVertComponent)
        count = 0
        while not iterator.isDone():
            _, component = iterator.getComponent()
            fn = om.MFnSingleIndexedComponent(component)
            for item in range(fn.elementCount):
                number = fn.element(item)
                weight = fn.weight(item).influence
                raw.setAttr(self.scene_address(skin) + f".weightList[{number}].weights[{index}]", weight)
                count += 1
            iterator.next()
        raw.softSelect(edit=True, softSelectEnabled=False)
        raw.softSelect(softSelectReset=True)
        for influence in raw.listConnections(self.scene_address(skin) + ".matrix") or []:
            raw.setAttr(influence + ".lockInfluenceWeights", False)
        raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", True)
        raw.skinPercent(self.scene_address(skin), self.scene_address(geometry), normalize=True)
        raw.setAttr(self.scene_address(joint) + ".lockInfluenceWeights", False)
        raw.select(selection, replace=True)
        return count

    def _weight_original_face_by_softmod_delta(self, joint, geometry, skin, radius, max_weight):
        """Original tempSoftModCopy/LipPull native deformation sample branch."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        selection = tuple(raw.ls(selection=True) or [])
        position = c.xform(joint, query=True, worldSpace=True, translation=True)
        namespace = c._creation_namespace if hasattr(c, "_creation_namespace") else nullcontext
        c.duplicate(geometry, name="tempMesh")
        with namespace(), self._original_face_softmod_sets():
            soft, handle = raw.softMod(self.scene_address("tempMesh"))
        soft = c.rename(soft, "TempSoftMod")
        handle = c.rename(handle, "TempSoftModHandle")
        if c.objExists("tempSoftModCopy"):
            for attr in ("falloffRadius", "falloffMode"):
                c.setAttr(soft + "." + attr, c.getAttr("tempSoftModCopy." + attr))
            for index in range(int(c.getAttr("tempSoftModCopy.falloffCurve", size=True))):
                c.connectAttr(f"tempSoftModCopy.falloffCurve[{index}]", soft + f".falloffCurve[{index}]", force=True)
        c.setAttr(handle + "Shape.origin", *position, type="float3")
        c.setAttr(soft + ".falloffCenter", *position)
        c.xform(handle, pivots=position)
        c.setAttr(soft + ".falloffMode", 1)
        c.setAttr(soft + ".falloffRadius", radius)
        if self._original_restore_leaf(joint).startswith("LipPullJoint_") and not c.objExists("tempSoftModCopy"):
            for index, (x, y) in enumerate(((0, 1), (1, 0), (.3043, .439273), (.0806, .945397))):
                c.setAttr(soft + f".falloffCurve[{index}].falloffCurve_Position", x)
                c.setAttr(soft + f".falloffCurve[{index}].falloffCurve_FloatValue", y)
                c.setAttr(soft + f".falloffCurve[{index}].falloffCurve_Interp", 3)
        if self._original_restore_leaf(joint).startswith("MouthNarrowJoint_") and not c.objExists("tempSoftModCopy"):
            c.setAttr(soft + ".falloffCurve[0].falloffCurve_Interp", 1)
        c.select("tempMesh", replace=True)
        raw.polySelectConstraint(mode=3, type=1, dist=1, distbound=(0, radius), distpoint=position)
        vertices = tuple(raw.ls(selection=True, flatten=True) or [])
        raw.polySelectConstraint(mode=0)
        initial = [raw.xform(vertex, query=True, worldSpace=True, translation=True)[1] for vertex in vertices]
        c.setAttr(handle + ".ty", 1)
        for vertex, y in zip(vertices, initial):
            weight = min(1, max(0, (raw.xform(vertex, query=True, worldSpace=True, translation=True)[1] - y) * max_weight))
            target = self.scene_address(geometry) + "." + vertex.split(".", 1)[1]
            try:
                raw.skinPercent(self.scene_address(skin), target, transformValue=((self.scene_address(joint), weight),))
            except RuntimeError:
                pass
        c.setAttr(handle + ".ty", 0)
        fit_joint = self._original_restore_leaf(joint).split("_", 1)[0].replace("Joint", "", 1)
        if c.objExists(fit_joint + ".falloffRadius"):
            c.setAttr(fit_joint + ".falloffRadius", radius)
        if c.objExists(fit_joint):
            if not c.objExists(fit_joint + ".falloffCurve"):
                c.addAttr(fit_joint, longName="falloffCurve", dataType="string")
            commands = []
            for index in range(int(c.getAttr(soft + ".falloffCurve", size=True))):
                for attr in ("Position", "Interp", "FloatValue"):
                    plug = f"TempSoftMod.falloffCurve[{index}].falloffCurve_" + attr
                    commands.append("setAttr " + plug + " " + str(c.getAttr(plug)) + ";")
            c.setAttr(fit_joint + ".falloffCurve", "".join(commands), type="string")
        c.delete("tempMesh")
        if c.objExists("tempSoftModCopy"):
            c.delete("tempSoftModCopy")
        raw.select(selection, replace=True)
        return len(vertices)
