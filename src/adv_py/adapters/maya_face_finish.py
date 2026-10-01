"""Original Face extra driving systems and Extras transfer (39792–39883)."""
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaFaceFinishMixin:
    def create_original_face_extra_drivers(self):
        self._require_transaction()
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return ()
        c.addAttr("ctrlMouth_M",longName="jawForward",attributeType="double",softMaxValue=10,softMinValue=-10,hasMinValue=True,keyable=True)
        self.original_face_output_bw("ctrlMouth_M.jawForward")
        self.add_original_face_sdk("ctrlMouth_M.jawForward","SDKJaw_M.tz",10,2)
        c.addAttr("ctrlMouth_M",longName="jawSide",attributeType="double",softMaxValue=10,softMinValue=-10,hasMinValue=True,keyable=True)
        self.original_face_output_bw("ctrlMouth_M.jawSide")
        self.add_original_face_sdk("ctrlMouth_M.jawSide","SDKJaw_M.ry",10,15)
        position=self._lip_pos("ChinCrease_M")
        control=self.create_original_face_controller("JawPull","_M",2)
        shape=c.listRelatives(control,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".overrideColor",17)
        self.shape_original_face_half_moon(control,-90)
        c.scale(5,5,5,control+".cv[0:99]",relative=True,pivot=(0,0,0))
        c.parent("JawPullOffset_M","SideReverse_M",relative=True)
        c.xform("JawPullOffset_M",worldSpace=True,translation=position)
        self.project_original_face_control(control)
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr(control+"."+attr,lock=True,keyable=False)
        for attr in ("tx","ty"): c.setAttr(control+"."+attr,lock=False,keyable=True)
        self.constrain_original_face("Jaw_M","JawPullOffset_M",maintain_offset=True,force_matrix=True)
        self.add_original_face_sdk(control+".ty","ctrlMouth_M.ty",-1,-1)
        self.add_original_face_sdk(control+".tx","ctrlMouth_M.jawSide",1,10)
        first=c.listConnections(control+".ty",source=False,destination=True) or []
        if not first: raise FitSkeletonValidationError("JawPull 缺少 Mouth 驱动曲线")
        curve=first[0]
        c.setAttr(curve+".preInfinity",4); c.setAttr(curve+".postInfinity",0)
        self.add_original_face_sdk(control+".ty","ctrlLips_M.ty",1,1)
        second=[node for node in c.listConnections(control+".ty",source=False,destination=True) or [] if node!=curve]
        if not second: raise FitSkeletonValidationError("JawPull 缺少 Lips 驱动曲线")
        c.setAttr(second[0]+".preInfinity",0); c.setAttr(second[0]+".postInfinity",4)
        return (control,)

    def transfer_original_face_extras(self):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        geometry=self.read_face_objects(FacePreRole.FACE)[0]
        head=c.getAttr(fit+".HeadJoint"); skin=self.original_face_production_skin(geometry,head)
        extras=self.read_original_face_parts("Extras")
        joints=tuple(c.listRelatives("FaceJoint_M",allDescendents=True,type="joint") or [])+("FaceJoint_M",)
        result=[]; head_uuid=set(raw.ls(self.scene_address(head),uuid=True) or [])
        for mesh in extras:
            sc=self._original_face_skin_history(mesh)
            if sc and set(raw.ls(sc,uuid=True) or [])==set(raw.ls(self.scene_address(skin),uuid=True) or []): continue
            if not sc:
                with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
                    sc=raw.skinCluster(mesh,self.scene_address(head),toSelectedBones=True,maximumInfluences=1,
                        dropoffRate=4,removeUnusedInfluence=False)[0]
            existing={uid for inf in raw.listConnections(sc,source=True,destination=False,type="joint") or [] for uid in raw.ls(inf,uuid=True) or []}
            additions=[]
            for joint in joints:
                address=self.scene_address(joint); uid=set(raw.ls(address,uuid=True) or [])
                if uid!=head_uuid and not uid & existing: additions.append(address)
            if additions: raw.skinCluster(sc,edit=True,addInfluence=additions)
            raw.select((self.scene_address(geometry),mesh),replace=True)
            raw.copySkinWeights(noMirror=True,surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            # Maya removeUnusedForSkin removes only exactly-zero influences.
            if raw.skinCluster(sc,query=True,removeUnusedInfluence=True):
                raw.skinCluster(sc,edit=True,removeUnusedInfluence=True)
            result.append(sc)
        c.select(clear=True)
        return tuple(result)

    def preflight_original_face_finish(self):
        c=self._cmds; fit=self._fit(required=True)
        for name in ("FaceJoint_M","FaceGroup","FaceControlSet","FaceAllSet","FaceAreas","FaceBuildingSets","allBeforeFaceBuild","faceBuildPose"):
            if not c.objExists(name): raise FitSkeletonValidationError("Face Finish 缺少前置节点："+name)
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("Face Finish 需要唯一 Face 网格")
        head=c.getAttr(fit+".HeadJoint")
        return geometry[0],self.original_face_production_skin(geometry[0],head)

    def finish_original_face(self,source):
        """asFaceFinish's ordinary joint-rig branch, source 39884–40063."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        geometry,skin=source
        controls=self.create_original_face_extra_drivers()
        skins=self.transfer_original_face_extras()
        self.hide_original_face_controllers(False)
        c.setAttr("ctrlBox2.v",1); c.setAttr("ctrlBox.EyeCtrlVis",0); c.setAttr("ctrlBox.AimCtrlVis",1)
        self.unlock_original_face_skin_influences((skin,*skins))
        raw.select(self.scene_address(geometry),replace=True)
        raw.skinPercent(self.scene_address(skin),pruneWeights=.01)
        joints=tuple(c.listRelatives("FaceJoint_M",allDescendents=True,type="joint") or [])+("FaceJoint_M",)
        for joint in joints: c.setAttr(joint+".radius",.1 if "LidMain" in joint or "LipJoint" in joint else .2)
        constraints=c.listRelatives("FaceJoint_M",allDescendents=True,type="constraint") or []
        if constraints: c.parent(constraints,"DeformJointConstraints")
        if c.objExists("FaceControlOrient"):
            if not c.objExists("FaceFitControlOrient"): c.createNode("transform",name="FaceFitControlOrient",parent=fit)
            c.parent("FaceControlOrient","FaceFitControlOrient"); c.setAttr("FaceControlOrient.v",0)
        for node in ("tempLocFlip","FaceBuildInProgress","DeformationLayers","SmileBulgePulled","FrownBulgePulled"):
            if c.objExists(node): c.delete(node)
        if not (c.objExists(fit+".NonSym") and c.getAttr(fit+".NonSym")):
            for node in c.listRelatives(fit,children=True,type="transform") or []:
                if node.endswith("Left"): c.delete(node)
        if c.objExists("eyeLidAreaLeft"):
            members=c.sets("eyeLidAreaLeft",query=True) or []
            if members: raw.sets(tuple(self.scene_address(member) for member in members),add=self.scene_address("eyeLidArea"))
            c.delete("eyeLidAreaLeft")
        if c.objExists(fit+".RobloxHead") and c.getAttr(fit+".RobloxHead"):
            self.create_original_face_roblox_head()
        for option in ("ARKit", "SnapChat"):
            if c.objExists(fit+"."+option) and c.getAttr(fit+"."+option):
                self.connect_original_face_arkit()
        if c.objExists(fit+".MultiSkinClusters") and c.getAttr(fit+".MultiSkinClusters"):
            for before,after in (("EyeLidSC","JawSC"),("JawSC","CageSC")):
                if c.objExists(before) and c.objExists(after):
                    raw.reorderDeformers(self.scene_address(before),self.scene_address(after),self.scene_address(geometry))
        # Capture all current keyable values, matching the source's final pose
        # rewrite, and keep the typed Python pose representation synchronized.
        members=tuple(c.sets("FaceControlSet",query=True) or [])
        self._write_face_pose_numeric_rows(self._face_pose_rows(members))
        if not c.objExists("FaceGroup.version"): c.addAttr("FaceGroup",longName="version",attributeType="double")
        c.setAttr("FaceGroup.version",lock=False); c.setAttr("FaceGroup.version",6.925,lock=True)
        if c.objExists(fit+".buildCompleted"): c.setAttr(fit+".buildCompleted",1)
        before=c.sets("allBeforeFaceBuild",query=True) or []
        old=set(c.ls(before,uuid=True) or []) if before else set()
        descendants=c.listRelatives(fit,allDescendents=True,fullPath=True) or []
        fit_nodes=set(c.ls(descendants,uuid=True) or []) if descendants else set()
        all_nodes=[]
        for node in c.ls(objectsOnly=True) or []:
            if c.nodeType(node) in ("objectSet","partition"): continue
            if set(c.ls(node,uuid=True) or []) & (old|fit_nodes): continue
            if c.nodeType(node)=="mesh" and c.getAttr(node+".intermediateObject"): continue
            all_nodes.append(node)
        all_nodes.extend(c.sets("FaceAreas",query=True) or []); all_nodes.append("FaceAreas")
        if all_nodes: c.sets(all_nodes,add="FaceAllSet")
        c.sets("allBeforeFaceBuild",remove="FaceBuildingSets")
        temporary=c.sets("FaceBuildingSets",query=True) or []
        if temporary: c.delete(temporary)
        for node in c.ls(type="unitConversion") or []:
            leaf=node.rsplit("|",1)[-1].rsplit(":",1)[-1]
            if leaf.startswith("unitConversion") and c.sets(node,isMember="FaceAllSet"):
                incoming=c.listConnections(node,source=True,destination=False,plugs=True) or []
                if incoming: c.rename(node,incoming[0].replace(".","_")+"UC")
        self.apply_face_build_pose(self.read_face_build_pose())
        for node in raw.listHistory(self.scene_address(geometry)) or []:
            if raw.nodeType(node)=="deltaMush": raw.setAttr(node+".envelope",1)
        self._finish_original_face_history()
        if c.objExists(fit+".RigType") and int(c.getAttr(fit+".RigType")) > 0 and not c.objExists("asFaceBS"):
            from adv_py.core.face_blendshape_conversion import FaceBlendShapeConversionOptions
            self.convert_original_face_to_blendshapes(FaceBlendShapeConversionOptions(
                keep_joints=int(c.getAttr(fit+".RigType")) == 2, keep_targets=False))
        if c.objExists(fit+".postRebuildScript"):
            script=c.getAttr(fit+".postRebuildScript")
            if script:
                # User-authored MEL hook is preserved as a hook, not used to
                # implement any of the ported Face procedures.
                from maya import mel
                mel.eval(script)
        raw.cycleCheck(evaluation=True)
        c.sets(clear="allBeforeFaceBuild"); c.delete("allBeforeFaceBuild")
        c.select(clear=True)
        self._transaction_changed=True
        return {"controls":controls,"production_skins":skins,"finished":True}

    def _finish_original_face_history(self):
        c=self._cmds
        for control in c.sets("FaceControlSet",query=True) or []:
            nodes=[]
            for future in (False,True):
                nodes.extend(c.listHistory(control,future=future,leaf=False,interestLevel=1,pruneDagObjects=True) or [])
            nodes.extend(c.listRelatives(control,shapes=True,fullPath=True) or [])
            for node in dict.fromkeys(nodes):
                if c.objExists(node+".isHistoricallyInteresting") and c.sets(node,isMember="FaceAllSet"):
                    c.setAttr(node+".isHistoricallyInteresting",0)
