"""Original asFacePrep previous-rig capture, MEL 31357–31500.

This internal stage preserves the source prefix graph and weight holders.
It is not an exposed rebuild operation until restoration is connected.
"""


class MayaFacePrepPrefixMixin:
    def capture_original_face_previous_rig(self, source):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        if c.objExists("prefix_FaceGroup"):
            raise ValueError("旧 Face 捕获尚未恢复，prefix_FaceGroup 已存在")
        try:
            self.apply_face_build_pose(self.read_face_build_pose())
        except (RuntimeError, ValueError):
            pass  # asFacePrep catchQuiet(asGoToBuildPose faceSetup).
        prefix = c.createNode("transform", name="prefix_FaceGroup")
        c.setAttr(prefix + ".v", False)
        c.addAttr(prefix, longName="version", attributeType="double")
        c.setAttr(prefix + ".version", c.getAttr("FaceGroup.version"), lock=True)
        holders = []
        number = 1
        for geometry in source["all_head"]:
            if geometry == source["geometry"]:
                name = "asFaceSkinWeightsHolder"
                skin = source["skin"]
            else:
                name = "asFaceSkinWeightsHolder" + str(number)
                skin = self._original_pupil_skin(self.scene_address(geometry), exclude_prefix=False)
            c.polySphere(name=name, radius=1, subdivisionsX=20, subdivisionsY=20,
                         axis=(0, 1, 0), createUVs=2, constructionHistory=False)
            mesh = self.scene_address(geometry)
            shape = c.listRelatives(name, shapes=True, noIntermediate=True, fullPath=True)[0]
            raw.connectAttr(mesh + ".outMesh", self.scene_address(shape) + ".inMesh")
            c.polyEvaluate(name, vertex=True)
            raw.disconnectAttr(mesh + ".outMesh", self.scene_address(shape) + ".inMesh")
            influences = raw.listConnections(self.scene_address(skin) + ".matrix",
                                             source=True, destination=False, type="joint") or []
            c.skinCluster(influences, name, toSelectedBones=True, maximumInfluences=3,
                          dropoffRate=4, removeUnusedInfluence=False, name=name + "SC")
            c.parent(name, prefix)
            self._cage_copy_selected((geometry,), (name,))
            c.addAttr(name, longName="sourceObject", dataType="string")
            c.setAttr(name + ".sourceObject", geometry, type="string")
            holders.append(name)
            number += 1
        if (source["keep_all"] or source["keep_custom"]) and c.objExists("FaceCustomSystem"):
            c.parent("FaceCustomSystem", world=True)
        fit = self._fit(required=True)
        if c.objExists(fit + ".RigType") and c.getAttr(fit + ".RigType") == 0:
            shapes = c.ls("asFaceBS*", type="blendShape") or []
            if shapes:
                c.delete(shapes)
                c.delete("asFaceSkinWeightsHolder")
                holders.remove("asFaceSkinWeightsHolder")
        # Existing face joints and Head alone are unlocked for the first flood;
        # all other influences stay locked to preserve non-face body weights.
        self._original_prefix_lock_joints(True)
        head = self.scene_address(source["head"])
        raw.setAttr(head + ".lockInfluenceWeights", False)
        skin = self.scene_address(source["skin"])
        for joint in raw.listConnections(skin + ".matrix") or []:
            paths = raw.ls(joint, long=True) or []
            if paths and any(part.rsplit(":", 1)[-1] == "FaceJoint_M" for part in paths[0].split("|")[:-1]):
                raw.setAttr(joint + ".lockInfluenceWeights", False)
        try:
            raw.skinPercent(skin, self.scene_address(source["geometry"]), transformValue=((head, 1),))
        except RuntimeError:
            pass
        raw.skinCluster(skin, edit=True, removeUnusedInfluence=True)
        self._original_prefix_lock_joints(False)
        for geometry in source["all_head"]:
            if geometry == source["geometry"]:
                continue
            skin = self._original_pupil_skin(self.scene_address(geometry), exclude_prefix=False)
            try:
                raw.skinPercent(skin, self.scene_address(geometry), transformValue=((head, 1),))
            except RuntimeError:
                pass
            raw.skinCluster(skin, edit=True, removeUnusedInfluence=True)
        if c.getAttr("FaceGroup.v"):
            c.setAttr(fit + ".v", lock=False)
            visible = c.getAttr(fit + ".v")
            c.setAttr(fit + ".v", not visible, lock=True)
            c.setAttr("FaceMotionSystem.v", visible)
        self._original_prefix_collect_sdk_curves()
        if c.objExists("SquashSetup"):
            self._original_prefix_remove_squash(prefix)
        nodes = [*(c.sets("FaceAllSet", query=True) or []), "FaceAllSet", "FaceControlSet", "FaceAreas"]
        # Resolve UUIDs before renaming parent transforms; set member paths can
        # otherwise become stale while preserving precisely the same nodes.
        identities = []
        for node in nodes:
            if c.objExists(node):
                identities.extend(c.ls(node, uuid=True) or [])
        renamed = []
        for identity in dict.fromkeys(identities):
            node = self._original_prefix_node_by_uuid(identity)
            if node is None:
                continue
            leaf = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            renamed.append(c.rename(node, "prefix_" + leaf))
        c.parent("prefix_FaceMotionSystem", "prefix_FaceDeformationSystem", prefix)
        for node in c.listRelatives(prefix, allDescendents=True, type="transform") or []:
            leaf = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if not leaf.startswith("prefix_"):
                c.rename(node, "prefix_" + leaf)
        self._transaction_changed = True
        return {"prefix_group": prefix, "weight_holders": tuple(holders), "renamed_nodes": tuple(renamed)}

    def _original_prefix_node_by_uuid(self, identity):
        c = self._cmds
        raw = getattr(c, "raw", c)
        # Querying a UUID is not a logical character name; retain its address.
        nodes = raw.ls(identity, long=True) or []
        return nodes[0] if len(nodes) == 1 else None

    def _original_prefix_lock_joints(self, lock):
        c = self._cmds
        raw = getattr(c, "raw", c)
        for joint in raw.ls(type="joint") or []:
            if raw.objExists(joint + ".lockInfluenceWeights"):
                raw.setAttr(joint + ".lockInfluenceWeights", lock)

    def _original_prefix_collect_sdk_curves(self):
        c = self._cmds
        for node in c.ls("bwSDK*") or []:
            if c.objExists("AllSet") and c.sets(node, isMember="AllSet"):
                continue
            driven = c.listConnections(node, source=False, destination=True) or []
            if driven:
                paths = c.ls(driven[0], long=True) or []
                if paths and paths[0].startswith("|Group|MotionSystem|"):
                    continue
            # Preserve the actual MEL condition, including its inverted comment.
            if c.sets(node, isMember="FaceAllSet"):
                continue
            for curve in c.listConnections(node, skipConversionNodes=True, source=True,
                                           destination=False, type="animCurve") or []:
                if not c.sets(curve, isMember="FaceAllSet"):
                    c.sets(curve, add="FaceAllSet")

    def _original_prefix_remove_squash(self, prefix):
        c = self._cmds
        marker = c.createNode("transform", name="prefix_SquashSetup", parent=prefix)
        if c.objExists("SquashSetup.optimizedSquash"):
            c.addAttr(marker, longName="optimizedSquash", attributeType="bool", defaultValue=True)
        if c.objExists("SquashSet"):
            if c.objExists("squashIKCurveInfo"):
                c.delete("squashIKCurveInfo")
            nodes = c.sets("SquashSet", query=True) or []
            deformers = [node for node in nodes if c.objExists(node) and c.nodeType(node) in ("skinCluster", "ffd", "cluster")]
            if deformers:
                c.delete(deformers)
            remaining = [node for node in nodes if c.objExists(node)]
            if remaining:
                c.delete(remaining)
            c.delete("SquashSet")
        else:
            c.delete("SquashSetup", "SquashControls", "squashFfd")
