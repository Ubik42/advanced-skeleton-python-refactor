"""Original Face Cage triangles and Nose Region, source 35962–36478."""
from math import dist,floor
from adv_py.core.face_cage import CAGE_MARKERS,CAGE_CENTER_MARKERS

class MayaFaceCageGeometryMixin:
    def original_face_cage_facet(self,a,b,c_node):
        c=self._cmds
        if not all(c.objExists(node) for node in (a,b,c_node)): return None
        node=c.polyCreateFacet(name="asCageFacet",constructionHistory=False,
                              point=[self._lip_pos(x) for x in (a,b,c_node)])[0]
        if any(x.endswith("Left") for x in (a,b,c_node)):
            c.polyNormal(node,constructionHistory=False,normalMode=0,userNormalMode=0)
        return node

    def _cage_suggest_smooth_passes(self,source):
        if not source.has_below_eye: return 0
        c=self._cmds; raw=getattr(c,"raw",c)
        start=self.sample_face_fit_vertices("Cheek",source.geometry)[0]
        end=self.sample_face_fit_vertices("upperLipOuterCurve.cv[99]",source.geometry)[0]
        raw.select(self.scene_address(start),replace=True)
        for step in range(20):
            raw.polySelectConstraint(propagate=1,type=1)
            vertices=raw.ls(selection=True,long=True,flatten=True) or []
            if self.scene_address(end) in vertices: break
        else: step=20
        raw.select(clear=True)
        return 2 if step>10 else 1 if step>1 else 0

    def _cage_projected_controls(self,source):
        c=self._cmds; raw=getattr(c,"raw",c)
        stems=list(CAGE_MARKERS)
        if source.has_above_eye:
            stems.append("EyeBrowInner")
            stems.extend("EyeBrowMid"+str(i) for i in range(1,4) if c.objExists("EyeBrowMid"+str(i)))
            stems.append("EyeBrowOuter")
            if c.objExists("EyeBrowCenter"): stems.append("EyeBrowCenter")
        joints=[]; controls=[]
        c.createNode("transform",name="TempPos")
        try:
            for stem in stems:
                for side,suffix in (("_R",""),("_L","Left")):
                    if stem in CAGE_CENTER_MARKERS:
                        if side=="_L": continue
                        side="_M"
                    if not c.objExists(stem+suffix): continue
                    kind=2 if stem=="EyeBrowInner" else 1 if stem.startswith("EyeBrow") else 3
                    c.xform("TempPos",worldSpace=True,translation=self._lip_pos(stem+suffix))
                    control=self.create_original_face_pp("TempPos",stem,side,kind,create_joint=True)
                    if stem.startswith("EyeBrow"): c.scale(1.5,1.5,1.5,control+".cv[0:99]",relative=True,objectSpace=True)
                    controls.append(control); joints.append(stem+"Joint"+side)
            if source.has_below_eye:
                if source.has_above_eye:
                    index=int(c.getAttr("FaceFitForeHead.noseCvNr"))
                    position=self._lip_pos(f"ForeHeadCurve.cv[{index}]")
                else: position=self._cage_nose_crease_position(source)
                c.xform("TempPos",worldSpace=True,translation=position)
                controls.append(self.create_original_face_pp("TempPos","NoseCrease","_M",3,create_joint=True))
                joints.append("NoseCreaseJoint_M")
            joints.extend(("lowerLidOuterJoint_R","lowerLidOuterJoint_L"))
            if not source.simpler_eye_lid:
                c.parent("lowerLidOuterJoint_R","lowerLidOuterJoint_L","FaceJoint_M",absolute=True)
                for side in ("_R","_L"):
                    c.connectAttr("FaceJoint_M.worldInverseMatrix[0]","lowerLidOuterJointMM"+side+".matrixIn[2]",force=True)
                    c.xform("lowerLidOuterJoint"+side,objectSpace=True,translation=(0,0,0))
                    self.reset_original_face_joint_matrix_scale("lowerLidOuterJoint"+side)
        finally: c.delete("TempPos")
        if source.multi_skin_clusters:
            matrix=self.original_face_matrix_values(source.head+".worldMatrix[0]")
            for joint in joints:
                stem,side=joint.rsplit("_",1); mm=stem+"MM_"+side
                raw.connectAttr(self.scene_address(source.head)+".worldInverseMatrix[0]",
                                self.scene_address(mm)+".matrixIn[2]",force=True)
                c.setAttr(mm+".matrixIn[3]",*matrix,type="matrix")
                parent=(c.listRelatives(joint,parent=True) or [None])[0]
                c.connectAttr(parent+".worldInverseMatrix[0]",mm+".matrixIn[4]")
        return tuple(controls),tuple(joints)

    def _cage_nose_crease_position(self,source):
        c=self._cmds; raw=getattr(c,"raw",c)
        a=self.sample_face_fit_vertices("upperEyeLidOuterCurve.cv[0]",source.geometry)[0]
        b=self.sample_face_fit_vertices("upperEyeLidOuterCurveLeft.cv[0]",source.geometry)[0]
        path=self._lip_least_path(source.geometry,int(a.rsplit("[",1)[1][:-1]),int(b.rsplit("[",1)[1][:-1]))
        vertices=raw.ls(raw.polyListComponentConversion(path,toVertex=True),long=True,flatten=True) or [] if path else []
        if not vertices:
            position=self._lip_pos("upperEyeLidOuterCurve.cv[0]")
            locator=c.spaceLocator(name="TempLocator")[0]
            try:
                c.xform(locator,worldSpace=True,translation=(0,position[1],position[2]))
                vertices=[self.scene_address(self.sample_face_fit_vertices(locator,source.geometry)[0])]
            finally: c.delete(locator)
        return tuple(raw.xform(min(vertices,key=lambda v: abs(raw.xform(v,query=True,worldSpace=True,translation=True)[0])),
                               query=True,worldSpace=True,translation=True))

    def _cage_make_triangles(self,source):
        c=self._cmds; facet=self.original_face_cage_facet
        upper_lid=int(c.getAttr("upperEyeLidOuterCurve.spans"))
        lower_lid=int(c.getAttr("lowerEyeLidOuterCurve.spans"))
        upper_lip=int(c.getAttr("upperLipOuterCurve.spans")) if source.has_below_eye else 0
        lower_lip=int(c.getAttr("lowerLipOuterCurve.spans")) if source.has_below_eye else 0
        mid_count=max((i for i in range(1,4) if c.objExists("EyeBrowMid"+str(i))),default=0)
        top=inner=outer=side_cv=nose=0
        if source.has_above_eye:
            top=int(c.getAttr("FaceFitForeHead.topCvNr"))
        if source.has_below_eye:
            for side,suffix in (("_R",""),("_L","Left")):
                c.createNode("transform",name="CheekRaiser"+suffix,parent="FaceBuildInProgressHidden")
                c.xform("CheekRaiser"+suffix,worldSpace=True,translation=self._lip_pos("lowerLidOuter"+side))
        previous=""
        for suffix in ("","Left"):
            if source.has_above_eye:
                inner=int(c.getAttr("FaceFitForeHead"+suffix+".innerEyeCnrNr"))
                outer=int(c.getAttr("FaceFitForeHead"+suffix+".outerEyeCnrNr"))
                side_cv=int(c.getAttr("FaceFitForeHead"+suffix+".sideCvNr"))
                nose=int(c.getAttr("FaceFitForeHead"+suffix+".noseCvNr"))
            s=lambda stem: stem+suffix
            cv=lambda stem,index: s(stem)+f".cv[{int(index)}]"
            for a,b,d in (("SmileBulge","Cheek","FrownBulge"),("Cheek","SmileBulge","CheekBone"),
                          ("CheekRaiser","SmileBulge","NoseSide"),("NoseCorner","NoseSide","SmileBulge"),
                          ("SmileBulge","CheekRaiser","CheekBone"),("Cheek","CheekBone","JawPivot"),
                          ("Cheek","JawPivot","JawCorner"),("Cheek","JawCorner","JawLine"),
                          ("Cheek","JawLine","FrownBulge")):
                facet(s(a),s(b),s(d))
            facet(s("FrownBulge"),s("JawLine"),"Jaw")
            facet("Jaw","ChinCrease",s("FrownBulge"))
            facet(s("SmileBulge"),s("FrownBulge"),cv("upperLipOuterCurve",99))
            for i in range(lower_lip+1):
                target="ChinCrease" if i<lower_lip/2 else s("FrownBulge")
                facet(target,cv("lowerLipOuterCurve",i),cv("lowerLipOuterCurve",i+1))
            facet(s("FrownBulge"),"ChinCrease",cv("lowerLipOuterCurve",lower_lip/2))
            split1=floor(upper_lip*.3+.5); split2=floor(upper_lip*.6+.5)
            for i in range(upper_lip+1):
                target="NoseUnder" if i<split1 else s("NoseCorner") if i<split2 else s("SmileBulge")
                facet(cv("upperLipOuterCurve",i),target,cv("upperLipOuterCurve",i+1))
            facet(s("NoseCorner"),s("SmileBulge"),cv("upperLipOuterCurve",split2))
            facet(s("NoseCorner"),cv("upperLipOuterCurve",split1),"NoseUnder")
            for a,b,d in ((s("NoseCorner"),"NoseUnder",s("Nostril")),("NoseUnder","Nose",s("Nostril")),
                          (s("NoseSide"),s("NoseCorner"),s("Nostril")),(s("NoseSide"),s("Nostril"),"Nose"),
                          ("NoseBridge",s("NoseSide"),"Nose"),
                          (cv("lowerEyeLidOuterCurve",0),s("NoseSide"),"NoseBridge"),
                          (cv("lowerEyeLidOuterCurve",0),"NoseBridge",f"ForeHeadCurve.cv[{nose}]")):
                facet(a,b,d)
            nearest=c.createNode("nearestPointOnCurve",name="tempNearestPointOnCurve")
            try:
                c.connectAttr(s("lowerEyeLidOuterCurve")+".worldSpace[0]",nearest+".inputCurve",force=True)
                if source.has_below_eye: position=self._lip_pos(s("CheekRaiser"))
                else: position=self._lip_pos(cv("lowerEyeLidOuterCurve",0))
                c.setAttr(nearest+".inPosition",*position,type="float3")
                u=float(c.getAttr(nearest+".parameter"))
            finally: c.delete(nearest)
            for i in range(lower_lid+1):
                target=s("NoseSide") if i<u/2 else s("CheekRaiser") if i<u else s("CheekBone")
                facet(target,cv("lowerEyeLidOuterCurve",i),cv("lowerEyeLidOuterCurve",i+1))
            facet(s("CheekRaiser"),s("NoseSide"),cv("lowerEyeLidOuterCurve",u/2+1))
            facet(s("CheekBone"),s("CheekRaiser"),cv("lowerEyeLidOuterCurve",u+1))
            midway=side_cv+int((outer-side_cv)/2)
            facet(s("JawPivot"),cv("ForeHeadCurve",midway),cv("ForeHeadCurve",side_cv))
            facet(s("JawPivot"),s("CheekBone"),cv("ForeHeadCurve",midway))
            facet(cv("ForeHeadCurve",outer),cv("ForeHeadCurve",midway),s("CheekBone"))
            facet(f"ForeHeadCurve.cv[{nose}]","EyeBrowCenter",cv("upperEyeLidOuterCurve",0))
            facet("EyeBrowCenter",s("EyeBrowInner"),cv("upperEyeLidOuterCurve",0))
            fraction=upper_lid/(2+mid_count)
            for i in range(upper_lid+1):
                if i<fraction: target=s("EyeBrowInner")
                elif i<fraction*2 and c.objExists("EyeBrowMid1"): target=s("EyeBrowMid1")
                elif i<fraction*3 and c.objExists("EyeBrowMid2"): target=s("EyeBrowMid2")
                elif i<fraction*4 and c.objExists("EyeBrowMid3"): target=s("EyeBrowMid3")
                elif i<fraction*5: target=s("EyeBrowOuter")
                facet(cv("upperEyeLidOuterCurve",i),target,cv("upperEyeLidOuterCurve",i+1))
                if target!=previous and i>0: facet(previous,target,cv("upperEyeLidOuterCurve",i))
                previous=target
            top_curve="ForeHeadTopToSideCurve"+suffix
            if source.has_above_eye:
                c.curve(name=top_curve,degree=1,point=[self._lip_pos(cv("ForeHeadCurve",i)) for i in range(top,side_cv+1)])
                c.rebuildCurve(top_curve,constructionHistory=False,replaceOriginal=True,rebuildType=0,
                    endKnots=1,keepRange=0,keepControlPoints=False,keepEndPoints=False,keepTangents=False,
                    spans=4+mid_count,degree=1,tolerance=.01)
                c.parent(top_curve,"FaceBuildInProgressHidden",absolute=True)
            tcv=lambda index: top_curve+f".cv[{index}]"
            facet("EyeBrowCenter",tcv(0),s("EyeBrowInner"))
            facet(tcv(0),tcv(1),s("EyeBrowInner"))
            previous=s("EyeBrowInner"); number=1
            for i in range(1,mid_count+2):
                target=s("EyeBrowOuter") if i==mid_count+1 else s("EyeBrowMid"+str(i))
                facet(tcv(number),tcv(number+1),target); facet(tcv(number),target,previous)
                previous=target; number+=1
            facet(tcv(3+mid_count),tcv(4+mid_count),cv("ForeHeadCurve",midway))
            facet(tcv(2+mid_count),tcv(3+mid_count),s("EyeBrowOuter"))
            facet(tcv(3+mid_count),cv("ForeHeadCurve",midway),s("EyeBrowOuter"))
            facet(cv("ForeHeadCurve",midway),cv("ForeHeadCurve",outer),s("EyeBrowOuter"))

    def _cage_bind_geometry(self,source,joints,skin):
        c=self._cmds; raw=getattr(c,"raw",c)
        facets=c.ls("asCageFacet*",long=True,type="transform") or []
        cage=c.polyUnite(facets,constructionHistory=False,mergeUVSets=1,name="asCage")[0]
        c.polyMergeVertex(cage,constructionHistory=False,distance=source.face_scale/345.5418,alwaysMergeTwoVertices=True)
        c.polyNormal(cage,constructionHistory=False,normalMode=2,userNormalMode=0)
        c.sets(cage,edit=True,forceElement="asRedSG")
        self._cage_bind_layer("asCageSC",(source.head,*joints),cage)
        c.skinPercent("asCageSC",cage,transformValue=[(source.head,1)])
        for index in range(int(c.polyEvaluate(cage,vertex=True))):
            vertex=cage+f".vtx[{index}]"; position=self._lip_pos(vertex)
            for joint in joints:
                if dist(position,self._lip_pos(joint))<.01: c.skinPercent("asCageSC",vertex,transformValue=[(joint,1)])
        for joint in joints:
            if source.simpler_eye_lid and joint.startswith("lowerLidOuterJoint_"): continue
            raw.skinCluster(self.scene_address(skin),edit=True,dropoffRate=4,lockWeights=False,weight=0,
                            addInfluence=self.scene_address(joint))
        sampler=c.createNode("closestPointOnMesh",name="closestSampler")
        c.connectAttr(cage+".outMesh",sampler+".inMesh",force=True)
        samples={}
        try:
            for region,stem in (("lip","Lip"),("lid","EyeLid")):
                vertices=[]
                for suffix in ("","Left"):
                    for arc in ("upper","lower"):
                        curve=arc+stem+"OuterCurve"+suffix
                        if not c.objExists(curve): continue
                        for index in range(int(c.getAttr(curve+".spans"))+1):
                            c.setAttr(sampler+".inPosition",*self._lip_pos(curve+f".cv[{index}]"),type="float3")
                            vertices.append(cage+f".vtx[{int(c.getAttr(sampler+'.closestVertexIndex'))}]")
                samples[region]=vertices
        finally: c.delete(sampler)
        extra=c.listRelatives("LipJoints_M",allDescendents=True,type="joint") or [] if source.has_below_eye else []
        extra+=(["lowerLidOuterJoint_R","lowerLidOuterJoint_L"] if source.simpler_eye_lid else
                 c.listRelatives("EyeLidJoints_M",allDescendents=True,type="joint") or [])
        for joint in extra:
            if source.simpler_eye_lid and joint.startswith("lowerLidOuterJoint_"): continue
            c.skinCluster("asCageSC",edit=True,lockWeights=False,weight=0,addInfluence=joint)
        raw.select((self.scene_address(source.geometry)+".vtx[0:99999]",
                    *(self.scene_address(v) for v in samples["lid"])),replace=True)
        raw.copySkinWeights(noMirror=True,surfaceAssociation="closestPoint",influenceAssociation="closestJoint")
        c.select(clear=True); c.joint(name="cageOffJoint")
        c.parent("cageOffJoint","FaceBuildInProgressHidden",absolute=True)
        c.skinCluster("asCageSC",edit=True,lockWeights=False,weight=0,addInfluence="cageOffJoint")
        if samples["lip"]: c.skinPercent("asCageSC",samples["lip"],transformValue=[("cageOffJoint",1)])
        raw.skinCluster(self.scene_address(skin),edit=True,lockWeights=False,weight=0,addInfluence=self.scene_address("cageOffJoint"))
        c.sets(joints,name="asCageJoints"); c.sets("asCageJoints",add="FaceBuildingSets")

    def _cage_nose_region(self):
        c=self._cmds
        nose=self._lip_pos("Nose"); corner=self._lip_pos("NoseCorner")
        self.create_original_face_controller("NoseRegion","_M",4)
        c.delete("NoseRegionJoint_M")
        c.parent("NoseRegionOffset_M","SideReverse_M",absolute=True)
        c.setAttr("NoseRegionOffset_M.scale",1,1,1)
        c.scale(6,6,6,"NoseRegion_M.cv[0:7]",relative=True,pivot=(0,0,0))
        c.xform("NoseRegionOffset_M",worldSpace=True,translation=(0,nose[1],(nose[2]+corner[2])/2))
        point=self._lip_pos("NoseRegion_M.cv[1]")
        c.xform("NoseRegion_M.cv[1]",worldSpace=True,translation=(0,nose[1]-corner[0]*1.5,point[2]))
        point=self._lip_pos("NoseRegion_M.cv[5]"); under=self._lip_pos("NoseUnder")
        for index,x in ((5,0),(4,corner[0]/2),(6,corner[0]/-2)):
            c.xform(f"NoseRegion_M.cv[{index}]",worldSpace=True,translation=(x,under[1],point[2]))
        point=self._lip_pos("NoseRegion_M.cv[3]")
        for index,x,y in ((3,corner[0]*1.2,corner[1]+corner[0]/-5),
                          (7,corner[0]*-1.2,corner[1]+corner[0]/-5),
                          (2,corner[0]*.65,corner[1]+corner[0]/-2),
                          (0,corner[0]*-.65,corner[1]+corner[0]/-2)):
            c.xform(f"NoseRegion_M.cv[{index}]",worldSpace=True,translation=(x,y,point[2]))
        nodes=[stem+"Offset"+side for stem in ("Nostril","NoseSide","NoseCorner") for side in ("_R","_L")]
        nodes.extend(stem+"Offset_M" for stem in ("Nose","NoseUnder","NoseBridge"))
        c.parent(*nodes,"NoseRegion_M",absolute=True)
