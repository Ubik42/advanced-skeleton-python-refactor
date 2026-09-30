"""ADV 6.925 asCreateFaceFit sphere and UpMidLo scene operations."""
from adv_py.core.face_fit_markers import MARKER_SHADERS, CENTER_MARKERS
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_base import MayaFaceBaseMixin
from .maya_face_pre import MayaFacePreHost
from .maya_face_body_jaw import MayaFaceBodyJawMixin
from .maya_face_forehead_fit import MayaFaceForeHeadFitMixin
from .maya_face_eye_loop_fit import MayaFaceEyeLoopFitMixin

class MayaFaceFitMarkersHost(MayaFaceEyeLoopFitMixin,MayaFaceForeHeadFitMixin,MayaFaceBodyJawMixin,MayaFaceBaseMixin,MayaFacePreHost):
    def _marker_context(self,section):
        c=self._cmds
        fit=self._fit(required=True)
        if not c.objExists(fit+".faceScale"):
            raise FitSkeletonValidationError("先在 Pre 记录 Mask")
        scale=float(c.getAttr(fit+".faceScale"))
        if scale<=0: raise FitSkeletonValidationError("Face Fit faceScale 必须为正")
        suffix="Left" if c.objExists(fit+".NonSymSide") and c.getAttr(fit+".NonSymSide")=="Left" else ""
        holder="FaceFit"+section+suffix
        names=[holder,*("FaceFit"+section+stem+suffix for stem in ("Geo","Curve","Loc"))]
        if section=="UpMidLo": names.extend(("upperFace","middleFace","lowerFace"))
        else: names.extend((section+suffix,section+"Sphere"+suffix))
        occupied=[name for name in names if self.find_name_collisions(name)]
        if occupied: raise FitSkeletonValidationError("Face Fit 名称已存在："+"、".join(occupied))
        return fit,scale,suffix,holder

    def _marker_containers(self,fit,section,suffix,holder):
        c=self._cmds
        self._transaction_changed=True
        self.ensure_face_fit_shaders()
        for name in ("upperTempSoftModHandle","lowerTempSoftModHandle"):
            if c.objExists(name): c.delete(name)
        c.createNode("transform",name=holder,parent=fit)
        for stem in ("Geo","Curve","Loc"):
            c.createNode("transform",name="FaceFit"+section+stem+suffix,parent=holder)

    def create_face_fit_marker(self,section):
        self._require_transaction()
        if section not in MARKER_SHADERS: raise ValueError("原版球形 Fit 类型无效")
        c=self._cmds
        if section=="Jaw" and c.objExists("FKJaw_M"):
            previous=tuple(c.ls(selection=True,long=True,flatten=True) or [])
            self.remove_original_body_jaw_for_face()
            c.select(previous,replace=True) if previous else c.select(clear=True)
        fit,scale,suffix,holder=self._marker_context(section)
        selected=tuple(c.ls(selection=True,long=True,flatten=True) or [])
        if not selected or any("." not in item for item in selected):
            raise FitSkeletonValidationError("请选择面部网格边或顶点")
        raw=getattr(c,"raw",c)
        vertices=[item for item in selected if ".vtx[" in item]
        edges=[item for item in selected if ".e[" in item]
        faces=[item for item in selected if ".f[" in item]
        if not (vertices or edges or faces): raise FitSkeletonValidationError("请选择多边形组件")
        position=None
        if vertices:
            # MEL keeps the last selected vertex, rather than averaging selection.
            position=list(c.xform(vertices[-1],query=True,worldSpace=True,translation=True))
        elif edges:
            converted=raw.polyListComponentConversion(self.scene_address(edges[-1]),toVertex=True)
            rows=raw.ls(converted,flatten=True,long=True) or []
            if not rows: raise FitSkeletonValidationError("所选边无法转换为顶点")
            position=list(raw.xform(rows[0],query=True,worldSpace=True,translation=True))
        if position is not None and section in CENTER_MARKERS: position[0]=0
        self._marker_containers(fit,section,suffix,holder)
        name=section+suffix
        c.spaceLocator(name=name)
        c.parent(name,"FaceFit"+section+"Loc"+suffix,relative=True)
        shape=c.listRelatives(name,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".localScale",*(scale*.035,)*3)
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        sphere=section+"Sphere"+suffix
        c.sphere(name=sphere,pivot=(0,0,0),axis=(0,1,0),startSweep=0,endSweep=360,
                 radius=scale*.02,degree=3,useTolerance=False,tolerance=.01,
                 sections=8,spans=4,constructionHistory=False)
        c.parent(sphere,"FaceFit"+section+"Geo"+suffix,relative=True)
        for channel in ("translate","rotate","scale"):
            c.connectAttr(name+"."+channel,sphere+"."+channel)
        sphere_shape=c.listRelatives(sphere,shapes=True,fullPath=True)[0]
        c.setAttr(sphere_shape+".overrideEnabled",True)
        c.setAttr(sphere_shape+".overrideDisplayType",2)
        c.addAttr(name,longName="falloffRadius",attributeType="double",minValue=0,defaultValue=1,keyable=True)
        c.addAttr(name,longName="falloffMode",attributeType="enum",enumName="volume:surface:",defaultValue=1,keyable=True)
        c.addAttr(holder,longName="selection",dataType="string")
        c.setAttr(holder+".selection"," ".join(self.scene_address(item) for item in selected)+" ",type="string")
        if position is not None:
            c.xform(name,worldSpace=True,translation=position)
            c.sets(sphere,edit=True,forceElement=MARKER_SHADERS[section])
            c.select(clear=True)
        return name

    def create_face_up_mid_lo_fit(self):
        self._require_transaction()
        c=self._cmds
        fit,scale,suffix,holder=self._marker_context("UpMidLo")
        if c.objExists(fit+".RigType") and c.getAttr(fit+".RigType")==1:
            raise FitSkeletonValidationError("原版 Game Engine RigType 不支持 UpMidLo")
        for name in ("JawPivot","NoseUnder","lowerEyeLidOuterCurve"):
            if len(c.ls(name,long=True) or [])!=1:
                raise FitSkeletonValidationError("UpMidLo 缺少定位节点："+name)
        jaw=c.xform("JawPivot",query=True,worldSpace=True,translation=True)
        bounds=c.exactWorldBoundingBox("lowerEyeLidOuterCurve")
        lower_y=c.getAttr("NoseUnder.ty")
        self._marker_containers(fit,"UpMidLo",suffix,holder)
        c.spaceLocator(name="upperFace")
        c.parent("upperFace","FaceFitUpMidLoLoc"+suffix,relative=True)
        shape=c.listRelatives("upperFace",shapes=True,fullPath=True)[0]
        c.setAttr(shape+".localScale",scale/2,0,0)
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        c.xform("upperFace",worldSpace=True,translation=(0,bounds[1],jaw[2]))
        for group in ("translate","rotate","scale"):
            for axis in "XYZ": c.setAttr("upperFace."+group+axis,lock=True,keyable=False)
        for axis in "yz": c.setAttr("upperFace.t"+axis,lock=False,keyable=True)
        c.duplicate("upperFace",name="middleFace")
        c.duplicate("upperFace",name="lowerFace")
        c.setAttr("lowerFace.ty",lower_y)
        c.setAttr("middleFace.ty",(c.getAttr("upperFace.ty")+lower_y)/2)
        c.select(clear=True)
        return ("upperFace","middleFace","lowerFace")
