"""ADV 6.925 Tongue Fit and asFaceTongue graph/weight scene port."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import replace
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_tongue import FaceTongueInput, TONGUE_FIT_NAMES, GNM_TONGUE_JAW_FACES
from adv_py.core.body_parent_constraint import plan_body_parent_constraint
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_eyelid_rig import MayaFaceEyeLidRigHost

class MayaFaceTongueHost(MayaFaceEyeLidRigHost):
    @property
    def _tongue_maya(self): return getattr(self._cmds,"raw",self._cmds)

    def _tongue_one(self,name,kind=None):
        paths=self._cmds.ls(name,long=True,**({"type":kind} if kind else {})) or []
        if len(paths)!=1: raise FitSkeletonValidationError("Tongue 节点缺失或不唯一："+name)
        return paths[0]

    def read_tongue_geometry(self):
        c=self._cmds
        fit=self._fit(required=True)
        text=c.getAttr(fit+".Tongue") if c.objExists(fit+".Tongue") else ""
        if not text: return ()
        # Original stores a space-separated list of objects or components.
        paths=tuple(c.ls(text.split(),long=True,flatten=True) or [])
        if not paths: raise FitSkeletonValidationError("记录的 Tongue 对象或组件已不存在")
        return paths

    def record_tongue_geometry(self):
        self._require_transaction()
        c=self._cmds
        fit=self._fit(required=True)
        nodes=tuple(c.ls(selection=True,long=True,flatten=True) or [])
        if not nodes: raise FitSkeletonValidationError("请先选择舌头网格或舌头组件")
        meshes={node.split(".",1)[0] for node in nodes}
        for mesh in meshes:
            if not c.listRelatives(mesh,shapes=True,noIntermediate=True,type="mesh"):
                raise FitSkeletonValidationError("Tongue 只接受多边形网格及其组件")
        self._transaction_changed=True
        if not c.objExists(fit+".Tongue"): c.addAttr(fit,longName="Tongue",dataType="string")
        c.setAttr(fit+".Tongue"," ".join(self.scene_address(node) for node in nodes),type="string")
        return nodes

    def create_tongue_fit(self):
        self._require_transaction()
        c=self._cmds
        fit=self._fit(required=True)
        scale=float(c.getAttr(fit+".faceScale"))
        if scale<=0: raise FitSkeletonValidationError("Tongue Fit faceScale 必须为正")
        if any(c.objExists(name) for name in TONGUE_FIT_NAMES):
            raise FitSkeletonValidationError("Tongue Fit 节点已经存在")
        geometry=self.read_tongue_geometry()
        origin=c.xform(fit,query=True,worldSpace=True,translation=True)
        points=((0,origin[1]+scale/10,0),(0,origin[1]+scale/5,scale/5),
                (0,origin[1]+scale/5,scale/3),(0,origin[1]+scale/5.5,scale/2.5),
                (0,origin[1]+scale/7,scale/2.2))
        self._transaction_changed=True
        c.createNode("transform",name="FaceFitTongue",parent=fit)
        for stem in ("Geo","Curve","Loc"):
            c.createNode("transform",name="FaceFitTongue"+stem,parent="FaceFitTongue")
        curve=c.curve(name="TongueCurve",degree=1,point=points)
        c.parent(curve,"FaceFitTongueCurve",absolute=True)
        c.setAttr("TongueCurve.inheritsTransform",False)
        shape=(c.listRelatives("TongueCurve",shapes=True,fullPath=True) or [None])[0]
        c.setAttr(shape+".overrideEnabled",True)
        c.setAttr(shape+".overrideColor",13)
        for index,position in enumerate(points):
            name=f"Tongue{index}"
            loc=c.spaceLocator(name=name)[0]
            c.parent(loc,"FaceFitTongueLoc",absolute=True)
            c.xform(name,worldSpace=True,translation=position)
            loc_shape=(c.listRelatives(name,shapes=True,fullPath=True) or [None])[0]
            c.setAttr(loc_shape+".localScale",*(scale*.035,)*3)
            c.setAttr(loc_shape+".overrideEnabled",True)
            c.setAttr(loc_shape+".overrideColor",17)
            c.connectAttr(loc_shape+".worldPosition[0]",shape+f".controlPoints[{index}]",force=True)
        if geometry:
            bounds=c.exactWorldBoundingBox(*geometry)
            for index in range(5):
                # Preserve the original sum-based placement formula verbatim.
                c.xform(f"Tongue{index}",worldSpace=True,translation=(0,
                    (bounds[1]+bounds[4])/2,bounds[2]+((bounds[2]+bounds[5])/6)*index))
        profile=c.circle(name="TongueProfile",normal=(0,1,0),radius=scale/400,
                         degree=3,sections=8,constructionHistory=False)[0]
        cylinder=c.extrude(profile,"TongueCurve",name="TongueCylinder",constructionHistory=False,
            extrudeType=2,useComponentPivot=True,fixedPath=True,useProfileNormal=True,
            rotation=0,scale=1)[0]
        c.delete(profile)
        c.parent(cylinder,"FaceFitTongueGeo",absolute=True)
        c.setAttr("TongueCylinder.overrideEnabled",True)
        c.setAttr("TongueCylinder.overrideDisplayType",2)
        cylinder_shape=(c.listRelatives("TongueCylinder",shapes=True,fullPath=True) or [None])[0]
        c.setAttr(cylinder_shape+".curvePrecisionShaded",4)
        first=c.xform("TongueCylinder.cv[6][0]",query=True,worldSpace=True,translation=True)
        second=c.xform("TongueCylinder.cv[6][1]",query=True,worldSpace=True,translation=True)
        if first[1]>second[1]: c.reverseSurface("TongueCylinder",direction=0,constructionHistory=False,replaceOriginal=True)
        self.ensure_face_fit_shaders()
        c.sets("TongueCylinder",edit=True,forceElement="asRedSG")
        c.select(tuple(f"Tongue{i}" for i in range(5)),replace=True)
        return tuple(f"Tongue{i}" for i in range(5))

    def capture_tongue_input(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve") or not c.objExists("FaceFitTongue"):
            return None # Original skip below-eyes and absent Tongue Fit branches.
        geometry=self.read_tongue_geometry()
        if not geometry: return None
        for node in ("FaceMotionSystem","FaceJoint_M","SideReverse_M","JawFollow_M",
                     "lowerFaceStatic_M","FaceControlSet","FaceAllSet","faceBuildPose","ctrlBox"):
            self._tongue_one(node)
        for attr in ("RegionsCtrlVis","TongueCtrlVis"):
            if not c.objExists("ctrlBox."+attr):
                raise FitSkeletonValidationError("原版 ctrlBox 缺少 Tongue 可见性通道")
        positions=[]
        for index in range(99):
            if not c.objExists(f"Tongue{index}"): break
            positions.append(tuple(c.xform(self._tongue_one(f"Tongue{index}","transform"),
                                           query=True,worldSpace=True,translation=True)))
        face=self.read_face_objects(FacePreRole.FACE)[0]
        history=c.listHistory(geometry[0].split(".",1)[0],pruneDagObjects=True) or []
        skin=next((node for node in history if c.nodeType(node)=="skinCluster"
            and not node.rsplit(":",1)[-1].startswith("prefix_")
            and node.rsplit(":",1)[-1]!="squashIKSC"),None)
        return FaceTongueInput(geometry,face,self.read_face_objects(FacePreRole.ALL_HEAD),
            tuple(positions),self.face_use_offset_parent_matrix(),skin,
            self.face_skin_cluster(face),int(self._tongue_maya.getModifiers() or 0))

    @contextmanager
    def _tongue_deformer_sets(self):
        from .maya_face_deformer_sets import original_face_deformer_sets
        with original_face_deformer_sets(self._tongue_maya):
            yield

    def create_tongue_rig(self,source):
        self._require_transaction()
        with self._tongue_deformer_sets():
            return self._create_tongue_graph(source)

    def _create_tongue_graph(self,source):
        c=self._cmds
        raw=self._tongue_maya
        count=source.control_count
        self._transaction_changed=True
        self.hide_original_face_controllers(True)
        # Switch the same normal production geometry display as asShowLayer Normal.
        for child in c.listRelatives("DeformationLayers",children=True,
                                     fullPath=True,type="transform") or []:
            c.setAttr(child+".visibility",False)
        for mesh in source.all_head:
            plug=self.scene_address(mesh)+".visibility"
            if not raw.getAttr(plug,lock=True): raw.setAttr(plug,source.component_geometry)
        for node in source.geometry:
            raw.setAttr(self.scene_address(node.split(".",1)[0])+".visibility",True)
        for index,position in enumerate(source.fit_positions[:-1]):
            name=f"Tongue{index}"
            control=self.create_original_face_controller(name,"_M",4)
            c.setAttr(name+"Joint_M.segmentScaleCompensate",False)
            shape=(c.listRelatives(control,shapes=True,fullPath=True) or [None])[0]
            c.setAttr(shape+".overrideColor",6)
            c.connectAttr("ctrlBox.TongueCtrlVis",shape+".overrideVisibility",force=True)
            for node in (name+"Offset_M",name+"Joint_M"):
                c.xform(node,worldSpace=True,translation=position)
            c.scale(6.8,3.4,1,control+".cv[0:7]",relative=True,pivot=position)
            c.rotate(0,90,0,control+".cv[0:7]",relative=True,objectSpace=True)
            c.parent(name+"Offset_M","SideReverse_M",absolute=True)
            c.setAttr(name+"Offset_M.scale",1,1,1)
        for index in range(count):
            for target in (f"Tongue{index}Offset_M",f"Tongue{index}Joint_M"):
                c.delete(c.aimConstraint(f"Tongue{index+1}",target,aimVector=(1,0,0),
                    upVector=(0,1,0),worldUpType="vector",worldUpVector=(0,1,0)))
        for index in range(1,count):
            c.parent(f"Tongue{index}Offset_M",f"Tongue{index-1}_M",absolute=True)
            c.parent(f"Tongue{index}Joint_M",f"Tongue{index-1}Joint_M",absolute=True)
        c.parent("Tongue0Joint_M","FaceJoint_M",absolute=True)
        for index in range(count):
            control=f"Tongue{index}_M"; joint=f"Tongue{index}Joint_M"
            if source.use_offset_parent_matrix:
                control_path=self._tongue_one(control,"transform")
                joint_path=self._tongue_one(joint,"joint")
                plan=plan_body_parent_constraint(replace(self.capture_parent_constraint_input(
                    control_path,joint_path,True),use_offset_parent_matrix=True))
                self.preflight_parent_constraint(plan)
                self.create_parent_constraint(plan)
            else:
                c.parentConstraint(control,joint,maintainOffset=True)
                # MEL creates this inside an axis loop, generating two unused
                # siblings; keep its actual connected multiply node once.
                multiply=c.createNode("multiplyDivide",name=joint+"ScaleMPD")
                c.connectAttr(control+".scale",multiply+".input1")
                c.connectAttr("SDK"+control+".scale",multiply+".input2")
                c.connectAttr(multiply+".output",joint+".scale")
        self.add_original_face_follow("Tongue0_M","JawFollow_M","lowerFaceStatic_M",10)
        cube=c.polyCube(name="tempWeightCube",width=1,height=1,depth=1,
            subdivisionsX=1,subdivisionsY=1,subdivisionsZ=count,axis=(0,1,0),
            createUVs=4,constructionHistory=True)[0]
        bounds=c.exactWorldBoundingBox(*source.geometry)
        rings=[]; lattices=[]
        try:
            for index in range(count+1):
                c.select(cube,replace=True)
                raw.polySelectConstraint(m=3,t=1,d=3,db=(0,.1),
                    da=(0,0,1),dp=(0,0,-.5+index/count))
                selected=tuple(c.ls(selection=True,flatten=True,long=True) or [])
                if not selected: raise RuntimeError("Tongue 权重立方体分段顶点为空")
                rings.append(selected)
                lattice=c.lattice(selected,name=f"TongueLattice{index}",
                    divisions=(2,5,2),objectCentered=True,ldv=(2,2,2))
                lattices.append(lattice)
        finally: raw.polySelectConstraint(mode=0)
        for index,(deformer,lattice,base) in enumerate(lattices):
            c.xform(lattice,worldSpace=True,translation=source.fit_positions[index])
            c.xform(lattice,worldSpace=True,scale=(bounds[3]-bounds[0],bounds[4]-bounds[1],0))
        c.delete(cube,constructionHistory=True)
        box_skin=c.skinCluster((*source.joints,cube),toSelectedBones=True,
            maximumInfluences=1,dropoffRate=4,removeUnusedInfluence=False,name="tongueBoxSC")[0]
        for index in range(count):
            vertices=(*rings[index],*rings[index+1]) if index==count-1 else rings[index]
            c.skinPercent(box_skin,vertices,transformValue=[(source.joints[index],1)])
            if index:
                c.skinPercent(box_skin,rings[index],transformValue=[(source.joints[index-1],.5)])
        skin=self.scene_address(source.skin) if source.skin else None
        if skin is None:
            # Explicit geometry may be in the model namespace; new Skin stays
            # inside this character and may bind an object or component region.
            with c._creation_namespace() if hasattr(c,"_creation_namespace") else _unchanged():
                skin=raw.skinCluster((*tuple(self.scene_address(j) for j in source.joints),
                    *tuple(self.scene_address(g) for g in source.geometry)),toSelectedBones=True,
                    maximumInfluences=1,dropoffRate=4,removeUnusedInfluence=False,
                    name=self.scene_address("tongueSC"))[0]
        else:
            for joint in source.joints:
                raw.skinCluster(skin,edit=True,lockWeights=True,weight=0,
                                addInfluence=self.scene_address(joint))
        for joint in source.joints: c.setAttr(joint+".lockInfluenceWeights",False)
        target=raw.polyListComponentConversion(tuple(self.scene_address(g) for g in source.geometry),
                                               toVertex=True)
        vertices=tuple(raw.ls(target,flatten=True,long=True) or [])
        if not vertices: raise RuntimeError("Tongue 未找到目标顶点")
        raw.skinPercent(skin,vertices,transformValue=[(self.scene_address(source.joints[0]),1)])
        raw.select(self.scene_address(cube),replace=True)
        raw.select(vertices if source.component_geometry else tuple(self.scene_address(g)
            for g in source.geometry),add=True)
        raw.copySkinWeights(noMirror=True,surfaceAssociation="closestPoint",
                            influenceAssociation="closestJoint")
        if c.objExists("GNM_Head"):
            components=tuple(self.scene_address("GNM_Head")+f".f[{r}]" for r in GNM_TONGUE_JAW_FACES)
            jaw_vertices=raw.polyListComponentConversion(components,toVertex=True)
            raw.skinPercent(self.scene_address(source.face_skin),jaw_vertices,
                            transformValue=[(self.scene_address("JawJoint_M"),1)])
        if source.modifiers!=4: c.delete(cube)
        c.select(clear=True)
        return {"controls":source.controls,"joints":source.joints,"skin":skin,
                "vertices":len(vertices),"weight_cube_retained":source.modifiers==4}

    def finish_tongue(self):
        self._require_transaction()
        c=self._cmds; raw=self._tongue_maya
        if not c.objExists("FaceFitTongue"): return False
        if c.objExists("tempWeightCube"): c.delete("tempWeightCube")
        geometry=self.read_tongue_geometry()
        if not any("." in node for node in geometry):
            for node in self.read_face_objects(FacePreRole.ALL_HEAD):
                plug=self.scene_address(node)+".visibility"
                if not raw.getAttr(plug,lock=True): raw.setAttr(plug,True)
        self._transaction_changed=True
        return True

    def validate_tongue_rig(self,result):
        c=self._cmds; raw=self._tongue_maya
        influences=set(raw.skinCluster(result["skin"],query=True,influence=True) or [])
        leaves={node.rsplit("|",1)[-1].rsplit(":",1)[-1] for node in influences}
        if not set(result["joints"])<=leaves: raise RuntimeError("Tongue Skin 缺少控制链关节")
        for control,joint in zip(result["controls"],result["joints"]):
            self._tongue_one(control,"transform"); self._tongue_one(joint,"joint")
            if c.getAttr(joint+".segmentScaleCompensate"):
                raise RuntimeError("Tongue 关节缩放补偿与原版不符")
        if not c.isConnected("Tongue0BM_M.outputMatrix",
            "Tongue0Follow_M.offsetParentMatrix" if self.face_use_offset_parent_matrix()
            else "Tongue0FollowDM_M.inputMatrix"):
            raise RuntimeError("Tongue Jaw 跟随图未接通")

@contextmanager
def _unchanged(): yield
