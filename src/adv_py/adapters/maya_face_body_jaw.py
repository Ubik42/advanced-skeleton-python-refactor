"""asFaceRemoveBodyJaw with Python pose/registration maintenance."""
import json
from .maya_face_body_roles import face_body_fk_offset
from .maya_original_control_identity import source_control_from_role
from adv_py.core.character_registry import REGISTRY_NAME
from adv_py.core.original_build_pose_cleanup import original_build_pose_commands
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_original_eye_ball_fit import remove_original_skin_influence

class MayaFaceBodyJawMixin:
    def remove_original_body_jaw_for_face(self):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        if not c.objExists(source_control_from_role(self, "FKJaw_M")): return False
        if not c.objExists("Jaw_M") or c.nodeType("Jaw_M")!="joint":
            raise FitSkeletonValidationError("Body Jaw 来源与原版不一致")
        accepted=True
        if not c.objExists('headTopology') and not c.objExists('asBatch'):
            accepted=raw.confirmDialog(title='Confirm',
                message='This will replace the Jaw from the Body-setup',
                button=['OK','Cancel'],defaultButton='OK',dismissString='Cancel')=='OK'
        # Decode while every old member still exists; do not invalidate the
        # registry by deleting its members before recording the old schema.
        registration=None
        if c.objExists(REGISTRY_NAME):
            registration=self.read_character_registration()
        jaw=self.scene_address("Jaw_M")
        self._transaction_changed=True
        # The native procedure removes the Body Jaw even when the dialog
        # returns Cancel; its return value only controls subsequent Fit creation.
        for skin in raw.ls(type="skinCluster") or []:
            remove_original_skin_influence(raw,jaw,skin)
        for node in (face_body_fk_offset(self, "Jaw_M"),"Jaw_M","Jaw"):
            if c.objExists(node): c.delete(node)
        self._prune_original_body_pose_after_jaw()
        if registration is not None:
            from .maya_original_export_preparation import MayaOriginalExportPreparationHost
            joined=MayaOriginalExportPreparationHost.__new__(MayaOriginalExportPreparationHost)
            joined.__dict__=self.__dict__
            joined._remember_export_preparation(registration)
        return accepted

    def _prune_original_body_pose_after_jaw(self):
        """asRemoveUnusedfromBuildPose plus the existing Python JSON pose rows."""
        c=self._cmds
        for pose in ("buildPose","bodyBuildPose"):
            if not c.objExists(pose): continue
            if c.objExists(pose+".advPyPoseData"):
                rows=json.loads(c.getAttr(pose+".advPyPoseData") or "[]")
                rows=[row for row in rows if c.objExists(row[0]+"."+row[1])]
                c.setAttr(pose+".advPyPoseData",json.dumps(rows,separators=(",",":")),type="string")
            for attr in ("udAttr","udExtraAttr"):
                if not c.objExists(pose+"."+attr): continue
                text=original_build_pose_commands(c.getAttr(pose+"."+attr) or '',c.objExists)
                c.setAttr(pose+"."+attr,text,type="string")
        if c.objExists("FitSkeleton.advPyBuildPoseOverrides"):
            rows=json.loads(c.getAttr("FitSkeleton.advPyBuildPoseOverrides") or "[]")
            rows=[row for row in rows if c.objExists(row[0]+"."+row[1])]
            c.setAttr("FitSkeleton.advPyBuildPoseOverrides",json.dumps(rows,separators=(",",":")),type="string")
