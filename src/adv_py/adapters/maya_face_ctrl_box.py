"""asFaceCtrlBox / asFaceCreateCtrlBox, including original optional icons."""
from __future__ import annotations
from dataclasses import replace
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_ctrl_box import SQUARE, SLIDERS, VISIBILITY, OPTIONAL_ICONS
from adv_py.core.body_parent_constraint import plan_body_parent_constraint
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_controllers import MayaFaceControllersMixin
from .maya_face_eyelid_rig import MayaFaceEyeLidRigHost

class MayaFaceCtrlBoxHost(MayaFaceControllersMixin,MayaFaceEyeLidRigHost):
    def capture_ctrl_box_input(self):
        c=self._cmds
        fit=self._fit(required=True)
        mesh,faces,scale=self.read_face_mask()
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("ctrlBox 需要唯一 Face 网格")
        head_name=c.getAttr(fit+".HeadJoint")
        heads=c.ls(head_name,long=True,type="joint") or []
        if len(heads)!=1: raise FitSkeletonValidationError("ctrlBox 需要唯一 Head 关节")
        options={name:bool(c.getAttr(fit+"."+name)) if c.objExists(fit+"."+name) else default
            for name,default in (("Phonemes",True),("Emotions",True),("ARKit",False),
                                 ("RobloxHead",False),("SnapChat",False),("EyeBase",False),("Cyclops",False))}
        bounds=tuple(c.exactWorldBoundingBox(*(mesh+f".f[{i}]" for i in faces)))
        eye=tuple(c.xform("FitEyeBall",query=True,worldSpace=True,translation=True)) if c.objExists("FitEyeBall") else None
        return fit,geometry[0],heads[0],scale,bounds,eye,options

    def ctrl_box_region_names(self,source):
        c=self._cmds; options=source[-1]
        names=["LipRegion1_M","NoseRegion1_M"]
        if c.objExists("FitEyeBall"):
            for side in ("_R","_L"):
                names.extend(stem+side for stem in ("Eye1","EyeRegion1","EyeBrowRegion1"))
                if options["EyeBase"]: names.append("EyeBase1"+side)
        if c.objExists("FaceFitUpMidLo"):
            names.extend(("upperFace1_M","middleFace1_M","lowerFace1_M"))
        if c.objExists(source[0]+".UpperTeeth") and c.getAttr(source[0]+".UpperTeeth"):
            names.extend(("upperTeeth1_M","lowerTeeth1_M"))
        if c.objExists("FaceFitTongue"):
            names.extend(("Tongue11_M","Tongue21_M","Tongue31_M"))
        return tuple(names)

    def validate_ctrl_box(self,controls):
        """Construction invariants checked within the same undo transaction."""
        c=self._cmds
        for control in controls:
            if len(c.ls(control,long=True,type="transform") or [])!=1:
                raise RuntimeError("原版 Face 控件缺失或重名："+control)
            if not c.sets(control,isMember="FaceControlSet"):
                raise RuntimeError("FaceControlSet 缺少控制器："+control)
        for name,x,y,half in SLIDERS:
            control="ctrl"+name
            for attr in ("translateX","translateY"):
                if not c.isConnected(control+"."+attr,"bw"+control+"_"+attr+".input[0]"):
                    raise RuntimeError("Face 滑块输出未连接："+control+"."+attr)
        for attr in ("limits",*VISIBILITY):
            if not c.objExists("ctrlBox."+attr): raise RuntimeError("ctrlBox 缺少原版属性："+attr)

    def _box_shape(self,node):
        return (self._cmds.listRelatives(node,shapes=True,fullPath=True) or [None])[0]

    def _box_lock(self,node):
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            self._cmds.setAttr(node+"."+attr,lock=True,keyable=False)

    def _box_circle(self,name,radius=.3,sections=8):
        return self._cmds.circle(name=name,normal=(0,0,1),radius=radius,degree=3,
                                  sections=sections,constructionHistory=False)[0]

    def _box_merge_shape(self,source,target,name=None):
        c=self._cmds
        shape=self._box_shape(source)
        shape=c.parent(shape,target,add=True,shape=True,relative=True)[0]
        c.delete(source)
        if name: c.rename(shape,name)

    def _box_empty_template_copy(self,name):
        c=self._cmds
        node=c.duplicate("ctrlBoxTemplate",name=name,returnRootsOnly=True)[0]
        children=c.listRelatives(node,children=True,fullPath=True,type="transform") or []
        if children: c.delete(children)
        return node

    def _box_slider(self,name,x,y,half):
        c=self._cmds
        box=c.duplicate("ctrlBoxTemplate",name="ctrlBox"+name,renameChildren=True,
                        returnRootsOnly=True)[0]
        children=c.listRelatives(box,children=True,fullPath=True,type="transform") or []
        if len(children)!=1: raise RuntimeError("ctrlBox 滑块模板子节点不完整")
        control=c.rename(children[0],"ctrl"+name)
        c.setAttr(box+".translate",x,y,0)
        for attr in ("minTransXLimitEnable","minTransYLimitEnable","maxTransXLimitEnable","maxTransYLimitEnable"):
            if c.objExists(control+"."+attr): c.connectAttr("ctrlBox.limits",control+"."+attr,force=True)
        for attr in ("translateX","translateY"):
            bw=c.createNode("blendWeighted",name="bwctrl"+name+"_"+attr)
            c.connectAttr(control+"."+attr,bw+".input[0]")
        c.sets(control,add="FaceControlSet")
        if half:
            positions=[c.xform(box+f".cv[{i}]",query=True,worldSpace=True,translation=True) for i in (0,2,3)]
            p0,p2,p3=positions
            if half==1:
                for index,point in ((2,p2),(3,p3)):
                    c.xform(box+f".cv[{index}]",worldSpace=True,translation=(point[0],(p0[1]+point[1])/2,point[2]))
                c.transformLimits(control,tx=(-1,1),ty=(0,1),tz=(0,0),etz=(True,True))
            else:
                for index,point in ((1,p2),(0,p3),(4,p3)):
                    c.xform(box+f".cv[{index}]",worldSpace=True,translation=(point[0],(p0[1]+p2[1])/2,point[2]))
                c.transformLimits(control,tx=(-1,1),ty=(-1,0),tz=(0,0),etz=(True,True))
        return "ctrl"+name

    def _box_phonemes(self,scale):
        c=self._cmds
        points=((- .922009,0,1),(-.176985,0,-.989507),(.194834,0,-.989507),(.934309,0,1),
                (.572202,0,1),(.39323,0,.493605),(-.389254,0,.493605),(-.56129,0,1),(-.922009,0,1))
        c.curve(name="ctrlPhonemes_M",degree=1,point=points)
        temp=c.curve(name="ctrlPhonemesInnerTemp",degree=1,point=((- .303236,0,.224453),
            (-.00217431,0,-.693995),(.305825,0,.224453),(-.303236,0,.224453)))
        self._box_merge_shape(temp,"ctrlPhonemes_M","ctrlPhonemes_MShape1")
        c.rotate(90,0,0,"ctrlPhonemes_M.cv[0:99]",relative=True,objectSpace=True,pivot=(0,0,0))
        c.scale(.6,.6,.6,"ctrlPhonemes_M.cv[0:99]",relative=True,pivot=(0,0,0))
        self._box_lock("ctrlPhonemes_M")
        box=self._box_empty_template_copy("ctrlBoxPhonemes_M")
        c.parent("ctrlPhonemes_M",box,absolute=True)
        c.setAttr(box+".translate",-scale/25,-scale/4*1.3,0)
        c.setAttr(box+".scale",*(scale/66,)*3)
        c.sets("ctrlPhonemes_M",add="FaceControlSet")

    def _box_emotions(self,scale):
        c=self._cmds
        self._box_circle("ctrlEmotions_M",.025,4)
        c.move(-.04,.075,0,"ctrlEmotions_M.cv[0:99]",relative=True)
        temp=self._box_circle("ctrlEmotionsEyeTemp",.025,4)
        c.move(.04,.075,0,temp+".cv[0:99]",relative=True)
        self._box_merge_shape(temp,"ctrlEmotions_M","ctrlEmotions_MShape1")
        for index,offset in ((1,-.02),(3,.02)):
            for shape in ("ctrlEmotions_MShape","ctrlEmotions_MShape1"):
                c.move(0,offset,0,shape+f".cv[{index}]",relative=True,objectSpace=True,worldSpaceDistance=True)
        temp=self._box_circle("ctrlEmotionsMouthTemp",.07,8)
        for indices,y in (((1,),-.12),((0,2),-.07)):
            c.move(0,y,0,*(temp+f".cv[{i}]" for i in indices),relative=True,objectSpace=True,worldSpaceDistance=True)
        c.move(0,.04,0,temp+".cv[0:99]",relative=True)
        self._box_merge_shape(temp,"ctrlEmotions_M","ctrlEmotions_MShape2")
        cvs=tuple(shape+".cv[0:99]" for shape in c.listRelatives("ctrlEmotions_M",shapes=True,fullPath=True))
        c.scale(10,10,10,*cvs,relative=True,pivot=(0,0,0))
        c.move(0,-.3,0,*cvs,relative=True)
        self._box_lock("ctrlEmotions_M")
        box=self._box_empty_template_copy("ctrlBoxEmotions_M")
        c.parent("ctrlEmotions_M",box,absolute=True)
        c.setAttr(box+".translate",0,-scale/4*1.3,0)
        c.setAttr(box+".scale",*(scale/66,)*3)
        c.sets("ctrlEmotions_M",add="FaceControlSet")

    def _box_optional_icon(self,kind,scale):
        c=self._cmds
        box="ctrlBox"+kind+"_M"; control="ctrl"+kind+"_M"
        if kind=="SnapChat":
            if not c.objExists("ctrlBoxEmotions_M"):
                raise FitSkeletonValidationError("原版 SnapChat 图标需要 Emotions 模板")
            c.duplicate("ctrlBoxEmotions_M",name=box,returnRootsOnly=True)
            for child in c.listRelatives(box,children=True,fullPath=True,type="transform") or []: c.delete(child)
        else: self._box_empty_template_copy(box)
        c.setAttr(box+".translateX",scale/25*(2 if kind=="RobloxHead" else 1))
        c.setAttr(box+".translateY",-scale/4*1.3)
        c.setAttr(box+".scale",*(scale/66,)*3)
        c.createNode("transform",name=control,parent=box)
        for shape,(degree,knots,points) in OPTIONAL_ICONS.items():
            if not shape.startswith(control+"Shape"): continue
            temp=c.curve(name=control+"IconTemp#",degree=degree,knot=knots,point=points)
            self._box_merge_shape(temp,control,shape)
            c.setAttr(shape+".isHistoricallyInteresting",0)
        self._box_lock(control)
        c.sets(control,add="FaceControlSet")

    def _box_region_icons(self,scale,options):
        c=self._cmds
        if c.objExists("FitEyeBall"):
            for side,factor in (("_R",1),("_L",-1)):
                if options["EyeBase"]:
                    name="EyeBase1"+side
                    c.curve(name=name,degree=1,point=((0,1,0),(0,-1,0),(0,0,0),(1,0,0),(-1,0,0)))
                    c.scale(*(scale/80,)*3,name+".cv[0:99]",relative=True,pivot=(0,0,0))
                    c.setAttr(name+".translate",-.05*scale*factor,.095*scale,0)
                    c.parent(name,"ctrlBox2",relative=True)
                name="Eye1"+side
                self._box_circle(name)
                c.scale(*(scale/10,)*3,name+".cv[0:99]",relative=True,pivot=(0,0,0))
                c.setAttr(name+".translate",-.05*scale*factor,.095*scale,0)
                c.parent(name,"ctrlBox2",relative=True)
                region=c.duplicate(name,name="EyeRegion1"+side,returnRootsOnly=True)[0]
                pivot=c.xform(region,query=True,worldSpace=True,translation=True)
                c.scale(1.5,1.5,1.5,region+".cv[0:99]",relative=True,pivot=pivot)
                brow="EyeBrowRegion1"+side
                self._box_circle(brow)
                c.scale(scale/7,scale/10,scale/8,brow+".cv[0:99]",relative=True,pivot=(0,0,0))
                c.setAttr(brow+".translate",-.05*scale*factor,.188*scale,0)
                for indices,fraction in (((5,),.06),((4,6),.03)):
                    c.move(0,fraction*scale,0,*(brow+f".cv[{i}]" for i in indices),relative=True,objectSpace=True,worldSpaceDistance=True)
                c.parent(brow,"ctrlBox2",relative=True)
                shape=self._box_shape(name)
                c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",18)
        self._box_circle("LipRegion1_M")
        for indices,y in (((1,),-.3),((2,0),-.15),((3,7),.15),((4,6),.25),((5,),.25)):
            c.move(0,y,0,*(f"LipRegion1_M.cv[{i}]" for i in indices),relative=True,objectSpace=True,worldSpaceDistance=True)
        c.scale(*(scale/3.5,)*3,"LipRegion1_M.cv[0:99]",relative=True,pivot=(0,0,0))
        c.parent("LipRegion1_M","ctrlBox2",relative=True); c.setAttr("LipRegion1_M.ty",-.25*scale)
        self._box_circle("NoseRegion1_M")
        for index,y in ((1,.1),(5,.3)):
            c.move(0,y,0,f"NoseRegion1_M.cv[{index}]",relative=True,objectSpace=True,worldSpaceDistance=True)
        c.scale(*(scale/5,)*3,"NoseRegion1_M.cv[0:99]",relative=True,pivot=(0,0,0))
        c.scale(.5,1,1,"NoseRegion1_M.cv[0]","NoseRegion1_M.cv[2]",relative=True,pivot=(0,0,0))
        c.move(0,-.1,0,"NoseRegion1_M.cv[0]","NoseRegion1_M.cv[2]",relative=True,objectSpace=True,worldSpaceDistance=True)
        c.parent("NoseRegion1_M","ctrlBox2",relative=True); c.setAttr("NoseRegion1_M.ty",-.1*scale)
        rect=((1,-.02,0),(-1,-.02,0),(-1,.02,0),(1,.02,0),(1,-.02,0))
        def rectangle(name,x,y,color=None):
            c.curve(name=name,degree=1,point=rect)
            c.scale(scale/50,scale/10,scale/10,name+".cv[0:99]",relative=True,pivot=(0,0,0))
            c.parent(name,"ctrlBox2",relative=True); c.setAttr(name+".translate",x*scale,y*scale,0)
            if color is not None:
                shape=self._box_shape(name); c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",color)
        if c.objExists("FaceFitUpMidLo"):
            for name,y in (("lowerFace1_M",-.16),("middleFace1_M",-.0875),("upperFace1_M",-.015)):
                rectangle(name,.09,y)
        fit=self._fit(required=True)
        if c.objExists(fit+".UpperTeeth") and c.getAttr(fit+".UpperTeeth"):
            rectangle("upperTeeth1_M",-.1,-.2,14); rectangle("lowerTeeth1_M",-.1,-.25,14)
        if c.objExists("FaceFitTongue"):
            for index,y in ((1,-.26),(2,-.28),(3,-.3)): rectangle(f"Tongue{index}1_M",.09,y,6)

    def create_ctrl_box(self,source):
        self._require_transaction()
        c=self._cmds
        fit,mesh,head,scale,bounds,eye,options=source
        self._transaction_changed=True
        self.ensure_face_advanced_base(head,mesh,self.read_face_objects(FacePreRole.ALL_HEAD) or (mesh,))
        if not c.objExists("FaceJoint_M"):
            c.select(clear=True); joint=c.joint(name="FaceJoint_M")
            c.xform(joint,worldSpace=True,translation=c.xform(head,query=True,worldSpace=True,translation=True))
            c.parent(joint,head,absolute=True); c.setAttr("FaceJoint_M.drawStyle",2)
        c.setAttr(fit+".visibility",lock=False); c.setAttr(fit+".visibility",False,lock=True)
        c.curve(name="ctrlBox",degree=1,point=SQUARE)
        c.createNode("transform",name="ctrlBoxOffset",parent="ControlsSetup")
        c.parent("ctrlBox","ctrlBoxOffset",absolute=True)
        for attr in ("limits",*VISIBILITY):
            c.addAttr("ctrlBox",longName=attr,attributeType="bool",defaultValue=True,keyable=True)
        if not c.objExists("Main.jointVis"):
            c.addAttr("ctrlBox",longName="jointsVis",attributeType="bool",defaultValue=False,keyable=True)
            c.connectAttr("ctrlBox.jointsVis","FaceJoint_M.visibility")
        for attr in ("AimCtrlVis","RegionsCtrlVis"): c.setAttr("ctrlBox."+attr,False)
        c.setAttr("ctrlBox.overrideEnabled",True); c.setAttr("ctrlBox.overrideColor",17)
        c.move(0,-.4,0,"ctrlBox.cv[2:3]",relative=True)
        c.xform("ctrlBox",scale=(scale/8,scale/4,scale/8))
        c.makeIdentity("ctrlBox",apply=True,translate=False,rotate=False,scale=True)
        position=(bounds[3]*1.5,(bounds[1]+bounds[4])/2,(bounds[2]+bounds[5])/2)
        if eye: position=(position[0],eye[1]-scale/4*.38,eye[2])
        c.xform("ctrlBoxOffset",worldSpace=True,translation=position)
        if c.objExists("prefix_ctrlBox"):
            for attr in ("translate","scale"): c.setAttr("ctrlBox."+attr,*c.getAttr("prefix_ctrlBox."+attr)[0])
        c.curve(name="ctrlBoxTemplate",degree=1,point=SQUARE)
        c.parent("ctrlBoxTemplate","ctrlBox",absolute=True)
        c.setAttr("ctrlBoxTemplate.translate",0,0,0); c.setAttr("ctrlBoxTemplate.scale",*(scale/24,)*3)
        shape=self._box_shape("ctrlBoxTemplate")
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideDisplayType",2)
        c.duplicate("ctrlBoxTemplate",name="ctrlTemplate",returnRootsOnly=True)
        c.parent("ctrlTemplate","ctrlBoxTemplate",absolute=True)
        c.transformLimits("ctrlTemplate",tx=(-1,1),ty=(-1,1),tz=(0,0),etx=(True,True),ety=(True,True),etz=(True,True))
        for attr in ("minTransXLimitEnable","minTransYLimitEnable","maxTransXLimitEnable","maxTransYLimitEnable"):
            if c.objExists("ctrlTemplate."+attr): c.connectAttr("ctrlBox.limits","ctrlTemplate."+attr,force=True)
        shape=self._box_shape("ctrlTemplate")
        c.setAttr(shape+".overrideDisplayType",0); c.setAttr(shape+".overrideEnabled",False)
        c.setAttr("ctrlTemplate.rz",45); c.setAttr("ctrlTemplate.scale",.2,.2,.2)
        c.makeIdentity("ctrlTemplate",apply=True,translate=False,rotate=True,scale=True)
        for attr in ("tz","rx","ry","rz","sx","sy","sz","v"): c.setAttr("ctrlTemplate."+attr,lock=True,keyable=False)
        c.sets("ctrlTemplate",add="FaceControlSet")
        controls=[self._box_slider(name,x*scale/4,y*scale/4,half) for name,x,y,half in SLIDERS]
        for attr in c.listAttr("ctrlBox",keyable=True) or []: c.setAttr("ctrlBox."+attr,keyable=False,channelBox=True)
        if options["Phonemes"]: self._box_phonemes(scale); controls.append("ctrlPhonemes_M")
        if options["Emotions"]: self._box_emotions(scale); controls.append("ctrlEmotions_M")
        for kind in ("RobloxHead","ARKit","SnapChat"):
            if options[kind]: self._box_optional_icon(kind,scale); controls.append("ctrl"+kind+"_M")
        c.delete("ctrlBoxTemplate")
        c.duplicate("ctrlBoxOffset",name="ctrlBox2Offset",renameChildren=True,returnRootsOnly=True)
        children=c.listRelatives("ctrlBox2Offset",children=True,fullPath=True,type="transform") or []
        c.rename(children[0],"ctrlBox2")
        c.setAttr("ctrlBox2Offset.tx",c.getAttr("ctrlBox2Offset.tx")+scale/3.5)
        children=c.listRelatives("ctrlBox2",children=True,fullPath=True,type="transform") or []
        if children: c.delete(children)
        for attr in c.listAttr("ctrlBox2",userDefined=True) or []: c.deleteAttr("ctrlBox2."+attr)
        c.createNode("transform",name="ctrlBox2Constrained",parent="ConstrainedSetup")
        source_constraint=self.capture_parent_constraint_input(self._face_base_transform("ctrlBox2"),
            self._face_base_transform("ctrlBox2Constrained"),False)
        plan=plan_body_parent_constraint(replace(source_constraint,use_offset_parent_matrix=self.face_use_offset_parent_matrix()))
        self.preflight_parent_constraint(plan); self.create_parent_constraint(plan)
        self._box_region_icons(scale,options)
        loc=c.spaceLocator(name="tempLoc")[0]; c.setAttr(loc+".visibility",False)
        c.createNode("transform",name="tempLocFlip",parent="FaceMotionSystem")
        c.parent(loc,"tempLocFlip",absolute=True)
        if options["Cyclops"]:
            c.setAttr("ctrlBoxEye_R.overrideEnabled",True); c.setAttr("ctrlBoxEye_R.overrideVisibility",False)
            c.setAttr("ctrlBoxEye_L.tx",0)
        c.select(clear=True)
        return tuple(controls)
