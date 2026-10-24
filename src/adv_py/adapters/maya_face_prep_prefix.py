"""Original asFacePrep previous-rig capture, MEL 31357–31500.

This internal stage preserves the source prefix graph and weight holders.
The full native Face build calls this stage before regenerating Skin, then
restores the captured graph through asFaceRebuildRestore's Python port.
"""


import json

from .maya_original_skin_history import bind_original_skin, remove_unused_for_skin


class MayaFacePrepPrefixMixin:
    def capture_original_face_previous_rig(self, source):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        self.normalize_original_face_bind_pose_ownership()
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
        self._capture_original_face_external_bind_pre(prefix, source["skin"])
        holders = []
        number = 1
        for geometry in source["all_head"]:
            if geometry == source["geometry"]:
                name = "asFaceSkinWeightsHolder"
                skin = source["skin"]
            else:
                name = "asFaceSkinWeightsHolder" + str(number)
                skin = self.original_face_bs_skin(geometry)
            self._capture_original_face_weight_holder(geometry,skin,name,prefix)
            holders.append(name)
            number += 1
        # MEL captures one holder per All Head object. Do not invent extra
        # layer holders or delete upstream Skins while sampling the new rig.
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
        remove_unused_for_skin(raw, skin)
        self._original_prefix_lock_joints(False)
        for geometry in source["all_head"]:
            if geometry == source["geometry"]:
                continue
            skin = self.original_face_bs_skin(geometry)
            try:
                raw.skinPercent(skin, self.scene_address(geometry), transformValue=((head, 1),))
            except RuntimeError:
                pass
            remove_unused_for_skin(raw, skin)
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
            if leaf.startswith("prefix_"):
                # Renaming a transform may already rename its Shape. The MEL
                # walk then skips that Shape because its old name is gone.
                renamed.append(node)
                continue
            renamed.append(c.rename(node, "prefix_" + leaf))
        c.parent("prefix_FaceMotionSystem", "prefix_FaceDeformationSystem", prefix)
        for node in c.listRelatives(prefix, allDescendents=True, type="transform") or []:
            leaf = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if not leaf.startswith("prefix_"):
                c.rename(node, "prefix_" + leaf)
        self._transaction_changed = True
        return {"prefix_group": prefix, "weight_holders": tuple(holders), "renamed_nodes": tuple(renamed)}

    def _capture_original_face_external_bind_pre(self, prefix, primary_skin):
        """Retain bind data on surviving Face-part Skins before old joints go."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        primary = set(raw.ls(self.scene_address(primary_skin), uuid=True) or [])
        rows = []
        for skin in raw.ls(type="skinCluster") or []:
            identity = raw.ls(skin, uuid=True) or []
            if len(identity) != 1:
                continue
            key = "@primary" if identity[0] in primary else identity[0]
            for index in raw.getAttr(skin + ".matrix", multiIndices=True) or []:
                plug = f"{skin}.matrix[{index}]"
                source = raw.connectionInfo(plug, sourceFromDestination=True)
                if not source:
                    continue
                joints = raw.ls(source.split(".", 1)[0], long=True, type="joint") or []
                if len(joints) != 1 or not any(
                    part.rsplit(":", 1)[-1] == "FaceJoint_M"
                    for part in joints[0].split("|")[:-1]
                ):
                    continue
                bind_pre = f"{skin}.bindPreMatrix[{index}]"
                if raw.connectionInfo(bind_pre, sourceFromDestination=True):
                    continue
                value = raw.getAttr(bind_pre)
                if len(value) == 1 and isinstance(value[0], (tuple, list)):
                    value = value[0]
                rows.append((key, joints[0].rsplit("|", 1)[-1],
                             tuple(float(item) for item in value)))
        c.addAttr(prefix, longName="advPyExternalBindPre", dataType="string")
        c.setAttr(prefix + ".advPyExternalBindPre", json.dumps(rows), type="string")

    def _capture_original_face_weight_holder(self,geometry,skin,name,prefix):
        """Native holder for one production Skin, retaining source joint names."""
        c=self._cmds; raw=getattr(c,"raw",c)
        c.polySphere(name=name,radius=1,subdivisionsX=20,subdivisionsY=20,
                     axis=(0,1,0),createUVs=2,constructionHistory=False)
        shape=c.listRelatives(name,shapes=True,noIntermediate=True,fullPath=True)[0]
        mesh=self.scene_address(geometry); address=self.scene_address(skin)
        raw.connectAttr(mesh+".outMesh",self.scene_address(shape)+".inMesh")
        raw.refresh()
        raw.disconnectAttr(mesh+".outMesh",self.scene_address(shape)+".inMesh")
        influences=raw.listConnections(address+".matrix",source=True,
                                       destination=False,type="joint") or []
        bind_original_skin(c, (*influences, name), name+"SC", namespace=self.namespace)
        c.parent(name,prefix)
        raw.copySkinWeights(sourceSkin=address,destinationSkin=self.scene_address(name+"SC"),
            noMirror=True,surfaceAssociation="closestPoint",
            influenceAssociation="closestJoint")
        c.addAttr(name,longName="sourceObject",dataType="string")
        c.setAttr(name+".sourceObject",geometry,type="string")

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
