"""Shared asFaceEnsureAdvancedBase hierarchy and geometry layer port."""
from __future__ import annotations
from dataclasses import replace
from adv_py.core.body_parent_constraint import plan_body_parent_constraint
from adv_py.core.fit_settings import FitSkeletonValidationError

FACE_BASE_PARENTS = (
    ("FaceMotionSystem","FaceGroup"),
    ("ControlsSetup","FaceMotionSystem"),
    ("ConstrainedSetup","FaceMotionSystem"),
    ("DeformJointConstraints","ConstrainedSetup"),
    ("FaceDeformationSystem","FaceGroup"),
    ("FaceDeformationFollowHead","FaceDeformationSystem"),
    ("JawSetup","FaceDeformationFollowHead"),
    *((f"JawFollowSideReverse_{side}","JawSetup") for side in ("R","L","M")),
    *((f"JawFollow_{side}",f"JawFollowSideReverse_{side}") for side in ("R","L","M")),
    ("JawStatic_M","JawFollowSideReverse_M"),
    ("SideReverseSetup","ConstrainedSetup"),
    *((f"SideReverseSetup_{side}","SideReverseSetup") for side in ("M","R","L")),
    *((f"{stem}_{side}",f"SideReverseSetup_{side}")
      for side in ("M","R","L") for stem in ("FaceStatic","middleFaceStatic","lowerFaceStatic")),
    ("Aimcontrols","ControlsSetup"),
    ("OnFacecontrols","ControlsSetup"),
    *((f"SideReverse_{side}","OnFacecontrols") for side in ("R","L","M")),
    ("Regionscontrols","ControlsSetup"),
    ("Customcontrols","ControlsSetup"),
    ("FaceBuildInProgress",None),
    ("FaceBuildInProgressHidden","FaceBuildInProgress"),
    ("DeformationLayers","FaceDeformationSystem"))
FACE_BASE_NAMES = tuple(name for name,_ in FACE_BASE_PARENTS) + (
    "templateLayer","allHeadCombinedLayer","MainAndHeadScaleMultiplyDivide",
    "FaceMotionSystemMM","FaceDeformationFollowHeadMM")

class MayaFaceBaseMixin:
    def ensure_original_face_joint(self,head,scale):
        """Original Face Build anchor: Head position plus faceScale * .1 in Z."""
        self._require_transaction()
        c=self._cmds
        if c.objExists("FaceJoint_M"):
            return (c.ls("FaceJoint_M",long=True,type="joint") or [None])[0]
        self._transaction_changed=True
        c.select(clear=True); joint=c.joint(name="FaceJoint_M")
        point=c.xform(head,query=True,worldSpace=True,translation=True)
        c.xform(joint,worldSpace=True,translation=(point[0],point[1],point[2]+scale*.1))
        c.setAttr(joint+".drawStyle",2)
        fit=self._fit(required=True)
        multi=c.objExists(fit+".MultiSkinClusters") and c.getAttr(fit+".MultiSkinClusters")
        if multi:
            if not c.objExists("DeformationSystem"):
                raise FitSkeletonValidationError("Multi Skin Clusters 缺少 Body DeformationSystem")
            c.parent(joint,"DeformationSystem",absolute=True)
            c.setAttr("FaceJoint_M.inheritsTransform",False,lock=True)
            if c.objExists("Main.jointVis"): c.connectAttr("Main.jointVis","FaceJoint_M.visibility")
        else: c.parent(joint,head,absolute=True)
        c.setAttr("FaceJoint_M.segmentScaleCompensate",False)
        return c.ls("FaceJoint_M",long=True,type="joint")[0]

    def ensure_face_fit_shaders(self):
        """asFitModeEnsureShaders: recreate incomplete material/SG pairs."""
        from adv_py.core.face_fit_markers import FIT_MATERIALS
        self._require_transaction()
        c=self._cmds
        for name,color in FIT_MATERIALS:
            group=name+"SG"
            if c.objExists(name) and c.objExists(group): continue
            self._transaction_changed=True
            for node in (name,group):
                if c.objExists(node): c.delete(node)
            surface=name=="asRedSS"
            shader=c.shadingNode("surfaceShader" if surface else "lambert",name=name,asShader=True)
            c.sets(renderable=True,noSurfaceShader=True,empty=True,name=group)
            c.connectAttr(shader+".outColor",group+".surfaceShader",force=True)
            c.setAttr(shader+(".outColor" if surface else ".color"),*color,type="float3")

    def _face_base_transform(self,name):
        rows=self._cmds.ls(name,long=True,type="transform") or []
        if len(rows)!=1:
            raise FitSkeletonValidationError("Face 基础层级节点缺失或不唯一："+name)
        return rows[0]

    def _face_base_follow(self,head,node):
        """Reuse the actual source-shaped -mo -FMM constraint implementation."""
        target=self._face_base_transform(node)
        source=self.capture_parent_constraint_input(head,target,True)
        fit=self._cmds.ls("FitSkeleton",long=True,type="transform") or []
        opm=bool(len(fit)==1 and self._cmds.attributeQuery(
            "useOffsetParentMatrix",node=fit[0],exists=True) and self._cmds.getAttr(
                fit[0]+".useOffsetParentMatrix"))
        plan=plan_body_parent_constraint(replace(source,force_mult_matrix=True,
                                                 use_offset_parent_matrix=opm))
        self.preflight_parent_constraint(plan)
        self.create_parent_constraint(plan)

    def _face_base_copy_geometry(self,mesh,name):
        c=self._cmds
        node=c.duplicate(mesh,name=name,returnRootsOnly=True)[0]
        for channel in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr(node+"."+channel,lock=False)
        node=c.parent(node,"DeformationLayers",absolute=True)[0]
        # A template layer is a neutral geometry copy, not another driven Skin.
        c.delete(node,constructionHistory=True)
        for shape in c.listRelatives(node,shapes=True,fullPath=True) or []:
            if c.getAttr(shape+".intermediateObject"): c.delete(shape)
        raw=getattr(c,"raw",c)
        raw.sets(self.scene_address(node),edit=True,forceElement=":initialShadingGroup")
        c.setAttr(node+".visibility",False)
        return node

    def register_face_module_nodes(self, before, module_set, *, production_skins=(), reuse=False):
        """Append a completed module without replacing existing Face ownership."""
        self._require_transaction()
        c=self._cmds
        raw=getattr(c,"raw",c)
        if c.objExists(module_set) and (not reuse or c.nodeType(module_set)!="objectSet"):
            raise ValueError("Face 模块选择集名称已占用："+module_set)
        production_ids=set()
        for skin in production_skins:
            production_ids.update(raw.ls(self.scene_address(skin),uuid=True) or [])
            for group in raw.listConnections(self.scene_address(skin),type="objectSet") or []:
                production_ids.update(raw.ls(group,uuid=True) or [])
        created=[]
        for node in c.ls(long=True) or []:
            ids=c.ls(node,uuid=True) or []
            if len(ids)!=1 or ids[0] in before or ids[0] in production_ids: continue
            if c.nodeType(node)=="partition": continue
            if node.rsplit("|",1)[-1].rsplit(":",1)[-1]=="FaceAllSet": continue
            created.append(node)
        group=module_set if c.objExists(module_set) else c.sets(empty=True,name=module_set)
        if created: c.sets(tuple(created),add=group)
        c.sets((*created,group),add="FaceAllSet")
        self._transaction_changed=True
        return group

    def ensure_face_shaders(self):
        """Original five Lambert fit/controller materials and shading groups."""
        self._require_transaction()
        c = self._cmds
        for name, color in (("asFaceBlue", (0,0,1)),
                            ("asFaceBrown", (.541,.282,.2)),
                            ("asFaceGreen", (0,.275,.098)),
                            ("asFaceCyan", (0,.5,.5)),
                            ("asFaceRed", (.4,0,0))):
            group = name + "SG"
            if c.objExists(name) and c.objExists(group):
                continue
            for node in (name,group):
                if c.objExists(node): c.delete(node)
            shader = c.shadingNode("lambert", name=name, asShader=True)
            c.sets(renderable=True, noSurfaceShader=True, empty=True, name=group)
            c.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
            for attr in ("color", "ambientColor", "incandescence"):
                c.setAttr(shader + "." + attr, *color, type="float3")
            self._transaction_changed = True

    def ensure_face_advanced_base(self,head,geometry,all_head):
        """Build once, before face modules; generated nodes share Face ownership."""
        self._require_transaction()
        c=self._cmds
        if not c.objExists("FaceMotionSystem") and not c.objExists("allBeforeFaceBuild"):
            existing=tuple(node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet","partition"))
            snapshot=c.sets(empty=True,name="allBeforeFaceBuild")
            if existing: c.sets(existing,add=snapshot)
        self.ensure_face_shaders()
        # asFaceBuild source 31155: Multi Skin Clusters enables OPM before building.
        fit=self._fit(required=True)
        if c.objExists(fit+".MultiSkinClusters") and c.getAttr(fit+".MultiSkinClusters"):
            plug=fit+".useOffsetParentMatrix"
            if not c.objExists(plug): c.addAttr(fit,longName="useOffsetParentMatrix",attributeType="bool")
            locked=c.getAttr(plug,lock=True)
            c.setAttr(plug,lock=False)
            c.setAttr(plug,True)
            c.setAttr(plug,lock=locked)
        group=self._face_base_transform("FaceGroup")
        motions=c.ls("FaceMotionSystem",long=True,type="transform") or []
        if motions:
            if len(motions)!=1: raise FitSkeletonValidationError("FaceMotionSystem 名称不唯一")
            c.setAttr(motions[0]+".visibility",True)
            return motions[0]
        collisions=tuple(name for name in FACE_BASE_NAMES if c.objExists(name))
        if collisions:
            raise FitSkeletonValidationError("Face 基础节点名称已被占用："+"、".join(collisions))
        self._transaction_changed=True
        for name,parent in FACE_BASE_PARENTS:
            c.createNode("transform",name=name,**({"parent":parent} if parent else {}))
        position=c.xform(head,query=True,worldSpace=True,translation=True)
        for node in ("FaceMotionSystem","FaceDeformationFollowHead"):
            c.xform(node,worldSpace=True,translation=position)
        c.setAttr("FaceDeformationSystem.visibility",False,lock=True)
        c.setAttr("FaceBuildInProgressHidden.visibility",False)
        if c.objExists("JawPivot"):
            jaw=c.xform("JawPivot",query=True,worldSpace=True,translation=True)
            c.xform("JawSetup",worldSpace=True,translation=(0,jaw[1],jaw[2]))
        for node in ("JawFollowSideReverse_R","SideReverseSetup_R","SideReverse_R"):
            c.setAttr(node+".scaleX",-1)
        self._face_base_copy_geometry(geometry,"templateLayer")
        copies=[]
        for index,mesh in enumerate(all_head):
            copies.append(self._face_base_copy_geometry(mesh,
                "allHeadCombinedLayer" if len(all_head)==1 else f"advPyFaceHeadCopy{index}"))
        if len(copies)>1:
            combined=c.polyUnite(tuple(copies),constructionHistory=False,
                                 mergeUVSets=1,name="allHeadCombinedLayer")[0]
            combined=c.parent(combined,"DeformationLayers",absolute=True)[0]
            c.delete(tuple(node for node in copies if c.objExists(node)))
            c.setAttr(combined+".visibility",False)
        main=c.createNode("multiplyDivide",name="MainAndHeadScaleMultiplyDivide")
        c.setAttr(main+".input1",1,1,1)
        if c.objExists("MainScaleMultiplyDivide"):
            c.connectAttr("MainScaleMultiplyDivide.output",main+".input1")
            if c.getAttr("MainScaleMultiplyDivide.input1X",settable=True):
                c.setAttr("MainScaleMultiplyDivide.input1",1,1,1)
        elif c.objExists("Main"):
            c.connectAttr("Main.scale",main+".input1")
        for node in ("FaceMotionSystem","FaceDeformationFollowHead"):
            self._face_base_follow(head,node)
        pose=c.createNode("transform",name="faceBuildPose",parent="FaceMotionSystem")
        for attribute,value in (("udAttr",""),("udExtraAttr",""),("advPyPoseData","[]")):
            c.addAttr(pose,longName=attribute,dataType="string")
            c.setAttr(pose+"."+attribute,value,type="string")
        for name in ("FaceAllSet","FaceControlSet","FaceAreas","FaceBuildingSets"):
            c.sets(empty=True,name=name)
        c.sets("allBeforeFaceBuild",add="FaceBuildingSets")
        c.sets("FaceBuildingSets",add="FaceAllSet")
        if c.objExists("Sets"):
            c.sets(("FaceAllSet","FaceControlSet","FaceAreas"),add="Sets")
        self.ensure_original_face_orientation()
        return self._face_base_transform("FaceMotionSystem")

    def ensure_original_face_orientation(self):
        """Original preparation cylinder, source 31596–31617."""
        self._require_transaction()
        c=self._cmds
        if not c.objExists("FaceBuildInProgressHidden"):
            raise FitSkeletonValidationError("Face 定向面缺少构建隐藏分组")
        if not c.objExists("FaceControlOrient"):
            for shape in ("FaceFitSkeletonCircleShape","FaceFitSkeletonHeightShape"):
                if not c.objExists(shape): raise FitSkeletonValidationError("Face 定向面缺少 Fit 引导曲线："+shape)
            self.ensure_face_fit_shaders()
            c.cylinder(name="FaceControlOrient",pivot=(0,0,0),axis=(0,1,0),startSweep=0,endSweep=180,
                radius=1,heightRatio=2,degree=3,useTolerance=False,tolerance=.01,sections=8,spans=1,
                constructionHistory=False)
            c.sets("FaceControlOrient",edit=True,forceElement="asRedSG")
            c.scale(.5,.5,.5,"FaceControlOrient.cv[*][*]",relative=True,pivot=(0,0,0))
            c.move(0,.5,0,"FaceControlOrient.cv[*][*]",relative=True,objectSpace=True,worldSpaceDistance=True)
            def position(node): return c.xform(node,query=True,worldSpace=True,translation=True)
            bottom=position("FaceFitSkeletonCircleShape.cv[0]")
            top=position("FaceFitSkeletonHeightShape.cv[0]")
            jaw=position("JawPivot") if c.objExists("JawPivot") else position("FaceFitSkeletonCircleShape.cv[5]")
            nose=position("NoseUnder") if c.objExists("NoseUnder") else position("FaceFitSkeletonCircleShape.cv[6]")
            c.xform("FaceControlOrient",worldSpace=True,translation=(0,bottom[1],jaw[2]))
            c.scale(jaw[0]*2,top[1]-bottom[1],(nose[2]-jaw[2])*2,"FaceControlOrient",relative=True)
        elif c.listRelatives("FaceControlOrient",parent=True): c.parent("FaceControlOrient",world=True)
        c.parent("FaceControlOrient","FaceBuildInProgressHidden",absolute=True)
        self._transaction_changed=True
        return "FaceControlOrient"
