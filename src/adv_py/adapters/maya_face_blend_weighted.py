"""Literal Face use of asEnsureBlendWeighted / asEnsureSDKcurvesNamed.

Source: ADV 6.925, 65647–65803. Keep attribute spellings, graph ownership,
existing-input preservation and output-driver reconnection from the MEL.
"""
from contextlib import nullcontext
import re


class MayaFaceBlendWeightedMixin:
    @staticmethod
    def original_face_sdk_attribute(node, attribute):
        """asAttrToAttribute expands TRS short names only, preserving aliases."""
        channels = {short + axis.lower(): long + axis
                    for short, long in (("t", "translate"), ("r", "rotate"), ("s", "scale"))
                    for axis in "XYZ"}
        return channels.get(attribute, attribute)

    def original_face_control_bw_name(self, plug):
        tokens = re.split(r"[.\[\]]", plug)
        node, attribute = tokens[0], tokens[1]
        attribute = self.original_face_sdk_attribute(node, attribute)
        return "bw" + node + "_" + attribute

    def ensure_original_face_blend_weighted(self, plug, *, output=False):
        c = self._cmds
        node, attribute = plug.split(".", 1)
        if c.nodeType(node) == "blendWeighted":
            return node
        attribute = self.original_face_sdk_attribute(node, attribute)
        driven = node + "." + attribute
        name = "bw" + driven.replace(".", "_").replace("[", "_").replace("]", "_")
        if not c.objExists(name):
            c.createNode("blendWeighted", name=name)
            face = (c.objExists("FaceAllSet") and c.sets(node, isMember="FaceAllSet")) or c.objExists("FaceBuildingSets")
            owner = "FaceAllSet" if face else "AllSet"
            if c.objExists(owner) and c.sets(node, isMember=owner):
                c.sets(name, add=owner)
            if not output:
                previous = c.listConnections(driven, source=True, destination=False, plugs=True) or []
                if previous:
                    c.connectAttr(previous[0], name + ".input[0]", force=True)
                c.connectAttr(name + ".output", driven, force=True)
        if output and not c.isConnected(driven, name + ".input[0]", ignoreUnitConversion=True):
            # Source drivers may be external, but the BW being written belongs
            # to this character. A driver source is a read, as in native SDK.
            raw = getattr(c, "raw", c)
            with c._creation_namespace() if hasattr(c, "_creation_namespace") else nullcontext():
                raw.connectAttr(self.scene_address(driven), self.scene_address(name) + ".input[0]", force=True)
        return name

    def name_original_face_sdk_curves(self):
        """asEnsureSDKcurvesNamed, restricted to this host's character graph."""
        c = self._cmds
        renamed = []
        for transform in c.ls("*SDK*_*", type="transform") or []:
            paths = c.ls(transform, long=True) or []
            if not paths:
                continue
            ancestors = [part.rsplit(":", 1)[-1] for part in paths[0].split("|")]
            if "MotionSystem" not in ancestors and "FaceMotionSystem" not in ancestors:
                continue
            face = "FaceMotionSystem" in ancestors
            for weighted in c.listConnections(transform, source=True, destination=False,
                                               skipConversionNodes=True) or []:
                for curve in c.listConnections(weighted, source=True, destination=False,
                                                 skipConversionNodes=True) or []:
                    leaf = curve.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                    if not leaf.startswith("animCurve"):
                        continue
                    destinations = c.listConnections(weighted + ".output", source=False,
                        destination=True, skipConversionNodes=True, plugs=True) or []
                    if not destinations:
                        continue
                    node, attribute = destinations[0].split(".", 1)
                    name = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1] + "_" + attribute
                    curve = c.rename(curve, name)
                    renamed.append(curve)
                    owner = "FaceAllSet" if face else "AllSet"
                    if c.objExists(owner) and c.sets(transform, isMember=owner):
                        c.sets(curve, add=owner)
        return tuple(renamed)
