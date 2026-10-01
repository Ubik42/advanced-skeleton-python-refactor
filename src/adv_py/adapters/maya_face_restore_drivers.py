"""Original edit-history driven SDK and corrective restoration, 40342–40487."""


class MayaFaceRestoreDriversMixin:
    def restore_original_face_driving_systems(self):
        c = self._cmds
        markers = c.listAttr("FaceSetupEditHistory", userDefined=True, string="*_tweaked") or [] if c.objExists("FaceSetupEditHistory") else []
        count = 0
        for marker in markers:
            tokens = marker.split("_")
            driver = tokens[0] + "_" + tokens[1]
            attribute = tokens[2]
            previous = "prefix_" + driver + "." + attribute
            weighted = c.listConnections(previous, source=False, destination=True, type="blendWeighted") or [] if c.objExists(previous) else []
            for old_input in weighted:
                input_bw = self._original_restore_leaf(old_input).replace("prefix_", "", 1)
                if not c.objExists(input_bw):
                    self.original_face_output_bw(driver + "." + attribute)
                curves = c.listConnections(old_input, source=False, destination=True, type="animCurve") or []
                for old_curve in curves:
                    if not self._original_restore_leaf(old_curve).startswith("prefix_"):
                        old_curve = c.rename(old_curve, "prefix_" + self._original_restore_leaf(old_curve))
                    curve = self._original_restore_leaf(old_curve).replace("prefix_", "", 1)
                    old_outputs = c.listConnections(old_curve + ".output", source=False, destination=True, type="blendWeighted") or []
                    output_bw = self._original_restore_leaf(old_outputs[0]).replace("prefix_", "", 1)
                    if c.objExists(curve):
                        # Native nodeCast swaps the node payload/connections;
                        # copying only keys would lose curve type and settings.
                        c.nodeCast(old_curve, curve, swapNames=True)
                    else:
                        c.duplicate(old_curve, name=curve)
                        c.sets(curve, remove="prefix_FaceAllSet")
                        c.connectAttr(input_bw + ".output", curve + ".input")
                        if not c.objExists(output_bw):
                            parts = curve.split("_")
                            output_attribute = parts[2].rstrip("0123456789")
                            node = parts[0].replace("bw", "", 1) + "_" + parts[1]
                            self.original_face_input_bw(node + "." + output_attribute)
                        outputs = c.listConnections(old_curve + ".output", source=False, destination=True,
                                                     skipConversionNodes=True) or []
                        target = self._original_restore_leaf(outputs[0]).replace("prefix_", "", 1)
                        destination = self.next_original_face_bw_input(target)
                        c.connectAttr(curve + ".output", destination)
                    count += 1
        return count

    def restore_original_face_correctives(self, geometry, nodes):
        c = self._cmds
        for node in nodes:
            if c.objExists("asFaceBS") and c.objExists("FaceCorrective"):
                targets = self._original_face_blendshape_aliases("asFaceBS")
                c.blendShape("asFaceBS", edit=True, target=(self.scene_address(geometry), len(targets), "FaceCorrective", 1))
                c.setAttr("asFaceBS.FaceCorrective", 1)
            for curve in c.listConnections(node, source=True, destination=False, type="animCurve") or []:
                nodes_and_inputs = c.listConnections(curve, source=True, destination=False,
                                                     connections=True, type="transform") or []
                plugs = c.listConnections(curve, source=True, destination=False, connections=True,
                                          plugs=True, type="transform") or []
                for index in range(0, len(nodes_and_inputs), 2):
                    driver = nodes_and_inputs[index + 1]
                    if not self._original_restore_leaf(driver).startswith("prefix_") or not c.objExists(driver):
                        continue
                    old_plug = plugs[index + 1]
                    node_name, attr = old_plug.split(".", 1)
                    source = self._original_restore_leaf(node_name).replace("prefix_", "", 1) + "." + attr
                    if c.objExists(source):
                        c.connectAttr(source, nodes_and_inputs[index], force=True)

    def _original_face_blendshape_aliases(self, node):
        """Literal asFixMaya2025ListAttrBug: strip leading dots when present."""
        c = self._cmds
        values = c.listAttr(node + ".weight", multi=True) or []
        if values and values[0].startswith("."):
            values = [value[1:] if value.startswith(".") else value for value in values]
        return tuple(values)

    def original_face_input_bw(self, plug):
        """asEnsureBlendWeighted's driven direction (65647–65718)."""
        c = self._cmds
        node, attr = plug.split(".", 1)
        if c.nodeType(node) == "blendWeighted":
            return node
        channels = {short + axis.lower(): long + axis for short, long in
                    (("t", "translate"), ("r", "rotate"), ("s", "scale")) for axis in "XYZ"}
        attr = channels.get(attr, attr)
        driven = node + "." + attr
        name = "bw" + driven.replace(".", "_").replace("[", "_").replace("]", "_")
        if c.objExists(name):
            return name
        c.createNode("blendWeighted", name=name)
        face = c.objExists("FaceBuildingSets") or (c.objExists("FaceAllSet") and c.sets(node, isMember="FaceAllSet"))
        owner = "FaceAllSet" if face else "AllSet"
        if c.objExists(owner) and c.sets(node, isMember=owner):
            c.sets(name, add=owner)
        previous = c.listConnections(driven, source=True, destination=False, plugs=True) or []
        if previous:
            c.connectAttr(previous[0], name + ".input[0]", force=True)
        c.connectAttr(name + ".output", driven, force=True)
        return name
