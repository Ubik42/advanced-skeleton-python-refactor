"""asFaceEyeLid curve/control/point-joint graph, source 33220–33525.

The preparation, blink attribute graph and production topology weights belong
to separate source-shaped stages. This graph is not a complete EyeLid build.
"""
from math import dist

class MayaFaceEyeLidCurvesMixin:
    def create_original_eye_lid_fleshy_graph(self):
        """asFaceEyeLid 33528–33640: broad corner motion and blink targets.

        Called after the curve/control graph; this stage does not build the
        blink attributes or assign weights to the character's mesh.
        """
        self._require_transaction()
        c = self._cmds
        for side in ("_R", "_L"):
            c.createNode("transform", name="LidSetupFleshy" + side, parent="LidSetup")
            c.createNode("transform", name="LidFleshyAimAt" + side, parent="LidSetup")
            for corner in ("inner", "upper", "outer", "lower"):
                stem = corner + "Lid"
                aimer = c.createNode("transform", name=stem + "FleshyAimer" + side,
                                     parent="LidSetup" + side)
                c.parent(aimer, "LidSetupFleshy" + side)
                offset = c.createNode("transform", name=stem + "FleshyAimAtOffset" + side,
                                      parent=stem + "Joint" + side)
                c.parent(offset, "LidFleshyAimAt" + side)
                target = c.createNode("transform", name=stem + "FleshyAimAt" + side, parent=offset)
                for axis in ("x", "z"):
                    c.connectAttr(stem + "Joint" + side + ".t" + axis, target + ".t" + axis)
                am = c.createNode("aimMatrix", name=stem + "FleshyAimerAM" + side)
                c.setAttr(am + ".primaryInputAxis", 1, 0, 0, type="float3")
                c.setAttr(am + ".secondaryMode", 2)
                for attr in ("secondaryInputAxis", "secondaryTargetVector"):
                    c.setAttr(am + "." + attr, 0, 1, 0, type="float3")
                c.connectAttr(target + ".worldMatrix[0]", am + ".primaryTargetMatrix")
                c.setAttr(am + ".inputMatrix", *c.xform(aimer, query=True, objectSpace=True, matrix=True),
                          type="matrix")
                c.xform(aimer, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1))
                self.connect_original_face_matrix(am + ".outputMatrix", aimer)
                end = c.createNode("joint", name=stem + "FleshyAimEnd" + side, parent=stem + side)
                c.parent(end, aimer)
                plus = c.createNode("plusMinusAverage", name=stem + "JointPMAr" + side)
                c.connectAttr(stem + side + ".r", plus + ".input3D[0]")
                c.connectAttr("SDK" + stem + side + ".r", plus + ".input3D[1]")
                c.connectAttr(plus + ".output3D", end + ".r")
            for arc in ("upper", "lower"):
                curve = arc + "LidCurveFleshy" + side
                skin = arc + "LidCurveFleshySC" + side
                influences = tuple(name + "LidFleshyAimEnd" + side for name in (arc, "inner", "outer"))
                c.skinCluster(influences, curve, toSelectedBones=True, maximumInfluences=2,
                              dropoffRate=4, removeUnusedInfluence=False, name=skin)
                for corner, index, weight in (("outer", 6, .867), ("outer", 5, .6), ("outer", 4, .2),
                                              ("inner", 3, .2), ("inner", 2, .6), ("inner", 1, .867)):
                    c.skinPercent(skin, curve + f".cv[{index}]",
                                  transformValue=((corner + "LidFleshyAimEnd" + side, weight),))
            for corner in ("inner", "outer"):
                plus = corner + "LidJointPMAt" + side
                c.disconnectAttr(plus + ".output3D", corner + "LidJoint" + side + ".t")
                for axis in ("x", "y", "z"):
                    c.connectAttr(plus + ".output3D.output3D" + axis,
                                  corner + "LidFleshyAimAt" + side + ".t" + axis, force=True)
            for arc in ("upper", "lower"):
                c.blendShape(arc + "UnClosedLidCurve" + side, arc + "ClosedLidCurve" + side,
                             arc + "LidCurveBlink" + side, name=arc + "LidCurveBlinkBS" + side,
                             frontOfChain=True, weight=((0, 1), (1, 0)))
        return tuple(arc + "LidCurveFleshySC" + side for side in ("_R", "_L") for arc in ("upper", "lower"))

    def create_original_eye_lid_curve_graph(self,source):
        self._require_transaction()
        c=self._cmds; controls=[]
        sampler=c.createNode("nearestPointOnCurve",name="tempNearestPointOnCurve")
        for side,suffix in (("_R",""),("_L","Left")):
            for arc in ("upper","lower"):
                c.addAttr("LidSetup"+side,longName=arc+"LidOut",attributeType="double",defaultValue=0,softMinValue=0,softMaxValue=1,keyable=True)
            c.createNode("transform",name="LidLocs"+side)
            c.setAttr("LidLocs"+side+".inheritsTransform",False); c.parent("LidLocs"+side,"LidSetup")
            c.createNode("transform",name="LidCurves"+side,parent="FaceDeformationSystem")
            for arc,factor in (("upper",1),("lower",-1)):
                for part in ("Main","Outer"):
                    if part=="Outer" and source["simpler"]: continue
                    fit_curve=arc+"EyeLid"+part+"Curve"+suffix
                    curve=arc+"Lid"+part+"Curve"+side
                    count=int(c.getAttr(fit_curve+".spans"))+1
                    c.duplicate(fit_curve,name=curve,returnRootsOnly=True)
                    c.rebuildCurve(curve,constructionHistory=False,replaceOriginal=True,rebuildType=0,endKnots=1,
                        keepRange=0,keepControlPoints=False,keepEndPoints=True,keepTangents=False,spans=5,degree=3,tolerance=.004)
                    if side=="_L" and not source["non_sym"]:
                        c.parent(curve,world=True); c.makeIdentity(curve,apply=True,translate=True,rotate=True,scale=True)
                    c.parent(curve,"LidCurves"+side)
                    tweak=arc+"Lid"+part+"CurveTweak"+side
                    c.duplicate(curve,name=tweak,returnRootsOnly=True)
                    if part=="Main":
                        for name in (arc+"LidCurveFleshy"+side,arc+"LidCurveBlink"+side,arc+"UnClosedLidCurve"+side,
                                     ("lower" if arc=="upper" else "upper")+"ClosedLidCurve"+side):
                            c.duplicate(curve,name=name,returnRootsOnly=True)
                        c.skinCluster("EyeRegionJoint"+side,curve,toSelectedBones=True,maximumInfluences=3,
                            dropoffRate=4,removeUnusedInfluence=False,name=arc+"LidMainSC"+side)
                    c.connectAttr(curve+".worldSpace[0]",sampler+".inputCurve",force=True)
                    for index in range(count):
                        if arc=="lower" and index in (0,count-1): continue
                        self._original_lid_point_joint(source,arc,part,side,fit_curve,curve,index,sampler)
                    if part=="Main":
                        for index in range(1,count-1): self._original_lid_point_out(source,arc,side,suffix,index,count)
                        c.blendShape(tweak,arc+"LidCurveBlink"+side,arc+"LidCurveFleshy"+side,curve,
                            name=arc+"LidMainBS"+side,frontOfChain=True,weight=((0,1),(1,1),(2,1)))
                    else:
                        for index in range(count):
                            if arc=="lower" and index in (0,count-1): continue
                            self._original_lid_outer_point(source,arc,side,index)
                        c.blendShape(tweak,curve,name=arc+"LidOuterBS"+side,frontOfChain=True,weight=((0,1),))
                    controls.extend(self._original_lid_curve_controls(source,arc,part,side,factor))
                if not source["simpler"]:
                    names=[arc+"LidOuter"+side,*[arc+f"Lid{i}Outer"+side for i in range(1,5)]]
                    if arc=="upper": names.extend(("innerLidOuter"+side,"outerLidOuter"+side))
                    for name in names:
                        shape=c.listRelatives(name,shapes=True,fullPath=True)[0]
                        color=(0,.27,1) if any(name.startswith(arc+f"Lid{i}") for i in range(1,5)) else (.147,.578,.147)
                        c.setAttr(shape+".overrideRGBColors",True); c.setAttr(shape+".overrideColorRGB",*color,type="double3")
        c.delete(sampler)
        return tuple(controls)

    def _original_lid_point_joint(self,source,arc,part,side,fit_curve,curve,index,sampler):
        c=self._cmds; stem=arc+"Lid"+part+str(index)
        c.select(clear=True); joint=c.joint(name=stem+side)
        c.setAttr(joint+".segmentScaleCompensate",False); c.setAttr(joint+".radius",.1)
        point=c.xform(fit_curve+f".cv[{index}]",query=True,worldSpace=True,translation=True)
        c.xform(joint,worldSpace=True,translation=point); c.parent(joint,"EyeLidJoints_M")
        locator=c.spaceLocator(name=arc+"Lid"+part+"Loc"+str(index)+side)[0]
        shape=c.listRelatives(locator,shapes=True,fullPath=True)[0]
        c.setAttr(shape+".localScale",*(source["scale"]/100,)*3,type="float3")
        c.parent(locator,"LidLocs"+side)
        poci=c.createNode("pointOnCurveInfo",name=arc+"Lid"+part+"Poci"+str(index)+side)
        c.setAttr(sampler+".inPosition",*point,type="float3")
        c.setAttr(poci+".parameter",c.getAttr(sampler+".parameter"))
        c.connectAttr(poci+".position",locator+".translate"); c.connectAttr(curve+".worldSpace[0]",poci+".inputCurve")
        aim=c.createNode("transform",name=stem+"Aim"+side,parent="LidSetup"+side)
        c.setAttr(aim+".t",0,0,0,type="float3"); c.setAttr(aim+".r",0,0,0,type="float3")
        am=c.createNode("aimMatrix",name=arc+"Lid"+part+"Loc"+str(index)+"AimAM"+side)
        c.setAttr(am+".primaryInputAxis",1,0,0,type="float3"); c.setAttr(am+".secondaryMode",2)
        c.setAttr(am+".secondaryInputAxis",0,1,0,type="float3"); c.setAttr(am+".secondaryTargetVector",0,1,0,type="float3")
        c.connectAttr(locator+".worldMatrix[0]",am+".primaryTargetMatrix")
        c.connectAttr("LidSetup"+side+".worldMatrix[0]",am+".secondaryTargetMatrix")
        c.connectAttr("EyeRegion"+side+".worldMatrix[0]",am+".inputMatrix")
        mm=c.createNode("multMatrix",name=stem+"AimMM"+side)
        c.connectAttr(am+".outputMatrix",mm+".matrixIn[1]"); c.connectAttr("LidSetup"+side+".worldInverseMatrix[0]",mm+".matrixIn[2]")
        pick=c.createNode("pickMatrix",name=arc+"Lid"+part+"Loc"+str(index)+"AimPM"+side)
        for attr in ("useTranslate","useScale","useShear"): c.setAttr(pick+"."+attr,False)
        c.connectAttr(mm+".matrixSum",pick+".inputMatrix"); self.connect_original_face_matrix(pick+".outputMatrix",aim)
        end=c.createNode("transform",name=stem+"AimEnd"+side,parent=aim)
        c.xform(end,worldSpace=True,translation=point)
        self.constrain_original_face(end,joint,maintain_offset=True,pick=True)
        for attr in ("useScale","useShear"): c.setAttr(stem+"PM"+side+"."+attr,False)
        if source["multi"]: self._original_lid_multi_matrix(source,stem,side)

    def _original_lid_multi_matrix(self,source,stem,side):
        c=self._cmds; mm=stem+"MM"+side
        c.setAttr(mm+".matrixIn[3]",*c.getAttr("EyeLidJoints_M.worldMatrix")[0],type="matrix")
        c.connectAttr(source["head"]+".worldInverseMatrix",mm+".matrixIn[4]")
        temp=c.createNode("transform",name="tempXform",parent="EyeLidJoints_M")
        c.parent(temp,source["head"])
        c.setAttr(mm+".matrixIn[5]",*c.getAttr(temp+".inverseMatrix")[0],type="matrix"); c.delete(temp)

    def _original_lid_point_out(self,source,arc,side,suffix,index,count):
        c=self._cmds; stem=arc+"LidMain"+str(index)
        multiply=c.createNode("multiplyDivide",name=arc+"LidOutMult"+str(index)+side)
        value=(index if index<count//2 else count-1-index)/count
        factor=value*value*(3-2*value)*source["scale"]/3
        c.setAttr(multiply+".input1X",factor); c.connectAttr("LidSetup"+side+"."+arc+"LidOut",multiply+".input2X")
        if c.objExists("FitEyeBall.nonSphericalEye"):
            if not c.objExists("LidSetupNonSpAim1"+side):
                first=c.createNode("transform",name="LidSetupNonSpAim1"+side,parent="FitEyeBall"+suffix)
                c.parent(first,"LidSetup"+side); c.createNode("transform",name="LidSetupNonSpAim2"+side,parent=first)
            c.parent(stem+"AimEnd"+side,world=True); c.parent(stem+"Aim"+side,"LidSetupNonSpAim2"+side)
            if c.getAttr(stem+"Aim"+side+".rx",settable=True): c.setAttr(stem+"Aim"+side+".r",0,0,0)
            c.connectAttr("LidSetupNonSpAim2"+side+".worldInverseMatrix[0]",stem+"AimMM"+side+".matrixIn[2]",force=True)
            c.parent(stem+"AimEnd"+side,stem+"Aim"+side)
        plus=c.createNode("plusMinusAverage",name=arc+"LidOut"+str(index)+side)
        c.setAttr(plus+".input1D[0]",c.getAttr(stem+"AimEnd"+side+".tx"))
        c.connectAttr(multiply+".outputX",plus+".input1D[1]"); c.connectAttr(plus+".output1D",stem+"AimEnd"+side+".tx")

    def _original_lid_outer_point(self,source,arc,side,index):
        c=self._cmds; stem=arc+"LidOuter"+str(index); joint=stem+side
        point=self._lip_pos(joint); c.delete(stem+"Aim"+side); c.delete(stem+"MM"+side)
        if c.objExists(stem+"DM"+side): c.delete(stem+"DM"+side)
        c.xform(joint,worldSpace=True,translation=point)
        self.constrain_original_face(arc+"LidOuterLoc"+str(index)+side,joint,pick=True)
        for attr in ("useRotate","useScale","useShear"): c.setAttr(stem+"PM"+side+"."+attr,False)
        if source["multi"]: self._original_lid_multi_matrix(source,stem,side)

    def attach_original_eye_lid_pp(self,name,side):
        """asEyeLidAttachPP 45905: joint space and nearest Main AimEnd."""
        c=self._cmds; part="Outer" if name.endswith("Outer") else "Main"
        arc="lower" if name.startswith("lower") else "upper"; suffix="Left" if side=="_L" else ""
        if not any("Lid"+str(i) in name for i in range(10)): c.parent(name+"Offset"+side,"EyeRegion"+side)
        if c.objExists(name+"JointOffset"+side): c.parent(name+"JointOffset"+side,"LidJoints")
        elif c.objExists(name+"Joint"+side):
            joint=name+"Joint"+side; c.parent(joint,"LidJoints")
            c.connectAttr("LidJoints.worldInverseMatrix",name+"JointMM"+side+".matrixIn[2]",force=True)
            c.xform(joint,objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
            c.setAttr(name+"JointMM"+side+".matrixIn[0]",*c.xform("FaceGroup",query=True,objectSpace=True,matrix=True),type="matrix")
        if part=="Outer": return
        point=self._lip_pos(name+side); count=int(c.getAttr(arc+"EyeLidMainCurve"+suffix+".spans"))+1
        ends=[arc+f"LidMain{i}AimEnd"+side for i in range(count) if c.objExists(arc+f"LidMain{i}AimEnd"+side)]
        end=min(ends,key=lambda node:dist(point,self._lip_pos(node)))
        self.constrain_original_face(end,name+"Attach"+side,maintain_offset=True,pick=True)
        for attr in ("useRotate","useScale","useShear"): c.setAttr(name+"AttachPM"+side+"."+attr,False)

    def _original_lid_curve_controls(self,source,arc,part,side,factor):
        c=self._cmds; suffix="Outer" if part=="Outer" else ""; attach=part=="Main"; controls=[]
        curve=arc+"Lid"+part+"Curve"+side
        if arc=="upper":
            for name,index in (("inner",0),("outer",7)):
                stem=name+"Lid"+suffix
                controls.append(self.create_original_face_pp(curve+f".cv[{index}]",stem,side,2,create_joint=True,attach=attach))
                self.attach_original_eye_lid_pp(stem,side)
        for index in range(1,5):
            stem=arc+"Lid"+str(index)+suffix
            controls.append(self.create_original_face_pp(curve+f".cv[{index+1}]",stem,side,1,create_joint=True,attach=attach))
            self.attach_original_eye_lid_pp(stem,side)
            c.move(0,0,source["scale"]/200,stem+side+".cv[0:99]",relative=True,objectSpace=True,worldSpaceDistance=True)
        c.delete(c.pointConstraint(arc+"Lid2"+suffix+side,arc+"Lid3"+suffix+side,"TempPos"))
        stem=arc+"Lid"+suffix
        controls.append(self.create_original_face_pp("TempPos",stem,side,2,create_joint=True,attach=attach))
        self.attach_original_eye_lid_pp(stem,side)
        c.move(0,0,source["scale"]/100,stem+side+".cv[0:99]",relative=True,objectSpace=True,worldSpaceDistance=True)
        if part=="Outer":
            for index,corner,value in ((1,"inner",6.5),(2,"inner",10),(3,"outer",10),(4,"outer",6.5)):
                self.add_original_face_follow(arc+"Lid"+str(index)+suffix+side,stem+side,corner+"Lid"+suffix+side,value)
        tweak=arc+"Lid"+part+"CurveTweak"+side; skin=arc+"Lid"+part+"CurveTweakSC"+side
        infs=("outerLid"+suffix+"Joint"+side,"innerLid"+suffix+"Joint"+side,*[arc+f"Lid{i}"+suffix+"Joint"+side for i in range(1,5)])
        c.skinCluster(infs,tweak,toSelectedBones=True,maximumInfluences=3,dropoffRate=4,removeUnusedInfluence=False,name=skin)
        for joint,index in (("innerLid"+suffix+"Joint"+side,0),("outerLid"+suffix+"Joint"+side,7),*[(arc+f"Lid{i-1}"+suffix+"Joint"+side,i) for i in range(2,6)]):
            c.skinPercent(skin,tweak+f".cv[{index}]",transformValue=((joint,1),))
        # Source balances Main CV 1/6 again even while processing Outer.
        for corner,index,minor in (("inner",1,1),("outer",6,4)):
            main_skin=arc+"LidMainCurveTweakSC"+side; vertex=arc+"LidMainCurveTweak"+side+f".cv[{index}]"
            c.skinPercent(main_skin,vertex,transformValue=((corner+"LidJoint"+side,1),))
            c.skinPercent(main_skin,vertex,transformValue=((arc+f"Lid{minor}Joint"+side,.33),))
        self.shape_original_face_half_moon(stem+side,90*factor)
        if arc=="upper":
            self.shape_original_face_half_moon("innerLid"+suffix+side,180)
            self.shape_original_face_half_moon("outerLid"+suffix+side,0)
        return controls
