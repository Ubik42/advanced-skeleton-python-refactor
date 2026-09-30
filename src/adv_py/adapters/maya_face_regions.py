"""Original asFaceRegions projection and visibility stage."""
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_tongue import MayaFaceTongueHost

class MayaFaceRegionsHost(MayaFaceTongueHost):
    def capture_face_regions(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return None
        for name in ("ctrlBox","ctrlBox2","ctrlBox2Constrained","FaceAllSet"):
            if len(c.ls(name,long=True) or [])!=1: raise FitSkeletonValidationError("Regions 缺少原版节点："+name)
        result=[]
        for node in c.listRelatives("ctrlBox2",children=True,fullPath=True,type="transform") or []:
            icon=node.rsplit("|",1)[-1].rsplit(":",1)[-1]
            control=icon.replace("1","",1)
            exists=c.objExists(control)
            if exists:
                for name in (control+"TG",control+"TGXformOffset",control+"TGXform"):
                    if c.objExists(name): raise FitSkeletonValidationError("Regions 投影节点已占用："+name)
            result.append((icon,control,exists))
        return tuple(result)

    def create_face_regions(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self._transaction_changed=True
        self.finish_tongue()
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox2.visibility",True); c.setAttr("ctrlBox.RegionsCtrlVis",True)
        for name in ("EyeRegionOffset_R","EyeRegionOffset_L","EyeBrowRegionOffset_R",
                     "EyeBrowRegionOffset_L","EyeBrowRegionOffset_M","NoseRegionOffset_M","LipRegionOffset_M"):
            if c.objExists(name): c.setAttr(name+".visibility",True)
        built=[]
        for icon,control,exists in source:
            if not exists: c.setAttr(icon+".visibility",False); continue
            self.add_original_ctrl_box_second_shape(control,icon); built.append(control)
        # asShowLayer Normal: restore production meshes and hide generated layers.
        for role in (FacePreRole.ALL_HEAD,FacePreRole.FACE):
            for node in self.read_face_objects(role):
                plug=self.scene_address(node)+".visibility"
                if raw.getAttr(plug,settable=True): raw.setAttr(plug,True)
        if c.objExists("DeformationLayers"):
            for child in c.listRelatives("DeformationLayers",children=True,fullPath=True,type="transform") or []:
                c.setAttr(child+".visibility",lock=False); c.setAttr(child+".visibility",False)
            c.setAttr("DeformationLayers.visibility",lock=False)
            c.setAttr("DeformationLayers.visibility",False,lock=True)
        c.select(clear=True)
        return tuple(built)
