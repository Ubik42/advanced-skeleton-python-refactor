"""Python scene port of asAdvancedSquash / asOptimizeSquash (ADV 6.925)."""
from __future__ import annotations
from contextlib import contextmanager
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_head_squash import (
    FaceHeadSquashInput, FaceHeadSquashResult,
    HEAD_SQUASH_BOX, HEAD_SQUASH_CONTROLS)
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_eyelid_rig import MayaFaceEyeLidRigHost

class MayaFaceHeadSquashHost(MayaFaceEyeLidRigHost):
    def _squash_one(self,name,kind=None):
        c=self._cmds
        rows=c.ls(name,long=True,**({"type":kind} if kind else {})) or []
        if len(rows)!=1:
            raise FitSkeletonValidationError("HeadSquash 节点缺失或不唯一："+name)
        return rows[0]

    def _squash_shape(self,node,kind):
        rows=self._cmds.listRelatives(node,shapes=True,noIntermediate=True,
                                     fullPath=True,type=kind) or []
        if len(rows)!=1:
            raise FitSkeletonValidationError("HeadSquash Shape 缺失或不唯一："+node)
        return rows[0]

    def capture_head_squash_input(self):
        c=self._cmds
        fit=self._fit(required=True)
        for name,kind in (("FaceDeformationSystem","transform"),
                          ("FaceMotionSystem","transform"),
                          ("FaceControlSet","objectSet"),
                          ("FaceAllSet","objectSet"),
                          ("faceBuildPose","transform")):
            self._squash_one(name,kind)
        face_objects=self.read_face_objects(FacePreRole.FACE)
        if len(face_objects)!=1:
            raise FitSkeletonValidationError("HeadSquash 需要唯一面部网格")
        face=face_objects[0]
        head_name=c.getAttr(fit+".HeadJoint")
        head=self._squash_one(head_name,"joint")
        skin=self.face_skin_cluster(face)
        geometry=[]
        for node in self.read_face_objects(FacePreRole.ALL_HEAD):
            # The original excludes wrapped/wired additions such as eyebrows.
            history=c.listHistory(node,pruneDagObjects=True,levels=4) or []
            if any(c.nodeType(item) in ("wrap","wire") for item in history):
                continue
            geometry.append(node)
        control_shapes=[]
        on_face=c.ls("OnFacecontrols",long=True,type="transform") or []
        if len(on_face)>1:
            raise FitSkeletonValidationError("OnFacecontrols 名称不唯一")
        for root in on_face:
            for shape in c.listRelatives(root,allDescendents=True,fullPath=True,
                                         type=("nurbsCurve","nurbsSurface")) or []:
                source=c.listConnections(shape+".create",source=True,destination=False) or []
                if source and "_" in source[0] and source[0].endswith("TG"):
                    continue
                control_shapes.append(shape)
        # Original also includes the yellow on-face controller shapes, excluding
        # ctrlBox descendants and eye aim controls.
        extra_control_shapes=[]
        for node in c.sets("FaceControlSet",query=True) or []:
            path=self._squash_one(node)
            leaf=path.rsplit("|",1)[-1].rsplit(":",1)[-1]
            if "|ctrlBox|" in path or leaf.startswith("AimEye_"):
                continue
            shapes=c.listRelatives(path,shapes=True,fullPath=True) or []
            if shapes and c.getAttr(shapes[0]+".overrideColor")==17:
                extra_control_shapes.append(shapes[0])
        settings=c.ls("FitSkeleton",long=True,type="transform") or []
        opm=bool(len(settings)==1 and c.attributeQuery("useOffsetParentMatrix",node=settings[0],exists=True)
                 and c.getAttr(settings[0]+".useOffsetParentMatrix"))
        return FaceHeadSquashInput(head,face,skin,tuple(dict.fromkeys(geometry)),
            tuple(dict.fromkeys(control_shapes)),tuple(dict.fromkeys(extra_control_shapes)),
            float(c.getAttr(fit+".faceScale")),
            float(c.xform("FaceFitSkeletonShape.cv[0]",query=True,worldSpace=True,translation=True)[1]),
            float(c.xform("FaceFitSkeletonHeightShape.cv[0]",query=True,worldSpace=True,translation=True)[1]),opm)

    @contextmanager
    def _head_squash_deformer_sets(self):
        """asDeformer temporarily disables component tags for legacy sets."""
        from .maya_face_deformer_sets import original_face_deformer_sets
        with original_face_deformer_sets(self._cmds):
            yield

    def create_head_squash(self,source):
        with self._head_squash_deformer_sets():
            return self._create_head_squash_graph(source)

    def _create_head_squash_graph(self,source):
        self._require_transaction()
        c=self._cmds
        self._transaction_changed=True
        setup=c.createNode("transform",name="SquashSetup",parent="FaceDeformationSystem")
        c.setAttr(setup+".visibility",False,lock=True)
        controls={}
        # Original Top, Base, Middle, Bottom curve sizes and positions.
        base=c.createNode("transform",name="SquashControls")
        c.xform(base,worldSpace=True,translation=(0,source.bottom_y,0))
        for name,offset,y,size in (
            ("squashBase_M",None,source.bottom_y,(1,1,1)),
            ("squashTop_M","squashTopOffset",source.top_y,(1,1,1)),
            ("squashMiddle_M","squashMiddleOffset",source.center_y,(1.5,1,1)),
            ("squashBottom_M","squashBottomOffset",source.bottom_y,(1.5,.1,1.5))):
            curve=c.curve(name=name,degree=1,point=HEAD_SQUASH_BOX,knot=tuple(range(16)))
            c.xform(curve,worldSpace=True,scale=(source.scale/.75,source.scale/5,source.scale/5))
            c.makeIdentity(curve,apply=True,translate=True,rotate=True,scale=True,normal=0)
            if size!=(1,1,1):
                c.scale(*size,curve,relative=True)
                c.makeIdentity(curve,apply=True,translate=True,rotate=True,scale=True,normal=0)
            shape=self._squash_shape(curve,"nurbsCurve")
            c.setAttr(shape+".overrideEnabled",True)
            c.setAttr(shape+".overrideColor",13)
            parent=base if offset is None else c.createNode("transform",name=offset)
            curve=c.parent(curve,parent,relative=True)[0]
            if offset is not None:
                c.xform(parent,worldSpace=True,translation=(0,y,0))
                c.parent(parent,"squashBase_M",absolute=True)
            controls[name]=name
        c.addAttr("squashTop_M",longName="volume",attributeType="double",softMinValue=0,
                  softMaxValue=10,defaultValue=10,keyable=True)
        volume=c.createNode("unitConversion",name="squashTopVolumeUC")
        c.setAttr(volume+".conversionFactor",.1)
        c.connectAttr("squashTop_M.volume",volume+".input")
        for node in ("squashTop_M","squashMiddle_M","squashBase_M"):
            channels=("sx","sy","sz","v")
            if node!="squashBase_M": channels=("rx","ry","rz",*channels)
            for channel in channels: c.setAttr(node+"."+channel,lock=True,keyable=False)
        c.sets(HEAD_SQUASH_CONTROLS,add="FaceControlSet")

        ffd,lattice,rest=c.lattice((*source.geometry,*source.control_shapes),
            divisions=(2,11,2),objectCentered=True,ldv=(2,2,2))
        ffd=c.rename(ffd,"squashFfd")
        lattice=c.rename(lattice,"squashFfdLattice")
        rest=c.rename(rest,"squashFfdBase")
        sets=c.listConnections(ffd+".message",source=False,destination=True,type="objectSet") or []
        if len(sets)!=1:
            raise RuntimeError("HeadSquash 晶格缺少唯一变形集")
        c.rename(sets[0],"squashFfdSet")
        for node in (lattice,rest):
            c.xform(node,worldSpace=True,translation=(0,source.center_y,0))
            c.xform(node,scale=(source.height,source.height,source.height))
            c.scale(1.25,1.25,1.25,node,relative=True)
        c.setAttr(ffd+".outsideLattice",1)
        c.parent(rest,"squashBase_M",absolute=True)
        up=c.createNode("transform",name="squashXup")
        c.setAttr(up+".rotate",90,0,90)
        joints=[]
        for index in range(10):
            row=max(1,index)
            y=float(c.xform(lattice+f".pt[0][{row}][1]",query=True,
                            worldSpace=True,translation=True)[1])
            parent=up if index in (0,1) else joints[-1]
            c.select(parent,replace=True)
            joint=c.joint(name=f"squashIKX{index}",position=(0,y,0),absolute=True)
            joints.append(joint)
        c.setAttr("squashIKX1.segmentScaleCompensate",False)
        handle,effector,curve=c.ikHandle(name="squashIKHandle",createCurve=True,
            numSpans=2,solver="ikSplineSolver",startJoint="squashIKX1",endEffector="squashIKX9")
        c.rename(effector,"squashIKEffector")
        curve=c.rename(curve,"squashIKECurve")
        for index in range(5):
            deformer,cluster_handle=c.cluster(curve+f".cv[{index}]",envelope=1,
                                              name=f"squashIKCluster{index}")
            c.rename(cluster_handle,f"squashIKClusterHandle{index}")
        skin=c.skinCluster((*joints,lattice),toSelectedBones=True,maximumInfluences=3,
                           dropoffRate=4,removeUnusedInfluence=False,name="squashIKSC")[0]
        for index,component in ((0,".pt[0:1][0:1][0:1]"),
                                 *((i,f".pt[0:1][{i}][0:1]") for i in range(2,9)),
                                 (9,".pt[0:1][9:10][0:1]")):
            c.skinPercent(skin,lattice+component,transformValue=[(f"squashIKX{index}",1.0)])
        for child,parent,offset in ((3,4,-.1),(1,0,.1)):
            follower=f"squashIKClusterHandle{child}"
            target=f"squashIKClusterHandle{parent}"
            c.delete(c.pointConstraint(target,follower))
            c.parent(follower,target,absolute=True)
            c.move(0,source.scale*offset,0,follower,relative=True)
        c.parent("squashIKClusterHandle4","squashTop_M",absolute=True)
        c.parent("squashIKClusterHandle2","squashMiddle_M",absolute=True)
        c.parent("squashIKClusterHandle0","squashIKClusterHandle1",
                 "squashIKX0","squashBottom_M",absolute=True)

        info=c.createNode("curveInfo",name="squashIKCurveInfo")
        curve_shape=self._squash_shape(curve,"nurbsCurve")
        c.connectAttr(curve_shape+".worldSpace[0]",info+".inputCurve")
        def divide(name):
            node=c.createNode("multiplyDivide",name=name)
            c.setAttr(node+".operation",2)
            return node
        normalize=divide("squashIKCurveInfoNormalize")
        c.connectAttr(info+".arcLength",normalize+".input1X")
        length=float(c.getAttr(normalize+".input1X"))
        if length<=0: raise RuntimeError("HeadSquash 样条长度为零")
        c.setAttr(normalize+".input2X",length)
        main_scale=divide("squashIKCurveInfoMainScale")
        c.connectAttr(normalize+".outputX",main_scale+".input1X")
        if c.objExists("MainScaleMultiplyDivide"):
            c.connectAttr("MainScaleMultiplyDivide.outputY",main_scale+".input2X")
        scale=divide("squashIKScale")
        c.connectAttr(main_scale+".outputX",scale+".input1X")
        if source.use_offset_parent_matrix:
            dm=c.createNode("decomposeMatrix",name="squashIKCurveInfoMainScaleDM")
            c.connectAttr(source.head+".offsetParentMatrix",dm+".inputMatrix")
            c.connectAttr(dm+".outputScaleX",scale+".input2X")
        else:
            c.connectAttr(source.head+".scaleX",scale+".input2X")
        stretch=c.createNode("multiplyDivide",name="squashIKStretch")
        c.connectAttr(scale+".outputX",stretch+".input2X")
        c.setAttr(stretch+".input1X",float(c.getAttr("squashIKX2.tx")))
        for index in range(1,10): c.connectAttr(stretch+".outputX",f"squashIKX{index}.tx")
        inverse=divide("squashVolume1Over")
        c.setAttr(inverse+".input1X",1)
        c.connectAttr(scale+".outputX",inverse+".input2X")
        power=c.createNode("multiplyDivide",name="squashVolumePow")
        c.setAttr(power+".operation",3)
        c.setAttr(power+".input2X",.5)
        c.connectAttr(inverse+".outputX",power+".input1X")
        blend=c.createNode("blendTwoAttr",name="squashBlendTwo")
        c.setAttr(blend+".input[0]",1)
        c.connectAttr(power+".outputX",blend+".input[1]")
        c.connectAttr(volume+".output",blend+".attributesBlender")
        for index in range(2,9):
            for axis in "yz": c.connectAttr(blend+".output",f"squashIKX{index}.s{axis}")
        c.parent(lattice,curve,handle,setup,absolute=True)
        c.parent("squashIKX1","SquashControls","FaceMotionSystem",absolute=True)
        c.parentConstraint(source.head,"SquashControls",maintainOffset=True)
        c.delete(up)
        for node in ("squashIKX1","squashFfdBase","squashIKHandle","squashIKX0",
                     *(f"squashIKClusterHandle{i}" for i in range(5))):
            c.setAttr(node+".visibility",False,lock=True)
        if c.objExists("ctrlBox.SquashCtrlVis"):
            for control in ("squashTop_M","squashMiddle_M","squashBase_M"):
                shape=self._squash_shape(control,"nurbsCurve")
                c.connectAttr("ctrlBox.SquashCtrlVis",shape+".overrideVisibility")
        # Yellow controls are included after initial bounds and joint placement,
        # exactly as in MEL; they must not enlarge the original lattice bounds.
        if source.extra_control_shapes:
            c.sets(source.extra_control_shapes,add="squashFfdSet")
        c.select("squashTop_M",replace=True)
        return FaceHeadSquashResult(HEAD_SQUASH_CONTROLS,"squashFfdLattice",ffd,skin,
                                   (*source.geometry,*source.control_shapes,*source.extra_control_shapes))

    def register_head_squash_nodes(self,before):
        self._require_transaction()
        c=self._cmds
        created=[]
        for node in c.ls(long=True) or []:
            ids=c.ls(node,uuid=True) or []
            if len(ids)==1 and ids[0] not in before and c.nodeType(node) not in ("objectSet","partition"):
                created.append(node)
        # Include generated deformer sets, because deleting a deformer alone
        # can leave the set behind after a saved-scene round trip.
        for deformer in ("squashFfd","squashIKSC",*(f"squashIKCluster{i}" for i in range(5))):
            created.extend(c.listConnections(deformer,type="objectSet") or [])
        created=tuple(dict.fromkeys(created))
        squash_set=c.sets(empty=True,name="SquashSet")
        c.sets(created,add=squash_set)
        c.sets((*created,squash_set),add="FaceAllSet")
        c.addAttr(squash_set,longName="advPyHeadSquashOwner",dataType="string")
        c.setAttr(squash_set+".advPyHeadSquashOwner","adv_py.head_squash.v1",type="string",lock=True)

    def validate_head_squash(self,result):
        c=self._cmds
        for node in (*HEAD_SQUASH_CONTROLS,"SquashSetup","squashIKSC","squashFfd","SquashSet"):
            self._squash_one(node)
        if tuple(c.getAttr(self._squash_shape(result.lattice,"lattice")+"."+attr)
                 for attr in ("sDivisions","tDivisions","uDivisions"))!=(2,11,2):
            raise RuntimeError("HeadSquash 晶格分段与原版不一致")
        influences=c.skinCluster(result.skin,query=True,influence=True) or []
        leaves={node.rsplit("|",1)[-1].rsplit(":",1)[-1] for node in influences}
        if leaves!={f"squashIKX{i}" for i in range(10)}:
            raise RuntimeError("HeadSquash 晶格 Skin 关节不完整")
        for index in range(1,10):
            if not c.isConnected("squashIKStretch.outputX",f"squashIKX{index}.tx"):
                raise RuntimeError("HeadSquash 拉伸连接不完整")
        for index in range(2,9):
            for axis in "yz":
                if not c.isConnected("squashBlendTwo.output",f"squashIKX{index}.s{axis}"):
                    raise RuntimeError("HeadSquash 体积连接不完整")

    def _head_squash_owned(self):
        c=self._cmds
        rows=c.ls("SquashSet",type="objectSet") or []
        if not rows: return ()
        if len(rows)!=1: raise FitSkeletonValidationError("SquashSet 名称不唯一")
        return tuple(dict.fromkeys(self._squash_one(item) for item in c.sets(rows[0],query=True) or []))

    def delete_head_squash(self):
        self._require_transaction()
        c=self._cmds
        owned=self._head_squash_owned()
        if not owned: return False
        self._transaction_changed=True
        if c.objExists("squashIKCurveInfo"): c.delete("squashIKCurveInfo")
        # Remove dependent Skin/FFD/cluster graphs before their lattice/curve.
        nodes=tuple(node for node in owned if c.objExists(node))
        deformers=tuple(node for node in nodes if c.nodeType(node) in ("skinCluster","ffd","cluster"))
        if deformers: c.delete(deformers)
        remaining=tuple(node for node in nodes if c.objExists(node))
        roots=tuple(node for node in remaining if not any(node.startswith(parent+"|")
                    for parent in remaining if parent!=node))
        if roots: c.delete(roots)
        self.remove_face_build_pose_controls(HEAD_SQUASH_CONTROLS)
        if c.objExists("SquashSet"): c.delete("SquashSet")
        if any(c.objExists(control) for control in HEAD_SQUASH_CONTROLS):
            raise RuntimeError("HeadSquash 删除后仍有控制器")
        return True

    def optimize_head_squash(self):
        self._require_transaction()
        c=self._cmds
        self._squash_one("SquashSetup","transform")
        source=self.capture_head_squash_input()
        head_joints=set(c.listRelatives(source.head,allDescendents=True,
                                       type="joint",fullPath=True) or [])
        head_joints.add(source.head)
        for joint in c.listRelatives("FaceDeformationSystem",allDescendents=True,
                                     type="joint",fullPath=True) or []:
            links=c.listConnections(joint+".worldMatrix",source=False,destination=True,
                                    type="skinCluster") or []
            if source.skin in links: head_joints.add(joint)
        for name in ("EyeRegion_R","EyeRegion_L"):
            head_joints.update(c.ls(name,long=True,type="joint") or [])
        retained=[]; removed=[]
        for index in range(int(c.polyEvaluate(source.face,vertex=True))):
            vertex=source.face+f".vtx[{index}]"
            influences=c.skinPercent(source.skin,vertex,query=True,transform=None,ignoreBelow=.001) or []
            paths=set(c.ls(influences,long=True,type="joint") or [])
            (retained if paths & head_joints else removed).append(vertex)
        self._transaction_changed=True
        if removed:
            raw=getattr(c,"raw",c)
            raw.sets(tuple(self.scene_address(node) for node in removed),
                     remove=self.scene_address("squashFfdSet"))
        if not c.attributeQuery("optimizedSquash",node="SquashSetup",exists=True):
            c.addAttr("SquashSetup",longName="optimizedSquash",attributeType="bool",defaultValue=True)
        c.setAttr("SquashSetup.optimizedSquash",True)
        if retained: c.select(tuple(retained),replace=True)
        else: c.select(clear=True)
        return {"retained_vertices":len(retained),"removed_vertices":len(removed)}

    def include_selected_head_squash(self):
        self._require_transaction()
        c=self._cmds
        self._squash_one("squashFfdSet","objectSet")
        nodes=c.ls(selection=True,flatten=True,long=True) or []
        if not nodes: raise FitSkeletonValidationError("请先选择要加入 HeadSquash 的对象")
        self._transaction_changed=True
        raw=getattr(c,"raw",c)
        raw.sets(tuple(self.scene_address(node) for node in nodes),
                 add=self.scene_address("squashFfdSet"))
        return len(nodes)
