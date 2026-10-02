"""ADV original Blink/Wide fitting and Finish, source 34124–34227."""

class MayaFaceEyePosesMixin:
    def fit_original_face_eye_blink(self):
        self._require_transaction()
        c=self._cmds; fit=self._fit(required=True)
        simpler=bool(c.objExists(fit+".SimplerEyeLid") and c.getAttr(fit+".SimplerEyeLid"))
        for side in ("_R","_L"):
            for name in ("wide","blink"):
                c.addAttr("ctrlEye"+side,longName=name,attributeType="double",softMaxValue=10,hasSoftMaxValue=True,softMinValue=0,hasMinValue=True,keyable=True)
                self.original_face_output_bw("ctrlEye"+side+"."+name)
            bw="bwctrlEye"+side+"_blink"
            conversion=c.createNode("unitConversion",name=bw+"UnitConversion")
            reverse=c.createNode("reverse",name=bw+"Reverse")
            c.setAttr(conversion+".conversionFactor",.1)
            c.connectAttr(bw+".output",conversion+".input")
            c.connectAttr(conversion+".output",reverse+".inputX")
            for arc in ("upper","lower"):
                control=arc+"Lid"+side
                multiply=c.createNode("multiplyDivide",name=control+"FleshyBlinkMPD")
                c.connectAttr(control+".fleshy",multiply+".input1Y")
                c.connectAttr(reverse+".outputX",multiply+".input2Y")
                c.connectAttr(multiply+".outputY",control+"FleshyMPD.input2Y",force=True)
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        poses=(("ctrlEye_R.blink",10),("ctrlEye_L.blink",10),("upperLid_R.blink",10),
               ("lowerLid_R.blink",10),("upperLid_R.tx",-.2),("lowerLid_R.tx",-.2),("outerLid_R.tx",-.1))
        for plug,value in poses: self.original_face_fit_animation(plug,value)
        if not simpler:
            for plug,value in (("upperLidOuter_R.tx",-.05),("upperLidOuter_R.ty",-.07),
                               ("lowerLidOuter_R.tx",-.1),("lowerLidOuter_R.ty",.1)):
                self.original_face_fit_animation(plug,value)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_eye_blink(self):
        return self.finish_original_face_fit_stage("EyeBlink","ctrlEye","_RL","blink",10,("ctrlBoxEye_R","ctrlBoxEye_L"))

    def fit_original_face_eye_wide(self):
        self._require_transaction()
        self.finish_original_face_eye_blink()
        self.hide_original_face_controllers(True); self.mirror_original_face_controls(True)
        self.original_face_fit_animation("upperLid_R.ty",.3)
        self.original_face_fit_animation("lowerLid_R.ty",-.1)
        self._original_face_fit_timeline()
        return True

    def finish_original_face_eye_wide(self):
        return self.finish_original_face_fit_stage("EyeWide","ctrlEye","_RL","wide",10,("ctrlBoxEye_R","ctrlBoxEye_L"))
