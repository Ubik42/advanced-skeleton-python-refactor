"""Original Jaw Open and Lip Up/Down/Side fitting stages, MEL 38317–38707."""
import re

class MayaFaceJawPosesMixin:
    def _original_face_fit_timeline(self):
        c=self._cmds
        getattr(c,"raw",c).playbackOptions(minTime=0,maxTime=30,animationStartTime=0,animationEndTime=30)
        c.currentTime(30)
        c.select(clear=True)
        self._transaction_changed=True

    def fit_original_jaw_open(self,source):
        if not self._cmds.objExists("upperLipMainCurve"): return False
        self.finish_original_jaw_weighing(source)
        self.hide_original_face_controllers(True)
        self.show_original_face_layer_in_transaction("Normal")
        self.mirror_original_face_controls(True)
        self.original_face_fit_animation("ctrlMouth_M.ty",-1)
        for control,attr,value in (("Cheek_R","tz",-.3),("Lip_R","tx",-.4),
                                   ("NoseCorner_R","ty",-.2),("NoseUnder_M","ty",-.05)):
            self.original_face_fit_animation(control)
            self.original_face_fit_animation(control+"."+attr,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_jaw_open(self):
        result=self.finish_original_face_fit_stage("JawOpen","ctrlMouth","_M","ty",-1,("ctrlBoxMouth_M",))
        self._cmds.select(clear=True)
        return result

    def fit_original_lip_up(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return False
        self.finish_original_jaw_open()
        self.hide_original_face_controllers(True)
        self.mirror_original_face_controls(True)
        for attr in ("tx","ty"): c.setAttr("ctrlLips_M."+attr,lock=False,keyable=True)
        self.original_face_fit_animation("ctrlLips_M.ty",1)
        poses={"upperLip_M":{"ty":.8,"sy":.8},"lowerLip_M":{"ty":.8,"sy":.8},
               "Lip_R":{"tx":.1,"ty":.7},"SmileBulge_R":{"ty":.2,"tz":.75},
               "FrownBulge_R":{"ty":.2},"CheekBone_R":{"tx":.1,"ty":.1},
               "NoseCorner_R":{"ty":.3},"NoseSide_R":{"ty":.2},
               "Nostril_R":{"tx":.05,"ty":.1},"Nose_M":{"ty":.05},
               "NoseBridge_M":{"ty":.04},"NoseUnder_M":{"ty":.3},
               "ChinCrease_M":{"ty":.75,"tz":.25}}
        for control,channels in poses.items():
            if control!="Nostril_R": self.original_face_fit_animation(control)
            for attr,value in channels.items(): self.original_face_fit_animation(control+"."+attr,value)
        members=["upperLip_M","lowerLip_M","Nose_M","NoseBridge_M","NoseUnder_M","ChinCrease_M"]
        members.extend(stem+side for side in ("_R","_L") for stem in
                       ("Lip","SmileBulge","FrownBulge","CheekBone","NoseCorner","NoseSide","Nostril"))
        c.sets(members,name="LipUpControls")
        c.sets("LipUpControls",add="FaceBuildingSets")
        self._original_face_fit_timeline()
        return True

    def finish_original_lip_up(self):
        return self.finish_original_face_fit_stage("LipUp","ctrlLips","_M","ty",1,("ctrlBoxLips_M",))

    def fit_original_lip_down(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return False
        self.finish_original_lip_up()
        self.hide_original_face_controllers(True)
        self.mirror_original_face_controls(True)
        self.original_face_fit_animation("ctrlLips_M.ty",-1)
        c.currentTime(0)
        for control in c.sets("LipUpControls",query=True) or []:
            control=control.rsplit("|",1)[-1]
            sdk="SDK"+control
            for attr in c.listAttr(sdk,keyable=True) or []:
                plug=sdk+"."+attr
                if not c.listConnections(plug,source=True,destination=False): continue
                value=c.getAttr(plug,time=30)
                if attr.startswith("scale"): value=1-(value-1)
                c.mute(plug)
                if not control.endswith("_L"): self.original_face_fit_animation(control+"."+attr,value)
        c.setKeyframe("upperLip_M.sy","upperLip_M.sz","lowerLip_M.sy","lowerLip_M.sz",time=0,value=1)
        for plug,value in (("SmileBulge_R.tz",.1),("FrownBulge_R.tz",.1),
                           ("ChinCrease_M.ty",-.3),("ChinCrease_M.tz",.1)):
            self.original_face_fit_animation(plug,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_lip_down(self):
        c=self._cmds
        if c.objExists("FaceBuildInProgress.LipDownFinish"): return False
        c.addAttr("FaceBuildInProgress",longName="LipDownFinish",attributeType="bool",defaultValue=True)
        self.mirror_original_face_controls(False)
        self.remove_original_face_ctrl_box_fit_animation()
        c.currentTime(0)
        for control in c.sets("LipUpControls",query=True) or []:
            c.mute("SDK"+control.rsplit("|",1)[-1],disable=True)
        self.finish_original_face_sdk("ctrlLips","_M","ty",-1)
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBoxLips_M.visibility",True)
        self._transaction_changed=True
        return True

    def fit_original_lip_side(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return False
        self.finish_original_lip_down()
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox.RegionsCtrlVis",True)
        for attr in ("ty","tz","rx","rz","sy"): c.setAttr("LipRegion_M."+attr,lock=True)
        self.original_face_fit_animation("ctrlLips_M.tx",-1)
        poses={"LipRegion_M":{"tx":-1.2,"ry":-25,"sx":.8,"sz":.8},
               "NoseRegion_M":{"tx":-.3,"ty":-.05,"ry":-5,"rz":-5},
               "SmileBulge_R":{"tx":.35,"ty":.2,"tz":.7},
               "FrownBulge_R":{"tx":.35,"ty":-.2,"tz":.7},
               "CheekBone_R":{"tx":.25,"ty":.25},
               "SmileBulge_L":{"tx":-.35,"ty":-.05,"tz":-.1},
               "FrownBulge_L":{"tx":-.35,"ty":.05,"tz":-.1},
               "CheekBone_L":{"tx":-.25,"ty":-.1},"ChinCrease_M":{"tx":-.5}}
        for control,channels in poses.items():
            self.original_face_fit_animation(control)
            for attr,value in channels.items(): self.original_face_fit_animation(control+"."+attr,value)
        members=["LipRegion_M","NoseRegion_M","ChinCrease_M"]
        members.extend(stem+side for side in ("_R","_L") for stem in ("SmileBulge","FrownBulge","CheekBone"))
        c.sets(members,name="LipSideControls")
        c.sets("LipSideControls",add="FaceBuildingSets")
        self._original_face_fit_timeline()
        return True

    def finish_original_lip_side(self):
        """Store the separately fitted left side before converting mirrored SDKs."""
        c=self._cmds
        if c.objExists("FaceBuildInProgress.LipSideFinish"): return False
        c.addAttr("FaceBuildInProgress",longName="LipSideFinish",attributeType="bool",defaultValue=True)
        c.currentTime(30)
        driven=[]
        for shape in c.listRelatives("OnFacecontrols",allDescendents=True,type="nurbsCurve") or []:
            parents=c.listRelatives(shape,parent=True) or []
            if not parents: continue
            control=parents[0].rsplit("|",1)[-1]
            if control.endswith("_L") and c.listConnections(control,source=True,destination=False,type="animCurve"):
                driven.append(control)
        c.createNode("transform",name="LipLeftValues",parent="FaceBuildInProgress")
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr("LipLeftValues."+attr,lock=True,keyable=False)
        for control in driven:
            for channel in ("translate","rotate","scale"):
                for axis in "XYZ":
                    attr=channel+axis
                    c.addAttr("LipLeftValues",longName=control+"_"+attr,attributeType="double",
                              defaultValue=c.getAttr(control+"."+attr),keyable=True)
        self.mirror_original_face_controls(False)
        self.remove_original_face_ctrl_box_fit_animation()
        self.finish_original_face_sdk("ctrlLips","_M","tx",-1)
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr("LipRegion_M."+attr,lock=False)
        source="bwctrlLips_M_translateX.output"
        for axis in ("X","Z"):
            blend="bwSDKLipRegion_M_scale"+axis
            if c.objExists(blend):
                c.setDrivenKeyframe(blend+".input[0]",currentDriver=source,
                                   driverValue=1,value=.8,inTangentType="linear",outTangentType="linear")
        for curve in c.listConnections(source,source=False,destination=True) or []:
            tokens=curve.rsplit("|",1)[-1].split("_")
            if len(tokens)<3 or tokens[1]!="R": continue
            control=tokens[0].replace("SDK","")+"_L"
            attr=re.sub(r"\d+$","",tokens[2])
            saved="LipLeftValues."+control+"_"+attr
            if not c.objExists(saved): continue
            destinations=c.listConnections(curve+".output",source=False,destination=True,plugs=True) or []
            if not destinations: continue
            value=c.getAttr(saved); target=destinations[0]
            for driver,plug,key in ((source,target,1),(source.replace("_R","_L"),target.replace("_R","_L"),-1)):
                c.setDrivenKeyframe(plug,currentDriver=driver,driverValue=key,value=value,
                                   inTangentType="linear",outTangentType="linear")
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox.RegionsCtrlVis",False)
        c.setAttr("ctrlBoxLips_M.visibility",True)
        self._transaction_changed=True
        return True
