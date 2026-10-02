"""Ordered native asFaceRebuildRestore, source 40212–40576.

The source BlendShapes branch only compares names; it does not copy targets.
That behavior is retained explicitly rather than claiming target restoration.
"""
from adv_py.core.face_original_build import OriginalFaceKeepOptions
from adv_py.application.face_pre import FacePreRole
from .maya_face_restore_controls import MayaFaceRestoreControlsMixin
from .maya_face_restore_drivers import MayaFaceRestoreDriversMixin


class MayaFaceRestoreMixin(MayaFaceRestoreControlsMixin, MayaFaceRestoreDriversMixin):
    def restore_original_face_skin_weights(self, options):
        c = self._cmds
        raw = getattr(c, "raw", c)
        restored = []
        # The source tests keepSkinWeights alone, not keepAll here.
        if not options.skin_weights or not c.objExists("prefix_asFaceSkinWeightsHolder"):
            return ()
        for holder in c.ls("prefix_asFaceSkinWeightsHolder*", type="transform") or []:
            if not c.objExists(holder + ".sourceObject"):
                continue
            geometry = c.getAttr(holder + ".sourceObject")
            mesh = self.scene_address(geometry)
            if not raw.objExists(mesh):
                continue
            old_skin = self.original_face_bs_skin(holder)
            skin = self.original_face_bs_skin(geometry)
            if options.added_joints:
                influences = raw.listConnections(skin + ".matrix", source=True, destination=False, type="joint") or []
                identities = {uid for joint in influences for uid in raw.ls(joint, uuid=True) or []}
                for old_joint in raw.listConnections(old_skin + ".matrix", source=True, destination=False, type="joint") or []:
                    joint = self._original_restore_leaf(old_joint).replace("prefix_", "", 1)
                    if not c.objExists(joint):
                        continue
                    address = self.scene_address(joint)
                    if identities.intersection(raw.ls(address, uuid=True) or []):
                        continue
                    raw.skinCluster(skin, edit=True, addInfluence=address, lockWeights=False, weight=0)
                    parents = c.listRelatives(joint, parent=True) or []
                    if parents and self._original_restore_leaf(parents[0]).startswith("prefix_"):
                        parent = self._original_restore_leaf(parents[0]).replace("prefix_", "", 1)
                        c.parent(joint, parent)
            raw.select((self.scene_address(holder), mesh), replace=True)
            raw.copySkinWeights(sourceSkin=old_skin,destinationSkin=skin,
                noMirror=True, surfaceAssociation="closestPoint", influenceAssociation="closestJoint")
            restored.append(geometry)
        return tuple(restored)

    def restore_original_face(self, options=None):
        """Restore the captured graph in the existing build transaction."""
        self._require_transaction()
        c = self._cmds
        if not c.objExists("prefix_FaceGroup"):
            return None
        options = options or OriginalFaceKeepOptions()
        geometry = self.read_face_objects(FacePreRole.FACE)[0]
        controls = tuple(c.sets("FaceControlSet", query=True) or [])
        correctives = tuple(c.ls("*Corrective*", recursive=True, type="blendShape") or [])
        self._transaction_changed = True
        self.restore_original_face_user_attributes()
        weights = self.restore_original_face_skin_weights(options)
        drivers = self.restore_original_face_driving_systems() if options.all or options.driving_systems else 0
        squash = False
        if (options.all or options.head_squash) and c.objExists("prefix_SquashSetup"):
            before = self.capture_face_build_node_ids()
            result = self.create_head_squash(self.capture_head_squash_input())
            self.register_head_squash_nodes(before)
            self.extend_face_build_pose(result.controls)
            if c.objExists("prefix_SquashSetup.optimizedSquash"):
                self.optimize_head_squash()
            squash = True
        common_targets = {}
        if (options.all or options.blend_shapes) and c.objExists("asFaceBS"):
            for node in c.ls("asFaceBS*", type="blendShape") or []:
                old = "prefix_" + self._original_restore_leaf(node)
                if c.objExists(old):
                    previous = self._original_face_blendshape_aliases(old)
                    common_targets[node] = tuple(name for name in self._original_face_blendshape_aliases(node) if name in previous)
                    # MEL says "to be connected.." and performs no mutation.
        if (options.all or options.corrective_shapes) and correctives:
            self.restore_original_face_correctives(geometry, correctives)
        if options.all or options.curve_shapes:
            self.restore_original_face_control_shapes(controls)
        oriented = self.restore_original_face_custom_orient(controls) if options.all or options.custom_orient else False
        if not c.objExists("faceBuildPose.udExtraAttr") and c.objExists("prefix_faceBuildPose.udExtraAttr"):
            c.addAttr("faceBuildPose", longName="udExtraAttr", dataType="string")
            c.setAttr("faceBuildPose.udExtraAttr", c.getAttr("prefix_faceBuildPose.udExtraAttr"), type="string")
        # Original deliberately deletes members before their parent group to
        # avoid invalid transformGeometry evaluation during hierarchy deletion.
        if c.objExists("prefix_FaceAllSet"):
            # Native Skin edits during the new build may create another root
            # dagPose on the retained old set. Resolve ownership immediately
            # before deleting that set's graph, as well as before capture.
            self.normalize_original_face_bind_pose_ownership("prefix_FaceAllSet")
            members = c.sets("prefix_FaceAllSet", query=True) or []
            if members:
                c.delete(members)
        if c.objExists("prefix_FaceGroup"):
            c.delete("prefix_FaceGroup")
        if c.objExists("prefix_FaceControlSet"):
            custom = c.sets("prefix_FaceControlSet", query=True) or []
            if custom:
                c.sets(custom, add="FaceControlSet")
            c.delete("prefix_FaceControlSet")
        return {"skin_weights": weights, "sdk_curves": drivers, "head_squash": squash,
                "custom_orient": oriented, "compared_blendshape_targets": common_targets,
                "original_stage": "asFaceRebuildRestore"}
