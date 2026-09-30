"""Original Lip Outer/Main/Inner Fit curves, tubes and Inner area mesh."""
from __future__ import annotations
import json
import re
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_lip_fit import LipFitInput, lip_inner_area
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_base import MayaFaceBaseMixin
from .maya_face_pre import MayaFacePreHost

_COMPONENT=re.compile(r"^(?P<mesh>.+)\.(?P<kind>e|vtx)\[(?P<index>\d+)\]$")

class MayaFaceLipFitHost(MayaFaceBaseMixin,MayaFacePreHost):
    def _lip_mesh_fn(self,mesh):
        from maya.api import OpenMaya as om
        shapes=self._cmds.listRelatives(mesh,shapes=True,noIntermediate=True,fullPath=True,type="mesh") or []
        if len(shapes)!=1: raise FitSkeletonValidationError("Lip Face 网格需要唯一可见 Shape")
        selection=om.MSelectionList(); selection.add(self.scene_address(shapes[0]))
        return om.MFnMesh(selection.getDagPath(0))

    def _lip_nearest_vertex(self,mesh_fn,point):
        from maya.api import OpenMaya as om
        closest,face=mesh_fn.getClosestPoint(om.MPoint(*point),om.MSpace.kWorld)
        vertices=mesh_fn.getPolygonVertices(face)
        if not vertices: raise FitSkeletonValidationError("Lip 无法采样最近面顶点")
        return min(vertices,key=lambda index:(mesh_fn.getPoint(index,om.MSpace.kWorld)-om.MPoint(*point)).length())

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
        if part in ("Main","Inner") and c.objExists(previous):
            point=c.xform(previous+".cv[0]",query=True,worldSpace=True,translation=True)
            previous_start=self._lip_nearest_vertex(mesh_fn,point)
        if part=="Inner":
            for name in ("FaceFitLipOuter","FaceFitLipMain","upperLipMainCurve"):
                if len(c.ls(name,long=True) or [])!=1:
                    raise FitSkeletonValidationError("Lip Inner 缺少原版前置 Fit："+name)
        return LipFitInput(mesh,part,tuple((i,*mesh_edges[i]) for i in edge_ids),corners,
            positions,mesh_edges,tuple(tuple(mesh_fn.getPolygonVertices(i))
                for i in range(mesh_fn.numPolygons)),non_sym,previous_start)

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

    def _lip_outer_border(self,source,suffix):
        c=self._cmds
        holder="FaceFitLipOuter"+suffix
        # The original selection stores the complete ring, even though curves
        # use only one side. Both sides therefore share the border ring.
        record=c.getAttr(holder+".selection") if c.objExists(holder+".selection") else ""
        ids=[]
        for item in (record or "").split():
            match=_COMPONENT.fullmatch(item)
            if match is None: raise FitSkeletonValidationError("Lip Outer 选择记录无效")
            actual=c.ls(match.group("mesh"),long=True) or []
            if actual!=[source.mesh]: raise FitSkeletonValidationError("Lip Outer 网格与当前 Face 不一致")
            index=int(match.group("index"))
            if match.group("kind")=="e":
                if index>=len(source.mesh_edges): raise FitSkeletonValidationError("Lip Outer 边拓扑已改变")
                ids.extend(source.mesh_edges[index])
            else: ids.append(index)
        if not ids: raise FitSkeletonValidationError("Lip Outer 缺少边界选择记录")
        if c.objExists(holder+".advPyEdgeVertices"):
            expected=tuple(tuple(row) for row in json.loads(c.getAttr(holder+".advPyEdgeVertices")))
            if any(index>=len(source.mesh_edges) or tuple(sorted(source.mesh_edges[index]))!=tuple(sorted((a,b)))
                for index,a,b in expected): raise FitSkeletonValidationError("Lip Outer 边连接已改变")
        return tuple(sorted(set(ids)))

    def _lip_area_faces(self,source,suffix):
        c=self._cmds; curve="upperLipMainCurve"+suffix
        if not c.objExists(curve): raise FitSkeletonValidationError("Lip Inner 缺少同侧 Main 曲线")
        spans=int(c.getAttr(curve+".spans"))
        point=c.xform(curve+f".cv[{spans//2}]",query=True,worldSpace=True,translation=True)
        seed=self._lip_nearest_vertex(self._lip_mesh_fn(source.mesh),point)
        faces=lip_inner_area(source,self._lip_outer_border(source,suffix),seed)
        if not faces: raise FitSkeletonValidationError("Lip Inner 未能确定原版面部区域")
        return faces

    def _create_lip_inner_area(self,source,suffix,faces,geo,scale):
        c=self._cmds
        name="LipInnerAreaMesh"+suffix
        area=c.duplicate(source.mesh,name=name,returnRootsOnly=True)[0]
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr(area+"."+attr,lock=False)
        c.delete(area,constructionHistory=True)
        for shape in c.listRelatives(area,shapes=True,fullPath=True) or []:
            if c.getAttr(shape+".intermediateObject"): c.delete(shape)
        area=c.parent(area,geo,absolute=True)[0]
        outside=sorted(set(range(len(source.face_vertices)))-set(faces))
        if outside: c.polyDelFacet(tuple(area+f".f[{i}]" for i in outside),constructionHistory=False)
        c.sets(area,edit=True,forceElement="asRedSG")
        c.addAttr(area,longName="selection",dataType="string")
        c.setAttr(area+".selection"," ".join(self.scene_address(source.mesh)+f".f[{i}]" for i in faces),type="string")
        preview=c.duplicate(area,name="LipInnerAreaMeshExtrude"+suffix,returnRootsOnly=True)[0]
        c.setAttr(area+".visibility",False)
        nodes=c.polyExtrudeFacet(preview+f".f[0:{len(faces)-1}]",constructionHistory=True,
            localTranslateZ=scale/500,keepFacesTogether=True,divisions=1,twist=0,
            taper=1,offset=0,thickness=0,smoothingAngle=30)
        c.rename(nodes[0],"LipInnerAreaMeshPolyExtrudeFacet"+suffix)
        for shape in c.listRelatives(preview,shapes=True,fullPath=True) or []:
            if c.getAttr(shape+".intermediateObject"):
                c.rename(shape,"LipInnerAreaMeshExtrude"+suffix+"OrigShape")
        return area,preview

    def create_lip_fit(self,plan):
        self._require_transaction()
        c=self._cmds; source=plan.source; part=source.part
        fit=self._fit(required=True); scale=float(c.getAttr(fit+".faceScale"))
        areas={side.suffix:self._lip_area_faces(source,side.suffix) for side in plan.sides} if part=="Inner" else {}
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
                shape=c.listRelatives(name,shapes=True,fullPath=True)[0]
                c.setAttr(shape+".overrideEnabled",True)
                c.setAttr(shape+".overrideColor",{"Outer":14,"Main":13,"Inner":15}[part])
                profile=c.circle(name="LipProfile"+part+suffix,normal=(0,1,0),radius=scale/400,
                    degree=3,sections=8,constructionHistory=False)[0]
                cylinder=arc+"LipCylinder"+part+suffix
                tube=c.extrude(profile,name,name=cylinder,constructionHistory=False,
                    extrudeType=2,useComponentPivot=True,fixedPath=True,useProfileNormal=True,
                    rotation=0,scale=1)[0]
                c.delete(profile); c.parent(tube,"FaceFitLip"+part+"Geo"+suffix,absolute=True)
                c.setAttr(cylinder+".overrideEnabled",True); c.setAttr(cylinder+".overrideDisplayType",2)
                tube_shape=c.listRelatives(cylinder,shapes=True,fullPath=True)[0]
                c.setAttr(tube_shape+".curvePrecisionShaded",4)
                a=c.xform(cylinder+".cv[6][0]",query=True,worldSpace=True,translation=True)
                b=c.xform(cylinder+".cv[6][1]",query=True,worldSpace=True,translation=True)
                if a[1]>b[1]: c.reverseSurface(cylinder,direction=0,constructionHistory=False,replaceOriginal=True)
                c.sets(cylinder,edit=True,forceElement="asGreenSG" if arc=="upper" else "asGreen2SG")
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
            if part=="Inner": self._create_lip_inner_area(source,suffix,areas[suffix],"FaceFitLip"+part+"Geo"+suffix,scale)
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
        self._require_transaction()
        c=self._cmds
        if part not in ("Outer","Main","Inner"): raise ValueError("Lip Fit 层级无效")
        for arc in ("upper","lower"):
            for name in (arc+"LipCylinder"+part,arc+"Lip"+part+"Curve"):
                if len(c.ls(name,long=True) or [])!=1: raise FitSkeletonValidationError("Lip Swap 缺少原版节点："+name)
        for name in ("upperLipCylinder"+part+"Swapping","upperLip"+part+"CurveSwapping"):
            if c.objExists(name): raise FitSkeletonValidationError("Lip Swap 临时节点已占用："+name)
        self._transaction_changed=True
        for upper,lower in (("upperLipCylinder"+part,"lowerLipCylinder"+part),
                            ("upperLip"+part+"Curve","lowerLip"+part+"Curve")):
            temporary=c.rename(upper,upper+"Swapping")
            c.rename(lower,upper); c.rename(temporary,lower)
        groups=[]
        for arc in ("upper","lower"):
            node=arc+"LipCylinder"+part
            shape=c.listRelatives(node,shapes=True,noIntermediate=True,fullPath=True)[0]
            groups.append((c.listConnections(shape+".instObjGroups[0]",source=False,destination=True,type="shadingEngine") or [None])[0])
        if None in groups: raise FitSkeletonValidationError("Lip Swap 预览管缺少材质组")
        c.sets("upperLipCylinder"+part,edit=True,forceElement=groups[1])
        c.sets("lowerLipCylinder"+part,edit=True,forceElement=groups[0])
        return part
