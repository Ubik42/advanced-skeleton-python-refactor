"""Original asFaceEyeBrow region, followers, squeeze and geometry transfer."""

class MayaFaceBrowMixin:
    def create_original_face_eye_brow(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self.finish_original_face_cage()
        if not c.objExists("EyeBrowInner"): return None
        skin="CageSC" if source.multi_skin_clusters else source.skin
        head="MultiSkinClustersFaceCageJoint_M" if source.multi_skin_clusters else source.head
        ctrl_scale=float(c.getAttr("OnFacecontrols.sx")); scale=source.face_scale
        self.hide_original_face_controllers(True)
        for node in c.listRelatives("OnFacecontrols",allDescendents=True,type="transform") or []:
            leaf=node.rsplit("|",1)[-1]
            if leaf.startswith("EyeBrow") and "Offset_" in leaf: c.setAttr(node+".visibility",True)
        for side in ("_R","_L"): c.setAttr("ctrlBoxBrow"+side+".visibility",True)
        if c.objExists("NoseCreaseOffset_M"): c.setAttr("NoseCreaseOffset_M.visibility",True)
        c.setAttr("ctrlBox.RegionsCtrlVis",True)
        if c.objExists("tempPointOnCurveInfo"): c.delete("tempPointOnCurveInfo")
        point=self._lip_node("pointOnCurveInfo","tempPointOnCurveInfo")
        c.setAttr(point+".turnOnPercentage",True)
        c.connectAttr("ForeHeadTopToSideCurve.worldSpace[0]",point+".inputCurve",force=True)
        c.setAttr(point+".parameter",.65)
        a=self._lip_node("transform","TempPos"); b=self._lip_node("transform","TempPos2")
        c.xform(a,worldSpace=True,translation=self._lip_vector(point+".position"))
        c.delete(c.pointConstraint("EyeBrowOuter",a,b)); towards=self._lip_pos(b)
        c.delete(a,b,point)
        inner=self._lip_pos("EyeBrowInner"); outer=self._lip_pos("EyeBrowOuter")
        for factor,side,suffix in ((1,"_R",""),(-1,"_L","Left")):
            control=self.create_original_face_controller("EyeBrowRegion",side,4)
            self.shape_original_face_half_moon(control,90); c.delete("EyeBrowRegionJoint"+side)
            offset="EyeBrowRegionOffset"+side
            c.parent(offset,"SideReverse"+side,absolute=True)
            c.xform(offset,objectSpace=True,rotation=(0,0,0),scale=(1,1,1))
            position=((inner[0]+outer[0])/(2*factor),(inner[1]+outer[1])/2,(inner[2]+outer[2])/2)
            c.xform(offset,worldSpace=True,translation=position)
            width=inner[0]-outer[0]
            c.scale(scale/width,scale/(width*2),scale/width,control+".cv[0:7]",relative=True,pivot=position)
            self.project_original_face_control(control)
            target=self._lip_node("transform","EyeBrowRegionConstrainTo"+side)
            c.parent(target,control,absolute=True)
            c.xform(target,objectSpace=True,translation=(0,0,0),scale=(1,1,1))
            c.xform(target,worldSpace=True,translation=self._lip_pos("EyeBrowInner"+suffix))
        for side in ("_R","_L"):
            if c.objExists("EyeBrowMid1"+side): self.add_original_face_follow("EyeBrowMid1"+side,"EyeBrowInner"+side,"EyeBrowRegion"+side,3)
            if c.objExists("EyeBrowMid3"+side):
                self.add_original_face_follow("EyeBrowMid3"+side,"EyeBrowOuter"+side,"EyeBrowRegion"+side,3)
                self.add_original_face_follow("EyeBrowMid2"+side,"EyeBrowOuter"+side,"EyeBrowRegion"+side,1)
            elif c.objExists("EyeBrowMid2"+side): self.add_original_face_follow("EyeBrowMid2"+side,"EyeBrowOuter"+side,"EyeBrowRegion"+side,3)
            c.parent("EyeBrowInnerOffset"+side,"EyeBrowOuterOffset"+side,"EyeBrowRegion"+side,absolute=True)
            c.scale(.6,.6,.6,"EyeBrowInner"+side+".cv[0:99]",relative=True,pivot=self._lip_pos("EyeBrowInner"+side))
        self._brow_center_follow()
        distance=max(.25,min(1.,((inner[1]-self._lip_pos("FitEyeBall")[1])/ctrl_scale)/2))
        for side in ("_R","_L"):
            for sign in (1,-1):
                if c.objExists("EyeBrowInner_R"):
                    self.add_original_face_sdk("ctrlBrow"+side+".ty","SDKEyeBrowRegion"+side+".ty",sign,distance*sign)
                    self.add_original_face_sdk("ctrlBrow"+side+".tx","SDKEyeBrowInner"+side+".ty",sign,distance*sign)
                for stem,factor in (("EyeBrowMid1",.3),("EyeBrowMid2",.25)):
                    if c.objExists(stem+"_R"): self.add_original_face_sdk("ctrlBrow"+side+".tx","SDK"+stem+side+".ty",sign,distance*factor*sign)
            if c.objExists("NoseCrease_M"):
                for attr in ("tx","ty"): self.add_original_face_sdk("ctrlBrow"+side+"."+attr,"SDKNoseCrease_M.ty",1,distance*.02)
        self._brow_squeeze(ctrl_scale)
        for side in ("_R","_L"):
            control="ctrlBrow"+side
            c.addAttr(control,longName="outerUpDown",attributeType="double",softMaxValue=10,softMinValue=0,hasMinValue=True,keyable=True)
            self.original_face_output_bw(control+".outerUpDown")
            c.xform("EyeBrowOuter_R",worldSpace=True,translation=towards)
            position=self._lip_vector("EyeBrowOuter_R.translate"); c.setAttr("EyeBrowOuter_R.translate",0,0,0)
            for index,stem in enumerate(("EyeBrowInner","EyeBrowMid1","EyeBrowMid2","EyeBrowMid3","EyeBrowOuter")):
                if not c.objExists(stem+side): continue
                value=.2*(index+1); percentage=value*value*(3-2*value)
                for axis,amount in zip("xyz",position): self.add_original_face_sdk(control+".outerUpDown","SDK"+stem+side+".t"+axis,10,amount*percentage)
        raw.skinCluster(self.scene_address(skin),edit=True,selectInfluenceVerts=self.scene_address("EyeBrowCenterJoint_M"))
        for vertex in raw.ls(selection=True,long=True,flatten=True) or []:
            if "." in vertex and raw.skinPercent(self.scene_address(skin),vertex,transform=self.scene_address(head),query=True)>.99:
                raw.skinPercent(self.scene_address(skin),vertex,transformValue=[(self.scene_address(head),1)])
        self._brow_hammer_region(source,skin)
        extra_skins=self._brow_attach_geometry(source,skin)
        c.select(clear=True); self._transaction_changed=True
        return {"controls":("EyeBrowRegion_R","EyeBrowRegion_L"),"skin":skin,"production_skins":extra_skins}

    def _brow_center_follow(self):
        c=self._cmds
        c.addAttr("EyeBrowCenter_M",longName="follow",attributeType="double",minValue=0,maxValue=10,defaultValue=10,keyable=True)
        self._lip_node("transform","EyeBrowCenterFollow_M","EyeBrowCenterOffset_M")
        uc=self._lip_node("unitConversion","EyeBrowCenterFollowUnitConversion")
        c.setAttr(uc+".conversionFactor",.1); c.connectAttr("EyeBrowCenter_M.follow",uc+".input")
        c.parent("SDKEyeBrowCenter_M","EyeBrowCenterFollow_M",absolute=True)
        for side in ("_R","_L"):
            plus=self._lip_node("plusMinusAverage","EyeBrowCenterBlenderPMA"+side)
            for index,stem in enumerate(("EyeBrowInner","SDKEyeBrowInner","EyeBrowRegion","SDKEyeBrowRegion")):
                c.connectAttr(stem+side+".translate",plus+f".input3D[{index}]")
        plus=self._lip_node("plusMinusAverage","EyeBrowCenterBlenderPMA_M"); c.setAttr(plus+".operation",3)
        for index,side in enumerate(("_R","_L")): c.connectAttr("EyeBrowCenterBlenderPMA"+side+".output3D",plus+f".input3D[{index}]")
        multiply=self._lip_node("multiplyDivide","EyeBrowCenterBlenderMPD_M")
        for axis in "YZ":
            c.connectAttr(plus+".output3D"+axis.lower(),multiply+".input1"+axis)
            c.connectAttr(uc+".output",multiply+".input2"+axis)
            c.connectAttr(multiply+".output"+axis,"EyeBrowCenterFollow_M.t"+axis.lower())

    def _brow_squeeze(self,ctrl_scale):
        c=self._cmds
        points=[self._lip_pos("EyeBrowCenter"),self._lip_pos("EyeBrowInner")]
        points.extend(self._lip_pos("EyeBrowMid"+str(i)+"_R") for i in range(1,4) if c.objExists("EyeBrowMid"+str(i)+"_R"))
        points.append(self._lip_pos("EyeBrowOuter"))
        c.curve(name="EyeBrowCurve",degree=1,point=points)
        c.rebuildCurve("EyeBrowCurve",constructionHistory=False,replaceOriginal=True,rebuildType=0,endKnots=1,
            keepRange=0,keepControlPoints=False,keepEndPoints=False,keepTangents=False,spans=0,degree=3,tolerance=.01)
        a=self._lip_node("transform","TempPos"); path=self._lip_node("motionPath","tempMotionPath")
        c.setAttr(path+".fractionMode",True); c.connectAttr("EyeBrowCurve.worldSpace[0]",path+".geometryPath")
        c.connectAttr(path+".allCoordinates",a+".translate"); c.connectAttr(path+".rotate",a+".rotate")
        for attr,value in (("worldUpType",0),("upAxis",1),("frontAxis",0),("inverseFront",1)): c.setAttr(path+"."+attr,value)
        nearest=self._lip_node("nearestPointOnCurve","tempNearestPointOnCurve")
        c.connectAttr("EyeBrowCurve.worldSpace[0]",nearest+".inputCurve",force=True)
        b=self._lip_node("transform","TempPos2"); c.connectAttr(b+".translate",nearest+".inPosition")
        try:
            for side in ("_R","_L"):
                c.addAttr("ctrlBrow"+side,longName="squeeze",attributeType="double",softMaxValue=10,softMinValue=0,hasMinValue=True,keyable=True)
                self.original_face_output_bw("ctrlBrow"+side+".squeeze")
                inner=self._lip_pos("EyeBrowInner_R")
                for axis,factor in (("x",.5),("y",.25)): self.add_original_face_sdk("ctrlBrow"+side+".squeeze","SDKEyeBrowInner"+side+".t"+axis,10,inner[0]/ctrl_scale*factor)
                for stem in ("EyeBrowMid1","EyeBrowMid2","EyeBrowMid3","EyeBrowOuter"):
                    if not c.objExists(stem+side): continue
                    c.xform(b,worldSpace=True,translation=self._lip_pos(stem+"_R"))
                    c.delete(c.geometryConstraint(self.scene_address("EyeBrowCurve"),b))
                    parameter=c.getAttr(nearest+".parameter"); c.setAttr(path+".uValue",parameter)
                    angle=c.getAttr(a+".ry"); c.setAttr(path+".uValue",parameter-.1); angle-=c.getAttr(a+".ry")
                    c.xform(stem+"_R",worldSpace=True,translation=self._lip_pos(a))
                    position=self._lip_vector(stem+"_R.translate"); c.setAttr(stem+"_R.translate",0,0,0)
                    for axis,value in zip("xyz",position): self.add_original_face_sdk("ctrlBrow"+side+".squeeze","SDK"+stem+side+".t"+axis,10,value)
                    self.add_original_face_sdk("ctrlBrow"+side+".squeeze","SDK"+stem+side+".ry",10,angle)
        finally: c.delete(a,b,nearest,path,"EyeBrowCurve")

    def _brow_hammer_region(self,source,skin):
        c=self._cmds; raw=getattr(c,"raw",c)
        mesh=self.scene_address(source.geometry)
        all_vertices=set(raw.ls(mesh+".vtx[*]",long=True,flatten=True) or [])
        for suffix in ("","Left"):
            inner=self.scene_address(self.sample_face_fit_vertices("EyeBrowInner"+suffix,source.geometry)[0])
            outer=self.scene_address(self.sample_face_fit_vertices("EyeBrowOuter"+suffix,source.geometry)[0])
            outside=all_vertices-set(self.scene_address(v) for v in self.sample_face_fit_vertices("ForeHeadAreaMesh"+suffix,source.geometry))
            start=tuple(self.scene_address(v) for v in self.sample_face_fit_vertices("upperEyeLidOuterCurve"+suffix,source.geometry))
            raw.select(start,replace=True)
            for index in range(25):
                vertices=set(raw.ls(selection=True,long=True,flatten=True) or [])
                if inner in vertices or outer in vertices: break
                raw.polySelectConstraint(propagate=1,type=1); raw.select(tuple(outside),deselect=True)
            else: index=25
            raw.select(start,replace=True)
            for _ in range(max(0,index-1)):
                raw.polySelectConstraint(propagate=1,type=1); raw.select(tuple(outside),deselect=True)
            raw.select(start,deselect=True)
            vertices=tuple(raw.ls(selection=True,long=True,flatten=True) or [])
            if vertices: self._lip_falloff_hammer(skin,vertices,5)

    def _brow_attach_geometry(self,source,skin):
        c=self._cmds; raw=getattr(c,"raw",c); result=[]
        parts=self.read_original_face_parts("Eyebrow")
        for geometry in parts:
            target=self._original_face_skin_history(geometry)
            if not target: raise ValueError("Eyebrow 对象缺少 Skin："+geometry)
            if source.multi_skin_clusters:
                joint="MultiSkinClustersFaceEyeBrowJoint_M"
                if not c.objExists(joint):
                    self._lip_node("joint",joint,"FaceJoint_M")
                    c.setAttr(joint+".drawStyle",2); c.setAttr(joint+".inheritsTransform",False,lock=True)
                from contextlib import nullcontext
                with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
                    target=raw.skinCluster(self.scene_address(joint),geometry,multi=True,frontOfChain=True,
                        toSelectedBones=True,name=self.scene_address("EyeBrowSC"))[0]
            if set(raw.ls(target,uuid=True) or []) & set(raw.ls(self.scene_address(skin),uuid=True) or []):
                self._cage_copy_selected(("asCage",),(geometry,)); result.append(target); continue
            joints=["EyeBrowCenterJoint_M"]
            joints.extend(stem+"Joint"+side for side in ("_R","_L") for stem in
                ("EyeBrowInner","EyeBrowOuter","EyeBrowMid1","EyeBrowMid2","EyeBrowMid3") if c.objExists(stem+"Joint"+side))
            raw.skinCluster(target,edit=True,dropoffRate=4,lockWeights=False,weight=0,
                            addInfluence=[self.scene_address(j) for j in joints])
            if not source.multi_skin_clusters: raw.skinPercent(target,geometry,transformValue=[(self.scene_address(source.head),0)])
            self._cage_copy_selected((source.geometry,),(geometry,),source_skin="CageSC" if source.multi_skin_clusters else None,
                                    target_skin=target if source.multi_skin_clusters else None)
            raw.select(geometry,replace=True); result.append(target)
        return tuple(result)
