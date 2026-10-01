"""Original facial fitting stages and combined mouth-corner driver graph."""
from math import dist
from .maya_original_driver_attributes import MayaOriginalDriverAttributesMixin
from .maya_face_cage import MayaFaceCageHost
from .maya_face_smile import MayaFaceSmileMixin
from .maya_face_brow import MayaFaceBrowMixin
from .maya_face_up_mid_lo import MayaFaceUpMidLoMixin
from .maya_face_speech import MayaFaceSpeechMixin
from .maya_face_finish import MayaFaceFinishMixin
from .maya_face_eye_poses import MayaFaceEyePosesMixin
from .maya_face_roblox import MayaFaceRobloxMixin
from .maya_face_eye_ball import MayaFaceEyeBallMixin
from .maya_face_pupil_iris import MayaFacePupilIrisMixin
from .maya_face_prep_fits import MayaFacePrepFitsMixin
from .maya_face_eye_lid_original import MayaFaceEyeLidOriginalMixin
from .maya_face_prep_skin import MayaFacePrepSkinMixin
from .maya_face_prep_first import MayaFacePrepFirstMixin
from .maya_face_prep_prefix import MayaFacePrepPrefixMixin
from .maya_face_arkit import MayaFaceARKitMixin
from .maya_face_bs_conversion import MayaFaceBSConversionMixin

class MayaFaceExpressionHost(MayaOriginalDriverAttributesMixin,MayaFaceBSConversionMixin,MayaFaceARKitMixin,MayaFacePrepPrefixMixin,MayaFacePrepFirstMixin,MayaFacePrepSkinMixin,MayaFaceEyeLidOriginalMixin,MayaFacePrepFitsMixin,MayaFacePupilIrisMixin,MayaFaceEyeBallMixin,MayaFaceRobloxMixin,MayaFaceEyePosesMixin,MayaFaceFinishMixin,MayaFaceSpeechMixin,MayaFaceSmileMixin,MayaFaceBrowMixin,MayaFaceUpMidLoMixin,MayaFaceCageHost):
    def create_original_face_blended_attribute(self,drivers,attribute):
        return self.create_original_blended_attribute(drivers,attribute)

    def fit_original_face_squint(self):
        c=self._cmds; fit=self._fit(required=True)
        factor=dist(self._lip_pos("upperLid_R"),self._lip_pos("lowerLid_R"))/float(c.getAttr("OnFacecontrols.sx"))*.75
        simpler=bool(c.objExists(fit+".SimplerEyeLid") and c.getAttr(fit+".SimplerEyeLid"))
        cyclops=bool(c.objExists(fit+".Cyclops") and c.getAttr(fit+".Cyclops"))
        for side in ("_R","_L"):
            c.addAttr("ctrlEye"+side,longName="squint",attributeType="double",softMaxValue=10,
                      softMinValue=0,hasMinValue=True,minValue=0,defaultValue=0,keyable=True)
            self.original_face_output_bw("ctrlEye"+side+".squint")
            multiply=self._lip_node("multiplyDivide","eyeLidBlinkSquintMPD"+side)
            c.connectAttr("ctrlEye"+side+".blink",multiply+".input1X")
            c.connectAttr("ctrlEye"+side+".squint",multiply+".input2X")
            scale=self._lip_node("setRange","eyeLidBlinkSquintSR"+side)
            c.setAttr(scale+".maxX",-7.3); c.setAttr(scale+".oldMaxX",100)
            c.connectAttr(multiply+".outputX",scale+".valueX")
            bw="bwctrlEye"+side+"_blink"
            c.connectAttr(scale+".outValueX",self.next_original_face_bw_input(bw))
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        for side in ("_R","_L"): self.original_face_fit_animation("ctrlEye"+side+".squint",10)
        include=c.getAttr(fit+".Include",asString=True) if c.objExists(fit+".Include") else "Complete"
        if include not in ("Skip Above Eyes","Skip Above+Below Eyes"):
            self.original_face_fit_animation("EyeRegion_R.sy",.75)
            self.original_face_fit_animation("EyeBrowRegion_R.ty",-.75*factor)
        poses={"upperLid_R.ty":-.4*factor,"lowerLid_R.tx":-.4*factor*(not cyclops),
               "lowerLid_R.ty":.525*factor,"outerLid_R.tx":-.15*factor*(not cyclops),
               "lowerLidOuter_R.tx":-.07*factor*(not cyclops),"lowerLidOuter_R.ty":.07*factor}
        if not simpler: poses.update({"upperLidOuter_R.ty":-.2*factor,"outerLidOuter_R.sy":.5,"innerLidOuter_R.sy":.5})
        for plug,value in poses.items(): self.original_face_fit_animation(plug,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_squint(self):
        result=self.finish_original_face_fit_stage("Squint","ctrlEye","_RL","squint",10,("ctrlBoxEye_R","ctrlBoxEye_L"))
        if result:
            c=self._cmds; fit=self._fit(required=True)
            if c.objExists(fit+".Cyclops") and c.getAttr(fit+".Cyclops"):
                c.connectAttr("bwctrlEye_L_squint.output","bwctrlEye_R_squint.input[0]",force=True)
            c.setAttr("ctrlBox.RegionsCtrlVis",False)
        return result

    def finish_original_face_smile_pull(self):
        c=self._cmds
        if c.objExists("FaceBuildInProgress.SmilePullFinish"): return False
        c.addAttr("FaceBuildInProgress",longName="SmilePullFinish",attributeType="bool",defaultValue=True)
        for node in ("Lip","FaceMuscles","FaceMusclesLayer"):
            if c.objExists(node): c.delete(node)
        self.mirror_original_face_controls(False); self.remove_original_face_ctrl_box_fit_animation()
        c.currentTime(30)
        c.createNode("transform",name="SmileValues",parent="FaceBuildInProgress")
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr("SmileValues."+attr,lock=True,keyable=False)
        for stem in ("Lip","SmileBulge","FrownBulge","lowerLidOuter","CheekBone","Cheek","NoseCorner"):
            control=stem+"_R"
            if not c.objExists(control): continue
            for channel in "trs":
                for axis in "xyz":
                    c.addAttr("SmileValues",longName=control+"_"+channel+axis,attributeType="double",
                              defaultValue=c.getAttr(control+"."+channel+axis),keyable=True)
        self.finish_original_face_sdk("ctrlMouthCorner","_RL","smile",1)
        self.hide_original_face_controllers(True)
        for side in ("_R","_L"): c.setAttr("ctrlBoxMouthCorner"+side+".visibility",True)
        return True

    def fit_original_face_frown_pull(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return False
        self.finish_original_face_smile_pull()
        for side in ("_R","_L"):
            self.original_face_fit_animation("ctrlMouthCorner"+side+".tx",1)
            self.original_face_fit_animation("ctrlMouthCorner"+side+".ty",-1)
        for name in c.listAttr("SmileValues",userDefined=True) or []:
            stem,side,attr=name.split("_")
            value=c.getAttr("SmileValues."+name)
            if attr in ("ty","rz"): value*=-1
            self.original_face_fit_animation(stem+"_"+side+"."+attr,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_frown_pull(self):
        result=self.finish_original_face_fit_stage("FrownPull","ctrlMouthCorner","_RL","frown",1,
                                                   ("ctrlBoxMouthCorner_R","ctrlBoxMouthCorner_L"))
        if result: self.create_original_narrow_smile_frown()
        return result

    def fit_original_face_cheek(self):
        if not self._cmds.objExists("upperLipMainCurve"): return False
        self.finish_original_face_frown_pull()
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        for side in ("_R","_L"): self.original_face_fit_animation("ctrlCheek"+side+".tx",1)
        self.original_face_fit_animation("Cheek_R")
        for attr,value in (("tz",1),("sx",1.2),("sy",1.2),("sz",1.2)):
            self.original_face_fit_animation("Cheek_R."+attr,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_cheek(self):
        return self.finish_original_face_fit_stage("Cheek","ctrlCheek","_RL","tx",1,("ctrlBoxCheek_R","ctrlBoxCheek_L"))

    def fit_original_face_cheek_raiser(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return False
        self.finish_original_face_cheek()
        temp=c.createNode("transform",name="tempXform",parent="lowerLid_R")
        c.pointConstraint("innerLid_R","outerLid_R",temp)
        # Source computes half-close but retains the fixed values below.
        c.getAttr(temp+".ty"); c.delete(temp)
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        for side in ("_R","_L"): self.original_face_fit_animation("ctrlCheek"+side+".ty",1)
        for plug,value in (("lowerLid_R.ty",.5),("lowerLidOuter_R.ty",.45),
                           ("lowerLidOuter_R.tz",.1),("CheekBone_R.ty",.1),("NoseSide_R.ty",.2)):
            self.original_face_fit_animation(plug,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_cheek_raiser(self):
        return self.finish_original_face_fit_stage("CheekRaiser","ctrlCheek","_RL","ty",1,("ctrlBoxCheek_R","ctrlBoxCheek_L"))

    def fit_original_face_snarl(self,source):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return False
        self.finish_original_lip_side()
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        if c.objExists("NoseSide_R"):
            a=c.createNode("transform",name="TempPos",parent="upperLidMain0_R")
            c.delete(c.geometryConstraint(self.scene_address(source.geometry),a))
            c.parent(a,"NoseSide_R",absolute=True); c.setAttr(a+".tx",0); c.setAttr(a+".tz",0)
            c.delete(c.geometryConstraint(self.scene_address(source.geometry),a))
            b=c.createNode("transform",name="TempPos2")
            constraint=c.pointConstraint(a,"NoseSide_R",b,weight=.25)[0]
            c.pointConstraint("NoseSide_R",b,weight=.75)
            c.delete(constraint); c.delete(c.geometryConstraint(self.scene_address(source.geometry),b))
            c.parent(b,"NoseSideOffset_R",absolute=True); nose_side=self._lip_vector(b+".translate")
            c.delete(c.pointConstraint("NoseCorner_R","NoseSide_R",b))
            c.parent(b,"NoseCornerOffset_R",absolute=True); nose_corner=self._lip_vector(b+".translate")
            c.delete(c.pointConstraint("NoseCorner_R","upperLipB_R",b))
            c.parent(b,"upperLipBOffset_R",absolute=True); c.getAttr(b+".translate")
            c.delete(a,b)
        else: nose_side=(0,.25,0); nose_corner=(0,.5,0)
        for side in ("_R","_L"): self.original_face_fit_animation("ctrlNose"+side+".ty",1)
        self.original_face_fit_animation("NoseCorner_R")
        self.original_face_fit_animation("NoseCorner_R.ty",nose_corner[1])
        self.original_face_fit_animation("NoseSide_R")
        for axis,value in zip("xyz",nose_side): self.original_face_fit_animation("NoseSide_R.t"+axis,value)
        for plug,factor in (("NoseUnder_M.ty",.2),("Nostril_R.ty",.25),("Nose_M.ty",.075),
                            ("NoseBridge_M.ty",.04),("SmileBulge_R.ty",.3)):
            self.original_face_fit_animation(plug,nose_corner[1]*factor)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_snarl(self):
        c=self._cmds
        if c.objExists("FaceBuildInProgress.SnarlFinish"): return False
        c.addAttr("FaceBuildInProgress",longName="SnarlFinish",attributeType="bool",defaultValue=True)
        self.mirror_original_face_controls(False); self.remove_original_face_ctrl_box_fit_animation()
        self.finish_original_face_sdk("ctrlNose","_RL","ty",1)
        c.setAttr("ctrlNose_R.ty",1); position=self._lip_vector("SDKNoseCorner_R.translate"); c.setAttr("ctrlNose_R.ty",0)
        for plug,factor in (("NoseSide_R.ty",-.05),("NoseCorner_R.tx",.1),("Nostril_R.tx",.2),("Nostril_R.tz",.2)):
            self.original_face_fit_animation(plug,position[1]*factor)
        self.finish_original_face_sdk("ctrlNose","_RL","tx",1)
        self.hide_original_face_controllers(True)
        for side in ("_R","_L"): c.setAttr("ctrlBoxNose"+side+".visibility",True)
        c.select(clear=True)
        return True
