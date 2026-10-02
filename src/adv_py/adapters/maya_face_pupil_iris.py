"""Original pupil/iris control, topology weights and SDK (32560–32932)."""
from math import dist
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaFacePupilIrisMixin:
    def capture_original_face_pupil_input(self):
        c=self._cmds; fit=self._fit(required=True)
        for node in ("FitEyeBall","Eye_R","Eye_L","EyeJoint_R","EyeJoint_L","FaceControlSet"):
            if not c.objExists(node): raise FitSkeletonValidationError("Pupil／Iris 缺少原版 EyeBall 前置："+node)
        if c.objExists("Pupil_R") or c.objExists("Iris_R"): raise FitSkeletonValidationError("Pupil／Iris 已存在，请使用重建流程")
        def option(name): return bool(c.objExists(fit+"."+name) and c.getAttr(fit+"."+name))
        return {"head":c.getAttr(fit+".HeadJoint"),"scale":float(c.getAttr(fit+".faceScale")),
                "opm":self.face_use_offset_parent_matrix(),"multi":option("MultiSkinClusters"),"cyclops":option("Cyclops"),
                "eyes":{side:self.read_original_face_parts(name) for side,name in (("_R","RightEye"),("_L","LeftEye"))}}

    def _original_eye_fit_vertices(self,name,mesh):
        c=self._cmds; raw=getattr(c,"raw",c)
        if not c.objExists(name): return ()
        return tuple(raw.ls(tuple(self.scene_address(p) for p in self.sample_face_fit_vertices(name,mesh)),long=True,flatten=True) or [])

    def _original_eye_vertices(self,selection):
        raw=getattr(self._cmds,"raw",self._cmds)
        return tuple(raw.ls(raw.polyListComponentConversion(selection,toVertex=True),long=True,flatten=True) or [])

    def _original_pupil_skin(self,vertex,exclude_prefix=True):
        raw=getattr(self._cmds,"raw",self._cmds)
        nodes=[node for node in raw.listHistory(vertex) or [] if raw.nodeType(node)=="skinCluster"
               and node.rsplit(":",1)[-1]!="squashIKSC" and (not exclude_prefix or not node.rsplit(":",1)[-1].startswith("prefix_"))]
        if not nodes: raise FitSkeletonValidationError("Pupil／Iris 缺少眼球 Skin")
        return nodes[-1]

    def _original_eye_local_bounds(self,vertices):
        raw=getattr(self._cmds,"raw",self._cmds)
        return raw.xform(vertices,query=True,boundingBox=True)

    def create_original_face_pupil_iris(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        eye_scale=c.xform("FitEyeBall",query=True,worldSpace=True,scale=True)
        c.createNode("transform",name="TempPos")
        controls=[]; skins=[]
        # Source arrays are procedure-scoped. Keep the same state across sides.
        back_half=[]; adjacent=False; previous=[]; loops_between=0
        for side,suffix in (("_R",""),("_L","Left")):
            geos=list(source["eyes"][side]); eye_control="ctrlEye"+side
            if not geos: continue
            face_selection=".f[" in geos[0]
            if face_selection:
                object_name=geos[0].split(".",1)[0]
                # Original uses the first selected shape's parent transform.
                duplicate=c.duplicate(object_name,name="TempDuplicatedEye",returnRootsOnly=True)[0]
                chosen=raw.ls(geos,flatten=True) or []
                ids={int(p.rsplit("[",1)[1][:-1]) for p in chosen}
                outside=[duplicate+f".f[{i}]" for i in range(int(c.polyEvaluate(duplicate,face=True))) if i not in ids]
                if outside: c.polyDelFacet(outside,constructionHistory=False)
                geos=[object_name]
            elif len(geos)>1:
                # asGetFaceFitSelectionOtherObject samples CV[0], not pivot.
                point=c.xform("PupilCurve"+suffix+".cv[0]",query=True,worldSpace=True,translation=True)
                sampler=c.createNode("closestPointOnMesh",name="closestSampler")
                closest=None; minimum=999
                for geo in geos:
                    raw.connectAttr(geo+".outMesh",self.scene_address(sampler)+".inMesh",force=True)
                    c.setAttr(sampler+".inPosition",*point,type="float3")
                    vertex=geo+f".vtx[{int(c.getAttr(sampler+'.result.closestVertexIndex'))}]"
                    distance=dist(point,raw.xform(vertex,query=True,worldSpace=True,translation=True))
                    if distance<minimum: minimum=distance; closest=geo
                c.delete(sampler)
                if closest and closest!=geos[0]: geos.remove(closest); geos.insert(0,closest)
            pupil=self._original_eye_fit_vertices("PupilCurve"+suffix,geos[0])
            iris=self._original_eye_fit_vertices("IrisCurve"+suffix,geos[0])
            if not pupil or not iris:
                raw.warning("Pupil／Iris"+side+" EdgeLoop not defined")
                if c.objExists("TempDuplicatedEye"): c.delete("TempDuplicatedEye")
                continue
            pupil_bounds=self._original_eye_local_bounds(pupil); iris_bounds=self._original_eye_local_bounds(iris)
            pupil_center=tuple((pupil_bounds[i]+pupil_bounds[i+3])/2 for i in range(3))
            iris_center=tuple((iris_bounds[i]+iris_bounds[i+3])/2 for i in range(3))
            pupil_radius=(pupil_bounds[4]-pupil_bounds[1])/2; iris_radius=(iris_bounds[4]-iris_bounds[1])/2
            bounds=raw.exactWorldBoundingBox(self.scene_address("TempDuplicatedEye") if face_selection else geos[0])
            eye_radius=(bounds[4]-bounds[1])/2
            candidates=self._original_eye_vertices(source["eyes"][side] if face_selection else geos[0])
            temp=c.createNode("transform",name="tempTransform",parent="EyeJoint"+side)
            for vertex in candidates:
                c.xform(temp,worldSpace=True,translation=raw.xform(vertex,query=True,worldSpace=True,translation=True))
                if c.getAttr(temp+".tz")<0: back_half.append(vertex)
            c.delete(temp)
            skin=self._original_pupil_skin(pupil[0]); skins.append(skin)
            for stem,kind,center,vertices,radius in (("Pupil",2,pupil_center,pupil,pupil_radius),("Iris",1,iris_center,iris,iris_radius)):
                control=self.create_original_face_controller(stem,side,kind); controls.append(control)
                shape=c.listRelatives(control,shapes=True,fullPath=True)[0]
                c.connectAttr("ctrlBox.EyeCtrlVis",shape+".overrideVisibility",force=True)
                c.select("EyeJoint"+side,replace=True); joint=c.joint(name=stem+"Joint"+side)
                c.setAttr(joint+".segmentScaleCompensate",False)
                c.scale(*(radius*4,)*3,control+".cv[0:7]",pivot=(0,0,0))
                c.move(0,0,source["scale"]/100,control+".cv[0:7]",relative=True,objectSpace=True,worldSpaceDistance=True)
                c.xform((stem+"Offset"+side,joint),worldSpace=True,translation=center)
                c.parent(stem+"Offset"+side,"Eye"+side); c.setAttr(stem+"Offset"+side+".r",0,0,0)
                if stem=="Pupil":
                    for attr in ("iris","pupil"): c.addAttr(eye_control,longName=attr,attributeType="double",softMinValue=-10,hasSoftMinValue=True,softMaxValue=10,hasSoftMaxValue=True,defaultValue=0,keyable=True)
                raw.skinCluster(skin,edit=True,addInfluence=self.scene_address(joint),lockWeights=False,weight=0)
                raw.select(source["eyes"][side],replace=True)
                raw.skinPercent(skin,transformValue=((self.scene_address("EyeJoint"+side),1),))
                raw.skinPercent(skin,vertices,transformValue=((self.scene_address(joint),1),))
            c.parent("PupilOffset"+side,"Iris"+side); c.parent("PupilJoint"+side,"IrisJoint"+side)
            for stem in ("Pupil","Iris"):
                joint=stem+"Joint"+side; self.constrain_original_face(stem+side,joint,force_matrix=False)
                if source["multi"]:
                    matrix=stem+"JointMM"+side
                    c.connectAttr(source["head"]+".worldInverseMatrix",matrix+".matrixIn[1]",force=True)
                    c.setAttr(matrix+".matrixIn[2]",*self.original_face_matrix_values(source["head"]+".worldMatrix[0]"),type="matrix")
                    parent=c.listRelatives(joint,parent=True)[0]
                    c.connectAttr(parent+".worldInverseMatrix",matrix+".matrixIn[3]")
            raw.select(pupil[0],replace=True)
            edges=raw.polyListComponentConversion(pupil[0],toEdge=True)
            neighbors=list(self._original_eye_vertices(edges)); neighbors=[v for v in neighbors if v not in pupil]
            if not neighbors: raise FitSkeletonValidationError("Pupil 边界没有相邻顶点")
            def grow(seed):
                nonlocal adjacent,previous
                raw.select(seed,replace=True)
                for _ in range(99):
                    if seed in iris:
                        adjacent=True; raw.select(iris,replace=True); break
                    raw.polySelectConstraint(propagate=1,type=1); raw.select((*pupil,*iris),deselect=True)
                    selected=raw.ls(selection=True,flatten=True,long=True) or []
                    if len(selected)==len(previous): break
                    previous=selected
                return tuple(raw.ls(selection=True,flatten=True,long=True) or [])
            a=grow(neighbors[0])
            if len(neighbors)<2: outer=a; inner=pupil
            else:
                b=grow(neighbors[1]); ba=self._original_eye_local_bounds(a); bb=self._original_eye_local_bounds(b)
                if sum(ba[i+3]-ba[i] for i in range(3))<sum(bb[i+3]-bb[i] for i in range(3)): inner,outer=a,b
                else: inner,outer=b,a
            raw.select(pupil[0],replace=True)
            for i in range(10):
                raw.polySelectConstraint(propagate=1,type=1)
                if set(raw.ls(selection=True,long=True,flatten=True) or []) & set(iris): loops_between=i; break
            for joint,vertices in (("PupilJoint",pupil),("PupilJoint",inner),("IrisJoint",iris),("IrisJoint",outer)):
                if vertices: raw.skinPercent(skin,vertices,transformValue=((self.scene_address(joint+side),1),))
            if not adjacent and outer: self.smooth_original_face_flood(skin,outer,"PupilJoint"+side,"IrisJoint"+side,loops_between)
            raw.skinCluster(skin,edit=True,selectInfluenceVerts=self.scene_address("PupilJoint"+side))
            pupil_weighted=raw.ls(selection=True,long=True,flatten=True) or []
            raw.skinCluster(skin,edit=True,selectInfluenceVerts=self.scene_address("IrisJoint"+side))
            iris_weighted=raw.ls(selection=True,long=True,flatten=True) or []
            c.parent("TempPos","FitEyeBall"+suffix); raw.select(outer,replace=True); loops_half=0
            for i in range(20):
                loops_half=i; raw.polySelectConstraint(propagate=1,type=1)
                stop=False
                for vertex in raw.ls(selection=True,long=True,flatten=True) or []:
                    c.xform("TempPos",worldSpace=True,translation=raw.xform(vertex,query=True,worldSpace=True,translation=True))
                    if c.getAttr("TempPos.tz")<0: stop=True
                if stop: break
            raw.select(iris,replace=True)
            for _ in range(1,loops_half):
                raw.polySelectConstraint(propagate=1,type=1)
                raw.select((*pupil_weighted,*iris_weighted),deselect=True)
            transition=raw.ls(selection=True,long=True,flatten=True) or []
            if transition: self.smooth_original_face_flood(skin,transition,"IrisJoint"+side,"EyeJoint"+side,loops_half)
            iris_position=self._lip_pos("Iris_R")
            distance=dist(self._lip_pos("FitEyeBall"),iris_position)
            temp=c.createNode("transform",name="tempXform",parent="FitEyeBall")
            c.setAttr(temp+".tz",.5); distance2=dist(self._lip_pos(temp),iris_position); c.delete(temp)
            for axis,upper in zip("xyz","XYZ"):
                self.original_face_output_bw(eye_control+".pupil")
                for dv,value in ((0,1),(10,2)): self.add_original_face_sdk(eye_control+".pupil","SDKPupil"+side+".s"+axis,dv,value)
                self.original_face_output_bw(eye_control+".iris")
                for dv,value in ((0,1),(10,eye_scale[0]/(iris_radius*2)),(-10,0)): self.add_original_face_sdk(eye_control+".iris","SDKIris"+side+".s"+axis,dv,value)
                c.keyTangent("SDKIris"+side+"_scale"+upper,index=(1,1),inTangentType="spline",outTangentType="spline")
                c.keyTangent("SDKIris"+side+"_scale"+upper,index=(2,2),inTangentType="flat",outTangentType="flat")
            for dv,value in ((0,0),(10,-distance),(-10,distance2)): self.add_original_face_sdk(eye_control+".iris","SDKIris"+side+".tz",dv,value)
            c.keyTangent("SDKIris"+side+"_translateZ",index=(0,0),outTangentType="flat")
            c.keyTangent("SDKIris"+side+"_translateZ",index=(1,1),inTangentType="spline",outTangentType="spline")
            for geo in geos[1:]:
                if face_selection: break
                other=self._original_pupil_skin(geo,exclude_prefix=False); skins.append(other)
                joints=tuple(self.scene_address(stem+"Joint"+side) for stem in ("Pupil","Iris"))
                raw.skinCluster(other,edit=True,addInfluence=joints,lockWeights=False,weight=0)
                if source["cyclops"] and side=="_R": raw.skinCluster(other,edit=True,removeInfluence=joints)
                raw.select((geos[0],geo),replace=True)
                raw.copySkinWeights(noMirror=True,surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            self.extend_face_build_pose((eye_control,))
            if c.objExists("TempDuplicatedEye"): c.delete("TempDuplicatedEye")
        c.delete("TempPos"); c.select(clear=True)
        return {"controls":tuple(controls),"production_skins":tuple(dict.fromkeys(skins))}
