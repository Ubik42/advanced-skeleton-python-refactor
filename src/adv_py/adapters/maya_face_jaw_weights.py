"""ADV 6.925 JawCurve weighting and world-space pick walk, 41677–41977."""
from math import dist
from adv_py.core.fit_settings import FitSkeletonValidationError


def original_skin_paint_context(cmds, influence=None):
    """Initialize Maya's real Skin tool, as the source paint procedures do.

    Creating an artAttrSkinPaintCtx alone does not register the Skin painting
    callbacks. Only stock Maya tool commands run here, never ADV procedures.
    """
    from maya import mel
    mel.eval('ArtPaintSkinWeightsTool; source artAttrSkinJointMenu;')
    context = 'artAttrSkinContext'
    cmds.artAttrSkinPaintCtx(context, edit=True, selectedattroper='smooth')
    if influence:
        select_original_skin_paint_influence(cmds, influence)
    return context


def select_original_skin_paint_influence(cmds, influence):
    from maya import mel
    # Maya joint identities cannot contain quotation marks; JSON supplies a
    # literal MEL string for DAG paths and namespaces without interpolation.
    import json
    cmds.artAttrSkinPaintCtx('artAttrSkinContext', edit=True, influence=influence)
    mel.eval('artSkinInflListChanging ' + json.dumps(influence) + ' 1;')
    mel.eval('artSkinInflListChanged artAttrSkinPaintCtx;')


def original_skin_paint_flood():
    from maya import mel
    mel.eval('artFloodSurfaces;')

class MayaFaceJawWeightsMixin:
    def _jaw_set_members(self,name):
        raw=getattr(self._cmds,"raw",self._cmds)
        members=raw.sets(self.scene_address(name),query=True) or []
        return tuple(raw.ls(members,long=True,flatten=True) or [])

    def _jaw_vertex_set(self,name,vertices):
        c=self._cmds; raw=getattr(c,"raw",c)
        if c.objExists(name): c.delete(name)
        c.sets(empty=True,name=name)
        if vertices: raw.sets(tuple(vertices),add=self.scene_address(name))
        c.sets(name,add="FaceBuildingSets")

    def sample_original_face_curve_path(self,curve,geometry):
        """asSelectCurveVtx's 101 parameter samples on a frozen mesh copy."""
        c=self._cmds
        mesh=c.duplicate(geometry,name="jawCurveSamplerMeshTemp#",returnRootsOnly=True)[0]
        for shape in c.listRelatives(mesh,shapes=True,fullPath=True) or []:
            if c.getAttr(shape+".intermediateObject"): c.delete(shape)
        for attr in ("tx","ty","tz","rx","ry","rz","sx","sy","sz","v"):
            c.setAttr(mesh+"."+attr,lock=False)
        if c.listRelatives(mesh,parent=True): c.parent(mesh,world=True)
        c.makeIdentity(mesh,apply=True,translate=True,rotate=True,scale=True)
        point=self._lip_node("pointOnCurveInfo","jawCurvePOCITemp#")
        sampler=self._lip_node("closestPointOnMesh","jawCurveVertexSamplerTemp#")
        c.connectAttr(curve+".worldSpace[0]",point+".inputCurve")
        c.setAttr(point+".turnOnPercentage",True)
        c.connectAttr(mesh+".outMesh",sampler+".inMesh")
        c.connectAttr(point+".position",sampler+".inPosition")
        vertices=[]; previous=0
        try:
            for index in range(101):
                c.setAttr(point+".parameter",index*.01)
                vertex=int(c.getAttr(sampler+".closestVertexIndex"))
                if vertex!=previous: vertices.append(geometry+f".vtx[{vertex}]")
                previous=vertex
        finally: c.delete(mesh,point,sampler)
        return tuple(dict.fromkeys(vertices))

    def pick_original_face_vertex_world(self,vertex,direction=(0,1,0)):
        """asWsPickWalk: neighbor whose axis delta has largest Manhattan share."""
        raw=getattr(self._cmds,"raw",self._cmds)
        start=(raw.ls(self.scene_address(vertex),long=True,flatten=True) or [None])[0]
        if not start: raise FitSkeletonValidationError("World PickWalk 顶点不存在")
        position=raw.xform(start,query=True,worldSpace=True,translation=True)
        neighbors=raw.ls(raw.polyListComponentConversion(raw.polyListComponentConversion(start,toEdge=True),
                      toVertex=True),long=True,flatten=True) or []
        maximum=0.; selected=None
        for neighbor in neighbors:
            if neighbor==start: continue
            point=raw.xform(neighbor,query=True,worldSpace=True,translation=True)
            delta=[b-a for a,b in zip(position,point)]
            if any(d>0 and value<0 or d<0 and value>0 for d,value in zip(direction,delta)): continue
            total=sum(abs(value) for value in delta)
            if not total: continue
            weight=0.
            for d,value in zip(direction,delta):
                if abs(d): weight=abs(value)/total
            if weight>maximum: maximum=weight; selected=neighbor
        return selected or (neighbors[0] if neighbors else start)

    def smooth_original_face_flood(self,skin,vertices,influence_a,influence_b,iterations):
        """asSmoothFlood through the native paint context and native flood flag."""
        if not vertices or not iterations: return
        c=self._cmds; raw=getattr(c,"raw",c)
        skin_path=self.scene_address(skin)
        influences=raw.skinCluster(skin_path,query=True,influence=True) or []
        a=self.scene_address(influence_a)
        # Source locks other influences only when infB is nonempty. Empty B
        # deliberately smooths against every currently unlocked influence.
        if influence_b:
            b=self.scene_address(influence_b)
            ids=set(raw.ls((a,b),uuid=True) or [])
            for joint in influences:
                raw.setAttr(joint+".lockInfluenceWeights",not bool(ids & set(raw.ls(joint,uuid=True) or [])))
        raw.select(tuple(self.scene_address(v) for v in vertices),replace=True)
        try:
            original_skin_paint_context(raw,a)
            for _ in range(iterations): original_skin_paint_flood()
        finally:
            for joint in influences: raw.setAttr(joint+".lockInfluenceWeights",False)
            raw.setToolTo("selectSuperContext")

    def _jaw_mirror_layer(self):
        raw=getattr(self._cmds,"raw",self._cmds)
        raw.copySkinWeights(sourceSkin=self.scene_address("JawOpenLayerSC"),
            destinationSkin=self.scene_address("JawOpenLayerSC"),mirrorMode="YZ",mirrorInverse=True,
            surfaceAssociation="closestPoint",influenceAssociation="closestJoint")

    def hammer_original_face_weights(self,skin,vertices):
        """weightHammerVerts' native calls, including node max-influence policy.

        The installed Maya wrapper uses five iterations and then explicitly
        normalizes. ADV's asWeightHammerVertsMS has a different Fit policy.
        """
        if not vertices: return
        c=self._cmds; raw=getattr(c,"raw",c); path=self.scene_address(skin)
        raw.select(tuple(self.scene_address(v) for v in vertices),replace=True)
        obey=bool(raw.getAttr(path+".maintainMaxInfluences"))
        raw.skinCluster(path,edit=True,smoothWeights=0,smoothWeightsMaxIterations=5,
                        obeyMaxInfluences=obey)
        raw.skinCluster(path,edit=True,forceNormalizeWeights=True)
        raw.select(raw.ls(selection=True) or [],replace=True)

    def _jaw_bounds_selection(self,lower,upper,z_origin,z_radius=100):
        raw=getattr(self._cmds,"raw",self._cmds); mesh=self.scene_address("JawOpenLayer")
        raw.select(mesh,replace=True)
        raw.polySelectConstraint(mode=3,type=1,dist=3,distbound=(0,(upper-lower)/2),
            distpoint=(0,(upper+lower)/2,0),distaxis=(0,1,0))
        y=set(raw.ls(selection=True,long=True,flatten=True) or [])
        raw.select(mesh,replace=True)
        raw.polySelectConstraint(mode=3,type=1,dist=3,distbound=(0,z_radius),
            distpoint=(0,0,z_origin),distaxis=(0,0,1))
        z=set(raw.ls(selection=True,long=True,flatten=True) or [])
        raw.polySelectConstraint(mode=0)
        return y,z

    def update_original_jaw_curve_weights(self,source):
        """Complete asFaceUpdateJawCurvesWeights, including final layer transfers."""
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c); fit=self._fit(required=True)
        selection=tuple(raw.ls(selection=True,long=True) or []); time=c.currentTime(query=True)
        disabled=c.objExists("JawOpenLayerDeleteComponent")
        if disabled: c.setAttr("JawOpenLayerDeleteComponent.nodeState",1)
        temporary=[]
        def cast(vertices):
            return tuple(self.scene_address(v) for v in self._jaw_layer_cast(vertices))
        def weight(vertices,value):
            if vertices: raw.skinPercent(self.scene_address("JawOpenLayerSC"),tuple(vertices),
                                         transformValue=[(self.scene_address("JawJoint_M"),value)])
        try:
            c.currentTime(0)
            curve_vertices=cast(self.sample_original_face_curve_path("JawCurve",source.geometry))
            middle_vertices=cast(self.sample_original_face_curve_path("JawCurveMid",source.geometry))
            self._jaw_vertex_set("jawCurveVtxs",curve_vertices)
            weight(curve_vertices,1); weight(middle_vertices,.5)
            pivot=self._lip_pos("JawPivot")
            maximum=dist(pivot,self._lip_pos("Jaw"))
            for vertex in curve_vertices:
                distance=dist(pivot,raw.xform(vertex,query=True,worldSpace=True,translation=True))
                if distance<maximum/2: weight((vertex,),distance/maximum*2)
            endpoint=int(c.getAttr("upperLipOuterCurve.spans"))+1
            maximum=dist(pivot,self._lip_pos(f"upperLipOuterCurve.cv[{endpoint}]"))
            for vertex in middle_vertices:
                distance=dist(pivot,raw.xform(vertex,query=True,worldSpace=True,translation=True))
                if distance<maximum/2: weight((vertex,),distance/maximum)
            top=c.duplicate("JawCurveTop",name="JawCurveTopSampler",returnRootsOnly=True)[0]
            bottom=c.duplicate("JawCurveBottom",name="JawCurveBottomSampler",returnRootsOnly=True)[0]
            temporary.extend((top,bottom))
            c.move(0,top+".cv[0:6]",bottom+".cv[0:5]",x=True)
            c.move(0,-.001,0,bottom+".cv[5]",relative=True)
            jaw,throat=self._lip_pos("Jaw"),self._lip_pos("Throat")
            if jaw[1]<throat[1]:
                c.xform(bottom+".cv[5]",worldSpace=True,translation=(0,jaw[1],jaw[2]))
                point=self._lip_pos(bottom+".cv[4]")
                c.xform(bottom+".cv[4]",worldSpace=True,translation=(0,jaw[1]-source.face_scale/10,(jaw[2]+point[2])/2))
            locator=c.spaceLocator(name="samplerLocator")[0]
            top_loc=c.spaceLocator(name="samplerLocatorTop")[0]
            bottom_loc=c.spaceLocator(name="samplerLocatorBottom")[0]
            temporary.append(locator)
            c.parent(top_loc,bottom_loc,locator,absolute=True)
            c.geometryConstraint(top,top_loc,weight=1); c.pointConstraint(locator,top_loc)
            c.geometryConstraint(bottom,bottom_loc,weight=1); c.pointConstraint(locator,bottom_loc)
            top_bound=c.xform(top,query=True,worldSpace=True,boundingBox=True)
            bottom_bound=c.xform(bottom,query=True,worldSpace=True,boundingBox=True)
            # The original outer Y radius uses 1.99, not the ordinary 2.
            midpoint=(top_bound[4]+bottom_bound[1])/2
            width=(top_bound[4]-bottom_bound[1])/1.99
            y,z=self._jaw_bounds_selection(midpoint-width,midpoint+width,bottom_bound[2]-100)
            all_vertices=set(raw.ls(self.scene_address("JawOpenLayer")+".vtx[*]",long=True,flatten=True) or [])
            outside=all_vertices-(y-z)
            y,z=self._jaw_bounds_selection(bottom_bound[1],top_bound[1],bottom_bound[5]-100)
            inside=y-z
            y,_=self._jaw_bounds_selection(top_bound[1],top_bound[4],bottom_bound[5]-100)
            raw.select(self.scene_address("JawOpenLayer"),replace=True)
            raw.polySelectConstraint(mode=3,type=1,dist=3,
                distbound=(0,(bottom_bound[5]-bottom_bound[2])/2*1.001),
                distaxis=(0,0,1),distpoint=(0,0,(bottom_bound[5]+bottom_bound[2])/2))
            z=set(raw.ls(selection=True,long=True,flatten=True) or []); raw.polySelectConstraint(mode=0)
            boundary=(y|z)-outside
            selected=[]
            for vertex in sorted(boundary):
                c.xform(locator,worldSpace=True,translation=raw.xform(vertex,query=True,worldSpace=True,translation=True))
                if c.getAttr(top_loc+".ty")>0: selected.append(vertex)
            lip_area=set(self._jaw_set_members("lipAreaJawOpenLayer"))
            jaw_area=(set(selected)|inside)-lip_area
            self._jaw_vertex_set("jawArea",sorted(jaw_area))
            remaining=jaw_area-set(curve_vertices)-set(middle_vertices)
            if remaining:
                self.hammer_original_face_weights("JawOpenLayerSC",tuple(remaining))
                raw.copySkinWeights(mirrorMode="YZ",mirrorInverse=True,
                    surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            raw.copySkinWeights(sourceSkin=self.scene_address("JawOpenLayerSC"),
                destinationSkin=self.scene_address("JawCurveSC"),noMirror=True,
                surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            growth=int(c.getAttr(fit+".vtxsFromLipToNose")) if c.objExists(fit+".vtxsFromLipToNose") else 3
            outer=cast(self.sample_face_fit_vertices("upperLipOuterCurve",source.geometry))
            for vertex in outer:
                values=raw.skinPercent(self.scene_address("JawOpenLayerSC"),vertex,ignoreBelow=.001,query=True,value=True) or []
                if len(values)<2: continue
                # MEL intentionally uses the second returned weight here.
                initial=values[1]; current=vertex
                for step in range(growth):
                    current=self.pick_original_face_vertex_world(current,(0,1,0))
                    if current in lip_area: continue
                    weight((current,),initial-initial/growth*step)
            if not source.non_symmetrical: self._jaw_mirror_layer()
            c.currentTime(30)
            self.smooth_original_face_flood("JawOpenLayerSC",tuple(jaw_area-set(curve_vertices)),
                "FaceJoint_M","JawJoint_M",source.smooth_iterations)
            if not source.non_symmetrical: self._jaw_mirror_layer()
            if disabled: c.setAttr("JawOpenLayerDeleteComponent.nodeState",0)
            c.delete(temporary); temporary=[]
            c.skinPercent("JawLayerSC","JawLayer",transformValue=[("JawJoint_M",0)])
            # LipDeform has only the design SoftMod, never a Skin. Its sampled
            # weights were stored in JawOpenLayer by asFaceWeightLips above.
            # Maya 2024 rejects the MEL's implicit LipDeform -> JawLayer Skin
            # lookup. Address that sampled Skin explicitly, retaining the
            # source lip subset and closest-point/joint transfer.
            lip_members=self._jaw_set_members("lipArea")
            from_vertices=self._jaw_layer_cast(lip_members,"JawOpenLayer")
            to_vertices=self._jaw_layer_cast(lip_members,"JawLayer")
            raw.select(tuple(self.scene_address(v) for v in (*from_vertices,*to_vertices)),replace=True)
            raw.copySkinWeights(sourceSkin=self.scene_address("JawOpenLayerSC"),
                destinationSkin=self.scene_address("JawLayerSC"),noMirror=True,
                surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            falloff=cast(self._jaw_set_members("lipFalloffArea")) if c.objExists("lipFalloffArea") else ()
            self.hammer_original_face_weights("JawOpenLayerSC",falloff)
            geometry=self.scene_address(source.geometry)
            for parts in (source.lower_teeth,source.tongue):
                if parts and any("." in value for value in parts) and all(value.split(".",1)[0]==geometry for value in parts):
                    weight(cast(self._face_part_vertices(parts)),1)
            c.currentTime(0)
            if c.objExists("FaceFitLipMainLeft"):
                raw.select(tuple(all_vertices-set(cast(lip_members))),replace=True)
                raw.copySkinWeights(mirrorMode="YZ",mirrorInverse=True,
                    surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
            else: self._jaw_mirror_layer()
            self._transaction_changed=True
            return len(jaw_area)
        finally:
            raw.polySelectConstraint(mode=0)
            if temporary: c.delete(tuple(node for node in temporary if c.objExists(node)))
            if disabled: c.setAttr("JawOpenLayerDeleteComponent.nodeState",0)
            c.currentTime(time)
            raw.select(selection,replace=True) if selection else raw.select(clear=True)
