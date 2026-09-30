"""ADV 6.925 asFaceWeightLips (41546–41676), native SoftMod sampling."""
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_lip import MayaFaceLipHost

class MayaFaceJawLipWeightsHost(MayaFaceLipHost):
    def capture_jaw_lip_weights_input(self):
        c=self._cmds; fit=self._fit(required=True)
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("Jaw Lip 权重需要唯一 Face 网格")
        for name in ("JawOpenLayer","JawOpenLayerSC","JawJoint_M","FaceJoint_M","lipArea",
                     "mouthOpenSoftModSet","mouthOpenSoftModHandle","JawCurveMid","FaceBuildingSets"):
            if not c.objExists(name): raise FitSkeletonValidationError("Jaw Lip 权重缺少原版节点："+name)
        return geometry[0],bool(c.objExists(fit+".NonSym") and c.getAttr(fit+".NonSym"))

    def _jaw_layer_cast(self,vertices,layer="JawOpenLayer"):
        return tuple(layer+"."+vertex.split(".",1)[1] for vertex in vertices if ".vtx[" in vertex)

    def update_jaw_lip_weights(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); geometry,non_symmetrical=source
        self._transaction_changed=True
        selection=tuple(raw.ls(selection=True,long=True) or [])
        time=c.currentTime(query=True)
        disabled=c.objExists("JawOpenLayerDeleteComponent")
        if disabled: c.setAttr("JawOpenLayerDeleteComponent.nodeState",1)
        try:
            c.currentTime(0)
            c.skinPercent("JawOpenLayerSC","JawOpenLayer.vtx[*]",transformValue=[("FaceJoint_M",1)])
            weighter=c.duplicate(geometry,name="lipWeighter",returnRootsOnly=True)[0]
            for shape in c.listRelatives(weighter,shapes=True,fullPath=True) or []:
                if c.getAttr(shape+".intermediateObject"): c.delete(shape)
            c.sets(weighter+".vtx[*]",remove="lipArea")
            c.sets(weighter,add="mouthOpenSoftModSet")
            c.sets("JawCurveMid.cv[1:4]",add="mouthOpenSoftModSet")
            c.setAttr("mouthOpenSoftModHandle.ty",0)
            if not c.objExists("lipAreaJawOpenLayer"):
                c.sets(empty=True,name="lipAreaJawOpenLayer")
                c.sets("lipAreaJawOpenLayer",add="FaceBuildingSets")
            members=raw.sets(self.scene_address("lipArea"),query=True) or []
            flattened=raw.ls(members,long=True,flatten=True) or []
            area=self._jaw_layer_cast(flattened)
            for vertex in area:
                sample="lipWeighter."+vertex.split(".",1)[1]
                before=self._lip_pos(sample)
                c.setAttr("mouthOpenSoftModHandle.ty",1)
                after=self._lip_pos(sample)
                c.setAttr("mouthOpenSoftModHandle.ty",0)
                c.sets(vertex,add="lipAreaJawOpenLayer")
                c.skinPercent("JawOpenLayerSC",vertex,transformValue=[("JawJoint_M",after[1]-before[1])])
            c.delete(weighter)
            layers={}
            for part in ("Main","Outer","Inner"):
                sampled=[]
                for arc in ("upper","lower"):
                    for suffix in ("","Left"):
                        sampled.extend(self.sample_face_fit_vertices(arc+"Lip"+part+"Curve"+suffix,geometry))
                layers[part]=tuple(dict.fromkeys(self._jaw_layer_cast(sampled)))
            main_paths=set(raw.ls([self.scene_address(v) for v in layers['Main']],long=True,flatten=True) or [])
            for vertex in (*layers['Outer'],*layers['Inner']):
                current=[self.scene_address(vertex)]
                for _ in range(99):
                    edges=raw.polyListComponentConversion(current,toEdge=True)
                    current=raw.ls(raw.polyListComponentConversion(edges,toVertex=True),long=True,flatten=True) or []
                    hits=[item for item in current if item in main_paths]
                    if hits:
                        # MEL evaluates every hit in the first reached ring;
                        # the final matching vertex determines the final weight.
                        for hit in hits:
                            weight=raw.skinPercent(self.scene_address("JawOpenLayerSC"),hit,
                                                   query=True,transform=self.scene_address("JawJoint_M"))
                            c.skinPercent("JawOpenLayerSC",vertex,transformValue=[("JawJoint_M",weight)])
                        break
            borders=set((*layers['Main'],*layers['Outer'],*layers['Inner']))
            remaining=[vertex for vertex in area if vertex not in borders and self._lip_pos(vertex)[0]<-.001]
            self._lip_falloff_hammer("JawOpenLayerSC",remaining,5)
            if not non_symmetrical:
                raw.copySkinWeights(sourceSkin=self.scene_address("JawOpenLayerSC"),
                    destinationSkin=self.scene_address("JawOpenLayerSC"),mirrorMode="YZ",mirrorInverse=True,
                    surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            return len(area)
        finally:
            if c.objExists("lipWeighter"): c.delete("lipWeighter")
            c.setAttr("mouthOpenSoftModHandle.ty",0)
            if disabled: c.setAttr("JawOpenLayerDeleteComponent.nodeState",0)
            c.currentTime(time)
            raw.select(selection,replace=True) if selection else raw.select(clear=True)
