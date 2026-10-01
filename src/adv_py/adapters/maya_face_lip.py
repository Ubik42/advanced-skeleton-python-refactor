"""ADV 6.925 asFaceLip scene port, source 34224–35658.

Build curves, ribbon, follicles, Sticky, topology weights, projected controls,
fleshy curves, roll/scale and lipsTogether are one ordered transaction.
"""
from __future__ import annotations
from math import dist
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_lip import FaceLipInput
from adv_py.core.face_lip_falloff import lip_control_letter
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_lip_falloff import MayaFaceLipFalloffHost

class MayaFaceLipHost(MayaFaceLipFalloffHost):
    def capture_lip_input(self):
        c=self._cmds
        if not c.objExists("upperLipMainCurve"): return None
        fit=self._fit(required=True)
        geometry=self.read_face_objects(FacePreRole.FACE)
        if len(geometry)!=1: raise FitSkeletonValidationError("Lip 需要唯一 Face 网格")
        head=c.getAttr(fit+".HeadJoint")
        heads=c.ls(head,long=True,type="joint") or []
        if len(heads)!=1: raise FitSkeletonValidationError("Lip Head 关节缺失或不唯一")
        required=("FaceJoint_M","FaceDeformationSystem","FaceAreas","FaceBuildingSets",
            "OnFacecontrols","SideReverse_R","SideReverse_L","SideReverse_M","ctrlLips_M",
            "ctrlBox","FaceControlOrient","allHeadCombinedLayer","FaceBuildInProgress","FaceBuildInProgressHidden",
            "LipInnerAreaMesh","Jaw","JawPivot","NoseUnder","FitEyeBall","upperEyeLidMainCurve")
        required+=tuple(arc+"Lip"+part+"Curve"+suffix for arc in ("upper","lower")
                         for part in ("Inner","Outer","Main") for suffix in ("","Left"))
        for name in required:
            if len(c.ls(name,long=True) or [])!=1:
                raise FitSkeletonValidationError("Lip 缺少原版前置节点："+name)
        def option(name): return bool(c.objExists(fit+"."+name) and c.getAttr(fit+"."+name))
        count=int(c.getAttr(fit+".LipCtrls",asString=True)) if c.objExists(fit+".LipCtrls") else 12
        if count<8 or count%4 or count//4>26: raise FitSkeletonValidationError("LipCtrls 数量无效")
        scale=float(c.getAttr(fit+".faceScale")); ctrl_scale=float(c.getAttr("OnFacecontrols.sx"))
        if scale<=0 or ctrl_scale<=0: raise FitSkeletonValidationError("Lip 缩放必须为正")
        return FaceLipInput(geometry[0],heads[0],self.face_skin_cluster(geometry[0]),scale,
            ctrl_scale,count,option("MultiSkinClusters"),option("NonSym"),
            option("LongSnout"),option("LegacyFaceJointOrient"))

    def _lip_pos(self,node):
        return tuple(self._cmds.xform(node,query=True,worldSpace=True,translation=True))

    def _lip_vector(self,plug): return tuple(self._cmds.getAttr(plug)[0])

    def _lip_cv_count(self,curve):
        return int(self._cmds.getAttr(curve+".spans"))+int(self._cmds.getAttr(curve+".degree"))

    def _lip_last_cv(self,curve): return curve+f".cv[{self._lip_cv_count(curve)-1}]"

    def _lip_node(self,kind,name,parent=None):
        return self._cmds.createNode(kind,name=name,**({"parent":parent} if parent else {}))

    def _lip_skin(self,name,joints,geometry,maximum=3):
        return self._cmds.skinCluster((*joints,geometry),name=name,toSelectedBones=True,
            maximumInfluences=maximum,dropoffRate=4,removeUnusedInfluence=False)[0]

    def _lip_ordered_vertices(self,curve,geometry):
        c=self._cmds; raw=getattr(c,"raw",c)
        vertices=self.sample_face_fit_vertices(curve,geometry)
        allowed=set(raw.ls([self.scene_address(v) for v in vertices],long=True,flatten=True) or [])
        if not allowed: raise FitSkeletonValidationError("Lip Fit 曲线未映射到顶点："+curve)
        current=raw.ls(self.scene_address(vertices[0]),long=True,flatten=True) or []
        result=[]; completed=set()
        for _ in range(len(allowed)):
            if not current: continue
            completed.update(current)
            result.append(tuple(raw.xform(current,query=True,worldSpace=True,translation=True)[:3]))
            edges=raw.polyListComponentConversion(current,toEdge=True)
            neighbors=raw.ls(raw.polyListComponentConversion(edges,toVertex=True),long=True,flatten=True) or []
            current=[v for v in neighbors if v in allowed and v not in completed]
        if len(result)<2: raise FitSkeletonValidationError("Lip 拓扑路径不足两个顶点："+curve)
        return result

    def create_lip_rig(self,source):
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        self._transaction_changed=True
        self.finish_original_face_fit_stage("EyeWide","ctrlEye","_RL","wide",10,
                                            ("ctrlBoxEye_R","ctrlBoxEye_L"))
        self.hide_original_face_controllers(True)
        c.setAttr("ctrlBox.RegionsCtrlVis",False)
        # asFaceLip finishes EyeWide before the optional lower-face guard.
        if source is None:
            return None
        skin=source.skin; head=source.head
        if source.multi_skin_clusters:
            head=self._lip_node("joint","MultiSkinClustersFaceLipJoint_M","FaceJoint_M")
            c.setAttr(head+".drawStyle",2)
            c.setAttr(head+".inheritsTransform",False,lock=True)
            skin=raw.skinCluster(self.scene_address(head),self.scene_address(source.geometry),
                multi=True,frontOfChain=True,toSelectedBones=True,name=self.scene_address("LipSC"))[0]
            skin="LipSC"
        area=self.sample_face_fit_vertices("LipInnerAreaMesh",source.geometry)
        c.sets(empty=True,name="lipArea"); c.sets("lipArea",add="FaceAreas")
        raw.sets([self.scene_address(v) for v in area],add=self.scene_address("lipArea"))
        self._lip_node("transform","LipSetup","FaceDeformationSystem")
        for name in ("LipRibbon","LipFollicles","LipRibbonJoints","LipRibbonLocs",
                     "LipRibbonFleshy","LipRibbonFleshyJoints","LipSlider","LipFollowHead"):
            self._lip_node("transform",name,"LipSetup")
        self.constrain_original_face(source.head,"LipFollowHead")
        self._lip_node("transform","LipFollowHeadConstrained")
        c.parent("LipRibbonJoints","LipFollicles","LipFollowHeadConstrained","LipFollowHead",absolute=True)
        self._lip_node("transform","LipConstruction")
        self._lip_node("joint","LipJoints_M","FaceJoint_M")
        c.setAttr("LipJoints_M.segmentScaleCompensate",False); c.setAttr("LipJoints_M.drawStyle",2)
        a,b=self._lip_pos("upperLipOuterCurve.cv[0]"),self._lip_pos("lowerLipOuterCurve.cv[0]")
        c.xform("LipJoints_M",worldSpace=True,translation=(0,(a[1]+b[1])/2,max(a[2],b[2])))
        for action in ("Press","Squeeze","Roll","Pucker"):
            for arc in ("upper","lower"):
                attr=arc+action
                c.addAttr("ctrlLips_M",longName=attr,attributeType="double",keyable=True,
                          softMaxValue=10,softMinValue=-10)
                self.original_face_output_bw("ctrlLips_M."+attr)
        self._lip_region(source)
        counts=self._lip_build_curves(source)
        self._lip_slide_surface(source)
        shaped=self._lip_ribbon_curves(counts)
        self._lip_ribbons(source)
        self._lip_follicles(counts)
        self._lip_topology_weights(source,skin,head,counts,area)
        controls=self._lip_red_controls(source,shaped)
        controls+=self._lip_green_controls(source)
        self._lip_fleshy(source)
        self._lip_roll_scale(source,counts)
        self._lip_expression_keys(source)
        for side in ("_R","_L"):
            c.rename(f"upperLipJoint{counts['upper']-1}"+side,"cornerLipJoint"+side)
        c.parent("upperLipOffset_M","lowerLipOffset_M","LipOffset_R","LipOffset_L","LipRegion_M",absolute=True)
        c.rename("FaceControlOrient","FaceControlOrientLip")
        c.rename("FaceControlSuspended","FaceControlOrient")
        self._lip_together(source)
        main=[]
        for arc in ("upper","lower"):
            for suffix in ("","Left"): main.extend(self.sample_face_fit_vertices(arc+"LipMainCurve"+suffix,source.geometry))
        c.sets(empty=True,name="lipMainArea"); c.sets("lipMainArea",add="FaceAreas")
        raw.sets([self.scene_address(v) for v in main],add=self.scene_address("lipMainArea"))
        c.delete("LipConstruction")
        c.setAttr("ctrlBoxLips_M.visibility",True)
        for attr in ("tx","ty"): c.setAttr("ctrlLips_M."+attr,lock=True,keyable=False)
        return {"skin":skin,"controls":tuple(controls)+( "LipRegion_M",),"joint_counts":counts}

    def _lip_region(self,source):
        c=self._cmds
        a,b=self._lip_pos("upperLipMainCurve.cv[0]"),self._lip_pos("lowerLipMainCurve.cv[0]")
        self.create_original_face_controller("LipRegion","_M",4)
        c.delete("LipRegionJoint_M")
        c.parent("LipRegionOffset_M","SideReverse_M",absolute=True)
        c.setAttr("LipRegionOffset_M.scale",1,1,1)
        c.scale(6,6,6,"LipRegion_M.cv[0:7]",relative=True,pivot=(0,0,0))
        c.xform("LipRegionOffset_M",worldSpace=True,translation=(0,(a[1]+b[1])/2,(a[2]+b[2])/2))
        c.move(0,0,source.face_scale/25,"LipRegion_M.cv[*]",relative=True)
        for arc,indices,mirror in (("upper",(1,2),0),("lower",(5,4),6)):
            y=self._lip_pos(arc+"LipOuterCurve.cv[0]")[1]
            for index in indices:
                x,_,z=self._lip_pos(f"LipRegion_M.cv[{index}]")
                c.xform(f"LipRegion_M.cv[{index}]",worldSpace=True,translation=(x,y,z))
            c.xform(f"LipRegion_M.cv[{mirror}]",worldSpace=True,translation=(-x,y,z))
        for index,suffix in ((3,""),(7,"Left")):
            _,_,z=self._lip_pos(f"LipRegion_M.cv[{index}]")
            x,y,_=self._lip_pos(self._lip_last_cv("upperLipOuterCurve"+suffix))
            c.xform(f"LipRegion_M.cv[{index}]",worldSpace=True,translation=(x*1.2,y,z))

    def _lip_build_curves(self,source):
        c=self._cmds; counts={}
        motion=self._lip_node("motionPath","lipOrientMotionTemp#")
        transform=self._lip_node("transform","lipOrientTransformTemp#")
        c.connectAttr(motion+".allCoordinates",transform+".translate")
        c.connectAttr(motion+".rotate",transform+".rotate")
        for attr,value in (("fractionMode",False),("worldUpType",0),("frontAxis",0),("upAxis",1)):
            c.setAttr(motion+"."+attr,value)
        for side,suffix in (("_R",""),("_L","Left")):
            c.setAttr(motion+".inverseFront",side=="_R")
            for arc in ("upper","lower"):
                for part in ("Inner","Outer","Main"):
                    name=arc+"Lip"+part+"BuildCurve"+suffix
                    curve=c.curve(name=name,degree=1,point=self._lip_ordered_vertices(
                        arc+"Lip"+part+"Curve"+suffix,source.geometry))
                    c.parent(curve,"LipConstruction",absolute=True)
                curve=arc+"LipMainBuildCurve"+suffix
                count=self._lip_cv_count(curve)
                counts[arc]=count
                for index in range(count):
                    joint=f"{arc}LipJoint{index}"+side
                    self._lip_node("joint",joint,"LipJoints_M")
                    c.setAttr(joint+".segmentScaleCompensate",False); c.setAttr(joint+".radius",.1)
                    c.xform(joint,worldSpace=True,translation=self._lip_pos(curve+f".cv[{index}]"))
                rebuilt=c.duplicate(arc+"LipMainCurve"+suffix,name="lipOrientCurveTemp#",returnRootsOnly=True)[0]
                c.rebuildCurve(rebuilt,constructionHistory=False,replaceOriginal=True,rebuildType=0,
                    endKnots=1,keepRange=1,keepControlPoints=True,keepEndPoints=True,degree=3,tolerance=.01)
                c.connectAttr(rebuilt+".worldSpace[0]",motion+".geometryPath",force=True)
                for index in range(1,count):
                    c.setAttr(motion+".uValue",index if index==count-1 else index-1)
                    c.setAttr(f"{arc}LipJoint{index}"+side+".ry",c.getAttr(transform+".ry"))
                c.delete(rebuilt)
        c.delete(motion,transform)
        for arc in ("upper","lower"):
            c.rename(arc+"LipJoint0_R",arc+"LipJoint0_M"); c.delete(arc+"LipJoint0_L")
        for side in ("_R","_L"): c.delete(f"lowerLipJoint{counts['lower']-1}"+side)
        return counts

    def _lip_slide_surface(self,source):
        c=self._cmds
        jaw=self._lip_pos("JawPivot"); mid=self._lip_pos("upperLipMainCurve.cv[0]")
        a,b=self._lip_pos("FitEyeBall"),self._lip_pos(self._lip_last_cv("upperEyeLidMainCurve"))
        eye=tuple((x+y)/2 for x,y in zip(a,b)); nose=self._lip_pos("NoseUnder")
        c.nurbsPlane(name="lipSlideSurface",axis=(0,0,1),width=1,lengthRatio=1,
                     degree=3,patchesU=2,patchesV=4,constructionHistory=False)
        all_cvs="lipSlideSurface.cv[*][*]"
        c.rotate(0,0,-90,all_cvs,relative=True,objectSpace=True,pivot=(0,0,0))
        factor=(nose[1]-mid[1])*2
        c.scale(factor,factor,factor,all_cvs,relative=True)
        c.move(*mid,all_cvs,relative=True)
        factor=(eye[1]-mid[1])/(self._lip_pos("lipSlideSurface.cv[0][0]")[1]-mid[1])
        for row,multiplier in ((0,1),(1,.85)):
            c.scale(1,factor*multiplier,1,f"lipSlideSurface.cv[0:4][{row}]",relative=True,pivot=mid)
        for u in range(5):
            _,y,_=self._lip_pos(f"lipSlideSurface.cv[{u}][0]")
            c.xform(f"lipSlideSurface.cv[{u}][0]",worldSpace=True,translation=(eye[0],y,eye[2]))
        a=self._lip_pos("lipSlideSurface.cv[2][0]")
        center=((jaw[0]+a[0])/2,mid[1],(jaw[2]+a[2])/2)
        c.xform("lipSlideSurface.cv[2][0]",worldSpace=True,translation=center)
        for u in (1,3):
            a=self._lip_pos(f"lipSlideSurface.cv[{u}][0]")
            c.xform(f"lipSlideSurface.cv[{u}][0]",worldSpace=True,
                    translation=((center[0]+a[0])/2,a[1],(center[2]+a[2])/2))
        motion=self._lip_node("motionPath","lipSlideMotionTemp#")
        c.connectAttr("upperLipMainBuildCurve.worldSpace[0]",motion+".geometryPath")
        c.setAttr(motion+".fractionMode",True)
        for parameter,row in ((.25,2),(.75,1)):
            c.setAttr(motion+".uValue",parameter)
            a=self._lip_vector(motion+".allCoordinates")
            for u in range(5):
                _,y,_=self._lip_pos(f"lipSlideSurface.cv[{u}][{row}]")
                c.xform(f"lipSlideSurface.cv[{u}][{row}]",worldSpace=True,translation=(a[0],y,a[2]))
        c.delete(motion)
        for u in range(5):
            for v in range(3):
                x,y,z=self._lip_pos(f"lipSlideSurface.cv[{u}][{v}]")
                c.xform(f"lipSlideSurface.cv[{u}][{6-v}]",worldSpace=True,translation=(-x,y,z))
        temp=self._lip_node("transform","lipSlideAlignTemp#")
        target=self._lip_pos(self._lip_last_cv("upperLipMainCurve")); previous=99.
        rows=[f"lipSlideSurface.cv[{u}][{v}]" for u in range(5) for v in (1,5)]
        c.xform(temp,worldSpace=True,translation=target)
        for index in range(99):
            constraint=c.geometryConstraint("lipSlideSurface",temp)
            distance=dist(target,self._lip_pos(temp))
            if distance>previous: break
            previous=distance; c.delete(constraint)
            c.xform(temp,worldSpace=True,translation=target)
            c.scale(1.05,1,1,*rows,relative=True,pivot=(0,0,0))
        else: c.scale(.00766,1,1,*rows,relative=True,pivot=(0,0,0))
        a,b=self._lip_pos("lipSlideSurface.cv[2][1]"),self._lip_pos("lipSlideSurface.cv[2][0]")
        if a[0]<b[0]:
            c.scale(a[0]/b[0]*1.2,1,1,"lipSlideSurface.cv[0:4][0]","lipSlideSurface.cv[0:4][6]",
                    relative=True,pivot=(0,0,0))
        c.delete(temp)
        c.parent("lipSlideSurface","LipSlider",absolute=True)
        self._lip_skin("lipSlideSurfaceSC",("FaceJoint_M",),"lipSlideSurface")
        c.setAttr("lipSlideSurface.visibility",False)
        c.rename("FaceControlOrient","FaceControlSuspended")
        c.duplicate("lipSlideSurface",name="FaceControlOrient",returnRootsOnly=True)
        c.sets("FaceControlOrient",edit=True,forceElement="asRedSG")
        c.parent("FaceControlOrient","FaceBuildInProgressHidden",absolute=True)

    def _lip_ribbon_curves(self,counts):
        c=self._cmds; shaped={}
        for arc in ("upper","lower"):
            joints=[]
            for side,indices in (("_L",range(counts[arc]-1,0,-1)),("_M",(0,)),("_R",range(1,counts[arc]))):
                for index in indices:
                    joint=f"{arc}LipJoint{index}"+side
                    if not c.objExists(joint): joint=f"upperLipJoint{counts['upper']-1}"+side
                    joints.append(joint)
            curve=arc+"LipRibbonCurve"
            c.curve(name=curve,degree=3,point=[self._lip_pos(joint) for joint in joints])
            c.reverseCurve(curve,constructionHistory=False,replaceOriginal=True)
            influences=c.ls(arc+"LipJoint*_*",type="joint") or []
            if arc=="lower": influences+= [f"upperLipJoint{counts['upper']-1}"+side for side in ("_R","_L")]
            self._lip_skin(curve+"SC",influences,curve)
            a=c.duplicate(arc+"LipMainBuildCurve",name=arc+"LipMainBuildCurveShaped",returnRootsOnly=True)[0]
            b=c.duplicate(arc+"LipMainBuildCurveLeft",name=arc+"LipMainBuildCurveShapedLeft",returnRootsOnly=True)[0]
            c.attachCurve(a,b,constructionHistory=False,replaceOriginal=True,keepMultipleKnots=True,
                          method=0,blendBias=.5,blendKnotInsertion=False,parameter=.1)
            a=c.rename(a,arc+"LipRibbonCurveShaped"); c.delete(b); c.parent(a,world=True)
            c.rebuildCurve(a,constructionHistory=False,replaceOriginal=True,rebuildType=0,
                endKnots=1,keepRange=0,keepControlPoints=True,keepEndPoints=True,degree=3,tolerance=.01)
            result=c.rebuildCurve(a,constructionHistory=True,replaceOriginal=False,rebuildType=0,
                endKnots=1,keepRange=0,keepControlPoints=False,keepEndPoints=False,spans=0,degree=3,tolerance=.01)
            shaped[arc]=(a,result[0])
        return shaped

    def _lip_ribbons(self,source):
        c=self._cmds
        a,b=self._lip_pos("upperLipMainCurve.cv[0]"),self._lip_pos(self._lip_last_cv("upperLipMainCurve"))
        profile=c.curve(name="lipLoftProfileTemp#",degree=1,point=((b[0],a[1],b[2]),(0,a[1],a[2]),(-b[0],a[1],b[2])))
        c.rebuildCurve(profile,constructionHistory=False,replaceOriginal=True,rebuildType=0,
            endKnots=1,keepRange=0,keepControlPoints=False,keepEndPoints=True,spans=5,degree=3,tolerance=.01)
        distance=a[2]-b[2]
        for indices,factor,divisor in (((1,6),1.06,20),((2,5),1.2,4)):
            cvs=[profile+f".cv[{i}]" for i in indices]
            c.scale(factor,1,factor,*cvs,relative=True,pivot=(0,b[1],b[2]))
            c.move(0,0,distance/divisor,*cvs,relative=True,objectSpace=True,worldSpaceDistance=True)
        c.extrude(profile,name="upperLipRibbon",constructionHistory=False,range=False,polygon=0,
                  extrudeType=0,useProfileNormal=False,direction=(0,1,0),length=source.face_scale/200,
                  rotation=0,scale=1,degreeAlongLength=3)
        c.delete(profile)
        cluster,handle=c.cluster("upperLipRibbon",name="anglerCluster",envelope=1)
        handle=c.rename(handle,"anglerClusterHandle")
        c.xform(handle,pivots=(0,a[1],a[2]))
        temp=self._lip_node("transform","lipRibbonAngleTemp#")
        c.xform(temp,pivots=(0,b[1],b[2]))
        c.delete(c.aimConstraint(temp,handle,aimVector=(0,0,-1),upVector=(1,0,0),
            worldUpType="vector",worldUpVector=(1,0,0)))
        point=self._lip_pos("upperLipRibbon.cv[0][0]")
        c.setAttr(handle+".sz",(a[2]-b[2])/(a[2]-point[2]))
        c.delete("upperLipRibbon",constructionHistory=True); c.delete(temp)
        if c.objExists(handle): c.delete(handle)
        if source.control_count!=12:
            c.rebuildSurface("upperLipRibbon",constructionHistory=False,replaceOriginal=True,
                rebuildType=0,endKnots=1,keepRange=0,keepControlPoints=False,keepCorners=False,
                spansU=source.ribbon_spans,degreeU=3,spansV=0,degreeV=1,tolerance=.01,
                fitRebuild=False,direction=2)
        c.duplicate("upperLipRibbon",name="lowerLipRibbon",returnRootsOnly=True)
        c.move(0,-source.face_scale/200,0,"lowerLipRibbon.cv[*][*]",relative=True,
               objectSpace=True,worldSpaceDistance=True)
        c.xform("LipFollicles",worldSpace=True,translation=self._lip_pos("LipJoints_M"))

    def _lip_follicles(self,counts):
        c=self._cmds
        sampler=self._lip_node("closestPointOnSurface","lipFollicleSamplerTemp#")
        for side in ("_R","_L"):
            temp=self._lip_node("transform","PlaceHolderStickyLip"+side)
            c.addAttr(temp,longName="sticky",attributeType="double",keyable=True,minValue=0,maxValue=10)
        for arc in ("upper","lower"):
            c.connectAttr(arc+"LipRibbon.worldSpace[0]",sampler+".inputSurface",force=True)
            for lateral in ("_R","_L"):
                for index in range(counts[arc]):
                    side="_M" if index==0 else lateral
                    if index==0 and lateral=="_L" or arc=="lower" and index==counts[arc]-1: continue
                    joint=f"{arc}LipJoint{index}"+side
                    transform=self._lip_node("transform",f"{arc}follicle{index}"+side,"LipFollicles")
                    shape=self._lip_node("follicle",f"{arc}follicle{index}"+side+"Shape",transform)
                    c.setAttr(shape+".collide",False)
                    c.connectAttr(arc+"LipRibbon.local",shape+".inputSurface")
                    c.connectAttr("LipFollicles.worldInverseMatrix[0]",shape+".inputWorldMatrix")
                    c.connectAttr(shape+".outTranslate",transform+".translate")
                    c.connectAttr(shape+".outRotate",transform+".rotate")
                    c.setAttr(sampler+".inPosition",*self._lip_pos(joint))
                    u=float(c.getAttr(sampler+".parameterU"))
                    c.setAttr(shape+".parameterU",u); c.setAttr(shape+".parameterV",.5)
                    plus=self._lip_node("plusMinusAverage",f"{arc}LipPMA{index}"+side)
                    c.connectAttr(transform+".translate",plus+".input3D[0]")
                    a,b=self._lip_vector(transform+".translate"),self._lip_vector(joint+".translate")
                    c.setAttr(plus+".input3D[1]",*(y-x for x,y in zip(a,b)))
                    blend=self._lip_node("blendColors",f"{arc}LipBC{index}"+side)
                    c.setAttr(blend+".blender",1)
                    c.connectAttr(plus+".output3D",blend+".color1"); c.connectAttr(plus+".output3D",blend+".color2")
                    if arc=="lower":
                        if c.objExists(f"upperLipBC{index}"+side):
                            c.connectAttr(plus+".output3D",f"upperLipBC{index}"+side+".color2",force=True)
                        if c.objExists(f"upperLipPMA{index}"+side):
                            c.connectAttr(f"upperLipPMA{index}"+side+".output3D",blend+".color2",force=True)
                    for rgb,xyz in zip("RGB","xyz"): c.connectAttr(blend+".output"+rgb,joint+".t"+xyz)
                    sr=self._lip_node("setRange",f"{arc}LipSR{index}"+side)
                    for attr,value in (("min",(1,1,0)),("max",(.5,.5,0)),
                        ("oldMin",(u*8,10-(u*8+2),0)),("oldMax",(u*8+2,10-u*8,0))):
                        c.setAttr(sr+"."+attr,*value)
                    c.connectAttr("PlaceHolderStickyLip_R.sticky",sr+".valueX")
                    c.connectAttr("PlaceHolderStickyLip_L.sticky",sr+".valueY")
                    multiply=self._lip_node("multDoubleLinear",f"{arc}LipMDL{index}"+side)
                    c.connectAttr(sr+".outValueX",multiply+".input1"); c.connectAttr(sr+".outValueY",multiply+".input2")
                    clamp=self._lip_node("clamp",f"{arc}LipClamp{index}"+side)
                    c.setAttr(clamp+".minR",.5); c.setAttr(clamp+".maxR",1)
                    c.connectAttr(multiply+".output",clamp+".inputR"); c.connectAttr(clamp+".outputR",blend+".blender")
        for side in ("_R","_L"):
            for index in range(1,counts['upper']):
                if not c.objExists(f"lowerLipJoint{index}"+side):
                    c.connectAttr(f"lowerLipPMA{counts['lower']-2}"+side+".output3D",
                                  f"upperLipBC{index}"+side+".color2",force=True)
        c.delete(sampler)

    def _lip_least_path(self,geometry,start,end):
        """asSelectLeastEdgesPath: loop/ring preference, shortest-edge fallback."""
        from .maya_face_topology import original_face_least_edges
        raw=getattr(self._cmds,"raw",self._cmds)
        edges=original_face_least_edges(self,geometry,start,end)
        return tuple(raw.ls(raw.polyListComponentConversion(edges,toVertex=True),long=True,flatten=True) or []) if edges else ()

    def _lip_topology_weights(self,source,skin,head,counts,area):
        c=self._cmds; raw=getattr(c,"raw",c); skin_path=self.scene_address(skin)
        joints=[joint for joint in c.listRelatives("FaceJoint_M",allDescendents=True,type="joint") or []
                if "Lip" in joint and joint.rsplit("|",1)[-1]!="MultiSkinClustersFaceLipJoint_M"]
        if joints:
            raw.skinCluster(skin_path,edit=True,addInfluence=[self.scene_address(j) for j in joints],
                dropoffRate=4,lockWeights=True,weight=0)
            for joint in joints: c.setAttr(joint+".lockInfluenceWeights",False)
        sampler=self._lip_node("closestPointOnMesh","lipWeightSamplerTemp#")
        raw.connectAttr(self.scene_address(source.geometry)+".outMesh",self.scene_address(sampler)+".inMesh")
        for arc in ("upper","lower"):
            for lateral,suffix in (("_R",""),("_L","Left")):
                indices={}
                for part in ("Inner","Outer","Main"):
                    indices[part]={}
                    for index in range(counts[arc]):
                        side="_M" if index==0 else lateral
                        if index==0 and lateral=="_L" or arc=="lower" and index==counts[arc]-1: continue
                        curve=arc+"Lip"+part+"BuildCurve"+suffix
                        # MEL's cv[99] boundary behavior is made explicit here.
                        cv=min(index,self._lip_cv_count(curve)-1)
                        position=self._lip_pos(curve+f".cv[{cv}]")
                        c.setAttr(sampler+".inPosition",*position)
                        nearest=int(c.getAttr(sampler+".closestVertexIndex"))
                        indices[part][index]=nearest
                        raw.skinPercent(skin_path,self.scene_address(source.geometry)+f".vtx[{nearest}]",
                            transformValue=[(self.scene_address(f"{arc}LipJoint{index}"+side),1)])
                for index in indices['Main']:
                    side="_M" if index==0 else lateral
                    for part in ("Outer","Inner"):
                        vertices=self._lip_least_path(source.geometry,indices[part][index],indices['Main'][index])
                        if vertices:
                            raw.skinPercent(skin_path,vertices,transformValue=[(
                                self.scene_address(f"{arc}LipJoint{index}"+side),1)])
        c.delete(sampler)
        remaining=[]
        for vertex in area:
            weight=raw.skinPercent(skin_path,self.scene_address(vertex),query=True,
                transform=self.scene_address(head))
            if float(weight)>=1: remaining.append(vertex)
        self._lip_falloff_hammer(skin,remaining,5)

    def _lip_red_controls(self,source,shaped):
        c=self._cmds; controls=[]
        nearest=self._lip_node("nearestPointOnCurve","lipControlCurveSamplerTemp#")
        surface=self._lip_node("closestPointOnSurface","lipControlSurfaceSamplerTemp#")
        for arc,factor in (("upper",1),("lower",-1)):
            ribbon=arc+"LipRibbon"; curve=arc+"LipRibbonCurve"
            c.connectAttr(curve+".worldSpace[0]",nearest+".inputCurve",force=True)
            # Keep the active 6.925 shaped-curve sampling branch, despite the
            # MEL comment claiming it was removed in an earlier version.
            extrusion=c.extrude(shaped[arc][1],name="lipControlSurfaceTemp#",constructionHistory=False,
                range=False,polygon=0,extrudeType=0,useProfileNormal=True,
                length=source.face_scale/100,rotation=0,scale=1,degreeAlongLength=3)[0]
            c.connectAttr(extrusion+".worldSpace[0]",surface+".inputSurface",force=True)
            for side in ("_R","_L"):
                u=source.ribbon_spans//2+(2 if side=="_R" else 1)
                for index in range(source.end+1):
                    u+=-1 if side=="_R" else 1
                    if arc=="lower" and index==source.end: continue
                    name="cornerLip" if index==source.end else arc+"Lip"+lip_control_letter(index)
                    position=self._lip_pos(ribbon+f".cv[{u}][1]")
                    c.setAttr(surface+".inPosition",*position)
                    parameter=float(c.getAttr(surface+".parameterU"))
                    poci=self._lip_node("pointOnCurveInfo",name+"POCI"+side)
                    c.connectAttr(shaped[arc][1]+".worldSpace[0]",poci+".inputCurve")
                    c.setAttr(poci+".turnOnPercentage",True); c.setAttr(poci+".parameter",parameter)
                    position=self._lip_vector(poci+".position")
                    distance=source.control_scale*.2*factor
                    if index==source.end-1: distance/=2
                    if index==source.end: distance=0
                    alignment=(position[0],position[1]+distance,position[2])
                    control=self.create_original_face_pp(alignment,name,side,1,create_joint=True,
                        attach=True,legacy_orient=source.legacy_orient)
                    controls.append(control)
                    c.move(0,-distance,0,name+"Offset"+side,name+"JointOffset"+side,
                        relative=True,objectSpace=True,worldSpaceDistance=True)
                    c.setAttr(name+"Joint"+side+".radius",.25)
                    c.addAttr(control,longName="parameterOnUniform",attributeType="double",defaultValue=parameter)
                    loc=self._lip_node("transform",name+"Loc"+side,"LipRibbonLocs")
                    c.connectAttr(poci+".position",loc+".translate")
                    c.connectAttr(curve+".worldSpace[0]",poci+".inputCurve",force=True)
                    c.setAttr(nearest+".inPosition",*position)
                    c.setAttr(poci+".turnOnPercentage",False)
                    c.setAttr(poci+".parameter",c.getAttr(nearest+".parameter"))
                    self.constrain_original_face(loc,name+"Attach"+side,opm=False,pick=True)
                    pick=name+"AttachPM"+side; dm=name+"AttachDM"+side
                    for attr in ("useRotate","useScale","useShear"): c.setAttr(pick+"."+attr,False)
                    for axis,xyz,shear in zip("XYZ","xyz",("xy","xz","yz")):
                        for output,attr in (("Rotate","r"+xyz),("Scale","s"+xyz),("Shear","sh"+shear)):
                            source_plug=dm+".output"+output+axis; dest=name+"Attach"+side+"."+attr
                            if c.isConnected(source_plug,dest): c.disconnectAttr(source_plug,dest)
                    plus=self._lip_node("plusMinusAverage",name+"OffsetPMA"+side)
                    c.setAttr(plus+".operation",2)
                    c.connectAttr(dm+".outputTranslate",plus+".input3D[0]")
                    c.setAttr(plus+".input3D[1]",*self._lip_vector(plus+".input3D[0]"))
                    for xyz in "xyz":
                        c.connectAttr(plus+".output3D"+xyz,name+"Attach"+side+".t"+xyz,force=True)
                    if source.multi_skin_clusters:
                        plug=name+"AttachMM"+side+".matrixIn[1]"
                        incoming=c.listConnections(plug,source=True,destination=False,plugs=True) or []
                        if incoming:
                            matrix=c.getAttr(incoming[0]); c.disconnectAttr(incoming[0],plug)
                            c.setAttr(plug,*matrix,type="matrix")
                    joint=c.rename(name+"Joint"+side,name+"RibbonJoint"+side)
                    offset=c.rename(name+"JointOffset"+side,name+"RibbonJointOffset"+side)
                    c.parent(offset,"LipRibbonJoints",absolute=True)
                    c.move(0,distance,0,control+".cv[*]",relative=True,objectSpace=True,worldSpaceDistance=True)
                    if index==0 and side=="_R": self._lip_skin(ribbon+"SC",(joint,),ribbon)
                    else: c.skinCluster(ribbon+"SC",edit=True,addInfluence=joint,dropoffRate=4,lockWeights=False,weight=0)
                    c.skinPercent(ribbon+"SC",ribbon+f".cv[{u}][0:1]",transformValue=[(joint,1)])
            c.delete(extrusion,*shaped[arc])
            c.parent(curve,ribbon,"LipRibbon",absolute=True)
        c.delete(nearest,surface)
        for side,u in (("_R",0),("_L",source.end*2+1)):
            joint="cornerLipRibbonJoint"+side
            c.skinCluster("lowerLipRibbonSC",edit=True,addInfluence=joint,dropoffRate=4,lockWeights=False,weight=0)
            c.skinPercent("lowerLipRibbonSC",f"lowerLipRibbon.cv[{u}][0:1]",transformValue=[(joint,1)])
        return controls

    def _lip_green_controls(self,source):
        c=self._cmds; result=[]
        configurations=(("","_R",2),("","_L",2),("upper","_M",2),("lower","_M",2),
                        ("upper","_R",3),("lower","_R",3),("upper","_L",3),("lower","_L",3))
        for arc,side,kind in configurations:
            factor=1 if arc=="upper" else -1
            align="cornerLip"+side if not arc else arc+"LipA"+("_R" if side=="_M" else side)
            position=list(self._lip_pos(align))
            distance=source.control_scale*.2*factor if side=="_M" else 0
            if side=="_M": position[0]=0; position[1]+=distance
            if kind==3:
                rebuilt=c.rebuildCurve(arc+"LipOuterBuildCurve",constructionHistory=True,replaceOriginal=False,
                    rebuildType=0,endKnots=1,keepRange=0,keepControlPoints=False,keepEndPoints=True,
                    spans=2,degree=3,tolerance=.01)[0]
                position=list(self._lip_pos(rebuilt+".cv[2]"))
                position[0]*=1 if side=="_R" else -1
                c.delete(rebuilt)
            control=self.create_original_face_pp(position,arc+"Lip",side,kind,legacy_orient=source.legacy_orient)
            result.append(control)
            if side=="_M":
                c.move(0,-distance,0,arc+"LipOffset_M",relative=True,objectSpace=True,worldSpaceDistance=True)
        for control,rotation in (("upperLip_M",90),("lowerLip_M",-90),("Lip_R",0),("Lip_L",0)):
            self.shape_original_face_half_moon(control,rotation)
        for side in ("_R","_L"):
            c.addAttr("Lip"+side,longName="sticky",attributeType="double",minValue=0,maxValue=10,keyable=True)
            output=self.original_face_output_bw("Lip"+side+".sticky")
            for plug in c.listConnections("PlaceHolderStickyLip"+side+".sticky",source=False,destination=True,plugs=True) or []:
                c.connectAttr(output,plug,force=True)
            c.delete("PlaceHolderStickyLip"+side)
        for arc,factor in (("upper",1),("lower",-1)):
            control=arc+"Lip_M"
            c.move(0,source.control_scale*.2*factor,0,control+".cv[*]",relative=True,objectSpace=True,worldSpaceDistance=True)
            points=[self._lip_pos(control+f".cv[{i}]") for i in range(self._lip_cv_count(control))]
            pivot=tuple((min(p[a] for p in points)+max(p[a] for p in points))/2 for a in range(3))
            c.scale(2,2,2,control+".cv[*]",relative=True,pivot=pivot)
        return result

    def _lip_fleshy(self,source):
        c=self._cmds
        controls=("Lip_R","Lip_L","upperLip_M","lowerLip_M","upperLip_R","upperLip_L","lowerLip_R","lowerLip_L")
        for control in controls:
            stem,side=control.rsplit("_",1); side="_"+side
            joint=self._lip_node("joint",stem+"JointFleshy"+side,"LipRibbonFleshyJoints")
            constrained=self._lip_node("transform",stem+"ConstrainedFleshy"+side,"LipFollowHeadConstrained")
            mm=self._lip_node("multMatrix",stem+"ConstrainedFleshyMM"+side)
            dm=self._lip_node("decomposeMatrix",stem+"ConstrainedFleshyDM"+side)
            c.connectAttr(control+".worldMatrix[0]",mm+".matrixIn[0]")
            c.connectAttr("LipFollowHeadConstrained.worldInverseMatrix[0]",mm+".matrixIn[1]")
            c.connectAttr(mm+".matrixSum",dm+".inputMatrix")
            c.connectAttr(dm+".outputTranslate",constrained+".translate")
            if not c.objExists("LipRegionDM_M"):
                self._lip_node("decomposeMatrix","LipRegionDM_M")
                self._lip_node("multMatrix","LipRegionMM_M")
                c.connectAttr("LipRegion_M.worldMatrix[0]","LipRegionMM_M.matrixIn[0]")
                c.connectAttr("LipFollowHeadConstrained.worldInverseMatrix[0]","LipRegionMM_M.matrixIn[1]")
                c.connectAttr("LipRegionMM_M.matrixSum","LipRegionDM_M.inputMatrix")
            c.connectAttr("LipRegionDM_M.outputRotate",constrained+".rotate")
            c.connectAttr(constrained+".translate",joint+".translate")
        nearest=self._lip_node("nearestPointOnCurve","lipFleshySamplerTemp#")
        for arc in ("upper","lower"):
            c.addAttr(arc+"Lip_M",longName="fractionMode",attributeType="double",minValue=0,maxValue=10,
                      defaultValue=10,keyable=True)
            output=self.original_face_output_bw(arc+"Lip_M.fractionMode")
            uc=self._lip_node("unitConversion",arc+"LipFractionMode_MUnitConversion")
            reverse=self._lip_node("reverse",arc+"LipFractionMode_MReverse")
            c.connectAttr(output,uc+".input"); c.setAttr(uc+".conversionFactor",.1)
            c.connectAttr(uc+".output",reverse+".inputX")
            curve=c.duplicate(arc+"LipRibbonCurve",name=arc+"LipRibbonCurveFleshy",returnRootsOnly=True)[0]
            c.parent(curve,"LipRibbonFleshy",absolute=True)
            for shape in c.listRelatives(curve,shapes=True,fullPath=True) or []:
                if c.getAttr(shape+".intermediateObject"): c.delete(shape)
            c.rebuildCurve(curve,constructionHistory=False,replaceOriginal=True,rebuildType=0,
                endKnots=1,keepRange=0,keepControlPoints=False,keepEndPoints=True,spans=4,degree=3,tolerance=.01)
            skin=self._lip_skin(curve+"SC",("LipJointFleshy_R","LipJointFleshy_L",
                arc+"LipJointFleshy_R",arc+"LipJointFleshy_L"),curve,2)
            c.setAttr(skin+".maintainMaxInfluences",True)
            weights=(("0:2",arc+"LipJointFleshy_R",1),("4:6",arc+"LipJointFleshy_L",1),
                ("0","LipJointFleshy_R",1),("1","LipJointFleshy_R",.670),("2","LipJointFleshy_R",.100),
                ("3",arc+"LipJointFleshy_R",1),("3",arc+"LipJointFleshy_L",.5),
                ("4","LipJointFleshy_L",.100),("5","LipJointFleshy_L",.670),("6","LipJointFleshy_L",1))
            for indices,joint,value in weights:
                c.skinPercent(skin,curve+f".cv[{indices}]",transformValue=[(joint,value)])
            c.connectAttr(curve+".worldSpace[0]",nearest+".inputCurve",force=True)
            for side in ("_R","_L"):
                for index in range(source.end+1):
                    letter=lip_control_letter(index)
                    name="cornerLip" if index==source.end else arc+"Lip"+letter
                    if index==source.end and arc=="lower": continue
                    if index==source.end: parameter=0 if side=="_R" else 1
                    else:
                        c.setAttr(nearest+".inPosition",*self._lip_pos(name+side))
                        parameter=float(c.getAttr(nearest+".parameter"))
                    blend=self._lip_node("blendColors",name+"FleshyFractionalBlendColors"+side)
                    c.connectAttr(reverse+".outputX",blend+".blender")
                    original=self._lip_vector(name+"RibbonJointOffset"+side+".translate")
                    for number in (1,2):
                        follower=self._lip_node("transform",arc+"Lip"+letter+"RibbonJointFleshy"+str(number)+side,"LipRibbonFleshy")
                        motion=self._lip_node("motionPath",name+"FleshyMotionPath"+str(number)+side)
                        c.setAttr(motion+".fractionMode",number-1)
                        c.connectAttr(curve+".worldSpace[0]",motion+".geometryPath")
                        c.setAttr(motion+".uValue",parameter)
                        c.connectAttr(motion+".allCoordinates",follower+".translate")
                        plus=self._lip_node("plusMinusAverage",name+"FleshyAddPMA"+str(number)+side)
                        c.connectAttr(motion+".allCoordinates",plus+".input3D[0]")
                        position=self._lip_vector(motion+".allCoordinates")
                        c.setAttr(plus+".input3D[1]",*(b-a for a,b in zip(position,original)))
                        c.connectAttr(plus+".output3D",blend+".color"+str(number))
                    c.connectAttr(blend+".output",name+"RibbonJointOffset"+side+".translate")
        c.delete(nearest)

    def _lip_roll_scale(self,source,counts):
        c=self._cmds
        def smooth(value,maximum=1):
            t=max(0.,min(1.,value/maximum)); return t*t*(3-2*t)
        for arc in ("upper","lower"):
            mm=self._lip_node("multMatrix",arc+"LipMM_M")
            dm=self._lip_node("decomposeMatrix",arc+"LipDM_M")
            c.connectAttr(mm+".matrixSum",dm+".inputMatrix")
            drivers=[arc+"Lip_M","SDK"+arc+"Lip_M"]
            if arc=="upper": drivers.extend(("LipRegion_M","SDKLipRegion_M"))
            for index,node in enumerate(drivers): c.connectAttr(node+".matrix",mm+f".matrixIn[{index}]")
            controls=["cornerLip_L"]+[arc+"Lip"+lip_control_letter(i)+"_L" for i in range(source.end-1,-1,-1)]
            controls += [arc+"Lip"+lip_control_letter(i)+"_R" for i in range(source.end)]+["cornerLip_R"]
            samples=[(ctrl,float(c.getAttr(ctrl+".parameterOnUniform"))) for ctrl in controls]
            for lateral in ("_R","_L"):
                for index in range(counts[arc]):
                    side="_M" if index==0 else lateral
                    if index==0 and lateral=="_L" or arc=="lower" and index==counts[arc]-1: continue
                    parameter=float(c.getAttr(f"{arc}follicle{index}"+side+".parameterU"))
                    below=[(parameter-p,ctrl) for ctrl,p in samples if parameter-p>0]
                    above=[(p-parameter,ctrl) for ctrl,p in samples if p-parameter>0]
                    # At an exact boundary use its control for the missing side;
                    # avoids MEL's accidental reuse of a preceding loop value.
                    exact=min(samples,key=lambda item:abs(item[1]-parameter))[0]
                    d1,a=min(below) if below else (0.,exact)
                    d2,b=min(above) if above else (0.,exact)
                    blend=self._lip_node("blendWeighted",f"{arc}LipBW{index}"+side)
                    for number,control in enumerate((a,b,"SDK"+a,"SDK"+b,arc+"Lip_M","SDK"+arc+"Lip_M")):
                        c.connectAttr(control+".rx",blend+f".input[{number}]")
                    weight=smooth(d2,d1+d2) if d1+d2 else 1.
                    green=smooth(1-index/counts[arc],.7)
                    for number,value in enumerate((weight,1-weight,weight,1-weight,green,green)):
                        c.setAttr(blend+f".weight[{number}]",value)
                    joint=f"{arc}LipJoint{index}"+side
                    c.connectAttr(blend+".output",joint+".rx")
                    c.connectAttr(dm+".outputScale",joint+".scale",force=True)

    def _lip_expression_keys(self,source):
        # asFaceDsFinish's temporary frame-0/30 fitting animations are stored
        # directly as the resulting SDK keys; values and drivers are unchanged.
        for arc,factor in (("upper",1),("lower",-1)):
            target="SDK"+arc+"Lip_M"
            y=self._lip_pos(arc+"LipMainCurve.cv[0]")[1]-self._lip_pos(arc+"Lip_M")[1]
            actions=(("Press",10,(("sz",.2),)),
                ("Squeeze",10,(("sy",.3),("ty",y/source.control_scale*.5))),
                ("Roll",10,(("tz",.05),("rx",-30*factor))),
                ("Roll",-10,(("tz",-.35),)),
                ("Pucker",10,(("ty",.15*factor),("tz",.25),("rx",-30*factor))))
            for action,drive_value,values in actions:
                for attr,value in values:
                    self.add_original_face_sdk("ctrlLips_M."+arc+action,target+"."+attr,drive_value,value)
            thickness=self._lip_pos("upperLipOuterCurve.cv[0]")[1]-self._lip_pos("upperLipMainCurve.cv[0]")[1]
            for side in ("_R","_L"):
                self.add_original_face_sdk("ctrlLips_M."+arc+"Pucker","SDKLip"+side+".tx",
                                           10,thickness/source.control_scale*-.3)

    def _lip_together(self,source):
        c=self._cmds
        for side in ("_R","_L"):
            for arc in ("upper","lower"):
                control=arc+"Lip"+side; constrained=arc+"LipConstrainedFleshy_M"
                static=self._lip_node("transform",arc+"LipsTogetherStatic"+side,control)
                c.parent(static,constrained,absolute=True); c.xform(static,objectSpace=True,scale=(1,1,1))
                follow=c.duplicate(static,name=arc+"LipsTogetherFollow"+side,returnRootsOnly=True)[0]
                lip_follow=self._lip_node("transform",arc+"LipFollow"+side,arc+"LipOffset"+side)
                c.parent("SDK"+control,lip_follow,absolute=True)
                bm=self._lip_node("blendMatrix",arc+"LipsTogetherFollowBM"+side)
                c.connectAttr("upperLip_M.worldMatrix[0]",bm+".inputMatrix")
                c.connectAttr("lowerLip_M.worldMatrix[0]",bm+".target[0].targetMatrix")
                c.setAttr(bm+".target[0].weight",.5)
                mm=self._lip_node("multMatrix",arc+"LipsTogetherFollowMM"+side)
                for index in (0,1):
                    parent=self._lip_node("transform","lipTogetherMatrixTemp#","upperLipConstrainedFleshy_M")
                    c.delete(c.scaleConstraint("OnFacecontrols",parent))
                    child=self._lip_node("transform","lipTogetherChildTemp#",parent)
                    if index==0:
                        c.xform(child,worldSpace=True,translation=self._lip_pos(control))
                        matrix=c.getAttr(child+".matrix")
                    else:
                        c.pointConstraint("upperLip_M","lowerLip_M",child)
                        matrix=c.getAttr(child+".inverseMatrix")
                    c.setAttr(mm+f".matrixIn[{index}]",*matrix,type="matrix"); c.delete(parent)
                pick=self._lip_node("pickMatrix",arc+"LipsTogetherFollowPM"+side)
                for attr in ("useScale","useShear"): c.setAttr(pick+"."+attr,False)
                c.connectAttr(mm+".matrixSum",pick+".inputMatrix")
                self.connect_original_face_matrix(pick+".outputMatrix",follow)
                unused=self._lip_node("pickMatrix",arc+"LipFollowPM1"+side)
                for attr in ("useRotate","useScale","useShear"): c.setAttr(unused+"."+attr,False)
                c.connectAttr(bm+".outputMatrix",unused+".inputMatrix")
                c.connectAttr(bm+".outputMatrix",mm+".matrixIn[2]")
                c.connectAttr(constrained+".worldInverseMatrix[0]",mm+".matrixIn[3]")
                c.xform(follow,objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
                c.delete(c.pointConstraint(static,follow))
                blend=self._lip_node("blendMatrix",arc+"LipFollowBM"+side)
                c.connectAttr(static+".worldMatrix[0]",blend+".inputMatrix")
                c.connectAttr(follow+".worldMatrix[0]",blend+".target[0].targetMatrix")
                final_mm=self._lip_node("multMatrix",arc+"LipFollowMM"+side)
                c.connectAttr(blend+".outputMatrix",final_mm+".matrixIn[0]")
                c.connectAttr(arc+"LipOffset"+side+".worldInverseMatrix[0]",final_mm+".matrixIn[1]")
                final_pick=self._lip_node("pickMatrix",arc+"LipFollowPM2"+side)
                for attr in ("useRotate","useScale","useShear"): c.setAttr(final_pick+"."+attr,False)
                c.connectAttr(final_mm+".matrixSum",final_pick+".inputMatrix")
                self.connect_original_face_matrix(final_pick+".outputMatrix",lip_follow)
                c.addAttr(control,longName="lipsTogether",attributeType="double",minValue=0,maxValue=10,keyable=True)
                output=self.original_face_output_bw(control+".lipsTogether")
                uc=self._lip_node("unitConversion",arc+"LipsTogether"+side+"UnitConversion")
                c.connectAttr(output,uc+".input"); c.setAttr(uc+".conversionFactor",.1)
                c.connectAttr(uc+".output",blend+".target[0].weight")
