"""Original Zygomaticus Major pull and narrow Smile/Frown, MEL 37220–37702."""
from math import dist

class MayaFaceSmileMixin:
    def fit_original_face_smile_pull(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self.finish_original_face_squint()
        if not c.objExists("upperLipMainCurve"): return False
        scale=source.face_scale
        if not c.objExists("FaceMuscles"): self._lip_node("transform","FaceMuscles","FaceBuildInProgress")
        if not c.objExists("FaceMusclesLayer"): c.createDisplayLayer(name="FaceMusclesLayer")
        self._lip_node("transform","ZygomaticusMajor","FaceMuscles")
        c.circle(name="ZygomaticusMajor_curve1",center=(0,0,0),normal=(0,0,1),sweep=360,
                 radius=scale/25,degree=3,useTolerance=False,tolerance=.000393701,sections=8,constructionHistory=False)
        c.setAttr("ZygomaticusMajor_curve1.visibility",False)
        c.spaceLocator(name="ZygomaticusMajorPosition1")
        c.parent("ZygomaticusMajorPosition1","ZygomaticusMajor",absolute=True)
        c.setAttr("ZygomaticusMajorPosition1.visibility",False)
        c.setAttr("ZygomaticusMajorPosition1.overrideEnabled",True); c.setAttr("ZygomaticusMajorPosition1.overrideColor",17)
        c.setAttr("ZygomaticusMajorPosition1Shape.localScale",scale/15,scale/15,scale/15,type="float3")
        a=self._lip_node("transform","tempXform","Lip_R")
        b=self._lip_node("transform","tempXform2")
        c.xform(b,worldSpace=True,translation=self._lip_pos("upperEyeLidOuterCurve.cv[99]"))
        constraint=c.pointConstraint(b,"JawPivot",a)[0]
        c.geometryConstraint(self.scene_address(source.geometry),a)
        c.setAttr(a+".displayLocalAxis",True)
        aliases=c.pointConstraint(constraint,query=True,weightAliasList=True)
        for index in range(101):
            c.setAttr(constraint+"."+aliases[0],1-index/100)
            c.setAttr(constraint+"."+aliases[1],index/100)
            if c.getAttr(a+".tx")>c.getAttr(a+".ty"): break
        position=self._lip_pos(a); c.delete(a,b)
        c.xform("ZygomaticusMajorPosition1",worldSpace=True,translation=position)
        c.parent("ZygomaticusMajor_curve1","ZygomaticusMajorPosition1",relative=True)
        c.delete(c.aimConstraint("Lip_R","ZygomaticusMajorPosition1",offset=(0,0,0),weight=1,
            aimVector=(0,0,1),upVector=(0,0,1),worldUpType="objectrotation",worldUpObject="Lip_R"))
        for index in (2,3):
            c.duplicate("ZygomaticusMajorPosition1",name="ZygomaticusMajorPosition"+str(index),returnRootsOnly=True)
            c.rename("ZygomaticusMajorPosition"+str(index)+"|ZygomaticusMajor_curve1","ZygomaticusMajor_curve"+str(index))
        for index,value in ((1,0),(2,.5),(3,0)): c.setAttr("ZygomaticusMajor_curve"+str(index)+".scaleX",value)
        position=self._lip_pos("ZygomaticusMajorPosition2"); lip=self._lip_pos("Lip_R")
        c.xform("ZygomaticusMajorPosition2",worldSpace=True,translation=tuple((a+b)/2 for a,b in zip(position,lip)))
        c.xform("ZygomaticusMajorPosition3",worldSpace=True,translation=lip)
        c.loft("ZygomaticusMajor_curve1","ZygomaticusMajor_curve2","ZygomaticusMajor_curve3",name="ZygomaticusMajor_loft",
               constructionHistory=True,uniform=True,close=False,autoReverse=False,degree=3,sectionSpans=1,
               range=False,polygon=0,reverseSurfaceNormals=True)
        c.sets("ZygomaticusMajor_loft",edit=True,forceElement="asFaceRedSG")
        c.parent("ZygomaticusMajor_loft","ZygomaticusMajor",absolute=True)
        self._lip_node("transform","ZygomaticusMajorScale","ZygomaticusMajorPosition1")
        for plug,value in (("ZygomaticusMajorScale.scale",.75),("ZygomaticusMajorPosition2.scale",1.3)):
            c.setKeyframe(plug,time=0,value=1); c.setKeyframe(plug,time=30,value=value)
        c.currentTime(0)
        c.parentConstraint("ZygomaticusMajorScale","ZygomaticusMajorPosition3",maintainOffset=True)
        c.parentConstraint("ZygomaticusMajorPosition1","ZygomaticusMajorPosition3","ZygomaticusMajorPosition2")
        lip_constraint=c.parentConstraint("ZygomaticusMajorScale","Lip_R",maintainOffset=True)[0]
        # Source's 30-frame display demonstration ends at these same values.
        # No refresh or playback is needed to construct its persistent graph.
        c.setAttr("FaceMusclesLayer.visibility",False); c.currentTime(0)
        descendants=c.listRelatives("FaceJoint_M",allDescendents=True,type="joint") or []
        for joint in (*descendants,"Face_M"):
            if c.objExists(joint+".lockInfluenceWeights"): c.setAttr(joint+".lockInfluenceWeights",False)
        raw.setAttr(self.scene_address(source.head)+".lockInfluenceWeights",False)
        fit=self._fit(required=True)
        if not c.objExists("Lip"):
            lip=self._lip_pos("Lip_R"); radius=dist(lip,self._lip_pos("SmileBulge"))
            self._lip_node("transform","Lip","LipSetup")
            c.xform("Lip",worldSpace=True,translation=lip)
            c.addAttr("Lip",longName="falloffRadius",attributeType="double",defaultValue=radius,keyable=True)
            if c.objExists(fit+".NonSym") and c.getAttr(fit+".NonSym"):
                c.duplicate("Lip",name="LipLeft",returnRootsOnly=True)
                c.xform("LipLeft",worldSpace=True,translation=self._lip_pos("Lip_L"))
        for stem in ("Lip","SmileBulge","FrownBulge"):
            self._lip_node("transform",stem+"Pulled",stem+"_R")
        c.parent("LipPulled","SmileBulgePulled","FrownBulgePulled","ZygomaticusMajorScale",absolute=True)
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        c.currentTime(30)
        for stem in ("Lip","SmileBulge","FrownBulge"): c.parent(stem+"Pulled","SDK"+stem+"_R",absolute=True)
        temp=self._lip_node("transform","tempTransform","cornerLipAttach_R")
        c.parent(temp,"cornerLipOffset_R",absolute=True); lip=self._lip_vector(temp+".translate"); c.delete(temp)
        smile=self._lip_vector("SmileBulgePulled.translate"); frown=self._lip_vector("FrownBulgePulled.translate")
        pull=dist(lip,(0,0,0)); c.delete(lip_constraint); c.currentTime(0)
        for side in ("_R","_L"):
            c.setAttr("ctrlBoxMouthCorner"+side+".visibility",True)
            for attribute,x,y in (("smile",1,1),("frown",1,-1),("narrowSmile",-1,1),("narrowFrown",-1,-1)):
                c.setAttr("ctrlMouthCorner"+side+".tx",x); c.setAttr("ctrlMouthCorner"+side+".ty",y)
                self.create_original_face_blended_attribute(("ctrlMouthCorner"+side+".tx","ctrlMouthCorner"+side+".ty"),attribute)
            c.setAttr("ctrlMouthCorner"+side+".tx",0); c.setAttr("ctrlMouthCorner"+side+".ty",0)
        c.setAttr("ctrlMouthCorner_R.tx",1); c.setAttr("ctrlMouthCorner_R.ty",1)
        for side in ("_R","_L"):
            for attr in ("tx","ty"): self.original_face_fit_animation("ctrlMouthCorner"+side+"."+attr,1)
        poses={"Lip_R":lip,"SmileBulge_R":(smile[0]*.8,smile[1]*.8,.33*pull),
               "FrownBulge_R":(frown[0]*.7,frown[1]*.7,.212*pull),
               "CheekBone_R":(frown[0]*.025,frown[1]*.1,.1*pull),
               "Cheek_R":(frown[0]*.1,frown[1]*.25,.3*pull),
               "NoseCorner_R":(frown[0]*.1,frown[1]*.1,None)}
        if c.objExists("lowerLidOuter_R"): poses["lowerLidOuter_R"]=(frown[0]*.0075,frown[1]*.025,.1*pull)
        for control,values in poses.items():
            self.original_face_fit_animation(control)
            for axis,value in zip("xyz",values):
                if value is not None: self.original_face_fit_animation(control+".t"+axis,value)
        self._original_face_fit_timeline()
        return True

    def create_original_smile_pull_controller(self):
        c=self._cmds; raw=getattr(c,"raw",c)
        auto=bool(raw.autoKeyframe(query=True,state=True))
        if auto: raw.autoKeyframe(state=False)
        try:
            temp=self._lip_node("transform","tempXform","LipOffset_R")
            c.parent(temp,"SideReverse_R",absolute=True); rotation=c.getAttr(temp+".ry"); c.delete(temp)
            x=y=0.
            for side in ("_R","_L"):
                control=self.create_original_face_controller("SmilePull",side,2)
                shape=(c.listRelatives(control,shapes=True,fullPath=True) or [None])[0]
                c.setAttr(shape+".overrideColor",17)
                c.scale(1.8,1.8,1.8,control+".cv[0:99]",relative=True,pivot=(0,0,0))
                c.xform("SmilePullOffset"+side,worldSpace=True,translation=self._lip_pos("Lip"+side))
                c.parent("SmilePullOffset"+side,"SideReverse"+side,absolute=True)
                c.setAttr("SmilePullOffset"+side+".scale",1,1,1,type="float3")
                self.shape_original_face_half_moon(control)
                c.setAttr("SmilePullOffset"+side+".ry",rotation)
                for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
                    c.setAttr(control+"."+attr,lock=True,keyable=False)
                for attr in ("tx","ty"): c.setAttr(control+"."+attr,lock=False,keyable=True)
                self.project_original_face_control(control)
                if side=="_R":
                    temp=self._lip_node("transform","tempTransform1",control)
                    c.pointConstraint("Lip_R",temp)
                    c.setAttr("ctrlMouthCorner_R.tx",1); x=c.getAttr(temp+".tx"); c.setAttr("ctrlMouthCorner_R.tx",0)
                    c.setAttr("ctrlMouthCorner_R.ty",1); y=c.getAttr(temp+".ty"); c.setAttr("ctrlMouthCorner_R.ty",0)
                    c.delete(temp)
                self.original_face_output_bw(control+".tx"); self.original_face_output_bw(control+".ty")
                self.add_original_face_sdk(control+".tx","bwctrlMouthCorner"+side+"_translateX.input",x,1)
                self.add_original_face_sdk(control+".ty","bwctrlMouthCorner"+side+"_translateY.input",y,.5)
        finally:
            if auto: raw.autoKeyframe(state=True)

    def create_original_narrow_smile_frown(self):
        c=self._cmds
        self.mirror_original_face_controls(False); self.remove_original_face_ctrl_box_fit_animation()
        self.remove_original_face_fit_animations(); self.create_original_smile_pull_controller()
        for side in ("_R","_L"):
            for arc in ("upper","lower"):
                self.add_original_face_sdk("ctrlMouthCorner"+side+".tx","SDK"+arc+"Lip"+side+".tx",-1,
                                           c.getAttr("SmileValues.Lip_R_tx")/-2)
                c.setAttr("SDK"+arc+"Lip"+side+"_translateX.postInfinity",1)
        for stage,y in (("narrowSmile",1),("narrowFrown",-1)):
            for name in c.listAttr("SmileValues",userDefined=True) or []:
                stem,side,attr=name.split("_"); value=c.getAttr("SmileValues."+name)
                if attr=="tx" or stage=="narrowFrown" and attr=="ty": value*=-1
                if attr=="tz": continue
                self.original_face_fit_animation(stem+"_"+side+"."+attr,value)
            self.original_face_fit_animation("ctrlMouthCorner_R.tx",-1)
            self.original_face_fit_animation("ctrlMouthCorner_R.ty",y)
            self.remove_original_face_ctrl_box_fit_animation()
            self.finish_original_face_sdk("ctrlMouthCorner","_RL",stage,1)
        self.hide_original_face_controllers(True)
        for side in ("_R","_L"):
            c.setAttr("ctrlBoxMouthCorner"+side+".visibility",True)
            c.setAttr("SmilePullOffset"+side+".visibility",True)
            c.connectAttr("bwctrlMouth_M_translateX.output","bwctrlMouthCorner"+side+"_translateX.input[2]")
