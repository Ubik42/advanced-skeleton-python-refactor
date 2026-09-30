"""Original upper/middle/lower face controls and Head-weight redistribution."""
from contextlib import nullcontext
from adv_py.application.face_pre import FacePreRole

class MayaFaceUpMidLoMixin:
    def show_original_face_eye_aim(self):
        c=self._cmds
        self.hide_original_face_controllers(True)
        for plug,value in (("ctrlBox2.visibility",False),("ctrlBox.RegionsCtrlVis",False),
                           ("ctrlBox.AimCtrlVis",True),("AimEyeOffset_M.visibility",True)):
            c.setAttr(plug,value)
        c.select(clear=True)
        return True

    def create_original_face_up_mid_lo(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        c.setAttr("ctrlBox.AimCtrlVis",False)
        if not c.objExists("upperFace") or not c.objExists("JawPivot"): return None
        skin=self.add_original_face_multi_skin("UpMidLoc",source.geometry) if source.multi_skin_clusters else source.skin
        if source.multi_skin_clusters:
            raw.reorderDeformers(self.scene_address(source.skin),self.scene_address(skin),self.scene_address(source.geometry))
        head="MultiSkinClustersFaceUpMidLocJoint_M" if source.multi_skin_clusters else source.head
        c.duplicate("templateLayer",name="UpMidLoLayer",returnRootsOnly=True)
        c.duplicate("allHeadCombinedLayer",name="UpMidLoAllHeadCombinedLayer",returnRootsOnly=True)
        self.show_original_face_layer_in_transaction("UpMidLo")
        c.parent("UpMidLoLayer",world=True)
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox2.visibility",True); c.setAttr("ctrlBox.UpMidLoCtrlVis",True)
        for influence in self._cage_skin_influences(skin): raw.setAttr(influence+".lockInfluenceWeights",True)
        raw.setAttr(self.scene_address(head)+".lockInfluenceWeights",False)
        stems=("upper","middle","lower")
        for stem in stems:
            joint=stem+"FaceJoint_M"; control=stem+"Face_M"; offset=stem+"FaceOffset_M"
            c.select("FaceJoint_M",replace=True); c.joint(name=joint)
            c.setAttr(joint+".segmentScaleCompensate",False)
            position=self._lip_pos(stem+"Face")
            c.xform(joint,worldSpace=True,translation=(0,position[1],position[2]))
            c.circle(name=control,center=(0,0,0),normal=(0,1,0),sweep=180,radius=4,degree=3,
                useTolerance=False,tolerance=.000393701,sections=8,constructionHistory=False)
            shape=(c.listRelatives(control,shapes=True,fullPath=True) or [None])[0]
            c.connectAttr("ctrlBox.UpMidLoCtrlVis",shape+".overrideVisibility")
            factor=-4.5*self._lip_pos("JawPivot")[0]/source.face_scale
            c.scale(factor,factor,factor,control+".cv[0:99]",relative=True,pivot=(0,0,0))
            c.rotate(0,-90,0,control+".cv[0:99]",relative=True)
            c.sets(control,add="FaceControlSet"); c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",17)
            self._lip_node("transform",offset); c.parent(control,offset,absolute=True)
            c.parent(offset,"OnFacecontrols",absolute=True); c.setAttr(offset+".scale",1,1,1,type="float3")
            c.xform(offset,worldSpace=True,translation=self._lip_pos(joint))
            self.constrain_original_face(control,joint,True,force_matrix=False)
            if source.multi_skin_clusters:
                mm=stem+"FaceJointMM_M"
                raw.connectAttr(self.scene_address(source.head)+".worldInverseMatrix[0]",self.scene_address(mm)+".matrixIn[2]",force=True)
                c.setAttr(mm+".matrixIn[3]",*raw.getAttr(self.scene_address(source.head)+".worldMatrix[0]"),type="matrix")
                c.connectAttr("FaceJoint_M.worldInverseMatrix[0]",mm+".matrixIn[4]")
            else:
                nodes=[]
                for side in ("_R","_L","_M"):
                    nodes.append(self._lip_node("transform",stem+"SideReverse"+side,"SideReverse"+side))
                c.parent(*nodes,control,absolute=True)
            self.add_original_ctrl_box_second_shape(control,stem+"Face1_M")
        if not source.multi_skin_clusters: self._up_mid_lo_reparent_controls()
        joints=tuple(stem+"FaceJoint_M" for stem in stems)
        self._cage_bind_layer("UpMidLoSC",("FaceJoint_M",*joints),"UpMidLoLayer")
        c.skinPercent("UpMidLoSC","UpMidLoLayer",transformValue=[("middleFaceJoint_M",1)])
        try:
            for stem,bounds in (("upper",(self._lip_pos("upperFace")[1],9999)),("lower",(0,self._lip_pos("lowerFace")[1]))):
                raw.select(self.scene_address("UpMidLoLayer"),replace=True)
                raw.polySelectConstraint(mode=3,type=1,distance=3,distancebound=bounds,distanceaxis=(0,1,0),distancepoint=(0,0,0))
                raw.skinPercent(self.scene_address("UpMidLoSC"),transformValue=[(self.scene_address(stem+"FaceJoint_M"),1)])
        finally: raw.polySelectConstraint(mode=0)
        all_vertices=tuple(c.ls("UpMidLoLayer.vtx[*]",long=True,flatten=True) or [])
        for a,b in (("upperFaceJoint_M","middleFaceJoint_M"),("lowerFaceJoint_M","middleFaceJoint_M"),
                    ("lowerFaceJoint_M","FaceJoint_M")):
            self.smooth_original_face_flood("UpMidLoSC",all_vertices,a,b,10)
        raw.skinCluster(self.scene_address(skin),edit=True,lockWeights=False,weight=0,
                        addInfluence=[self.scene_address(j) for j in joints])
        c.skinCluster("lipSlideSurfaceSC",edit=True,lockWeights=False,weight=0,addInfluence="lowerFaceJoint_M")
        c.skinPercent("lipSlideSurfaceSC","lipSlideSurface",transformValue=[("lowerFaceJoint_M",1)])
        non_sym=bool(c.objExists(fit+".NonSym") and c.getAttr(fit+".NonSym"))
        head_id=set(raw.ls(self.scene_address(head),uuid=True) or [])
        stored={joint:[] for joint in (head,*joints)}
        vertex_indices=[]
        for index in range(int(raw.polyEvaluate(self.scene_address(source.geometry),vertex=True))):
            layer="UpMidLoLayer"+f".vtx[{index}]"; vertex=self.scene_address(source.geometry)+f".vtx[{index}]"
            if not non_sym and self._lip_pos(layer)[0]>source.face_scale*.01: continue
            influences=raw.skinPercent(self.scene_address(skin),vertex,ignoreBelow=.01,query=True,transform=None) or []
            if not any(head_id.intersection(raw.ls(j,uuid=True) or []) for j in influences): continue
            head_weight=raw.skinPercent(self.scene_address(skin),vertex,transform=self.scene_address(head),query=True)
            vertex_indices.append(index); stored[head].append(0.)
            for joint in joints:
                value=c.skinPercent("UpMidLoSC",layer,transform=joint,query=True)
                stored[joint].append(head_weight*value)
        for joint in (head,*joints):
            self.set_original_face_influence_weights(joint,source.geometry,skin,vertex_indices,stored[joint])
        if not non_sym:
            raw.copySkinWeights(sourceSkin=self.scene_address(skin),destinationSkin=self.scene_address(skin),
                mirrorMode="YZ",mirrorInverse=True,surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
        extra=self._up_mid_lo_other_geometry(source,skin,joints)
        c.parent("UpMidLoLayer","DeformationLayers",absolute=True)
        self.show_original_face_layer_in_transaction("Normal")
        self._transaction_changed=True
        return {"controls":tuple(stem+"Face_M" for stem in stems),"production_skins":(source.skin,skin,*extra)}

    def set_original_face_influence_weights(self,joint,geometry,skin,indices,values):
        """asSkinWeightSet: sparse writes then the two lock-aware normalizations."""
        c=self._cmds; raw=getattr(c,"raw",c); path=self.scene_address(skin)
        ids=set(raw.ls(self.scene_address(joint),uuid=True) or [])
        connections=raw.listConnections(path+".matrix",source=True,destination=False,connections=True,plugs=True) or []
        influence=None
        for offset in range(0,len(connections),2):
            destination,source=connections[offset:offset+2]
            if ids.intersection(raw.ls(source.split(".",1)[0],uuid=True) or []):
                influence=int(destination.rsplit("[",1)[1][:-1]); break
        if influence is None: raise ValueError("UpMidLo Skin 缺少影响关节："+joint)
        for index,value in zip(indices,values): raw.setAttr(path+f".weightList[{index}].weights[{influence}]",value)
        for locked in (True,False):
            raw.setAttr(self.scene_address(joint)+".lockInfluenceWeights",locked)
            try: raw.skinPercent(path,self.scene_address(geometry),normalize=True)
            except RuntimeError: pass  # Original catchQuiet on each normalization.

    def _up_mid_lo_reparent_controls(self):
        c=self._cmds; fit=self._fit(required=True)
        include=c.getAttr(fit+".Include",asString=True) if c.objExists(fit+".Include") else "Complete"
        above=include not in ("Skip Above Eyes","Skip Above+Below Eyes")
        eye_base=bool(c.objExists(fit+".EyeBase") and c.getAttr(fit+".EyeBase"))
        for side in ("_R","_L"):
            if above:
                c.parent(("EyeBaseOffset" if eye_base else "EyeRegionOffset")+side,"EyeOffset"+side,
                         "EyeBrowRegionOffset"+side,"upperSideReverse"+side,absolute=True)
            c.parent("middleFaceStatic"+side,"middleSideReverse"+side,absolute=True)
            c.parent("lowerFaceStatic"+side,"SmilePullOffset"+side,"lowerSideReverse"+side,absolute=True)
        if above: c.parent("EyeBrowCenterOffset_M","NoseCreaseOffset_M","upperSideReverse_M",absolute=True)
        c.parent("NoseRegionOffset_M","middleFaceStatic_M","middleSideReverse_M",absolute=True)
        c.parent("JawOffset_M","lowerFaceStatic_M","lowerSideReverse_M",absolute=True)
        if c.objExists("upperTeethOffset_M"): c.parent("upperTeethOffset_M","lowerSideReverse_M",absolute=True)

    def _up_mid_lo_other_geometry(self,source,skin,joints):
        c=self._cmds; raw=getattr(c,"raw",c); result=[]
        defined=[self.scene_address(source.geometry)]
        for attribute in ("RightEye","LeftEye","UpperTeeth","LowerTeeth","Tongue","Eyebrow","EyeLash"):
            defined.extend(self.read_original_face_parts(attribute))
        objects={value.split(".",1)[0] for value in defined}
        for geometry in self.read_face_objects(FacePreRole.ALL_HEAD):
            physical=self.scene_address(geometry)
            if source.multi_skin_clusters:
                if physical==self.scene_address(source.geometry): continue
                with c._creation_namespace() if hasattr(c,"_creation_namespace") else nullcontext():
                    target=raw.skinCluster([physical,self.scene_address("MultiSkinClustersFaceUpMidLocJoint_M"),
                        *(self.scene_address(j) for j in joints)],multi=True,frontOfChain=True,toSelectedBones=True,
                        name=self.scene_address("UpMidLocSC"))[0]
                history=[n for n in raw.listHistory(physical,pruneDagObjects=True,interestLevel=2) or [] if raw.nodeType(n)=="skinCluster"]
                if len(history)>2:
                    shapes=raw.listRelatives(physical,shapes=True,noIntermediate=True,fullPath=True) or []
                    chain=raw.skinClusterChain(shapes[0]) or []
                    if chain: raw.reorderDeformers(chain[0],target,physical)
                self._cage_copy_selected(("UpMidLoLayer",),(physical,),source_skin=skin,target_skin=target)
            else:
                if physical in defined or physical in objects: continue
                target=self._original_face_skin_history(physical)
                raw.skinCluster(target,edit=True,lockWeights=False,weight=0,addInfluence=[self.scene_address(j) for j in joints])
                self._cage_copy_selected(("UpMidLoLayer",),(physical,))
            result.append(target)
        return tuple(result)
