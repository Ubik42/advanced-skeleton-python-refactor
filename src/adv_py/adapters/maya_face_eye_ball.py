"""Original asFaceEyeBall graph and non-spherical eyes, MEL 32138–32559."""
from .maya_face_body_roles import face_body_main
from contextlib import contextmanager, nullcontext
from math import dist
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_original_transform_channels import align_original_transform

class MayaFaceEyeBallMixin:
    def capture_original_face_eye_input(self):
        c=self._cmds; fit=self._fit(required=True)
        for node in ("FitEyeBall","FaceJoint_M","FaceDeformationSystem","Aimcontrols","SideReverse_R","SideReverse_L","ctrlEye_R","ctrlEye_L","FaceControlSet","ctrlBox2"):
            if not c.objExists(node): raise FitSkeletonValidationError("原版 EyeBall 缺少前置节点："+node)
        if c.objExists("EyeSetup"): raise FitSkeletonValidationError("原版 EyeBall 已存在，请使用重建流程")
        scale=tuple(c.getAttr("FitEyeBall.scale")[0])
        squashed=abs(scale[0]-scale[1])>=.001 or abs(scale[0]-scale[2])>=.001
        if squashed and c.objExists(fit+".GameEngine") and c.getAttr(fit+".GameEngine"):
            raise FitSkeletonValidationError("原版非球形 EyeBall 不支持 GameEngine")
        def option(name): return bool(c.objExists(fit+"."+name) and c.getAttr(fit+"."+name))
        head=c.getAttr(fit+".HeadJoint")
        if len(c.ls(head,long=True,type="joint") or [])!=1: raise FitSkeletonValidationError("EyeBall 缺少唯一 Head 关节")
        return {"head":head,"scale":float(c.getAttr(fit+".faceScale")),"opm":self.face_use_offset_parent_matrix(),
                "multi":option("MultiSkinClusters"),"base":option("EyeBase"),"cyclops":option("Cyclops"),"squashed":squashed,
                "eyes":{side:self.read_original_face_parts(name) for side,name in (("_R","RightEye"),("_L","LeftEye"))}}

    def _original_eye_align(self,node,target,translate=True,rotate=True):
        return align_original_transform(self._cmds,node,target,translate,rotate)

    def _original_eye_aim_follow(self,head):
        """asParentConstraintBlend AimEye_M AimEyeFollow_M EyeAimFollowHead."""
        c=self._cmds; driven="AimEyeFollow_M"; driver="AimEye_M"
        world=c.xform(driven,query=True,worldSpace=True,matrix=True)
        temp=c.createNode("transform",name="tempTransformMatrix",parent=driven)
        c.parent(temp,"EyeAimFollowHead")
        offset=c.xform(temp,query=True,objectSpace=True,matrix=True); c.delete(temp)
        blend=c.createNode("blendMatrix",name="AimEyeFollowBM_M")
        c.setAttr(blend+".inputMatrix",*world,type="matrix")
        c.addAttr(driver,longName="follow",attributeType="double",minValue=0,maxValue=10,defaultValue=10,keyable=True)
        multiply=c.createNode("multDoubleLinear",name="AimEye_MFollowMDL_M")
        c.connectAttr(driver+".follow",multiply+".input1"); c.setAttr(multiply+".input2",.1)
        follow=c.createNode("multMatrix",name="AimEyeFollowMMFollow_M")
        c.setAttr(follow+".matrixIn[0]",*offset,type="matrix")
        c.connectAttr("EyeAimFollowHead.worldMatrix[0]",follow+".matrixIn[1]")
        c.connectAttr(follow+".matrixSum",blend+".target[0].targetMatrix")
        c.connectAttr(multiply+".output",blend+".target[0].weight")
        static=c.createNode("multMatrix",name="AimEyeFollowMMStatic_M")
        c.setAttr(static+".matrixIn[0]",*world,type="matrix")
        if c.objExists(face_body_main(self)): c.connectAttr(face_body_main(self)+".worldMatrix[0]",static+".matrixIn[1]")
        else:
            c.setAttr(static+".matrixIn[0]",1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,type="matrix")
            c.connectAttr(head+".worldMatrix[0]",static+".matrixIn[1]")
        c.connectAttr(static+".matrixSum",blend+".inputMatrix")
        relative=c.createNode("multMatrix",name="AimEyeFollowMMRelToParent_M")
        c.connectAttr(blend+".outputMatrix",relative+".matrixIn[0]")
        parent=c.listRelatives(driven,parent=True)[0]
        c.connectAttr(parent+".worldInverseMatrix",relative+".matrixIn[1]")
        if self.face_use_offset_parent_matrix():
            c.connectAttr(relative+".matrixSum",driven+".offsetParentMatrix")
            c.xform(driven,objectSpace=True,translation=(0,0,0),rotation=(0,0,0))
        else:
            decompose=c.createNode("decomposeMatrix",name="AimEyeFollowDM_M")
            c.setAttr(decompose+".inputRotateOrder",c.getAttr(driven+".rotateOrder"))
            c.connectAttr(relative+".matrixSum",decompose+".inputMatrix")
            for output,attr in (("Translate","t"),("Rotate","r"),("Scale","s")):
                c.connectAttr(decompose+".output"+output,driven+"."+attr)

    def create_original_face_eye_ball(self,source):
        self._require_transaction()
        c=self._cmds; head=source["head"]; scale=source["scale"]
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox2.v",0)
        for side in ("_R","_L"): c.setAttr("ctrlBoxEye"+side+".v",1)
        c.createNode("transform",name="EyeSetup",parent="FaceDeformationSystem")
        center=self._lip_pos("FitEyeBall")
        if source["squashed"] and not c.objExists("FitEyeBall.nonSphericalEye"):
            c.addAttr("FitEyeBall",longName="nonSphericalEye",attributeType="bool",defaultValue=True)
        for name,parent in (("EyeAimSetup","EyeSetup"),("EyeAimFollowHead","EyeAimSetup"),("EyeAimStatic","EyeAimSetup")):
            c.createNode("transform",name=name,parent=parent)
        self.constrain_original_face(head,"EyeAimFollowHead")
        self._original_eye_align("EyeAimStatic",head)
        aim=c.curve(name="AimEye_M",degree=1,point=((0,1,0),(0,-1,0),(0,0,0),(1,0,0),(-1,0,0)),knot=(0,1,2,3,4))
        shape=c.listRelatives(aim,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        c.connectAttr("ctrlBox.AimCtrlVis",shape+".overrideVisibility"); c.sets(aim,add="FaceControlSet")
        c.createNode("transform",name="AimAimAt",parent="EyeAimSetup")
        c.xform("AimAimAt",worldSpace=True,translation=(0,center[1],center[2]))
        c.createNode("transform",name="AimEyeOffset_M")
        c.createNode("transform",name="AimEyeFollow_M",parent="Aimcontrols")
        self._original_eye_align("AimEyeFollow_M",head)
        c.parent(aim,"AimEyeOffset_M"); c.setAttr("AimEyeOffset_M.s",*(scale/10,)*3,type="float3")
        self._original_eye_align("AimEyeOffset_M","AimEyeFollow_M",rotate=False)
        c.parent("AimEyeOffset_M","AimEyeFollow_M")
        c.xform("AimEyeOffset_M",worldSpace=True,translation=(0,center[1],center[2]+scale))
        c.parent("AimEyeOffset_M","FitEyeBall"); c.setAttr("AimEyeOffset_M.ty",0)
        c.parent("AimEyeOffset_M","AimEyeFollow_M")
        c.createNode("transform",name="AimEyeUpVec",parent="EyeAimFollowHead")
        self._original_eye_aim_follow(head)
        controls=[aim]; skins=[]
        for side,factor,suffix in (("_R",1,""),("_L",-1,"Left")):
            point=self._lip_pos("FitEyeBallLeft") if suffix and c.objExists("FitEyeBallLeft") else (center[0]*factor,center[1],center[2])
            if source["base"]:
                control=self.create_original_face_controller("EyeBase",side,4); c.delete("EyeBaseJoint"+side)
                c.xform("EyeBaseOffset"+side,worldSpace=True,translation=point)
                c.scale(8,8,8,control+".cv[0:7]",relative=True,pivot=point)
                c.setAttr(c.listRelatives(control,shapes=True,fullPath=True)[0]+".overrideColor",17)
                c.parent("EyeBaseOffset"+side,"SideReverse"+side)
                c.xform("EyeBaseOffset"+side,objectSpace=True,rotation=(0,0,0),scale=(1,1,1))
                self.project_original_face_control(control); controls.append(control)
            region=self.create_original_face_controller("EyeRegion",side,4)
            c.parent("EyeRegionJoint"+side,"FaceDeformationSystem")
            self.constrain_original_face(region,"EyeRegionJoint"+side)
            c.xform("EyeRegionOffset"+side,worldSpace=True,translation=point)
            c.scale(6,6,6,region+".cv[0:7]",relative=True,pivot=point)
            c.parent("EyeRegionOffset"+side,("EyeBase" if source["base"] else "SideReverse")+side)
            c.xform("EyeRegionOffset"+side,objectSpace=True,rotation=(0,0,0),scale=(1,1,1))
            self.reset_original_face_joint_matrix_scale("EyeRegionJoint"+side)
            self.project_original_face_control(region); controls.append(region)
            eye=self.create_original_face_controller("Eye",side,3)
            c.setAttr(eye+".rotateOrder",2); c.setAttr("EyeOffset"+side+".s",1,1,1,type="float3")
            c.xform("EyeOffset"+side,worldSpace=True,translation=point)
            point=self._lip_pos(eye)
            c.scale(2.16,2.16,2.16,eye+".cv[0:7]",relative=True,pivot=point)
            shape=c.listRelatives(eye,shapes=True,fullPath=True)[0]
            c.setAttr(shape+".overrideColor",18); c.connectAttr("ctrlBox.EyeCtrlVis",shape+".overrideVisibility",force=True)
            c.select("FaceJoint_M",replace=True); joint=c.joint(name="EyeJoint"+side)
            c.setAttr(joint+".rotateOrder",2)
            c.xform(joint,worldSpace=True,translation=(center[0]*factor,center[1],center[2]))
            if not c.objExists("EyeControls"):
                c.createNode("transform",name="EyeControls",parent="OnFacecontrols")
                c.parent("EyeControls","ControlsSetup"); c.xform("EyeControls",scale=(1,1,1))
            c.parent("EyeOffset"+side,"EyeControls")
            c.xform("EyeOffset"+side,objectSpace=True,rotation=(0,0,0),scale=(1,1,1))
            c.delete(c.orientConstraint("FitEyeBall","EyeOffset"+side))
            if suffix: c.setAttr("EyeOffset_L.ry",-c.getAttr("EyeOffset_L.ry"))
            c.delete(c.parentConstraint(eye,joint)); c.makeIdentity(joint,apply=True,translate=False,rotate=True,scale=False)
            self.constrain_original_face(eye,joint,force_matrix=False)
            c.setAttr(joint+".segmentScaleCompensate",False)
            if source["multi"]: self._original_eye_multi_matrix(joint,side,head)
            controls.append(eye)
            geometry=source["eyes"][side]
            if not geometry: continue
            eye_skins=self._original_eye_skin(source,side,geometry,point)
            skins.extend(eye_skins)
            for driver,driven,dv,value in (("tx","ry",1,30),("tx","ry",-1,-30),("ty","rx",1,-30),("ty","rx",-1,30)):
                self.add_original_face_sdk("ctrlEye"+side+"."+driver,"SDKEye"+side+"."+driven,dv,value)
            self._original_eye_side_aim(source,side)
            controls.append("AimEye"+side)
            if c.objExists("FitEyeBall.nonSphericalEye"): self._original_eye_squash(source,side,suffix,geometry,eye_skins)
        if c.objExists("FaceFitPupil") or c.objExists("FaceFitIris"):
            result=self.create_original_face_pupil_iris(source)
            controls.extend(result["controls"]); skins.extend(result["production_skins"])
        if source["cyclops"]:
            for node in ("EyeOffset_R","EyeRegionOffset_R"):
                c.setAttr(node+".overrideEnabled",True); c.setAttr(node+".overrideVisibility",False)
        c.select(clear=True); self._transaction_changed=True
        return {"controls":tuple(controls),"production_skins":tuple(dict.fromkeys(skins))}

    def _original_eye_multi_matrix(self,joint,side,head):
        c=self._cmds; matrix="EyeJointMM"+side
        c.setAttr(matrix+".matrixIn[3]",*self.original_face_matrix_values("FaceJoint_M.worldMatrix[0]"),type="matrix")
        c.connectAttr(head+".worldInverseMatrix",matrix+".matrixIn[4]")
        for _ in range(2): c.setAttr(matrix+".matrixIn[5]",*self.original_face_matrix_values(head+".worldMatrix[0]"),type="matrix")
        c.setAttr(matrix+".matrixIn[6]",*self.original_face_matrix_values("FaceJoint_M.inverseMatrix"),type="matrix")

    def _original_eye_skin(self,source,side,geometry,point):
        c=self._cmds; raw=getattr(c,"raw",c); joint=self.scene_address("EyeJoint"+side)
        bounding=[geometry[0]]
        if "." in geometry[0]:
            bounding=list(geometry)
            while len({row.split(".",1)[0] for row in bounding})>1: bounding.pop()
        bounds=raw.exactWorldBoundingBox(*bounding)
        c.move(0,0,bounds[5]*1.1-point[2],"Eye"+side+".cv[0:7]",relative=True,objectSpace=True,worldSpaceDistance=True)
        skins=[]
        for geo in geometry:
            candidates=[node for node in raw.listHistory(geo) or [] if raw.nodeType(node)=="skinCluster" and not node.rsplit(":",1)[-1].startswith("prefix_")]
            skin=candidates[-1] if candidates else None
            if source["multi"]:
                with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
                    skin=raw.skinCluster(joint,geo,multi=True,frontOfChain=True,toSelectedBones=True)[0]
                    skin=raw.rename(skin,self.scene_address("EyeBallSC"+side))
            elif skin:
                uid=set(raw.ls(joint,uuid=True) or [])
                infs=raw.listConnections(skin+".matrix",source=True,destination=False,type="joint") or []
                if not any(uid & set(raw.ls(inf,uuid=True) or []) for inf in infs):
                    raw.skinCluster(skin,edit=True,lockWeights=True,weight=0,addInfluence=joint)
                    if raw.objExists(joint+".lockInfluenceWeights"): raw.setAttr(joint+".lockInfluenceWeights",0)
                    raw.skinPercent(skin,geo,transformValue=((joint,1),))
            else:
                from .maya_original_skin_history import new_original_skin_clusters
                raw.select((joint,geo),replace=True)
                created=new_original_skin_clusters(commands=raw,namespace=self.namespace)
                # Source renames every Skin returned by native expansion,
                # retaining the last returned name for this eye selection.
                for created_skin in created:
                    skin=raw.rename(created_skin,self.scene_address("eyeSC"+side))
            skins.append(skin)
        return skins

    def _original_eye_side_aim(self,source,side):
        c=self._cmds
        node=c.createNode("transform",name="AimOffsetEye"+side,parent="Eye"+side)
        c.setAttr(node+".tz",dist(self._lip_pos("Eye"+side),self._lip_pos("AimEye_M")))
        c.parent(node,"AimEye_M"); c.setAttr(node+".s",1,1,1,type="float3"); c.setAttr(node+".r",0,0,0,type="float3")
        aim=c.duplicate("AimEye_M",name="AimEye"+side,returnRootsOnly=True)[0]
        children=c.listRelatives(aim,children=True,fullPath=True,type="transform") or []
        if children: c.delete(children)
        c.deleteAttr(aim+".follow"); c.parent(aim,node,relative=True)
        shape=c.listRelatives(aim,shapes=True,fullPath=True)[0]
        c.connectAttr("ctrlBox.AimCtrlVis",shape+".overrideVisibility")
        point=self._lip_pos(aim); c.scale(.5,.5,.5,aim+".cv[0:99]",relative=True,pivot=point)
        c.createNode("transform",name="EyeAim"+side,parent="EyeOffset"+side)
        if source["opm"]:
            am=c.createNode("aimMatrix",name="EyeAimAM"+side)
            for attr,value in (("primaryInputAxis",(0,0,1)),("secondaryInputAxis",(0,1,0)),("secondaryTargetVector",(0,1,0))): c.setAttr(am+"."+attr,*value,type="float3")
            c.setAttr(am+".secondaryMode",2)
            for source_plug,target in ((aim+".worldMatrix[0]","primaryTargetMatrix"),("AimEyeUpVec.worldMatrix[0]","secondaryTargetMatrix"),("EyeOffset"+side+".worldMatrix[0]","inputMatrix")): c.connectAttr(source_plug,am+"."+target)
            mm=c.createNode("multMatrix",name="EyeAimMM"+side)
            c.connectAttr(am+".outputMatrix",mm+".matrixIn[1]")
            c.connectAttr("EyeOffset"+side+".worldInverseMatrix[0]",mm+".matrixIn[2]")
            c.connectAttr(mm+".matrixSum","EyeAim"+side+".offsetParentMatrix")
        else: c.aimConstraint(aim,"EyeAim"+side,aimVector=(0,0,1),worldUpType="objectrotation",worldUpObject="AimEyeUpVec",worldUpVector=(0,1,0))
        c.parent("SDKEye"+side,"EyeAim"+side)
        c.sets(aim,add="FaceControlSet")
        if source["base"]: self._original_eye_base_follow(side)

    def _original_eye_base_follow(self,side):
        c=self._cmds
        ts=c.createNode("transform",name="EyeBaseFollowTS"+side,parent="EyeOffset"+side)
        c.parent("EyeAim"+side,ts)
        rotation=c.createNode("transform",name="EyeBaseFollowR"+side,parent="EyeAim"+side)
        c.parent("SDKEye"+side,rotation)
        mm=c.createNode("multMatrix",name="EyeBaseMM"+side)
        c.connectAttr("EyeBase"+side+".worldMatrix",mm+".matrixIn[2]")
        c.connectAttr("EyeOffset"+side+".worldInverseMatrix",mm+".matrixIn[3]")
        dm=c.createNode("decomposeMatrix",name="EyeBaseDM"+side)
        c.connectAttr(mm+".matrixSum",dm+".inputMatrix")
        for output,target in (("Translate",ts+".t"),("Scale",ts+".s"),("Rotate",rotation+".r")): c.connectAttr(dm+".output"+output,target)
        temp=c.createNode("transform",name="tempMatrixTransform")
        c.parent(temp,"SideReverse"+side); c.xform(temp,objectSpace=True,translation=(0,0,0))
        c.setAttr(mm+".matrixIn[1]",*c.xform(temp,query=True,objectSpace=True,matrix=True),type="matrix")
        c.parent(temp,"EyeOffset"+side); c.xform(temp,objectSpace=True,translation=(0,0,0))
        c.setAttr(mm+".matrixIn[0]",*self.original_face_matrix_values(temp+".inverseMatrix"),type="matrix"); c.delete(temp)

    @contextmanager
    def _original_eye_deformer_sets(self):
        from .maya_face_deformer_sets import original_face_deformer_sets
        with original_face_deformer_sets(self._cmds):
            yield

    def _original_eye_squash(self,source,side,suffix,geometry,skins):
        c=self._cmds; raw=getattr(c,"raw",c)
        c.xform("Eye"+side,worldSpace=True,rotation=(0,0,0)); original_scale=None
        for number in (1,2):
            with self._original_eye_deformer_sets(), c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
                nodes=raw.lattice(geometry,divisions=(2,2,2),objectCentered=True,ldivisions=(2,2,2))
            stem=f"squashEyeFfd{number}"+side
            ffd=c.rename(nodes[0],stem); lattice=c.rename(nodes[1],stem.replace(side,"Lattice"+side)); base=c.rename(nodes[2],stem.replace(side,"Base"+side))
            sets=c.listConnections(ffd+".message") or []
            if sets: c.rename(sets[0],stem.replace(side,"Set"+side))
            c.setAttr(ffd+".outsideLattice",1)
            for node in (lattice,base): c.delete(c.orientConstraint("FitEyeBall"+suffix,node))
            if number==1:
                original_scale=self._lip_vector(lattice+".s"); c.setAttr(lattice+".s",*(original_scale[0],)*3,type="float3")
                for skin,geo in zip(skins,geometry): raw.reorderDeformers(self.scene_address(skin),self.scene_address(ffd),geo)
            else: c.setAttr(lattice+".s",*original_scale,type="float3")
        c.xform("Eye"+side,objectSpace=True,rotation=(0,0,0))
        for number in (1,2): c.createNode("transform",name=f"EyeLattice{number}"+side,parent="EyeSetup")
        c.parentConstraint(source["head"],"EyeLattice2"+side); c.scaleConstraint(source["head"],"EyeLattice2"+side)
        for number in (1,2): c.parent(f"squashEyeFfd{number}Lattice"+side,f"squashEyeFfd{number}Base"+side,f"EyeLattice{number}"+side)
