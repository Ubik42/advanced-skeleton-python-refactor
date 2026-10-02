"""Shared original Face controller and two-space follow graph builders."""
from __future__ import annotations
import re
from .maya_face_sdk_insert import MayaFaceSDKInsertMixin

class MayaFaceControllersMixin(MayaFaceSDKInsertMixin):
    def original_face_matrix_values(self,plug):
        """Read native matrix attributes independent of array return shape."""
        values=self._cmds.getAttr(plug)
        if len(values)==1 and isinstance(values[0],(tuple,list)):
            values=values[0]
        if len(values)!=16:
            raise ValueError("Face 矩阵不是 4×4："+plug)
        return tuple(float(value) for value in values)

    def next_original_face_bw_input(self,bw):
        """Append an additive input without replacing an existing driver.

        Maya may report size zero for a connected, unevaluated multi. Include
        the actual connection plugs as well as materialized logical indices.
        This preserves asDsSdk's append behavior with sparse native arrays.
        """
        c=self._cmds
        indices=list(c.getAttr(bw+".input",multiIndices=True) or [])
        pairs=c.listConnections(bw+".input",source=True,destination=False,
            plugs=True,connections=True) or []
        for plug in pairs[::2]:
            match=re.search(r"\.input\[(\d+)\]$",plug)
            if match: indices.append(int(match.group(1)))
        return bw+f".input[{max(indices,default=-1)+1}]"

    def face_use_offset_parent_matrix(self):
        c=self._cmds
        fit=c.ls("FitSkeleton",long=True,type="transform") or []
        if not fit: fit=c.ls("FaceFitSkeleton",long=True,type="transform") or []
        return bool(len(fit)==1 and c.attributeQuery("useOffsetParentMatrix",node=fit[0],exists=True)
                    and c.getAttr(fit[0]+".useOffsetParentMatrix"))

    def create_original_face_controller(self,name,side,kind):
        """asCreateFaceController: circle → SDK → Offset, optional joint."""
        self._require_transaction()
        c=self._cmds
        if kind not in (1,2,3,4,5,12,13) or side not in ("_R","_L","_M"):
            raise ValueError("Face 控制器类型或侧别无效")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",name):
            raise ValueError("Face 控制器名称无效")
        radius={1:.15,2:.3,12:.3,3:.15,13:.15}.get(kind,.2)
        letter,color={1:("B",13),2:("A",14),12:("A",14),3:("C",6),
                      13:("C",6),4:("Regions",14),5:("Custom",28)}[kind]
        control=name+side
        offset=name+"Offset"+side
        sdk="SDK"+control
        for node in (control,offset,sdk,*((name+"Joint"+side,) if kind==4 else ())):
            if c.objExists(node): raise ValueError("Face 控制器节点名称已占用："+node)
        self._transaction_changed=True
        node=c.circle(name=control,center=(0,0,0),normal=(0,0,1),sweep=360,
                      radius=radius,degree=3,sections=8,constructionHistory=False)[0]
        shape=(c.listRelatives(node,shapes=True,fullPath=True) or [None])[0]
        c.sets(node,add="FaceControlSet")
        c.setAttr(shape+".overrideEnabled",True)
        c.setAttr(shape+".overrideColor",color)
        c.createNode("transform",name=offset)
        c.createNode("transform",name=sdk,parent=offset)
        c.parent(node,sdk,absolute=True)
        if kind==4:
            c.select(clear=True)
            c.joint(name=name+"Joint"+side)
        shape=(c.listRelatives(control,shapes=True,fullPath=True) or [None])[0]
        c.connectAttr("ctrlBox."+letter+"CtrlVis",shape+".overrideVisibility")
        return control

    def connect_original_face_matrix(self,source,destination):
        """asMatrixConnectAttr keeps both OPM and decompose/shear branches."""
        self._require_transaction()
        c=self._cmds
        if self.face_use_offset_parent_matrix():
            c.connectAttr(source,destination+".offsetParentMatrix")
            return
        stem,side=destination.rsplit("_",1)
        dm=c.createNode("decomposeMatrix",name=stem+"DM_"+side)
        c.setAttr(dm+".inputRotateOrder",c.getAttr(destination+".rotateOrder"))
        c.connectAttr(source,dm+".inputMatrix")
        for axis,lower,shear in zip("XYZ","xyz",("xy","xz","yz")):
            for output,attr in (("Translate","t"+lower),("Rotate","r"+lower),
                                ("Scale","s"+lower),("Shear","sh"+shear)):
                c.connectAttr(dm+".output"+output+axis,destination+"."+attr)

    def add_original_face_follow(self,target,source_a,source_b,value):
        """asFaceAddConstrained: output BW, normalized follow and blendMatrix."""
        self._require_transaction()
        c=self._cmds
        name,side=target.rsplit("_",1)
        side="_"+side
        attr="follow"+source_a
        c.addAttr(target,longName=attr,attributeType="double",minValue=0,maxValue=10,
                  defaultValue=value,keyable=True)
        blend_name=target+"Blend"+source_a
        uc=c.createNode("unitConversion",name=blend_name+"UnitConversion")
        reverse=c.createNode("reverse",name=blend_name+"Reverse")
        bw=c.createNode("blendWeighted",name="bw"+target+"_"+attr)
        c.connectAttr(target+"."+attr,bw+".input[0]")
        c.connectAttr(bw+".output",uc+".input")
        c.setAttr(uc+".conversionFactor",.1)
        c.connectAttr(uc+".output",reverse+".inputX")
        follow=name+"Follow"+side
        c.createNode("transform",name=follow,parent=name+"Offset"+side)
        c.parent("SDK"+target,follow,absolute=True)
        bm=c.createNode("blendMatrix",name=name+"BM"+side)
        for suffix,driver in (("A",source_a),("B",source_b)):
            mm=c.createNode("multMatrix",name=name+"MM"+suffix+side)
            temp=c.createNode("transform",name="faceFollowMatrixTemp#",parent=target)
            temp=c.parent(temp,driver,absolute=True)[0]
            matrix=c.xform(temp,query=True,objectSpace=True,matrix=True)
            c.delete(temp)
            c.setAttr(mm+".matrixIn[0]",*matrix,type="matrix")
            c.connectAttr(driver+".worldMatrix[0]",mm+".matrixIn[1]")
            c.connectAttr(name+"Offset"+side+".worldInverseMatrix[0]",mm+".matrixIn[2]")
        c.connectAttr(name+"MMA"+side+".matrixSum",bm+".inputMatrix")
        c.connectAttr(name+"MMB"+side+".matrixSum",bm+".target[0].targetMatrix")
        c.connectAttr(reverse+".outputX",bm+".target[0].weight")
        self.connect_original_face_matrix(bm+".outputMatrix",follow)
        self._transaction_changed=True

    def add_original_ctrl_box_second_shape(self,control,icon):
        """asAddCtrlBox2Shape: a projected icon driven through transformGeometry."""
        from dataclasses import replace
        from adv_py.core.body_parent_constraint import plan_body_parent_constraint
        self._require_transaction()
        c=self._cmds
        for name in (control+"TG",control+"TGXformOffset",control+"TGXform"):
            if c.objExists(name): raise ValueError("ctrlBox2 投影节点名称已占用："+name)
        source_shapes=c.listRelatives(icon,shapes=True,noIntermediate=True,fullPath=True,type="nurbsCurve") or []
        target_shapes=c.listRelatives(control,shapes=True,noIntermediate=True,fullPath=True,type="nurbsCurve") or []
        if len(source_shapes)!=1 or not target_shapes:
            raise ValueError("ctrlBox2 图标或目标控制器缺少曲线")
        count=int(c.getAttr(source_shapes[0]+".spans"))+int(c.getAttr(source_shapes[0]+".degree"))
        points=tuple(c.xform(source_shapes[0]+f".cv[{i}]",query=True,worldSpace=True,translation=True) for i in range(count))
        color=c.getAttr(target_shapes[0]+".overrideColor")
        temporary=c.duplicate(icon,name="ctrlBox2ShapeTemp#",returnRootsOnly=True)[0]
        shape=c.listRelatives(temporary,shapes=True,fullPath=True,type="nurbsCurve")[0]
        shape=c.parent(shape,control,add=True,shape=True)[0]
        c.delete(temporary)
        for index,point in enumerate(points): c.xform(shape+f".cv[{index}]",worldSpace=True,translation=point)
        shape=c.rename(shape,icon+"Shape")
        c.delete(icon)
        c.setAttr(shape+".overrideEnabled",True); c.setAttr(shape+".overrideColor",color)
        originals=c.listRelatives(control,shapes=True,fullPath=True,type="nurbsCurve") or []
        icon_index=next(i for i,s in enumerate(originals) if s.rsplit("|",1)[-1]==shape.rsplit("|",1)[-1])
        temporary=c.duplicate(control,name="ctrlBox2OrigShapeTemp#",returnRootsOnly=True)[0]
        original=c.listRelatives(temporary,shapes=True,fullPath=True,type="nurbsCurve")[icon_index]
        original=c.parent(original,control,add=True,shape=True)[0]
        c.delete(temporary)
        original=c.rename(original,icon+"OrigShape"); c.setAttr(original+".intermediateObject",True)
        geometry=c.createNode("transformGeometry",name=control+"TG")
        c.connectAttr(original+".worldSpace[0]",geometry+".inputGeometry",force=True)
        c.connectAttr(geometry+".outputGeometry",shape+".create",force=True)
        offset=c.createNode("transform",name=control+"TGXformOffset",parent=control)
        offset=c.parent(offset,"ctrlBox2Constrained",absolute=True)[0]
        transform=c.createNode("transform",name=control+"TGXform",parent=offset)
        driver=c.ls(control,long=True,type="transform")[0]
        driven=c.ls(transform,long=True,type="transform")[0]
        source=self.capture_parent_constraint_input(driver,driven,False)
        plan=plan_body_parent_constraint(replace(source,force_mult_matrix=True,
            use_offset_parent_matrix=self.face_use_offset_parent_matrix()))
        self.preflight_parent_constraint(plan); self.create_parent_constraint(plan)
        # asParentConstraint splits at the last underscore even when the
        # suffix is RTGXform/LTGXform/MTGXform rather than a bare side.
        # Mixed later reconnects these exact original matrix node names.
        # The shared Body planner only recognizes bare R/L/M suffixes.
        stem, separator, suffix = control.rpartition("_")
        if separator and plan.mult_matrix:
            source_matrix = stem + "MM_" + suffix + "TGXform"
            if plan.mult_matrix != source_matrix:
                c.rename(plan.mult_matrix, source_matrix)
        c.connectAttr(transform+(".offsetParentMatrix" if self.face_use_offset_parent_matrix() else ".matrix"),
                      geometry+".transform",force=True)
        c.setAttr(geometry+".invertTransform",True)
        self._transaction_changed=True
        return geometry

    def hide_original_face_controllers(self,hide):
        self._require_transaction()
        c=self._cmds
        for node in c.listRelatives("ControlsSetup",allDescendents=True,
                                    fullPath=True,type="transform") or []:
            if re.search(r"Offset_[A-Z]$",node): c.setAttr(node+".visibility",not hide)
        for box in ("ctrlBox","ctrlBox2"):
            if not c.objExists(box): continue
            for node in c.listRelatives(box,children=True,fullPath=True,type="transform") or []:
                c.setAttr(node+".visibility",not hide)
        self._transaction_changed=True

    def constrain_original_face(self,driver,driven,maintain_offset=False,*,opm=None,pick=False,force_matrix=True):
        """Shared asParentConstraint -FMM path, including explicit DM mode."""
        from dataclasses import replace
        from adv_py.core.body_parent_constraint import plan_body_parent_constraint
        c=self._cmds
        driver_path=(c.ls(driver,long=True) or [None])[0]
        driven_path=(c.ls(driven,long=True) or [None])[0]
        if not driver_path or not driven_path: raise ValueError("Face 约束节点缺失")
        plan=plan_body_parent_constraint(replace(self.capture_parent_constraint_input(
            driver_path,driven_path,maintain_offset),force_mult_matrix=force_matrix,
            include_pick_matrix=pick,use_offset_parent_matrix=(
                self.face_use_offset_parent_matrix() if opm is None else opm)))
        self.preflight_parent_constraint(plan)
        self.create_parent_constraint(plan)
        return plan

    def project_original_face_control(self,control):
        """asFacePlaceCtrlByProjection, source 46224–46272."""
        from math import sin,cos,radians
        c=self._cmds
        stem,side=control.rsplit("_",1)
        angle=radians(float(c.getAttr(stem+"Offset_"+side+".ry")))
        direction=(sin(angle)*(-1 if side=="R" else 1),0,cos(angle))
        projected=c.polyProjectCurve(control,"allHeadCombinedLayer",constructionHistory=True,
            direction=direction,pointsOnEdges=False,tolerance=.01)
        temp=c.createNode("transform",name="faceProjectionCVTemp#",parent=control)
        maximum=-999.
        try:
            for curve in c.listRelatives(projected[0],children=True,type="transform") or []:
                count=int(c.getAttr(curve+".spans"))+int(c.getAttr(curve+".degree"))
                for index in range(count):
                    position=c.xform(curve+f".cv[{index}]",query=True,worldSpace=True,translation=True)
                    c.xform(temp,worldSpace=True,translation=position)
                    maximum=max(maximum,float(c.getAttr(temp+".tz")))
        finally:
            c.delete(temp,projected[0])
        scale=c.xform(control,query=True,worldSpace=True,scale=True)[0]
        c.move(0,0,maximum*scale,control+".cv[*]",relative=True,
               objectSpace=True,worldSpaceDistance=True)

    def create_original_face_pp(self,position,name,side,kind,*,create_joint=False,
                                bind_skin=None,attach=False,legacy_orient=False):
        """asCreatePP: projected control, matrix joint, subtracter and attacher."""
        self._require_transaction()
        c=self._cmds
        if isinstance(position,str): position=c.xform(position,query=True,worldSpace=True,translation=True)
        control=self.create_original_face_controller(name,side,kind)
        offset=name+"Offset"+side; sdk="SDK"+control
        joint=name+"Joint"+side; joint_offset=name+"JointOffset"+side
        c.xform(offset,worldSpace=True,translation=position)
        if create_joint:
            c.createNode("transform",name=joint_offset,parent="FaceJoint_M")
            c.createNode("joint",name=joint,parent=joint_offset)
            c.setAttr(joint+".segmentScaleCompensate",False)
            c.xform(joint_offset,worldSpace=True,translation=position)
            self.constrain_original_face(control,joint,True)
        if bind_skin:
            raw=getattr(c,"raw",c)
            raw.skinCluster(self.scene_address(bind_skin),edit=True,
                addInfluence=self.scene_address(joint),lockWeights=False,weight=0)
        c.parent(offset,"SideReverse"+side,absolute=True)
        c.xform(offset,objectSpace=True,rotation=(0,0,0),scale=(1,1,1))
        fit=self._fit(required=True)
        skip=c.objExists(fit+".SkipFaceJointOrient") and c.getAttr(fit+".SkipFaceJointOrient")
        if side!="_M" and c.objExists("FaceControlOrient") and not skip:
            c.delete(c.normalConstraint("FaceControlOrient",offset,aimVector=(0,0,1),
                upVector=(0,1,0),worldUpType="vector",worldUpVector=(0,1,0)))
        self.project_original_face_control(control)
        if create_joint:
            c.parent(joint,"FaceJoint_M",absolute=True)
            c.connectAttr("FaceJoint_M.worldInverseMatrix[0]",name+"JointMM"+side+".matrixIn[2]",force=True)
            c.xform(joint,objectSpace=True,translation=(0,0,0))
            c.delete(joint_offset)
            temp=c.createNode("transform",name="facePPMatrixTemp#",parent=control)
            c.xform(temp,objectSpace=True,translation=(0,0,0),rotation=(0,0,180 if legacy_orient else 0))
            matrix=c.xform(temp,query=True,objectSpace=True,matrix=True)
            c.delete(temp)
            c.setAttr(name+"JointMM"+side+".matrixIn[0]",*matrix,type="matrix")
        if attach:
            attacher=c.createNode("transform",name=name+"Attach"+side,parent=offset)
            c.parent(sdk,attacher,absolute=True)
            plus=c.createNode("plusMinusAverage",name=name+"PMA"+side)
            c.connectAttr(control+".translate",plus+".input3D[0]")
            c.connectAttr(sdk+".translate",plus+".input3D[1]")
            subtract=c.createNode("transform",name=name+"Subtract"+side,parent=sdk)
            multiply=c.createNode("multiplyDivide",name=name+"SubtractMPD"+side)
            c.setAttr(multiply+".input1",-1,-1,-1)
            c.connectAttr(plus+".output3D",multiply+".input2")
            c.connectAttr(multiply+".output",subtract+".translate")
            c.parent(control,subtract,absolute=True)
        if attach and create_joint:
            c.delete(name+"JointMM"+side)
            # DM mode leaves its decomposer connected after deleting the MM.
            # Remove its transform inputs before installing the original PMA.
            dm=name+"JointDM"+side
            if c.objExists(dm): c.delete(dm)
            c.setAttr(joint+".offsetParentMatrix",1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,type="matrix")
            c.createNode("transform",name=joint_offset,parent=offset)
            if side=="_R": c.setAttr(joint_offset+".sx",-1)
            c.parent(joint_offset,world=True)
            if side=="_R": c.setAttr(joint_offset+".sx",-c.getAttr(joint_offset+".sx"))
            c.parent(joint,joint_offset,relative=True)
            c.setAttr(joint+".rotate",0,0,0)
            plus=c.createNode("plusMinusAverage",name=name+"JointPMAt"+side)
            c.connectAttr(control+".translate",plus+".input3D[0]")
            c.connectAttr(sdk+".translate",plus+".input3D[1]")
            if c.objExists(name+"Follow"+side):
                c.connectAttr(name+"Follow"+side+".translate",plus+".input3D[2]")
            c.connectAttr(plus+".output3D",joint+".translate",force=True)
        return control

    def shape_original_face_half_moon(self,control,rotation=0,outer_lid=False):
        """asFaceHalfMoonCurve CV deformation; no replacement icon geometry."""
        c=self._cmds
        def point(index): return c.xform(control+f".cv[{index}]",query=True,worldSpace=True,translation=True)
        for source,target,factor in ((7,3,8),(0,2,4),(6,4,4)):
            a,b=point(source),point(target)
            c.xform(control+f".cv[{target}]",worldSpace=True,translation=(
                (a[0]*factor+b[0])/(factor+1),(a[1]*3+b[1])/4,(a[2]*3+b[2])/4))
        for index in (1,5):
            a,b=point(index),point(3)
            c.xform(control+f".cv[{index}]",worldSpace=True,translation=((a[0]*4+b[0])/5,a[1],a[2]))
        pivot=c.xform(control,query=True,worldSpace=True,translation=True)
        c.scale(.8,1,1,control+".cv[*]",relative=True,pivot=pivot)
        if outer_lid: c.scale(.75,1.5,1,control+".cv[*]",relative=True,pivot=pivot)
        c.rotate(0,0,rotation,control+".cv[*]",relative=True,objectSpace=True,pivot=pivot)

    def original_face_output_bw(self,plug):
        c=self._cmds
        node,attr=plug.split(".",1)
        attr=c.attributeQuery(attr,node=node,longName=True)
        plug=node+"."+attr
        bw="bw"+node+"_"+attr
        if not c.objExists(bw):
            c.createNode("blendWeighted",name=bw)
            face=(c.objExists("FaceAllSet") and c.sets(node,isMember="FaceAllSet")) or c.objExists("FaceBuildingSets")
            group="FaceAllSet" if face else "AllSet"
            if c.objExists(group) and c.sets(node,isMember=group):c.sets(bw,add=group)
        if not c.isConnected(plug,bw+".input[0]",ignoreUnitConversion=True):
            c.connectAttr(plug,bw+".input[0]",force=True)
        return bw+".output"

    def add_original_face_sdk(self,driver,driven,driver_value,driven_value):
        """asDsSdk additive keys, scale baseline, output BW and cycle infinity."""
        c=self._cmds
        start=1. if driven.rsplit(".",1)[-1] in ("sx","sy","sz","scaleX","scaleY","scaleZ") else 0.
        value=round(float(driven_value),3)
        if value==start or not c.objExists(driven): return
        node,attr=driven.split(".",1)
        driver_node,driver_attr=driver.split(".",1)
        driver_attr=self.original_face_sdk_attribute(driver_node,driver_attr)
        attr_root=attr.split("[",1)[0]
        attr=c.attributeQuery(attr_root,node=node,longName=True)+attr[len(attr_root):]
        driver=driver_node+"."+driver_attr
        driver_bw="bw"+driver_node+"_"+driver_attr
        if c.objExists(driver_bw): driver=driver_bw+".output"
        direct_bw=c.nodeType(node)=="blendWeighted"
        bw=node if direct_bw else "bw"+node+"_"+attr
        if not direct_bw and not c.objExists(bw):
            incoming=c.listConnections(driven,source=True,destination=False,plugs=True) or []
            c.createNode("blendWeighted",name=bw)
            if incoming:
                c.disconnectAttr(incoming[0],driven)
                c.connectAttr(incoming[0],bw+".input[0]")
            c.connectAttr(bw+".output",driven,force=True)
        # Source asDsSdk redirects a non-SDK control through its output BW
        # and allocates a fresh input on each call. SDK transforms retain
        # same-driver curve updates on their driven channel.
        if not direct_bw and not node.rsplit("|",1)[-1].rsplit(":",1)[-1].startswith("SDK"):
            direct_bw=True
            attr="input"
        indices=c.getAttr(bw+".input",multiIndices=True) or []
        curves=c.listConnections(bw+".input",source=True,destination=False,type="animCurve",skipConversionNodes=True) or []
        existing=None
        for curve in curves:
            sources=c.listConnections(curve+".input",source=True,destination=False,plugs=True,skipConversionNodes=True) or []
            if driver in sources: existing=curve; break
        if direct_bw and "[" not in attr:
            destination=self.next_original_face_bw_input(bw)
        elif direct_bw:
            destination=driven
        elif existing:
            destination=(c.listConnections(existing+".output",source=False,destination=True,plugs=True) or [None])[0]
        else:
            destination=self.next_original_face_bw_input(bw)
            if start and not destination.endswith("[0]"): value-=1; start-=1
        if c.objExists("ARKitQuickConnecting"):
            destination=driven
        before=set(c.listConnections(bw+".input",source=True,destination=False,
                                     type="animCurve",skipConversionNodes=True) or [])
        keys=((0,start),(driver_value,value))
        if c.objExists("ARKitQuickConnecting"):
            self.set_original_face_sdk_keys(driver,destination,keys)
        else:
            for dv,v in keys:
                c.setDrivenKeyframe(destination,currentDriver=driver,driverValue=dv,value=v,
                                    inTangentType="linear",outTangentType="linear")
        # asDsSdk compares curves on the ensured BW, not the target channel.
        # Quick SDK transforms may be behind an existing BW/unitConversion;
        # querying the target would miss their new curves and infinity flags.
        after=c.listConnections(bw+".input",source=True,destination=False,
                                type="animCurve",skipConversionNodes=True) or []
        for curve in after:
            if curve not in before:
                leaf=node.rsplit("|",1)[-1].rsplit(":",1)[-1]
                if leaf.startswith("SDK"):
                    curve=c.rename(curve,leaf+"_"+attr)
                c.setAttr(curve+".preInfinity",4); c.setAttr(curve+".postInfinity",4)
        self._transaction_changed=True

    def original_face_fit_animation(self,object_attr,value=0):
        """asFaceFitAnim neutral/full pose keys at 0 and 30."""
        c=self._cmds
        if not c.objExists(object_attr): return
        node=object_attr.split(".",1)[0]
        raw=getattr(c,"raw",c)
        raw.showHidden(self.scene_address(node),above=True)
        if "." in object_attr:
            attr=object_attr.rsplit(".",1)[1]
            default=1 if attr in ("sx","sy","sz","scaleX","scaleY","scaleZ") else 0
            for frame,target in ((0,default),(30,value)):
                c.setKeyframe(object_attr,shape=False,time=frame,value=target)
        else:
            for channel in ("t","r","s"):
                for axis in "xyz":
                    for frame in (0,30):
                        c.setKeyframe(node+"."+channel+axis,shape=False,time=frame,value=1 if channel=="s" else 0)

    def remove_original_face_fit_animations(self):
        """asFaceRemoveFitAnimationsFromOnFaceCtrls, including Values helpers."""
        c=self._cmds
        nodes=c.listRelatives("OnFacecontrols",allDescendents=True,type="transform") or []
        for offset in nodes:
            name=offset.rsplit("|",1)[-1]
            if "Offset_" not in name: continue
            control=name.replace("Offset","")
            if not c.objExists(control): continue
            curves=c.listConnections(control,source=True,destination=False,type="animCurve") or []
            if curves: c.delete(tuple(dict.fromkeys(curves)))
            c.xform(control,objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
        values=[node for node in c.listRelatives("OnFacecontrols",allDescendents=True,type="transform") or []
                if re.search(r"Values_[A-Z]$",node)]
        if values: c.delete(values)

    def finish_original_face_sdk(self,driver_name,driver_side,driver_attr,driver_value):
        """asFaceDsFinish + asFaceStoreAsDsSdk, source 40868–41015.

        Capture right/center fitting channels at frame 30, mirror the source
        rules into SDK transforms or custom-attribute BWs, then remove fitting
        animation. This is shared by subsequent original Face stages.
        """
        self._require_transaction()
        c=self._cmds; raw=getattr(c,"raw",c)
        auto=bool(raw.autoKeyframe(query=True,state=True))
        groups={"_RL":[],"_M":[]}
        for shape in c.listRelatives("OnFacecontrols",allDescendents=True,fullPath=True,type="nurbsCurve") or []:
            parents=c.listRelatives(shape,parent=True,fullPath=True) or []
            if not parents: continue
            control=parents[0].rsplit("|",1)[-1]
            if control.endswith("_L"): continue
            if not c.listConnections(control,source=True,destination=False,type="animCurve"): continue
            group="_RL" if control.endswith("_R") else "_M"
            stem=control[:-2]
            if stem not in groups[group]: groups[group].append(stem)
        if auto: raw.autoKeyframe(state=False)
        try:
            for group,stems in groups.items():
                for stem in stems:
                    sides=("_R","_L") if group=="_RL" else (("_M",) if driver_side=="_M" else ("_R","_L"))
                    value_node=stem+"Values"+("_R" if group=="_RL" else "_M")
                    c.currentTime(30)
                    for side in sides:
                        control=stem+(side if group=="_RL" else "_M")
                        if not c.objExists(control): continue
                        if not c.objExists(value_node):
                            self_parent=(c.listRelatives(control,parent=True) or [None])[0]
                            c.createNode("transform",name=value_node,parent=control)
                            c.parent(value_node,self_parent,absolute=True)
                    c.currentTime(0)
                    first_control=stem+("_R" if group=="_RL" else "_M")
                    if not c.objExists(first_control): continue
                    c.delete(first_control,staticChannels=True)
                    channels=[]
                    for attr in c.listAttr(first_control,keyable=True) or []:
                        animated=bool(c.listConnections(first_control+"."+attr,source=True,destination=False,type="animCurve"))
                        if not animated: continue
                        standard=c.attributeQuery(attr,node=value_node,exists=True)
                        value=c.getAttr(value_node+"."+attr) if standard else c.getAttr(first_control+"."+attr,time=30)
                        channels.append((attr,standard,value))
                    for side in sides:
                        control=stem+(side if group=="_RL" else "_M")
                        if not c.objExists(control): continue
                        driven_driver=driver_name+("_M" if driver_side=="_M" else side)+"."+driver_attr
                        drive_value=1 if driver_name=="ctrlLips" and driver_side=="_M" and driver_attr=="tx" and side=="_L" else driver_value
                        for attr,standard,value in channels:
                            current=value
                            if group=="_M" and side=="_L" and attr in ("translateX","rotateY","rotateZ"): current=-current
                            c.setAttr(control+"."+attr,1 if attr in ("scaleX","scaleY","scaleZ") else 0)
                            if driver_name.startswith("ctrlMouth") and driver_name+"_M."+driver_attr!="ctrlMouth_M.ty":
                                vertical=attr in ("translateY","rotateZ")
                                if driver_attr=="tx" and vertical or driver_attr=="ty" and not vertical: continue
                            if standard:
                                self.add_original_face_sdk(driven_driver,"SDK"+control+"."+attr,drive_value,current)
                            else:
                                bw="bw"+control+"_"+attr
                                if c.objExists(bw):
                                    self.add_original_face_sdk(driven_driver,control+"."+attr,drive_value,current)
            self.remove_original_face_fit_animations()
        finally:
            if auto: raw.autoKeyframe(state=True)
        self._transaction_changed=True

    def mirror_original_face_controls(self,connect):
        """asFaceMirrorConnectCtrls copies channels directly in mirrored spaces."""
        c=self._cmds
        for offset in c.listRelatives("OnFacecontrols",allDescendents=True,type="transform") or []:
            leaf=offset.rsplit("|",1)[-1]
            if not leaf.endswith("Offset_R"): continue
            right=leaf.replace("Offset",""); left=right[:-2]+"_L"
            if not c.objExists(left): continue
            for attr in c.listAttr(right,keyable=True) or []:
                if not c.attributeQuery(attr,node=left,exists=True): continue
                source=right+"."+attr; dest=left+"."+attr
                if connect: c.connectAttr(source,dest)
                elif c.isConnected(source,dest): c.disconnectAttr(source,dest)

    def remove_original_face_ctrl_box_fit_animation(self):
        """asFaceRemoveFitAnimFromCtrlBox resets each unlocked keyable channel."""
        c=self._cmds
        for control in c.listRelatives("ctrlBox",allDescendents=True,type="transform") or []:
            if control.rsplit("|",1)[-1].startswith("ctrlBox"): continue
            curves=c.listConnections(control,source=True,destination=False,type="animCurve") or []
            if curves: c.delete(tuple(dict.fromkeys(curves)))
            for attr in c.listAttr(control,keyable=True) or []:
                if not c.getAttr(control+"."+attr,lock=True): c.setAttr(control+"."+attr,0)

    def finish_original_face_fit_stage(self,stage,driver,side,attribute,value,visible_boxes=()):
        """Original idempotent stage-finish order, without executing any MEL."""
        c=self._cmds; marker="FaceBuildInProgress."+stage+"Finish"
        if c.objExists(marker): return False
        c.addAttr("FaceBuildInProgress",longName=stage+"Finish",attributeType="bool",defaultValue=True)
        self.mirror_original_face_controls(False)
        self.remove_original_face_ctrl_box_fit_animation()
        self.finish_original_face_sdk(driver,side,attribute,value)
        self.hide_original_face_controllers(True)
        for box in visible_boxes: c.setAttr(box+".visibility",True)
        return True

    def reset_original_face_joint_matrix_scale(self,joint):
        """asOPMScaleReset: remove control world scale from the joint MM offset."""
        c=self._cmds; stem,side=joint.rsplit("_",1); side="_"+side
        opm=self.face_use_offset_parent_matrix()
        plug=joint+".offsetParentMatrix" if opm else stem+"DM"+side+".inputMatrix"
        matrix=self.original_face_matrix_values(plug)
        if .999<float(matrix[10])<1.001: return
        inverse=self.original_face_matrix_values("SideReverse"+side+".worldInverseMatrix[0]")
        nodes=c.listConnections(plug,source=True,destination=False,type="multMatrix") or []
        if not nodes: raise ValueError("Face OPM Scale Reset 缺少 MultMatrix："+joint)
        mm=nodes[0]; first=mm+".matrixIn[0]"
        incoming=c.listConnections(first,source=True,destination=False,plugs=True) or []
        if incoming:
            indices=c.getAttr(mm+".matrixIn",multiIndices=True) or []
            for index in sorted(indices,reverse=True):
                old=mm+f".matrixIn[{index}]"; new=mm+f".matrixIn[{index+1}]"
                connection=c.listConnections(old,source=True,destination=False,plugs=True) or []
                value=self.original_face_matrix_values(old)
                if connection:
                    c.disconnectAttr(connection[0],old); c.connectAttr(connection[0],new,force=True)
                else: c.setAttr(new,*value,type="matrix")
            value=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        else: value=list(self.original_face_matrix_values(first))
        for index in (0,5,10): value[index]=inverse[index]
        c.setAttr(first,*value,type="matrix")
