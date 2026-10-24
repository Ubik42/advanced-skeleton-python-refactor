"""Original Lip Outer/Main/Inner Fit curves, tubes and Inner area mesh."""
from __future__ import annotations
import json
import re
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_lip_fit import LipFitInput
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_base import MayaFaceBaseMixin
from .maya_face_pre import MayaFacePreHost
from .maya_face_fit_selection import MayaFaceFitSelectionMixin
from .maya_original_face_fit_tube import create_original_face_fit_tube

_COMPONENT=re.compile(r"^(?P<mesh>.+)\.(?P<kind>e|vtx)\[(?P<index>\d+)\]$")

class MayaFaceLipFitHost(MayaFaceFitSelectionMixin,MayaFaceBaseMixin,MayaFacePreHost):
    def _lip_mesh_fn(self,mesh):
        from maya.api import OpenMaya as om
        shapes=self._cmds.listRelatives(mesh,shapes=True,noIntermediate=True,fullPath=True,type="mesh") or []
        if len(shapes)!=1: raise FitSkeletonValidationError("Lip Face 网格需要唯一可见 Shape")
        selection=om.MSelectionList(); selection.add(self.scene_address(shapes[0]))
        return om.MFnMesh(selection.getDagPath(0))

    def capture_lip_fit_input(self,part):
        from maya.api import OpenMaya as om
        c=self._cmds; fit=self._fit(required=True)
        self.read_face_mask()
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("Lip Fit 需要唯一 Face 网格")
        selected=tuple(c.ls(selection=True,flatten=True,long=True) or [])
        matches=[_COMPONENT.fullmatch(item) for item in selected]
        if not matches or any(match is None for match in matches):
            raise FitSkeletonValidationError("请选择 Lip 完整边环，可加选三个指定顶点")
        mesh=geometry[0]
        if any(match.group("mesh")!=mesh for match in matches):
            raise FitSkeletonValidationError("Lip 组件必须来自已记录的 Face 网格")
        edge_ids=tuple(sorted({int(m.group("index")) for m in matches if m.group("kind")=="e"}))
        corners=tuple(int(m.group("index")) for m in matches if m.group("kind")=="vtx")
        mesh_fn=self._lip_mesh_fn(mesh)
        if not edge_ids or edge_ids[-1]>=mesh_fn.numEdges or any(v>=mesh_fn.numVertices for v in corners):
            raise FitSkeletonValidationError("Lip 边环索引无效")
        non_sym=bool(c.getAttr(fit+".NonSym")) if c.objExists(fit+".NonSym") else False
        if self.active_face_side().value=="Left":
            raise FitSkeletonValidationError("原版 Lip 从右侧入口一次生成两侧；请切回 Right")
        points=mesh_fn.getPoints(om.MSpace.kWorld)
        positions=tuple((float(p.x),float(p.y),float(p.z)) for p in points)
        mesh_edges=tuple(tuple(mesh_fn.getEdgeVertices(i)) for i in range(mesh_fn.numEdges))
        previous="upperLip"+("Outer" if part=="Main" else "Main")+"Curve"
        previous_start=None
        previous_left_start=None
        if part in ("Main","Inner") and c.objExists(previous):
            # asGetFaceFitSelection samples every authored CV in order;
            # asCreateFaceFit uses its first returned vertex for growth.
            sampled=self.sample_face_fit_vertices(previous,mesh)
            if sampled:
                previous_start=int(sampled[0].rsplit('[',1)[1][:-1])
        if part in ('Main','Inner') and non_sym and c.objExists(previous+'Left'):
            sampled=self.sample_face_fit_vertices(previous+'Left',mesh)
            if sampled:
                previous_left_start=int(sampled[0].rsplit('[',1)[1][:-1])
        if part=="Inner":
            for name in ("FaceFitLipOuter","FaceFitLipMain","upperLipMainCurve"):
                if len(c.ls(name,long=True) or [])!=1:
                    raise FitSkeletonValidationError("Lip Inner 缺少原版前置 Fit："+name)
        return LipFitInput(mesh,part,tuple((i,*mesh_edges[i]) for i in edge_ids),corners,
            positions,mesh_edges,tuple(tuple(mesh_fn.getPolygonVertices(i))
                for i in range(mesh_fn.numPolygons)),non_sym,previous_start,previous_left_start)

    def preflight_lip_fit(self,plan):
        c=self._cmds; part=plan.source.part
        names=[]
        for side in plan.sides:
            suffix=side.suffix
            names.extend("FaceFitLip"+part+stem+suffix for stem in ("","Geo","Curve","Loc"))
            for arc in ("upper","lower"):
                names.extend((arc+"Lip"+part+"Curve"+suffix,arc+"LipCylinder"+part+suffix))
            if part=="Inner": names.extend("LipInnerAreaMesh"+stem+suffix for stem in ("","Extrude","PolyExtrudeFacet"))
        collisions=[name for name in names if self.find_name_collisions(name)]
        if collisions: raise FitSkeletonValidationError("Lip Fit 名称已占用："+"、".join(collisions))
        if c.referenceQuery(self._fit(required=True),isNodeReferenced=True):
            raise FitSkeletonValidationError("不能编辑引用中的 FaceFitSkeleton")

    def create_lip_fit(self,plan):
        self._require_transaction()
        c=self._cmds; source=plan.source; part=source.part
        fit=self._fit(required=True); scale=float(c.getAttr(fit+".faceScale"))
        self._transaction_changed=True
        self.ensure_face_fit_shaders()
        for name in ("upperTempSoftModHandle","lowerTempSoftModHandle"):
            if c.objExists(name): c.delete(name)
        result={}
        for side in plan.sides:
            suffix=side.suffix; holder="FaceFitLip"+part+suffix
            c.createNode("transform",name=holder,parent=fit)
            for stem in ("Geo","Curve","Loc"):
                c.createNode("transform",name="FaceFitLip"+part+stem+suffix,parent=holder)
            curves=[]
            for arc,vertices in (("upper",side.upper),("lower",side.lower)):
                name=arc+"Lip"+part+"Curve"+suffix
                curve=c.curve(name=name,degree=1,point=tuple(source.positions[v] for v in vertices))
                c.parent(curve,"FaceFitLip"+part+"Curve"+suffix,absolute=True)
                c.makeIdentity(holder,apply=True,translate=True,rotate=True,scale=True)
                shape=c.listRelatives(name,shapes=True,fullPath=True)[0]
                c.rename(shape, name + "Shape")
                shape=c.listRelatives(name,shapes=True,fullPath=True)[0]
                c.setAttr(shape+".overrideEnabled",True)
                c.setAttr(shape+".overrideColor",{"Outer":14,"Main":13,"Inner":15}[part])
                create_original_face_fit_tube(self,'Lip',part,suffix,arc,scale,
                    'asGreenSG' if arc=='upper' else 'asGreen2SG')
                curves.append(name)
            c.addAttr(holder,longName="selection",dataType="string")
            record=[self.scene_address(source.mesh)+f".e[{index}]" for index,_,_ in source.edges]
            recorded_corners=source.corners if not suffix else (side.upper[-1],side.upper[0],side.lower[0])
            record.extend(self.scene_address(source.mesh)+f".vtx[{v}]" for v in recorded_corners)
            c.setAttr(holder+".selection"," ".join(record)+" ",type="string")
            c.addAttr(holder,longName="advPyFaceCount",attributeType="long")
            c.setAttr(holder+".advPyFaceCount",len(source.face_vertices))
            c.addAttr(holder,longName="advPyEdgeVertices",dataType="string")
            c.setAttr(holder+".advPyEdgeVertices",json.dumps(source.edges,separators=(",",":")),type="string")
            if part=="Inner":
                self.create_original_face_fit_inner_area('Lip', suffix, source.mesh,
                    "FaceFitLip"+part+"Geo"+suffix, scale, record)
            result[suffix or "Right"]=tuple(curves)
        c.select("FaceFitLip"+part,replace=True)
        return result

    def select_lip_fit(self,part):
        c=self._cmds; suffix="Left" if self.active_face_side().value=="Left" else ""
        holder="FaceFitLip"+part+suffix
        if not c.objExists(holder+".selection"): raise FitSkeletonValidationError("Lip Fit 选择记录缺失")
        selected=tuple(c.ls((c.getAttr(holder+".selection") or "").split(),long=True,flatten=True) or [])
        if not selected: raise FitSkeletonValidationError("Lip Fit 组件已经不存在")
        mesh=self.read_face_objects(FacePreRole.FACE)[0]
        if c.objExists(holder+".advPyFaceCount") and int(c.polyEvaluate(mesh,face=True))!=int(c.getAttr(holder+".advPyFaceCount")):
            raise FitSkeletonValidationError("Lip Fit 的 Face 拓扑已改变")
        c.select(selected,replace=True)
        return len(selected)

    def swap_lip_upper_lower(self,part):
        """asFaceFitSwapUpperLower Lip: original right-side curve/tube swap."""
        self.swap_original_face_fit_upper_lower('Lip',part)
        return part
