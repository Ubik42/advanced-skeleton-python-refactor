"""Original CageLayer transfer/smoothing/removal, source 36479–36772."""

class MayaFaceCageWeightsMixin:
    def _cage_add_set_vertices(self,name,vertices):
        if not vertices: return
        c=self._cmds; raw=getattr(c,"raw",c)
        raw.sets(tuple(self.scene_address(v) for v in vertices),add=self.scene_address(name))

    def _cage_skin_influences(self,skin):
        c=self._cmds; raw=getattr(c,"raw",c)
        return tuple(raw.skinCluster(self.scene_address(skin),query=True,influence=True) or [])

    def _cage_bind_layer(self,name,joints,geometry):
        c=self._cmds; raw=getattr(c,"raw",c)
        from .maya_original_skin_history import bind_original_skin
        return bind_original_skin(c, (*joints, geometry), name, namespace=self.namespace)

    def _cage_copy_selected(self,source_vertices,target_vertices,*,source_skin=None,target_skin=None):
        c=self._cmds; raw=getattr(c,"raw",c)
        raw.select(tuple(self.scene_address(v) for v in (*source_vertices,*target_vertices)),replace=True)
        flags={"noMirror":True,"surfaceAssociation":"closestPoint","influenceAssociation":"closestJoint"}
        if source_skin: flags["sourceSkin"]=self.scene_address(source_skin)
        if target_skin: flags["destinationSkin"]=self.scene_address(target_skin)
        raw.copySkinWeights(**flags)

    def transfer_original_face_cage(self,source,smooth_passes):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        skin="CageSC" if source.multi_skin_clusters else source.skin
        raw.setAttr(self.scene_address(source.geometry)+".visibility",True)
        c.setAttr("asCage.visibility",False)
        c.duplicate("templateLayer",name="PreCageWeights",returnRootsOnly=True)
        self._cage_bind_layer("PreCageWeightsSC",self._cage_skin_influences(skin),"PreCageWeights")
        self._cage_copy_selected((source.geometry,),("PreCageWeights",))
        c.duplicate("templateLayer",name="CageLayer",returnRootsOnly=True)
        influences=list(self._cage_skin_influences(skin))
        if source.has_below_eye:
            excluded=set(raw.ls([self.scene_address(j) for j in c.listRelatives(
                "LipJoints_M",allDescendents=True,type="joint") or []],uuid=True) or [])
            influences=[j for j in influences if not excluded.intersection(raw.ls(j,uuid=True) or [])]
        cage_off=self.scene_address("cageOffJoint")
        if not set(raw.ls(cage_off,uuid=True) or []) & set(raw.ls(influences,uuid=True) or []): influences.append(cage_off)
        self._cage_bind_layer("CageLayerSC",tuple(influences),"CageLayer")
        if c.listRelatives("CageLayer",parent=True): c.parent("CageLayer",world=True)
        if source.multi_skin_clusters: c.skinPercent("CageLayerSC","CageLayer",transformValue=[("cageOffJoint",1)])
        else: self._cage_copy_selected((source.geometry,),("CageLayer",))
        result=self.update_original_face_cage_weights(source,smooth_passes)
        if source.has_above_eye:
            for name in ("eyeBrowArea","eyeBrowLineArea"):
                c.sets(empty=True,name=name); c.sets(name,add="FaceAreas")
            for side,suffix in (("_R",""),("_L","Left")):
                stems=["EyeBrowInner","EyeBrowOuter"]
                stems.extend("EyeBrowMid"+str(i) for i in range(1,4) if c.objExists("EyeBrowMid"+str(i)+"Joint"+side))
                for stem in stems:
                    raw.skinCluster(self.scene_address(skin),edit=True,selectInfluenceVerts=self.scene_address(stem+"Joint"+side))
                    self._cage_add_set_vertices("eyeBrowArea",raw.ls(selection=True,long=True,flatten=True) or [])
                    self._cage_add_set_vertices("eyeBrowLineArea",self.sample_face_fit_vertices(stem+suffix,source.geometry))
        if source.has_below_eye:
            for node in ("LipRegionOffset_M","LipOffset_R","LipOffset_L","upperLipOffset_M","lowerLipOffset_M"):
                c.setAttr(node+".visibility",True)
        c.select(clear=True)
        self._transaction_changed=True
        return result

    def _cage_mask_without_perimeter(self,source):
        c=self._cmds; raw=getattr(c,"raw",c)
        fit=self._fit(required=True)
        # The MEL stage selects FaceFitSkeleton.Mask as it exists at this
        # point in the build. Prep can clear this string while the Python
        # upgrade payload still retains the earlier mask faces.
        if not (c.getAttr(fit+".Mask") or "").strip():
            return ()
        mesh,faces,_=self.read_face_mask()
        selected=[self.scene_address(mesh)+f".f[{i}]" for i in faces]
        vertices=set(raw.ls(raw.polyListComponentConversion(selected,toVertex=True),long=True,flatten=True) or [])
        lash=self.original_face_part_text('Eyelash')
        if lash:
            raw.select(selected,replace=True)
            raw.select(tuple(self.scene_address(token) for token in lash.split()),deselect=True)
            selected=raw.ls(selection=True,long=True,flatten=True) or []
            vertices=set(raw.ls(raw.polyListComponentConversion(selected,toVertex=True),long=True,flatten=True) or [])
        # Native sequence used by ConvertSelectionToVertexPerimeter.
        contained=raw.polyListComponentConversion(tuple(vertices),fromVertex=True,toFace=True,internal=True) or []
        if not contained: contained=raw.polyListComponentConversion(tuple(vertices),fromVertex=True,toFace=True) or []
        edges=raw.polyListComponentConversion(contained,fromFace=True,toEdge=True,border=True) or []
        perimeter=set(raw.ls(raw.polyListComponentConversion(edges,fromEdge=True,toVertex=True),long=True,flatten=True) or []) if edges else set()
        result=vertices-perimeter
        include=c.getAttr(fit+".Include",asString=True) if c.objExists(fit+".Include") else "Complete"
        if include in ("Skip Below Eyes","Skip Above+Below Eyes"):
            result=set(self.scene_address(v) for suffix in ("","Left")
                for v in self.sample_face_fit_vertices("ForeHeadAreaMesh"+suffix,source.geometry))
        if include in ("Skip Above Eyes","Skip Above+Below Eyes"):
            height=self._lip_pos("upperEyeLidMainCurve.cv[0]")[1]
            result={v for v in result if raw.xform(v,query=True,worldSpace=True,translation=True)[1]<=height}
        return tuple(sorted(result))

    def _cage_smooth_layer(self,joints,passes):
        from .maya_face_jaw_weights import (original_skin_paint_context,
            select_original_skin_paint_influence,original_skin_paint_flood)
        c=self._cmds; raw=getattr(c,"raw",c)
        c.setAttr("CageLayer.visibility",True)
        c.select("CageLayer",replace=True)
        try:
            original_skin_paint_context(raw)
            for _ in range(passes):
                for joint in joints:
                    if joint.rsplit("|",1)[-1].rsplit(":",1)[-1].startswith("EyeBrow"): continue
                    select_original_skin_paint_influence(raw,self.scene_address(joint))
                    raw.refresh()
                    original_skin_paint_flood()
                    raw.refresh()
        finally:
            raw.setToolTo("selectSuperContext")
            c.setAttr("CageLayer.visibility",False)

    def update_original_face_cage_weights(self,source,smooth_passes):
        """Keep selection-driven copies where the MEL relies on subset filtering."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        previous=tuple(raw.ls(selection=True,long=True) or [])
        skin="CageSC" if source.multi_skin_clusters else source.skin
        joints=c.sets("asCageJoints",query=True) or []
        mask=self._cage_mask_without_perimeter(source)
        try:
            if source.multi_skin_clusters:
                influences=self._cage_skin_influences("asCageSC")
                for joint in influences: raw.setAttr(joint+".lockInfluenceWeights",True)
                c.setAttr("Head_M.lockInfluenceWeights",False); c.setAttr("cageOffJoint.lockInfluenceWeights",False)
                c.skinPercent("asCageSC","asCage",transformValue=[("Head_M",0)])
                for joint in influences: raw.setAttr(joint+".lockInfluenceWeights",False)
            self._cage_copy_selected(("asCage",),self._jaw_layer_cast(mask,"CageLayer"))
            self._cage_smooth_layer(joints,smooth_passes)
            fit=self._fit(required=True)
            eyes=[]
            for attribute in ("RightEye","LeftEye"):
                text=c.getAttr(fit+"."+attribute) if c.objExists(fit+"."+attribute) else ""
                if text: eyes.extend(self.scene_address(token) for token in text.split())
            eye_vertices=set(raw.ls(raw.polyListComponentConversion(eyes,toVertex=True),long=True,flatten=True) or []) if eyes else set()
            excluded=set(eye_vertices)
            for area in ("lipArea","eyeLidArea","eyeLidAreaLeft","eyeSocketArea","eyeSocketAreaLeft"):
                if c.objExists(area): excluded.update(self._jaw_set_members(area))
            # Exclusions are on production geometry; source CageLayer vertices
            # stay selected exactly as in the original selection-based copy.
            target=tuple(v for v in mask if v not in excluded)
            self._cage_copy_selected(self._jaw_layer_cast(mask,"CageLayer"),target,
                source_skin="CageLayerSC" if source.multi_skin_clusters else None,
                target_skin=skin if source.multi_skin_clusters else None)
            if source.multi_skin_clusters:
                areas=[]
                for area in ("eyeLidArea","eyeLidAreaLeft","eyeLidMainArea"):
                    areas.extend(self._jaw_set_members(area))
                raw.select(tuple(areas),replace=True)
                raw.skinPercent(self.scene_address(skin),transformValue=[(self.scene_address("MultiSkinClustersFaceCageJoint_M"),1)])
            else:
                falloff=self._jaw_set_members("lipFalloffArea") if c.objExists("lipFalloffArea") else ()
                for vertex in falloff:
                    layer=self.scene_address(self._jaw_layer_cast((vertex,),"LipFalloffLayer")[0])
                    influences=raw.skinPercent(self.scene_address("LipFalloffLayerSC"),layer,ignoreBelow=.01,query=True,transform=None) or []
                    values=raw.skinPercent(self.scene_address("LipFalloffLayerSC"),layer,ignoreBelow=.01,query=True,value=True) or []
                    weights=[(self.scene_address("cageOffJoint"),0)]
                    weights.extend((joint,value) for joint,value in zip(influences,values)
                                   if joint.rsplit("|",1)[-1].rsplit(":",1)[-1]!="lipOffJoint")
                    raw.skinPercent(self.scene_address(skin),self.scene_address(vertex),transformValue=weights)
                raw.skinPercent(self.scene_address(skin),self.scene_address(source.geometry),
                                transformValue=[(self.scene_address("cageOffJoint"),0)])
            self._transaction_changed=True
            return {"vertices":len(mask),"smooth_passes":smooth_passes,"skin":skin}
        finally: raw.select(previous,replace=True) if previous else raw.select(clear=True)

    def remove_original_face_cage_weights(self,source):
        self._require_transaction()
        self._cage_copy_selected(("PreCageWeights",),(source.geometry,))
        self._transaction_changed=True

    def finish_original_face_cage(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve") and not c.objExists("EyeBrowInner"): return False
        if c.objExists("FaceBuildInProgress.FaceCageFinish"): return False
        c.addAttr("FaceBuildInProgress",longName="FaceCageFinish",attributeType="bool",defaultValue=True)
        c.parent("asCage","FaceBuildInProgressHidden",absolute=True)
        for node in ("CageLayer","LipFalloffLayer"):
            if c.objExists(node): c.delete(node)
        self._transaction_changed=True
        return True
