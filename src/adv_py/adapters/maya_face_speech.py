"""ADV 6.925 asFacePhonemes/asFaceEmotions, source 39358–39791."""
from adv_py.application.face_pre import FacePreRole

PHONEMES=("aaa","eh","ahh","ohh","uuu","iee","rrr","www","sss","fff","tth","mbp","ssh","schwa","gk","lntd")
EMOTIONS=("happy","angry","sad","surprise","fear","disgust","contempt")

class MayaFaceSpeechMixin:
    def _original_face_speech_enabled(self,attribute):
        c=self._cmds; fit=self._fit(required=True)
        return (not c.objExists(fit+"."+attribute) or bool(c.getAttr(fit+"."+attribute))) and c.objExists("upperLipMainCurve")

    def _original_face_speech_attributes(self,control,names):
        c=self._cmds
        for name in names:
            c.addAttr(control,longName=name,attributeType="double",softMinValue=0,hasSoftMinValue=True,softMaxValue=10,hasSoftMaxValue=True,keyable=True)
            self.original_face_output_bw(control+"."+name)

    def create_original_face_phonemes(self):
        self._require_transaction()
        if not self._original_face_speech_enabled("Phonemes"): return False
        c=self._cmds; geometry=self.read_face_objects(FacePreRole.FACE)[0]
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox2.v",0); c.setAttr("ctrlBox.AimCtrlVis",0); c.setAttr("ctrlBoxPhonemes_M.v",1)
        self.show_original_face_layer_in_transaction("Normal")
        for node in ("upperFaceLocator_M","lowerFaceLocator_M","underFaceLocator_M"):
            if c.objExists(node): c.delete(node)
        c.xform("ctrlMouthCorner_R",objectSpace=True,translation=(1,1,0))
        c.createNode("transform",name="LipSmileValues",parent="SDKLip_R")
        c.parent("LipSmileValues",c.listRelatives("SDKLip_R",parent=True)[0])
        c.xform("ctrlMouthCorner_R",objectSpace=True,translation=(0,0,0))
        c.createNode("transform",name="tempXform"); c.createNode("transform",name="tempXform2")
        self._original_face_speech_attributes("ctrlPhonemes_M",PHONEMES)
        c.addAttr("ctrlPhonemes_M",longName="multipliers",keyable=True)
        c.setAttr("ctrlPhonemes_M.multipliers",lock=True)
        for name in ("jaw","lip"):
            c.addAttr("ctrlPhonemes_M",longName=name,attributeType="double",softMinValue=0,hasSoftMinValue=True,softMaxValue=2,hasSoftMaxValue=True,defaultValue=1,keyable=True)
            self.original_face_output_bw("ctrlPhonemes_M."+name)
        # Original computes this closest vertex even though later poses do not use it.
        for node in ("tempNearestPointOnCurve","closestSampler"):
            if c.objExists(node): c.delete(node)
        c.createNode("nearestPointOnCurve",name="tempNearestPointOnCurve")
        c.connectAttr("JawCurve.worldSpace[0]","tempNearestPointOnCurve.inputCurve",force=True)
        c.setAttr("tempNearestPointOnCurve.inPosition",*self._lip_pos("SmileBulge"),type="float3")
        position=c.getAttr("tempNearestPointOnCurve.result.position")[0]
        c.createNode("closestPointOnMesh",name="closestSampler")
        raw=getattr(c,"raw",c)
        raw.connectAttr(self.scene_address(geometry)+".outMesh",self.scene_address("closestSampler")+".inMesh",force=True)
        c.setAttr("closestSampler.inPosition",*position,type="float3")
        c.getAttr("closestSampler.result.closestVertexIndex")
        c.delete("tempNearestPointOnCurve","closestSampler")
        jaw={"aaa":.9,"eh":.5,"ahh":1,"ohh":.75,"uuu":.25,"iee":.25,"rrr":.5,"www":.4,"mbp":.4,"fff":.2,"tth":.2,"schwa":.5,"gk":.5,"lntd":.5}
        for phoneme in PHONEMES:
            value=jaw.get(phoneme,0)
            if not value: continue
            c.setAttr("ctrlMouth_M.ty",-value)
            position=self._lip_vector("SDKJaw_M.t"); rotation=self._lip_vector("SDKJaw_M.r")
            c.setAttr("ctrlMouth_M.ty",0)
            for attr,v in (("ty",position[1]),("tz",position[2]),("rx",rotation[0])):
                self.add_original_face_sdk("ctrlPhonemes_M."+phoneme,"SDKJaw_M."+attr,10,v)
        for phoneme in ("ohh","sss","ssh"):
            self.add_original_face_sdk("ctrlPhonemes_M."+phoneme,"SDKJaw_M.tz",10,.1)
        wide={"aaa":.3,"eh":.5,"ohh":-.65,"uuu":-.75,"iee":.5,"www":-1,"sss":-.15,"fff":.2,"ssh":-.4}
        for phoneme in PHONEMES:
            value=wide.get(phoneme,0)
            if not value: continue
            for side in ("_R","_L"):
                for stem in ("SDKLip","SmileBulge","FrownBulge","Cheek","NoseCorner"):
                    c.setAttr("ctrlMouth_M.tx",value)
                    position=self._lip_vector(stem+side+".t")
                    c.setAttr("ctrlMouth_M.tx",0)
                    for axis,v in zip("xyz",position): self.add_original_face_sdk("ctrlPhonemes_M."+phoneme,stem+side+".t"+axis,10,v)
        upper={"ohh":(0,.25),"uuu":(0,.45),"iee":(.1,0),"rrr":(.1,.1),"mbp":(-.45,-.45),"sss":(.1,0),"ssh":(.1,.25)}
        lower={"ohh":(0,.25),"uuu":(0,.45),"iee":(-.45,0),"rrr":(-.1,.1),"mbp":(.25,-.25),"sss":(-.45,0),"fff":(0,-.25),"ssh":(-.25,.25)}
        upper_roll={"ohh":3,"uuu":6,"rrr":3,"www":3,"mbp":-6,"sss":1.5,"tth":2,"ssh":5}
        lower_roll={"ohh":3,"uuu":6,"rrr":3,"www":3,"mbp":-4,"sss":3,"fff":-5,"tth":2,"ssh":5}
        tongue={"rrr":(17,17,17),"tth":(10,10,10),"gk":(0,40,-80),"lntd":(0,10,40)}
        for phoneme in PHONEMES:
            driver="ctrlPhonemes_M."+phoneme; c.setAttr(driver,10)
            if phoneme in ("iee","fff"):
                for side in ("_R","_L"): self.add_original_face_sdk(driver,"SDKLip"+side+".ty",10,c.getAttr("LipSmileValues.ty")*.2)
            for stem,poses in (("upper",upper),("lower",lower)):
                if phoneme in poses:
                    for axis,v in zip("yz",poses[phoneme]): self.add_original_face_sdk(driver,"SDK"+stem+"Lip_M.t"+axis,10,v)
            for stem,rolls in (("upper",upper_roll),("lower",lower_roll)):
                value=rolls.get(phoneme,0)
                if not value: continue
                roll="ctrlLips_M."+stem+"Roll"; driven="SDK"+stem+"Lip_M"
                c.setAttr(roll,value)
                position=self._lip_vector(driven+".t"); rotation=self._lip_vector(driven+".r")
                c.setAttr(roll,0)
                for group,values in (("t",position),("r",rotation)):
                    for axis,v in zip("xyz",values): self.add_original_face_sdk(driver,driven+"."+group+axis,10,v)
            if phoneme in tongue and c.objExists("Tongue3_M"):
                values=tongue[phoneme]
                # MEL indexes values[a] for a=1..3 (including zero beyond the
                # three-element array). Preserve that source behavior explicitly.
                for a in range(1,4): self.add_original_face_sdk(driver,f"SDKTongue{a}_M.rz",10,values[a] if a<len(values) else 0)
            c.setAttr(driver,0)
        for output in c.listConnections("ctrlPhonemes_M",source=False,destination=True,type="blendWeighted") or []:
            for curve in c.listConnections(output,source=False,destination=True,type="animCurve") or []:
                nodes=c.listConnections(curve,source=False,destination=True,type="blendWeighted") or []
                plugs=c.listConnections(curve,source=False,destination=True,plugs=True,type="blendWeighted") or []
                if not plugs: continue
                index=plugs[0].split("[",1)[1].split("]",1)[0]
                for bw in nodes:
                    multiplier="jaw" if "Jaw_M" in bw or bw=="bwctrlMouth_M_translateY" else "lip"
                    source="bwctrlPhonemes_M_"+multiplier+".output"; target=bw+".weight["+index+"]"
                    if not c.isConnected(source,target): c.connectAttr(source,target)
        c.delete("tempXform","tempXform2"); c.select(clear=True)
        return {"controls":("ctrlPhonemes_M",)}

    def create_original_face_emotions(self):
        self._require_transaction()
        if not self._original_face_speech_enabled("Emotions"): return False
        c=self._cmds; self.hide_original_face_controllers(True); c.setAttr("ctrlBoxEmotions_M.v",1)
        self._original_face_speech_attributes("ctrlEmotions_M",EMOTIONS)
        bilateral={
            "happy":(("SDKEyeBrowOuter{side}.ty",-.1),("bwctrlMouthCorner{side}_translateX.input",1),("bwctrlMouthCorner{side}_translateY.input",1),("bwctrlEye{side}_blink.input",3)),
            "angry":(("bwctrlBrow{side}_translateX.input",-.5),("bwctrlBrow{side}_translateY.input",-.5),("bwctrlBrow{side}_squeeze.input",8),("bwctrlMouthCorner{side}_translateX.input",-.5),("bwctrlEye{side}_blink.input",3),("bwctrlEye{side}_squint.input",3)),
            "sad":(("bwctrlBrow{side}_translateX.input",.5),("bwctrlBrow{side}_translateY.input",-.5),("bwctrlBrow{side}_squeeze.input",5),("bwctrlMouthCorner{side}_translateX.input",.5),("bwctrlMouthCorner{side}_translateY.input",-.5),("bwctrlEye{side}_blink.input",3),("bwctrlEye{side}_squint.input",3)),
            "surprise":(("bwctrlBrow{side}_translateY.input",.75),("bwctrlEye{side}_wide.input",3),("bwctrlEye{side}_squint.input",-1)),
            "fear":(("bwctrlBrow{side}_translateX.input",1),("bwctrlBrow{side}_squeeze.input",7),("bwctrlMouthCorner{side}_translateX.input",.4),("bwctrlMouthCorner{side}_translateY.input",-.25),("SDKNoseCorner{side}.ty",-.1),("SDKupperLid{side}.ty",.1),("SDKlowerLid{side}.ty",-.1)),
            "disgust":(("bwctrlBrow{side}_squeeze.input",5),("bwctrlEye{side}_squint.input",3),("bwctrlNose{side}_translateY.input",.75),("bwctrlCheek{side}_translateY.input",1),("bwctrlMouthCorner{side}_translateX.input",.25),("bwctrlMouthCorner{side}_translateY.input",-.25)),
            "contempt":(("bwctrlMouthCorner{side}_translateX.input",.6),("bwctrlMouthCorner{side}_translateY.input",.3))}
        center={"happy":(("SDKupperLip_M.ty",.1),("SDKlowerLip_M.ty",.1),("SDKNoseRegion_M.tz",-.1),("SDKNoseRegion_M.rx",5)),
                "angry":(("bwctrlLips_M_upperSqueeze.input",5),("bwctrlLips_M_lowerSqueeze.input",5)),
                "sad":(("bwctrlLips_M_upperSqueeze.input",3),("bwctrlLips_M_lowerSqueeze.input",3)),
                "surprise":(("bwctrlMouth_M_translateY.input",-1),),
                "fear":(("bwctrlMouth_M_translateY.input",-.75),("bwctrlLips_M_upperSqueeze.input",3),("bwctrlLips_M_lowerSqueeze.input",3)),
                "disgust":(("SDKlowerLip_M.ty",-.5),)}
        for emotion in EMOTIONS:
            driver="ctrlEmotions_M."+emotion
            for side in ("_R","_L"):
                for target,value in bilateral[emotion]:
                    # The optional outer-lid key precedes the main lids in
                    # asFaceEmotions, so preserve blendWeighted input order.
                    if emotion=="fear" and target=="SDKupperLid{side}.ty" and c.objExists("lowerLidOuter_R"):
                        self.add_original_face_sdk(driver,"SDKlowerLidOuter"+side+".ty",10,-.1)
                    self.add_original_face_sdk(driver,target.format(side=side),10,value)
                if emotion=="angry" and c.objExists("Nostril_R"): self.add_original_face_sdk(driver,"SDKNostril"+side+".tx",10,.2)
            for target,value in center.get(emotion,()): self.add_original_face_sdk(driver,target,10,value)
            c.setAttr(driver,10); getattr(c,"raw",c).refresh(); c.setAttr(driver,0)
        c.select(clear=True)
        return {"controls":("ctrlEmotions_M",)}
