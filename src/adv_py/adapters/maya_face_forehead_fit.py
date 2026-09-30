"""Original ForeHead Fit border, CV landmarks, tube and area preview."""
from math import floor
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_topology import original_face_least_edges

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
            start=floor(parameter(inner_point)+.5)
            old=c.rename(curve,"faceLoopCurve1OLD")
            count=int(c.getAttr(old+".spans"))+1
            points=[c.xform(old+f".cv[{(start+i)%count}]",query=True,worldSpace=True,translation=True) for i in range(count+1)]
            curve=c.curve(name="faceLoopCurve1",degree=1,point=points)
            c.connectAttr(curve+".worldSpace[0]",nearest_curve+".inputCurve",force=True); c.delete(old)
            half=int(c.getAttr(curve+".spans"))//2
            a=c.exactWorldBoundingBox(curve+f".cv[0:{half}]")
            b=c.exactWorldBoundingBox(curve+f".cv[{half+1}:{count}]")
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
        shape=c.listRelatives(curve,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
        profile=c.circle(name="ForeHeadProfile"+suffix,normal=(0,1,0),radius=scale/400,degree=3,sections=8,constructionHistory=False)[0]
        tube=c.extrude(profile,curve,name="ForeHeadCylinder"+suffix,constructionHistory=False,extrudeType=2,
            useComponentPivot=True,fixedPath=True,useProfileNormal=True,rotation=0,scale=1)[0]
        c.delete(profile); c.parent(tube,"FaceFitForeHeadGeo"+suffix)
        c.setAttr(tube+".overrideEnabled",True); c.setAttr(tube+".overrideDisplayType",2)
        c.setAttr(c.listRelatives(tube,shapes=True,fullPath=True)[0]+".curvePrecisionShaded",4)
        a=c.xform(tube+".cv[6][0]",query=True,worldSpace=True,translation=True)
        b=c.xform(tube+".cv[6][1]",query=True,worldSpace=True,translation=True)
        if a[1]>b[1]: c.reverseSurface(tube,direction=0,constructionHistory=False,replaceOriginal=True)
        c.sets(tube,edit=True,forceElement="asGreenSG")
        self._original_forehead_area(geometry,edges,suffix,scale)
        c.select(holder,replace=True)
        return curve

    def _original_forehead_area(self,geometry,edges,suffix,scale):
        c=self._cmds; raw=getattr(c,"raw",c); mesh=self.scene_address(geometry)
        lid_holder="FaceFitEyeLidOuter"+suffix
        record=(c.getAttr(lid_holder+".selection") or "").split()
        boundary=raw.ls(raw.polyListComponentConversion((*record,*edges),toVertex=True),long=True,flatten=True) or []
        sampler=c.createNode("closestPointOnMesh",name="closestSampler")
        raw.connectAttr(mesh+".outMesh",self.scene_address(sampler)+".inMesh")
        c.setAttr(sampler+".inPosition",*c.xform("EyeBrowInner"+suffix,query=True,worldSpace=True,translation=True),type="float3")
        raw.select(mesh+f".vtx[{int(c.getAttr(sampler+'.result.closestVertexIndex'))}]",replace=True)
        previous=0
        for _ in range(199):
            raw.polySelectConstraint(propagate=1,type=1)
            if boundary: raw.select(boundary,deselect=True)
            vertices=raw.ls(selection=True,long=True,flatten=True) or []
            if len(vertices)==previous: break
            previous=len(vertices)
        c.delete(sampler)
        faces=raw.ls(raw.polyListComponentConversion(vertices,toFace=True),long=True,flatten=True) or []
        ids={int(p.rsplit("[",1)[1][:-1]) for p in faces}
        name="ForeHeadAreaMesh"+suffix
        c.polyCube(name=name,width=1,height=1,depth=1,subdivisionsX=1,subdivisionsY=1,subdivisionsZ=1,constructionHistory=False)
        shape=c.listRelatives(name,shapes=True,fullPath=True)[0]
        raw.connectAttr(mesh+".outMesh",self.scene_address(shape)+".inMesh")
        # Request evaluated mesh data before disconnecting, as original refresh does.
        c.polyEvaluate(name,face=True)
        raw.disconnectAttr(mesh+".outMesh",self.scene_address(shape)+".inMesh")
        c.parent(name,"FaceFitForeHeadGeo"+suffix); c.sets(name,edit=True,forceElement="asGreenSG")
        outside=[name+f".f[{i}]" for i in range(int(raw.polyEvaluate(mesh,face=True))) if i not in ids]
        if outside: c.polyDelFacet(outside,constructionHistory=False)
        preview=c.duplicate(name,name="ForeHeadAreaMeshExtrude"+suffix,returnRootsOnly=True)[0]
        c.setAttr(name+".visibility",False)
        extrusion=c.polyExtrudeFacet(preview,constructionHistory=True,localTranslateZ=scale/500,keepFacesTogether=True,
            divisions=1,twist=0,taper=1,offset=0,thickness=0,smoothingAngle=30)
        c.rename(extrusion[0],"ForeHeadAreaMeshPolyExtrudeFacet"+suffix)
        for shape in c.listRelatives(preview,shapes=True,fullPath=True) or []:
            if c.getAttr(shape+".intermediateObject"): c.rename(shape,"ForeHeadAreaMeshExtrude"+suffix+"OrigShape")
