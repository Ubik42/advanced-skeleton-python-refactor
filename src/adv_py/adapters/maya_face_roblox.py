"""Original 50 Roblox Head channels and SDK mapping, source 40064–40211."""

ROBLOX_HEAD_SHAPES=(
    "ChinRaiserUpperLip","ChinRaiser","FlatPucker","Funneler","LowerLipSuck","LipPresser","LipsTogether","MouthLeft",
    "MouthRight","Pucker","UpperLipSuck","LeftCheekPuff","LeftDimpler","LeftLipCornerDown","LeftLowerLipDepressor",
    "LeftLipCornerPuller","LeftLipStretcher","LeftUpperLipRaiser","RightCheekPuff","RightDimpler","RightLipCornerDown",
    "RightLowerLipDepressor","RightLipCornerPuller","RightLipStretcher","RightUpperLipRaiser","JawDrop","JawLeft","JawRight",
    "Corrugator","LeftBrowLowerer","LeftOuterBrowRaiser","LeftNoseWrinkler","LeftInnerBrowRaiser","RightBrowLowerer",
    "RightOuterBrowRaiser","RightInnerBrowRaiser","RightNoseWrinkler","EyesLookDown","EyesLookLeft","EyesLookUp",
    "EyesLookRight","LeftCheekRaiser","LeftEyeUpperLidRaiser","LeftEyeClosed","RightCheekRaiser","RightEyeUpperLidRaiser",
    "RightEyeClosed","TongueDown","TongueOut","TongueUp")

class MayaFaceRobloxMixin:
    def create_original_face_roblox_head(self):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self._original_face_speech_attributes("ctrlRobloxHead_M",ROBLOX_HEAD_SHAPES)
        c.select("ctrlRobloxHead_M",replace=True); c.currentTime(0)
        auto=bool(raw.autoKeyframe(query=True,state=True))
        if auto: raw.autoKeyframe(state=False)
        direct={
            "ChinRaiserUpperLip":(("SDKupperLip_M.ty",.5),),"ChinRaiser":(("SDKlowerLip_M.ty",.5),),
            "JawDrop":(("ctrlMouth_M.ty",-1),),"JawLeft":(("ctrlMouth_M.jawSide",10),),"JawRight":(("ctrlMouth_M.jawSide",-10),),
            "Corrugator":(("ctrlBrow_R.squeeze",10),("ctrlBrow_L.squeeze",10)),
            "FlatPucker":(("ctrlMouth_M.upperPucker",5),("ctrlMouth_M.lowerPucker",5)),
            "Funneler":(("ctrlMouth_M.upperPucker",10),("ctrlMouth_M.lowerPucker",10),("SDKupperLip_M.ty",.3),("SDKlowerLip_M.ty",-.3)),
            "LowerLipSuck":(("ctrlMouth_M.lowerPress",5),("ctrlMouth_M.lowerRoll",-5)),
            "LipPresser":(("ctrlMouth_M.upperPress",5),("ctrlMouth_M.lowerPress",5),("ctrlMouth_M.upperSqueeze",5),("ctrlMouth_M.lowerSqueeze",5)),
            "MouthLeft":(("ctrlLips_M.tx",1),),"MouthRight":(("ctrlLips_M.tx",-1),),
            "Pucker":(("ctrlMouth_M.upperPucker",10),("ctrlMouth_M.lowerPucker",10)),
            "UpperLipSuck":(("ctrlMouth_M.upperSqueeze",10),),
            "EyesLookDown":(("ctrlEye_R.ty",-1),("ctrlEye_L.ty",-1)),
            "EyesLookLeft":(("ctrlEye_R.tx",1),("ctrlEye_L.tx",1)),
            "EyesLookUp":(("ctrlEye_R.ty",1),("ctrlEye_L.ty",1)),
            "EyesLookRight":(("ctrlEye_R.tx",-1),("ctrlEye_L.tx",-1)),
            "TongueDown":(("SDKTongue0_M.rz",-30),),"TongueOut":(("SDKTongue0_M.tx",1.5),("SDKTongue0_M.rz",15)),
            "TongueUp":(("SDKTongue0_M.rz",30),)}
        sided={
            "CheekPuff":(("ctrlCheek{side}.tx",.4),),"Dimpler":(("ctrlMouthCorner{side}.tx",.3),),
            "LipCornerDown":(("ctrlMouthCorner{side}.tx",.5),("ctrlMouthCorner{side}.ty",-.5)),
            "LowerLipDepressor":(("SDKlowerLipA{side}.ty",-.75),),
            "LipCornerPuller":(("ctrlMouthCorner{side}.tx",.75),("ctrlMouthCorner{side}.ty",.75)),
            "LipStretcher":(("ctrlMouthCorner{side}.tx",.75),),"UpperLipRaiser":(("SDKupperLipA{side}.ty",.75),),
            "EyeClosed":(("ctrlEye{side}.blink",10),),"BrowLowerer":(("ctrlBrow{side}.tx",-1),),
            "OuterBrowRaiser":(("ctrlBrow{side}.outerUpDown",10),),
            "NoseWrinkler":(("ctrlBrow{side}.outerUpDown",-5),("ctrlNose{side}.ty",1)),
            "InnerBrowRaiser":(("ctrlBrow{side}.tx",1),),"CheekRaiser":(("CheekRaiser{side}.ty",.75),),
            "EyeUpperLidRaiser":(("SDKupperLid{side}.ty",.5),)}
        try:
            for shape in ROBLOX_HEAD_SHAPES:
                driver="ctrlRobloxHead_M."+shape
                for target,value in direct.get(shape,()): self.add_original_face_sdk(driver,target,10,value)
                if shape=="LipsTogether":
                    c.setAttr("ctrlMouth_M.ty",0); a=self._lip_pos("lowerLip_M")
                    c.setAttr("ctrlMouth_M.ty",-1); b=self._lip_pos("lowerLip_M")
                    c.xform("lowerLip_M",worldSpace=True,translation=(b[0],b[1]+a[1]-b[1],b[2]))
                    value=self._lip_vector("lowerLip_M.t")[1]
                    c.setAttr("ctrlMouth_M.ty",0); c.setAttr("lowerLip_M.t",0,0,0,type="float3")
                    self.add_original_face_sdk(driver,"SDKlowerLip_M.ty",10,value/2)
                    self.add_original_face_sdk(driver,"SDKupperLip_M.ty",10,value/-2)
                for prefix,side in (("Right","_R"),("Left","_L")):
                    if not shape.startswith(prefix): continue
                    stem=shape[len(prefix):]
                    for target,value in sided.get(stem,()): self.add_original_face_sdk(driver,target.format(side=side),10,value)
                    # Source invokes EyeClosed twice; retain both additive BW
                    # inputs rather than silently removing the repeated call.
                    if stem=="EyeClosed": self.add_original_face_sdk(driver,"ctrlEye"+side+".blink",10,10)
        finally:
            if auto: raw.autoKeyframe(state=True)
        c.select("ctrlRobloxHead_M",replace=True)
        return {"controls":("ctrlRobloxHead_M",)}
