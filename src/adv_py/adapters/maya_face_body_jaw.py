"""asFaceRemoveBodyJaw with Python pose/registration maintenance."""
from dataclasses import replace
import json
from adv_py.core.character_registry import REGISTRY_NAME,encode_registration
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaFaceBodyJawMixin:
    def remove_original_body_jaw_for_face(self):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        if not c.objExists("FKJaw_M"): return False
        if not c.objExists("Jaw_M") or c.nodeType("Jaw_M")!="joint":
            raise FitSkeletonValidationError("Body Jaw 来源与原版不一致")
        # Decode while every old member still exists; do not invalidate the
        # registry by deleting its members before recording the old schema.
        registration=None
        if c.objExists(REGISTRY_NAME):
            registration=self.read_character_registration()
        jaw=self.scene_address("Jaw_M")
        jaw_ids=set(raw.ls(jaw,uuid=True) or [])
        self._transaction_changed=True
        for skin in raw.ls(type="skinCluster") or []:
            influences=raw.skinCluster(skin,query=True,influence=True) or []
            if not any(jaw_ids & set(raw.ls(inf,uuid=True) or []) for inf in influences): continue
            if len(influences)==1: raw.delete(skin)
            else: raw.skinCluster(skin,edit=True,removeInfluence=jaw)
        for node in ("FKOffsetJaw_M","Jaw_M","Jaw"):
            if c.objExists(node): c.delete(node)
        self._prune_original_body_pose_after_jaw()
        if registration is not None:
            body=tuple(joint for joint in registration.body if c.objExists(joint.path))
            channels=tuple(channel for channel in registration.channels if c.objExists(channel.node+"."+channel.attribute))
            spaces=replace(registration.spaces,spaces=tuple(spec for spec in registration.spaces.spaces
                if all(c.objExists(node) for node in (*spec.targets,*spec.sources))))
            # Re-snapshot remaining inputs; deletion can remove a message/input
            # edge on a surviving helper without deleting that helper itself.
            nodes=tuple(self.capture_character_registration_node(node.path) for node in registration.nodes
                        if c.objExists(node.path))
            updated=replace(registration,body=body,channels=channels,nodes=nodes,spaces=spaces)
            if c.objExists(registration.container+".advPyBodyJointCount"):
                c.setAttr(registration.container+".advPyBodyJointCount",len(body),lock=False)
                c.setAttr(registration.container+".advPyBodyJointCount",lock=True)
            c.setAttr(REGISTRY_NAME+".advPyRegistryDocument",lock=False)
            c.setAttr(REGISTRY_NAME+".advPyRegistryDocument",encode_registration(updated),type="string")
            c.setAttr(REGISTRY_NAME+".advPyRegistryDocument",lock=True)
            c.setAttr(REGISTRY_NAME+".members",lock=False)
            for index in c.getAttr(REGISTRY_NAME+".members",multiIndices=True) or []:
                plug=REGISTRY_NAME+f".members[{index}]"
                incoming=c.listConnections(plug,source=True,destination=False,plugs=True) or []
                for source in incoming: c.disconnectAttr(source,plug)
            for index,node in enumerate(updated.nodes):
                c.connectAttr(node.path+".message",REGISTRY_NAME+f".members[{index}]")
            c.setAttr(REGISTRY_NAME+".members",lock=True)
        return True

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
                statements=[]
                for statement in (c.getAttr(pose+"."+attr) or "").split(";"):
                    parts=statement.strip().split()
                    if len(parts)<2: continue
                    address=parts[-2 if "." in statement else -1].strip('"')
                    if c.objExists(address): statements.append(statement.strip()+";")
                c.setAttr(pose+"."+attr,"".join(statements),type="string")
        if c.objExists("FitSkeleton.advPyBuildPoseOverrides"):
            rows=json.loads(c.getAttr("FitSkeleton.advPyBuildPoseOverrides") or "[]")
            rows=[row for row in rows if c.objExists(row[0]+"."+row[1])]
            c.setAttr("FitSkeleton.advPyBuildPoseOverrides",json.dumps(rows,separators=(",",":")),type="string")
