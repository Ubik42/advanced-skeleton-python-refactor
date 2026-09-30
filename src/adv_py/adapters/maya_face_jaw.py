"""ADV 6.925 asFaceJawWeighing / Finish, 37805–38316."""
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_jaw import FaceJawInput
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_mouth_open import MayaFaceMouthOpenHost
from .maya_face_jaw_fit import MayaFaceJawFitHost
from .maya_face_teeth import MayaFaceTeethMixin
from .maya_face_jaw_weights import MayaFaceJawWeightsMixin
from .maya_face_jaw_poses import MayaFaceJawPosesMixin

class MayaFaceJawHost(MayaFaceJawPosesMixin,MayaFaceTeethMixin,MayaFaceJawWeightsMixin,MayaFaceMouthOpenHost,MayaFaceJawFitHost):
    def capture_jaw_input(self,smooth_iterations=50):
        c=self._cmds; raw=getattr(c,"raw",c)
        if not c.objExists("upperLipMainCurve"): return None
        if type(smooth_iterations) is not int or smooth_iterations<0: raise ValueError("Jaw 平滑次数必须是非负整数")
        fit=self._fit(required=True)
        meshes=self.read_face_objects(FacePreRole.FACE)
        if len(meshes)!=1: raise FitSkeletonValidationError("Jaw 需要唯一 Face 网格")
        head=c.getAttr(fit+".HeadJoint")
        heads=c.ls(head,long=True,type="joint") or []
        if len(heads)!=1: raise FitSkeletonValidationError("Jaw Head 缺失或不唯一")
        def option(attr): return bool(c.objExists(fit+"."+attr) and c.getAttr(fit+"."+attr))
        required=("FaceJoint_M","FaceBuildInProgress","FaceBuildInProgressHidden","DeformationLayers",
            "FaceAreas","FaceBuildingSets","templateLayer","ctrlBox","SideReverse_M","JawFollow_M",
            "JawStatic_M","JawPivot","Jaw","LipJoints_M","LipRegion_M","upperLip_M","lowerLip_M",
            "Lip_R","Lip_L","lipArea","ctrlMouth_M")
        for node in required:
            if not c.objExists(node): raise FitSkeletonValidationError("Jaw 缺少原版前置节点："+node)
        if c.objExists("FaceFitJawCurves"):
            for node in ("JawCurve","JawCurveMid","JawCurveTop","JawCurveBottom"):
                if not c.objExists(node): raise FitSkeletonValidationError("Jaw Fit 曲线缺失："+node)
        else: self.capture_jaw_fit_input()
        # Multi-layer Lip may already be in the Face history. The original UI
        # retains its original Skin text instead of switching to that layer.
        primary=self.original_face_production_skin(meshes[0],heads[0])
        scale=float(c.getAttr(fit+".faceScale"))
        if scale<=0: raise FitSkeletonValidationError("Jaw faceScale 必须为正")
        return FaceJawInput(meshes[0],heads[0],primary,scale,self.face_use_offset_parent_matrix(),
            option("MultiSkinClusters"),option("LongSnout"),option("NonSym"),
            self.read_original_face_parts("UpperTeeth"),self.read_original_face_parts("LowerTeeth"),
            self.read_original_face_parts("Tongue"),smooth_iterations)

    def original_face_production_skin(self,geometry,head):
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        if c.objExists(fit+".SkinCluster"):
            saved=c.getAttr(fit+".SkinCluster")
            if saved and raw.objExists(saved) and raw.nodeType(saved)=="skinCluster": return saved
        ids=set(raw.ls(self.scene_address(head),uuid=True) or [])
        matches=[]
        for skin in raw.listHistory(self.scene_address(geometry),pruneDagObjects=True) or []:
            if raw.nodeType(skin)!="skinCluster": continue
            influences=raw.skinCluster(skin,query=True,influence=True) or []
            if any(ids & set(raw.ls(inf,uuid=True) or []) for inf in influences): matches.append(skin)
        if len(set(matches))!=1: raise FitSkeletonValidationError("原版 Face 生产 Skin 缺失或不唯一")
        return matches[0]

    def show_original_face_layer_in_transaction(self,layer):
        """asShowLayer; no interactive RigType gate on internal build stages."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        if not c.objExists("DeformationLayers"): return
        normal=layer=="Normal"
        meshes=[]
        for role in (FacePreRole.ALL_HEAD,FacePreRole.FACE):
            meshes.extend(self.scene_address(mesh) for mesh in self.read_face_objects(role))
        for mesh in dict.fromkeys(meshes): raw.setAttr(mesh+".visibility",normal)
        children=c.listRelatives("DeformationLayers",children=True,type="transform") or []
        for node in children:
            c.setAttr(node+".visibility",lock=False); c.setAttr(node+".visibility",False)
        c.select(clear=True)
        c.setAttr("DeformationLayers.visibility",lock=False)
        c.setAttr("DeformationLayers.visibility",not normal,lock=normal)
        if not normal:
            for node in children:
                if node.rsplit("|",1)[-1].startswith(layer+"Layer"):
                    c.setAttr(node+".visibility",True); c.select(node,add=True)

    def add_original_face_multi_skin(self,name,geometry):
        c=self._cmds; raw=getattr(c,"raw",c)
        joint=self._lip_node("joint","MultiSkinClustersFace"+name+"Joint_M","FaceJoint_M")
        c.setAttr(joint+".drawStyle",2); c.setAttr(joint+".inheritsTransform",False,lock=True)
        with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
            raw.skinCluster(self.scene_address(joint),self.scene_address(geometry),multi=True,
                frontOfChain=True,toSelectedBones=True,name=self.scene_address(name+"SC"))
        return name+"SC"

    def unlock_original_face_skin_influences(self,skins):
        c=self._cmds; raw=getattr(c,"raw",c)
        joints=set(self.scene_address(joint) for joint in c.ls(type="joint") or [])
        for skin in skins:
            joints.update(raw.skinCluster(self.scene_address(skin),query=True,influence=True) or [])
        for joint in joints:
            if raw.objExists(joint+".lockInfluenceWeights"): raw.setAttr(joint+".lockInfluenceWeights",False)

    def create_original_jaw_weighing(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self._transaction_changed=True
        self.finish_original_face_fit_stage("CheekRaiser","ctrlCheek","_RL","ty",1,
                                           ("ctrlBoxCheek_R","ctrlBoxCheek_L"))
        if not c.objExists("FaceFitJawCurves"): self.create_jaw_fit_curves(self.capture_jaw_fit_input())
        geometry=self.scene_address(source.geometry)
        if not raw.getAttr(geometry+".visibility",lock=True): raw.setAttr(geometry+".visibility",False)
        for child in c.listRelatives("DeformationLayers",children=True) or []:
            c.setAttr(child+".visibility",False)
        c.duplicate("templateLayer",name="JawLayer",returnRootsOnly=True)
        self._lip_skin("JawLayerSC",(source.head,),"JawLayer")
        self.show_original_face_layer_in_transaction("Jaw")
        self.hide_original_face_controllers(True)
        self.create_original_face_controller("Jaw","_M",2)
        self._lip_node("joint","JawJoint_M","FaceJoint_M")
        c.setAttr("JawJoint_M.segmentScaleCompensate",False)
        pivot=self._lip_pos("JawPivot")
        c.xform("JawOffset_M",worldSpace=True,translation=(0,pivot[1],pivot[2]))
        c.xform("JawJoint_M",worldSpace=True,translation=self._lip_pos("Jaw_M"))
        c.parent("JawOffset_M","SideReverse_M",absolute=True)
        c.setAttr("JawOffset_M.scale",1,1,1)
        self.constrain_original_face("Jaw_M","JawJoint_M",True,force_matrix=False)
        if source.multi_skin_clusters:
            raw.connectAttr(self.scene_address(source.head)+".worldInverseMatrix[0]",
                self.scene_address("JawJointMM_M")+".matrixIn[2]",force=True)
            matrix=raw.getAttr(self.scene_address(source.head)+".worldMatrix[0]")
            c.setAttr("JawJointMM_M.matrixIn[3]",*matrix,type="matrix")
            parent=(c.listRelatives("JawJoint_M",parent=True) or [None])[0]
            c.connectAttr(parent+".worldInverseMatrix[0]","JawJointMM_M.matrixIn[4]")
        c.scale(5,1,5,"Jaw_M.cv[*]",relative=True,pivot=(0,pivot[1],pivot[2]))
        c.scale(1.5,1,1,*(f"Jaw_M.cv[{index}]" for index in (2,4,0,6)),relative=True,pivot=(0,pivot[1],pivot[2]))
        c.scale(1,.4,1,"Jaw_M.cv[1]","Jaw_M.cv[5]",relative=True,pivot=(0,pivot[1],pivot[2]))
        jaw=self._lip_pos("Jaw")
        c.move(0,jaw[1]-pivot[1],(jaw[2]-pivot[2])*1.1,"Jaw_M.cv[*]",relative=True)
        if source.long_snout: self._jaw_long_snout(source)
        self._lip_node("transform","JawMix_M","JawOffset_M")
        for channel,stem in (("translate","JawMixTPMA"),("rotate","JawMixRPMA")):
            plus=self._lip_node("plusMinusAverage",stem)
            c.connectAttr("Jaw_M."+channel,plus+".input3D[0]")
            c.connectAttr("SDKJaw_M."+channel,plus+".input3D[1]")
            c.connectAttr(plus+".output3D","JawMix_M."+channel)
        multiply=self._lip_node("multiplyDivide","JawMixSMPD")
        c.connectAttr("Jaw_M.scale",multiply+".input1"); c.connectAttr("SDKJaw_M.scale",multiply+".input2")
        c.connectAttr(multiply+".output","JawMix_M.scale")
        self.constrain_original_face("Jaw_M","JawFollow_M",True,force_matrix=False)
        teeth=self.create_original_teeth_controls(source)
        c.skinCluster("JawLayerSC",edit=True,addInfluence="JawJoint_M",lockWeights=False,weight=0)
        self._lip_skin("JawCurveSC",("FaceJoint_M","JawJoint_M"),"JawCurve",1)
        c.duplicate("templateLayer",name="JawOpenLayer",returnRootsOnly=True)
        c.parent("JawOpenLayer","FaceBuildInProgress",absolute=True)
        c.setAttr("JawLayer.visibility",False); c.setAttr("JawOpenLayer.visibility",True)
        raw.sets(self.scene_address("JawOpenLayer"),edit=True,forceElement=":initialShadingGroup")
        self._lip_skin("JawOpenLayerSC",("FaceJoint_M","JawJoint_M"),"JawOpenLayer",1)
        c.skinPercent("JawOpenLayerSC","JawOpenLayer.vtx[*]",transformValue=[("FaceJoint_M",1)])
        members=self._jaw_layer_cast(self._jaw_set_members("lipArea"))
        self._jaw_vertex_set("lipAreaJawOpenLayer",tuple(self.scene_address(v) for v in members))
        self.unlock_original_face_skin_influences((source.skin,"JawLayerSC","JawOpenLayerSC"))
        production_skins=self.skin_original_face_teeth(source)
        self.create_mouth_open_design(source.face_scale)
        self.update_jaw_lip_weights((source.geometry,source.non_symmetrical))
        area=self.update_original_jaw_curve_weights(source)
        c.setAttr("JawLayer.visibility",False)
        c.parent("FaceFitJawCurves","FaceBuildInProgress",absolute=True)
        c.parent("mouthOpenSoftModHandle","FaceBuildInProgressHidden",absolute=True)
        c.currentTime(30); c.select(clear=True)
        return {"controls":("Jaw_M",*teeth),"production_skins":(source.skin,*production_skins),"jaw_area":area}

    def _jaw_long_snout(self,source):
        c=self._cmds
        from adv_py.core.face_lip_falloff import lip_control_letter
        for index in range(19):
            for side in ("_R","_L"):
                stem="lowerLip"+lip_control_letter(index)
                ribbon_offset=stem+"RibbonJointOffset"+side
                if not c.objExists(ribbon_offset): break
                follow=self._lip_node("transform",stem+"LongSnoutFollowJaw"+side,ribbon_offset)
                self.constrain_original_face("JawJoint_M",follow,opm=False,pick=True)
                for attr in ("useTranslate","useScale","useShear"):
                    c.setAttr(stem+"LongSnoutFollowJawPM"+side+"."+attr,False)
                revert=self._lip_node("transform",stem+"LongSnoutFollowRevertJaw"+side,ribbon_offset)
                c.parent(revert,follow,absolute=True)
                c.parent(stem+"RibbonJoint"+side,revert,absolute=True)
                attach=stem+"Attach"+side
                ctrl_follow=self._lip_node("transform",stem+"AttachLongSnoutFollowJaw"+side,attach)
                c.connectAttr(follow+".rotate",ctrl_follow+".rotate")
                ctrl_revert=self._lip_node("transform",stem+"AttachLongSnoutFollowRevertJaw"+side,attach)
                c.parent(ctrl_revert,ctrl_follow,absolute=True)
                c.setAttr(stem+"OffsetPMA"+side+".input3D[1]",0,0,0)
                offset=self._lip_node("transform",stem+"AttachLongSnoutFollowRotOffsetJaw"+side,ctrl_revert)
                c.xform(offset,worldSpace=True,translation=self._lip_pos(stem+"Offset"+side))
                c.parent("SDK"+stem+side,offset,relative=True)
        if source.use_offset_parent_matrix and not c.objExists("JawJointDM_M"):
            self._lip_node("decomposeMatrix","JawJointDM_M")
            c.connectAttr("JawJointMM_M.matrixSum","JawJointDM_M.inputMatrix")
        for side in ("_R","_L"):
            follow="lowerLipFollow"+side
            world=self._lip_node("transform","lowerLipAttachLongSnoutFollowJawToWs"+side,follow)
            c.parent(world,world=True); c.setAttr(world+".rotate",0,180 if side=="_R" else 0,0)
            c.parent(world,follow,absolute=True)
            rotate=self._lip_node("transform","lowerLipAttachLongSnoutFollowJaw"+side,world)
            revert=self._lip_node("transform","lowerLipAttachLongSnoutFollowJawRevert"+side,follow)
            c.parent(revert,rotate,absolute=True)
            c.connectAttr("JawJointDM_M.outputRotateX" if source.use_offset_parent_matrix else "JawJoint_M.rx",rotate+".rx")
            c.parent("SDKlowerLip"+side,revert,absolute=True)
        for follicle in c.listRelatives("LipFollicles",children=True) or []:
            leaf=follicle.rsplit("|",1)[-1]
            if not leaf.startswith("lowerfollicle"): continue
            number,side=leaf[len("lowerfollicle"):].rsplit("_",1); side="_"+side
            offset=self._lip_node("transform","lowerLongSnoutOffset"+number+side,follicle)
            c.xform(offset,worldSpace=True,translation=self._lip_pos("lowerLipJoint"+number+side))
            mm=self._lip_node("multMatrix","lowerLongSnoutOffsetMM"+number+side)
            dm=self._lip_node("decomposeMatrix","lowerLongSnoutOffsetDM"+number+side)
            c.connectAttr(offset+".worldMatrix[0]",mm+".matrixIn[0]")
            c.connectAttr("LipFollicles.worldInverseMatrix[0]",mm+".matrixIn[1]")
            c.connectAttr(mm+".matrixSum",dm+".inputMatrix")
            c.connectAttr(dm+".outputTranslate","lowerLipBC"+number+side+".color1",force=True)

    def capture_jaw_finish_input(self,smooth_iterations=50):
        source=self.capture_jaw_input(smooth_iterations)
        if source is None: return None
        c=self._cmds
        if c.objExists("FaceBuildInProgress.JawWeighingFinish"): return source
        required=("JawCurveSC","JawOpenLayer","JawOpenLayerSC","Jaw_M","JawJoint_M",
                  "JawLayer","JawLayerSC","LipRegionOffset_M","lowerLipOffset_M")
        if not source.multi_skin_clusters:
            required+=("ChinCrease_M","lowerFaceStatic_M")
            required+=tuple(stem+side for side in ("_R","_L") for stem in (
                "Cheek","FrownBulge","SmileBulge","CheekBone","JawFollow","lowerFaceStatic","middleFaceStatic"))
        missing=[node for node in required if not c.objExists(node)]
        if missing: raise FitSkeletonValidationError("Jaw 完成阶段缺少原版前置节点："+"、".join(missing))
        return source

    def finish_original_jaw_weighing(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        if c.objExists("FaceBuildInProgress.JawWeighingFinish"): return {"skin":source.skin,"vertices":0,"already_finished":True}
        self._transaction_changed=True
        c.addAttr("FaceBuildInProgress",longName="JawWeighingFinish",attributeType="bool",defaultValue=True)
        c.currentTime(0); c.delete("JawCurveSC")
        c.parent("JawOpenLayer","DeformationLayers",absolute=True)
        skin=self.add_original_face_multi_skin("Jaw",source.geometry) if source.multi_skin_clusters else source.skin
        c.parent("FaceFitJawCurves",self._fit(required=True),absolute=True)
        self.show_original_face_layer_in_transaction("Normal")
        c.setAttr("LipRegionOffset_M.visibility",True); c.setAttr("lowerLipOffset_M.visibility",True)
        if not source.multi_skin_clusters:
            for control,value in (("upperLip_M",0),("lowerLip_M",10),("ChinCrease_M",10)):
                self.add_original_face_follow(control,"JawFollow_M","lowerFaceStatic_M",value)
            for side in ("_R","_L"):
                self.constrain_original_face("Jaw_M","JawFollow"+side,True,force_matrix=False)
                c.setAttr("LipOffset"+side+".visibility",True)
                for control,static,value in (("Lip","lowerFaceStatic",5),("Cheek","middleFaceStatic",5),
                    ("FrownBulge","middleFaceStatic",8),("SmileBulge","middleFaceStatic",2),
                    ("CheekBone","middleFaceStatic",1)):
                    self.add_original_face_follow(control+side,"JawFollow"+side,static+side,value)
                offset=self._lip_node("transform","LipOffsetUnderLipRegion"+side,"LipOffset"+side)
                c.parent(offset,"LipRegionOffset_M",absolute=True)
                for letter in ("A","B"):
                    c.connectAttr(offset+".worldInverseMatrix[0]","LipMM"+letter+side+".matrixIn[2]",force=True)
                    if side=="_L":
                        for arc in ("upper","lower"):
                            central=arc+"LipOffsetUnderLipRegion_M"
                            if letter=="A":
                                self._lip_node("transform",central,arc+"LipOffset_M")
                                c.parent(central,"LipRegionOffset_M",absolute=True)
                            c.connectAttr(central+".worldInverseMatrix[0]",arc+"LipMM"+letter+"_M.matrixIn[2]",force=True)
            self._jaw_finish_lip_roll(source)
        raw.skinCluster(self.scene_address(skin),edit=True,addInfluence=self.scene_address("JawJoint_M"),lockWeights=False,weight=0)
        descendants=c.listRelatives("FaceJoint_M",allDescendents=True,type="joint") or []
        for joint in (*descendants,"FaceJoint_M"):
            if c.objExists(joint+".lockInfluenceWeights"): c.setAttr(joint+".lockInfluenceWeights",True)
        c.setAttr("JawJoint_M.lockInfluenceWeights",False)
        raw.setAttr(self.scene_address(source.head)+".lockInfluenceWeights",False)
        if source.multi_skin_clusters: c.setAttr("MultiSkinClustersFaceJawJoint_M.lockInfluenceWeights",False)
        # Native selectInfluenceVerts preserves the original affected subset.
        raw.select(self.scene_address("JawOpenLayer"),replace=True)
        raw.skinCluster(self.scene_address("JawOpenLayerSC"),edit=True,
                        selectInfluenceVerts=self.scene_address("JawJoint_M"))
        affected=raw.ls(selection=True,long=True,flatten=True) or []
        copied=0
        for vertex in affected:
            if "." not in vertex: continue
            component=vertex.split(".",1)[1]
            value=raw.skinPercent(self.scene_address("JawOpenLayerSC"),vertex,query=True,
                                  transform=self.scene_address("JawJoint_M"))
            raw.skinPercent(self.scene_address(skin),self.scene_address(source.geometry)+"."+component,
                            transformValue=[(self.scene_address("JawJoint_M"),value)])
            copied+=1
        self.unlock_original_face_skin_influences((skin,source.skin,"JawOpenLayerSC"))
        c.currentTime(30)
        for attr in ("ty","tz","rx"):
            self.add_original_face_sdk("ctrlMouth_M.ty","SDKJaw_M."+attr,-1,c.getAttr("Jaw_M."+attr))
        for control in ("Jaw_M","ctrlMouth_M"):
            curves=c.listConnections(control,source=True,destination=False,type="animCurve") or []
            if curves: c.delete(tuple(dict.fromkeys(curves)))
        c.setAttr("ctrlMouth_M.ty",0)
        for attr in ("tx","ry","rz"): c.setAttr("Jaw_M."+attr,lock=False)
        c.xform("Jaw_M",objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
        self.hide_original_face_controllers(True); c.setAttr("ctrlBoxMouth_M.visibility",True)
        return {"skin":skin,"vertices":copied,"already_finished":False}

    def _jaw_finish_lip_roll(self,source):
        c=self._cmds
        joints=c.listRelatives("LipJoints_M",children=True,type="joint") or []
        for joint in joints:
            blends=c.listConnections(joint+".rx",source=True,destination=False,skipConversionNodes=True,type="blendWeighted") or []
            if not blends: raise FitSkeletonValidationError("Jaw Lip RX 缺少原版 BW："+joint)
            blend=blends[0]
            if not c.objExists("lowerLipFollowRXDM_M"):
                self._lip_node("decomposeMatrix","lowerLipFollowRXDM_M")
                c.connectAttr("lowerLipBM_M.outputMatrix","lowerLipFollowRXDM_M.inputMatrix")
            if not source.long_snout:
                c.connectAttr("lowerLipFollowRXDM_M.outputRotateX",blend+".input[6]")
                value=.5+max(0.,min(1.,float(c.getAttr(blend+".weight[5]"))))*.5
                if blend.rsplit("|",1)[-1].startswith("upper"): value=1-value
                if joint.rsplit("|",1)[-1].startswith("cornerLipJoint"): value=.5
                c.setAttr(blend+".weight[6]",value)
        if source.long_snout:
            for joint in joints:
                if not joint.rsplit("|",1)[-1].startswith("lowerLipJoint"): continue
                incoming=c.listConnections(joint+".rx",source=True,destination=False,plugs=True) or []
                if not incoming: raise FitSkeletonValidationError("Long Snout Lip RX 缺少输入")
                c.disconnectAttr(incoming[0],joint+".rx")
                constraint=c.orientConstraint("JawJoint_M",joint,maintainOffset=True)[0]
                c.connectAttr(incoming[0],constraint+".offsetX")
            c.connectAttr("lowerLipConstrainedFleshyDM_M.outputRotate","lowerLipConstrainedFleshy_M.rotate",force=True)
            if source.use_offset_parent_matrix and not c.objExists("JawJointDM_M"):
                self._lip_node("decomposeMatrix","JawJointDM_M")
                c.connectAttr("JawJointMM_M.matrixSum","JawJointDM_M.inputMatrix")
            output="JawJointDM_M.outputRotateX" if source.use_offset_parent_matrix else "JawJoint_M.rx"
            for side in ("_R","_L"): c.connectAttr(output,"lowerLipJointFleshy"+side+".rotateX")
