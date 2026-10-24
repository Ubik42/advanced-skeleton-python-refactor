"""Original ForeHead Fit border, CV landmarks, tube and area preview."""
from math import floor
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_topology import original_face_least_edges
from .maya_original_face_fit_tube import create_original_face_fit_tube

class MayaFaceForeHeadFitMixin:
    def create_original_face_forehead_fit(self):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        fit,scale,suffix,holder=self._marker_context("ForeHead")
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("ForeHead 需要唯一 Face 网格")
        geometry=geometry[0]; mesh=self.scene_address(geometry)
        selected=tuple(raw.ls(selection=True,long=True,flatten=True) or [])
        vertices=[p for p in selected if ".vtx[" in p]; edges=[p for p in selected if ".e[" in p]
        if len(vertices)!=3 or len(vertices)+len(edges)!=len(selected):
            raise FitSkeletonValidationError("ForeHead 请选择三个顶点；手动边界需同时选择完整边界和边界上的三个顶点")
        actual=(raw.ls(mesh,long=True) or [mesh])[0]
        if any(p.split(".",1)[0]!=actual for p in selected): raise FitSkeletonValidationError("ForeHead 组件须来自已记录的 Face 网格")
        if edges:
            edge_vertices=raw.ls(raw.polyListComponentConversion(edges,toVertex=True),long=True,flatten=True) or []
            if any(p not in edge_vertices for p in vertices): raise FitSkeletonValidationError("ForeHead 的三个顶点必须位于所选边界上")
        lid="upperEyeLidOuterCurve"+suffix
        if not c.objExists(lid) or not c.objExists("EyeBrowInner"+suffix): raise FitSkeletonValidationError("ForeHead 需要同侧 EyeLid Outer 和 EyeBrowInner Fit")
        positions={p:raw.xform(p,query=True,worldSpace=True,translation=True) for p in vertices}
        side=(max if suffix else min)(vertices,key=lambda p:positions[p][0])
        top=max((p for p in vertices if p!=side),key=lambda p:positions[p][1])
        nose=next(p for p in vertices if p not in (side,top))
        self._marker_containers(fit,"ForeHead",suffix,holder)
        c.addAttr(holder,longName="selection",dataType="string")
        c.setAttr(holder+".selection"," ".join(selected)+" ",type="string")
        sampler=c.createNode("closestPointOnMesh",name="closestSampler")
        raw.connectAttr(mesh+".outMesh",self.scene_address(sampler)+".inMesh")
        def nearest(point):
            c.setAttr(sampler+".inPosition",*point,type="float3")
            return int(c.getAttr(sampler+".result.closestVertexIndex"))
        def index(component): return int(component.rsplit("[",1)[1][:-1])
        inner=nearest(c.xform(lid+".cv[0]",query=True,worldSpace=True,translation=True))
        spans=int(c.getAttr(lid+".spans"))
        outer=nearest(c.xform(lid+f".cv[{spans}]",query=True,worldSpace=True,translation=True))
        if not edges:
            paths=[list(original_face_least_edges(self,geometry,a,b)) for a,b in
                   ((inner,index(nose)),(index(nose),index(top)),(index(top),index(side)),(index(side),outer))]
            if not paths[0]: raise FitSkeletonValidationError("无法确定 ForeHead 区域，请手动选择完整边界及三个顶点")
            # Original removes detours shared by successive boundary paths.
            for a in range(3):
                for item in tuple(paths[a]):
                    for b in range(a+1,4):
                        if item in paths[b]:
                            paths[b].remove(item)
                            if item in paths[a]: paths[a].remove(item)
            edges=list(dict.fromkeys(p for path in paths for p in path))
        c.delete(sampler)
        # DuplicateCurve is the native command used by the MEL runtime wrapper;
        # attach and rebuild retain the original degree-1 parameter convention.
        raw.select(edges,replace=True)
        with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
            curves=[]
            history=raw.constructionHistory(query=True,toggle=True)
            local=bool(raw.optionVar(query="duplicateCurveLocal")) if raw.optionVar(exists="duplicateCurveLocal") else False
            partial=bool(raw.optionVar(query="duplicateCurveRangePartial")) if raw.optionVar(exists="duplicateCurveRangePartial") else False
            for edge in edges:
                curves.extend(raw.duplicateCurve(edge,constructionHistory=history,local=local,range=partial) or [])
        curves=[node for node in curves if raw.nodeType(node)=="transform"]
        if not curves: raise FitSkeletonValidationError("ForeHead 边界未生成曲线")
        if len(curves)>1:
            curve=c.attachCurve(*curves,name="faceLoopCurve1",constructionHistory=True,replaceOriginal=False,
                keepMultipleKnots=True,method=1,blendBias=.5,blendKnotInsertion=False,parameter=.1)[0]
            c.delete(curves)
        else: curve=c.rename(curves[0],"faceLoopCurve1")
        c.rebuildCurve(curve,constructionHistory=False,replaceOriginal=True,rebuildType=0,endKnots=1,
            keepRange=2,keepControlPoints=True,keepEndPoints=False,keepTangents=False,spans=0,degree=1,tolerance=.01)
        nearest_curve=c.createNode("nearestPointOnCurve",name="tempNearestPointOnCurve")
        c.connectAttr(curve+".worldSpace[0]",nearest_curve+".inputCurve",force=True)
        def parameter(point):
            c.setAttr(nearest_curve+".inPosition",*point,type="float3")
            return float(c.getAttr(nearest_curve+".result.parameter"))
        inner_point=c.xform(lid+".cv[0]",query=True,worldSpace=True,translation=True)
        if any(".e[" in p for p in selected):
            # Source uses the returned parameter in the component address,
            # then Maya pickWalk. Numeric modulo changes endpoint behavior.
            start=parameter(inner_point)
            raw.select(curve+f'.cv[{start}]',replace=True)
            old=c.rename(curve,"faceLoopCurve1OLD")
            points=[]
            for _ in range(int(c.getAttr(old+'.spans'))+2):
                points.append(raw.xform(query=True,worldSpace=True,translation=True))
                raw.pickWalk(direction='right')
            curve=c.curve(name="faceLoopCurve1",degree=1,point=points)
            c.connectAttr(curve+".worldSpace[0]",nearest_curve+".inputCurve",force=True); c.delete(old)
            half=int(c.getAttr(curve+".spans"))//2
            raw.select(curve+f'.cv[0:{half}]',replace=True)
            selected_half=raw.ls(selection=True,flatten=True) or []
            a=raw.xform(query=True,worldSpace=True,boundingBox=True)
            raw.select(curve+'.cv[*]',replace=True)
            if selected_half:
                raw.select(selected_half,deselect=True)
            b=raw.xform(query=True,worldSpace=True,boundingBox=True)
            reverse=a[0]>b[0] if suffix else a[0]<b[0]
        else: reverse=parameter(inner_point)>2
        if reverse:
            c.reverseCurve(curve,constructionHistory=False,replaceOriginal=True)
            c.addAttr(holder,longName="directionChecked",attributeType="bool",defaultValue=True)
        landmarks=(("noseCvNr",positions[nose]),("topCvNr",positions[top]),("sideCvNr",positions[side]),
                   ("innerEyeCnrNr",inner_point),("outerEyeCnrNr",c.xform(lid+".cv[99]",query=True,worldSpace=True,translation=True)))
        for name,point in landmarks: c.addAttr(holder,longName=name,attributeType="long",defaultValue=floor(parameter(point)+.5))
        c.delete(nearest_curve)
        curve=c.rename(curve,"ForeHeadCurve"+suffix)
        c.parent(curve,"FaceFitForeHeadCurve"+suffix)
        c.makeIdentity(holder,apply=True,translate=True,rotate=True,scale=True)
        shape=c.listRelatives(curve,shapes=True,fullPath=True)[0]
        c.rename(shape,"ForeHeadCurve"+suffix+"Shape")
        shape=c.listRelatives(curve,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        # ForeHead's green assignment is performed by its area branch.
        create_original_face_fit_tube(self,'ForeHead','',suffix,'',scale,'asGreenSG')
        self.create_original_face_fit_inner_area('ForeHead',suffix,geometry,
            'FaceFitForeHeadGeo'+suffix,scale,edges)
        c.select(holder,replace=True)
        return curve
