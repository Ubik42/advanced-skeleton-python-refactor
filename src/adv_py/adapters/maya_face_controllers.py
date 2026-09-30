"""Shared original Face controller and two-space follow graph builders."""
from __future__ import annotations
import re

class MayaFaceControllersMixin:
    def face_use_offset_parent_matrix(self):
        c=self._cmds
        fit=c.ls("FitSkeleton",long=True,type="transform") or []
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
