"""ADV 6.925 asFaceLipFalloff, including preview/update and layer Skin."""
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_lip_falloff import lip_control_letter
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_fit_selection import MayaFaceFitSelectionMixin
from .maya_face_eyelid_rig import MayaFaceEyeLidRigHost

class MayaFaceLipFalloffHost(MayaFaceFitSelectionMixin,MayaFaceEyeLidRigHost):
    def resolve_lip_falloff_options(self,options):
        from dataclasses import replace
        return replace(options,preview=options.preview or self._cmds.objExists("asFaceLipFalloffTest"),
                       update=options.update or self._cmds.objExists("asFaceLipFalloffUpdate"))

    def capture_lip_falloff_context(self,options):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return None
        fit=self._fit(required=True)
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("Lip Falloff 需要唯一 Face 网格")
        heads=c.ls(c.getAttr(fit+".HeadJoint"),long=True,type="joint") or []
        if len(heads)!=1: raise FitSkeletonValidationError("Lip Falloff Head 关节缺失或不唯一")
        head="MultiSkinClustersFaceLipJoint_M" if options.multi_skin_clusters else heads[0]
        skin="LipSC" if options.multi_skin_clusters else self.face_skin_cluster(geometry[0])
        required=("LipJoints_M","FaceAreas","FaceBuildingSets","lipArea","NoseUnder",
            "upperLipOuterCurve","lowerLipOuterCurve","upperLipInnerCurve","lowerLipInnerCurve",head,skin)
        if not options.preview:
            required+=tuple(("upperLipA_R","upperLipB_R","lowerLipA_R","lowerLipB_R","Lip_R",
                             "templateLayer","FaceBuildInProgressHidden"))
        for name in required:
            if len(c.ls(name,long=True) or [])!=1: raise FitSkeletonValidationError("Lip Falloff 缺少原版节点："+name)
        count=12
        if c.objExists(fit+".LipCtrls"):
            try: count=int(c.getAttr(fit+".LipCtrls",asString=True))
            except (ValueError,TypeError): raise FitSkeletonValidationError("LipCtrls 不是原版有效控制器数") from None
        if count%4 or count<8 or count//4>26: raise FitSkeletonValidationError("LipCtrls 必须是原版四组控制器数量")
        if (options.preview or options.update) and not c.objExists(fit+".vtxsFromLipToNose"):
            raise FitSkeletonValidationError("先运行 Lip Falloff 建立 lip-to-nose 数据，再预览或更新")
        return geometry[0],head,skin,count

    def _lip_falloff_hammer(self,skin,vertices,iterations):
        if not vertices: return
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        obey=False
        if all(c.objExists(fit+"."+name) for name in ("GameEngine","UseMaxInf","MaxInf")):
            if c.getAttr(fit+".GameEngine") and c.getAttr(fit+".UseMaxInf"):
                obey=int(c.getAttr(fit+".MaxInf",asString=True))>0
        raw.select(tuple(self.scene_address(v) for v in vertices),replace=True)
        raw.skinCluster(self.scene_address(skin),edit=True,smoothWeights=0,
            smoothWeightsMaxIterations=iterations,obeyMaxInfluences=obey)

    def create_lip_falloff(self,context,options):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        geometry,head,skin,count=context
        self._transaction_changed=True
        for flag in ("asFaceLipFalloffTest","asFaceLipFalloffUpdate"):
            if c.objExists(flag): c.delete(flag)
        start=self.sample_face_fit_vertices("upperLipOuterCurve.cv[0]",geometry)[0]
        end=self.sample_face_fit_vertices("NoseUnder",geometry)[0]
        c.currentTime(0)
        # Lock every participating Skin influence, including an external Head.
        influence_nodes=raw.skinCluster(self.scene_address(skin),query=True,influence=True) or []
        for joint in influence_nodes:
            if raw.objExists(joint+".lockInfluenceWeights"): raw.setAttr(joint+".lockInfluenceWeights",True)
        raw.setAttr(self.scene_address(head)+".lockInfluenceWeights",False)
        for joint in c.listRelatives("LipJoints_M",children=True,type="joint") or []:
            c.setAttr(joint+".lockInfluenceWeights",False)
        if not (options.preview or options.update):
            if not c.objExists(fit+".vtxsFromLipToNose"):
                c.addAttr(fit,longName="vtxsFromLipToNose",attributeType="long",defaultValue=3)
            raw.select(self.scene_address(start),replace=True)
            distance=0
            for _ in range(25):
                selected=set(raw.ls(selection=True,long=True,flatten=True) or [])
                target=raw.ls(self.scene_address(end),long=True,flatten=True)[0]
                if target in selected: break
                distance+=1; raw.polySelectConstraint(propagate=1,type=1)
            if start==end: distance=0
            c.setAttr(fit+".vtxsFromLipToNose",distance)
        if not options.preview:
            for control in ("upperLipA_R","upperLipB_R","lowerLipA_R","lowerLipB_R","Lip_R"):
                c.xform(control,objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
        for name in ("lipFalloffArea","lipFalloffInsideMouthArea"):
            if c.objExists(name): c.delete(name)
        c.sets(empty=True,name="lipFalloffArea"); c.sets("lipFalloffArea",add="FaceAreas")
        if not c.objExists("lipFalloffAreaMax"):
            c.sets(empty=True,name="lipFalloffAreaMax"); c.sets("lipFalloffAreaMax",add="FaceBuildingSets")
        parts={}
        for part,growth in (("Inner",options.inner),("Outer",options.outer)):
            mirrors=[]
            for arc in ("upper","lower"):
                name=arc+"Lip"+part+"Curve_L"
                if c.objExists(name): raise FitSkeletonValidationError("Lip Falloff 临时镜像名已占用："+name)
                c.duplicate(arc+"Lip"+part+"Curve",name=name,returnRootsOnly=True)
                c.setAttr(name+".scaleX",-1); mirrors.append(name)
            try:
                vertices=[]
                for arc in ("upper","lower"):
                    base=arc+"Lip"+part+"Curve"
                    vertices.extend(self.sample_face_fit_vertices(base,geometry))
                    left=base+"Left" if c.objExists(base+"Left") else base+"_L"
                    vertices.extend(self.sample_face_fit_vertices(left,geometry))
                raw.select(tuple(self.scene_address(v) for v in vertices),replace=True)
                for _ in range(growth):
                    raw.polySelectConstraint(propagate=1,type=1)
                    raw.select(self.scene_address("lipArea"),deselect=True)
                raw.select(self.scene_address("lipArea"),deselect=True)
                selected=tuple(c.ls(selection=True,flatten=True,long=True) or [])
                if selected:
                    scene_vertices=tuple(self.scene_address(v) for v in selected)
                    raw.sets(scene_vertices,add=self.scene_address("lipFalloffArea"))
                    raw.sets(scene_vertices,add=self.scene_address("lipFalloffAreaMax"))
                parts[part]=selected
            finally: c.delete(mirrors)
        c.select("lipFalloffArea",replace=True)
        if options.preview:
            c.currentTime(30)
            return {"preview":True,"vertices":sum(len(v) for v in parts.values()),"layer_skin":None}
        maximum=tuple(c.sets("lipFalloffAreaMax",query=True) or [])
        if maximum:
            raw.skinPercent(self.scene_address(skin),tuple(self.scene_address(v) for v in maximum),
                            transformValue=[(self.scene_address(head),1)])
        selected=tuple(c.sets("lipFalloffArea",query=True) or [])
        self._lip_falloff_hammer(skin,selected,options.iterations)
        if not c.objExists("lipOffJoint"):
            c.select(head,replace=True); c.joint(name="lipOffJoint")
            c.parent("lipOffJoint","FaceBuildInProgressHidden",absolute=True)
        if c.objExists("LipFalloffLayer"): c.delete("LipFalloffLayer")
        if c.objExists("LipFalloffLayerSC"): c.delete("LipFalloffLayerSC")
        c.duplicate("templateLayer",name="LipFalloffLayer",returnRootsOnly=True)
        influences=raw.listConnections(self.scene_address(skin),source=True,destination=False,type="joint") or []
        head_ids=set(raw.ls(self.scene_address(head),uuid=True) or [])
        joints=tuple(dict.fromkeys(j for j in influences if not head_ids.intersection(raw.ls(j,uuid=True) or [])))
        with c._creation_namespace() if hasattr(c,"_creation_namespace") else _unchanged():
            layer_skin=raw.skinCluster((*joints,self.scene_address("lipOffJoint"),self.scene_address("LipFalloffLayer")),
                toSelectedBones=True,maximumInfluences=3,dropoffRate=4,removeUnusedInfluence=False,
                name=self.scene_address("LipFalloffLayerSC"))[0]
        raw.select((self.scene_address(geometry),self.scene_address("LipFalloffLayer")),replace=True)
        raw.copySkinWeights(noMirror=True,surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
        raw.skinPercent(layer_skin,pruneWeights=.01)
        for index in range(2,count//4):
            control="upperLip"+lip_control_letter(index)+"_R"
            c.setKeyframe(control+".ty",time=0,value=0)
            c.setKeyframe(control+".ty",time=30,value=1)
        c.currentTime(30); c.select(clear=True)
        return {"preview":False,"vertices":len(selected),"layer_skin":layer_skin}

from contextlib import contextmanager
@contextmanager
def _unchanged(): yield
