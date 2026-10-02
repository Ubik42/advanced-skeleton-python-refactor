"""Original edit-history driven SDK and corrective restoration, 40342–40487."""


class MayaFaceRestoreDriversMixin:
    def prepare_original_face_restore_dependencies(self, options=None):
        """Prepare native SDK swaps before opening the rebuild undo chunk."""
        from adv_py.core.face_original_build import OriginalFaceKeepOptions
        options = options or OriginalFaceKeepOptions()
        if not (options.all or options.driving_systems):
            return
        c = self._cmds
        # Restoring a missing user attribute creates a new *_tweaked marker
        # later, even when the old rig had no edit-history node. Prepare for
        # any existing Face rebuild, not just already recorded SDK edits.
        if c.objExists("FaceGroup") or c.objExists("prefix_FaceGroup"):
            from .maya_native_node_cast import prepare_native_node_cast
            prepare_native_node_cast(self)

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
                    output_bw = self._original_restore_leaf(old_outputs[0] if old_outputs else "").replace("prefix_", "", 1)
                    if c.objExists(curve):
                        # Native nodeCast swaps the node payload/connections;
                        # copying only keys would lose curve type and settings.
                        from .maya_native_node_cast import native_node_cast
                        native_node_cast(self, old_curve, curve, swap_names=True)
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
                        destination = target + ".input[" + str(c.getAttr(target + ".input", size=True)) + "]"
                        c.connectAttr(curve + ".output", destination, force=True)
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
        return self.ensure_original_face_blend_weighted(plug)
