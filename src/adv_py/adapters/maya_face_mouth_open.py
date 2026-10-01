"""ADV 6.925 asFaceDesignMouthOpen, source 29232–29342."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_jaw_lip_weights import MayaFaceJawLipWeightsHost
from .maya_face_deformer_sets import original_face_deformer_sets

class MayaFaceMouthOpenHost(MayaFaceJawLipWeightsHost):
    def capture_mouth_open_input(self):
        c=self._cmds; fit=self._fit(required=True)
        for name in ("FaceBuildInProgressHidden","templateLayer","lipArea","Jaw_M","ctrlMouth_M",
                     "lowerLipMainCurve","upperLipOuterCurve"):
            if not c.objExists(name): raise FitSkeletonValidationError("Mouth Open 缺少原版节点："+name)
        return float(c.getAttr(fit+".faceScale"))

    def create_mouth_open_design(self,scale):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self._transaction_changed=True
        count=int(c.getAttr("lowerLipMainCurve.spans"))+1
        center=self._lip_pos("lowerLipMainCurve.cv[0]")
        corner=self._lip_pos(f"lowerLipMainCurve.cv[{count}]")
        self._lip_node("transform","LipDeformations","FaceBuildInProgressHidden")
        c.duplicate("templateLayer",name="LipDeform",returnRootsOnly=True)
        raw.sets(self.scene_address("LipDeform"),edit=True,forceElement=":initialShadingGroup")
        with original_face_deformer_sets(c):
            soft,handle=c.softMod("LipDeform",name="mouthOpenSoftMod",
                                  falloffMode=1,falloffAroundSelection=False)
        if handle!="mouthOpenSoftModHandle": handle=c.rename(handle,"mouthOpenSoftModHandle")
        shape=(c.listRelatives(handle,shapes=True,fullPath=True) or [None])[0]
        if shape.rsplit("|",1)[-1]!="mouthOpenSoftModHandleShape": shape=c.rename(shape,"mouthOpenSoftModHandleShape")
        groups=c.listConnections(soft+".message",type="objectSet") or []
        if len(groups)!=1: raise RuntimeError("Mouth Open SoftMod 未生成唯一原版变形集")
        c.rename(groups[0],"mouthOpenSoftModSet")
        c.setAttr(shape+".origin",*center)
        c.setAttr(soft+".falloffCenter",*center); c.xform(handle,pivots=center)
        c.setAttr(soft+".falloffMode",1)
        c.setAttr(soft+".falloffRadius",-corner[0]*2)
        sampler=self._lip_node("closestPointOnMesh","mouthOpenSamplerTemp#")
        c.connectAttr("LipDeform.outMesh",sampler+".inMesh")
        c.setAttr(sampler+".inPosition",*self._lip_pos("upperLipOuterCurve.cv[0]"))
        top="LipDeform.vtx["+str(int(c.getAttr(sampler+".closestVertexIndex")))+"]"
        c.setAttr(sampler+".inPosition",*corner)
        corner_vertex="LipDeform.vtx["+str(int(c.getAttr(sampler+".closestVertexIndex")))+"]"
        corner_before=self._lip_pos(corner_vertex)
        c.delete(sampler)
        c.setAttr(handle+".ty",-scale/10)
        c.setAttr(soft+".falloffCurve[1].falloffCurve_FloatValue",1)
        c.setAttr(soft+".falloffRadius",0)
        top_before=self._lip_pos(top)
        radius=-corner[0]*2
        c.setAttr(soft+".falloffRadius",radius)
        for index in range(99):
            if self._lip_pos(top)[1]-top_before[1]!=0: break
            radius+=scale/1000*index
            c.setAttr(soft+".falloffRadius",radius)
        c.setAttr(soft+".falloffCurve[1].falloffCurve_FloatValue",.05)
        c.setAttr(soft+".falloffCurve[0].falloffCurve_FloatValue",.95)
        corner_after=self._lip_pos(corner_vertex)
        percentage=1-(corner_before[1]-corner_after[1])/(scale/10)
        for index,position,value in ((2,percentage,.5),(3,percentage-.15,.8),(4,percentage+.15,.2)):
            c.setAttr(soft+f".falloffCurve[{index}].falloffCurve_Position",position)
            c.setAttr(soft+f".falloffCurve[{index}].falloffCurve_FloatValue",value)
        for index in range(5): c.setAttr(soft+f".falloffCurve[{index}].falloffCurve_Interp",3)
        members=raw.sets(self.scene_address("lipArea"),query=True) or []
        vertices=raw.ls(members,long=True,flatten=True) or []
        cast=self._jaw_layer_cast(vertices,"LipDeform")
        faces=raw.ls(raw.polyListComponentConversion([self.scene_address(v) for v in cast],
                     toFace=True,internal=True),flatten=True) or []
        keep=set(faces)
        all_faces=raw.ls(self.scene_address("LipDeform")+".f[*]",flatten=True) or []
        remove=[face for face in all_faces if face not in keep]
        if remove: c.polyDelFacet(remove,constructionHistory=True)
        c.setAttr(handle+".ty",0)
        c.parentConstraint("Jaw_M",handle,maintainOffset=True)
        c.scaleConstraint("Jaw_M",handle,maintainOffset=True)
        raw.playbackOptions(minTime=0,maxTime=30,animationStartTime=0,animationEndTime=30)
        for plug,value in (("ctrlMouth_M.ty",-1),("Jaw_M.ty",-.5),("Jaw_M.tz",.5),("Jaw_M.rx",15)):
            self.original_face_fit_animation(plug,value)
        # The original scale keys are both at frame 0; keep that behavior.
        for attr in ("sx","sy","sz"): c.setKeyframe("Jaw_M."+attr,time=0,value=1)
        for attr in ("tx","ry","rz"): c.setAttr("Jaw_M."+attr,lock=True)
        return ("LipDeform",soft,handle)
