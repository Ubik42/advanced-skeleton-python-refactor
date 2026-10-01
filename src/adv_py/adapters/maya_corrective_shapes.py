"""Original corrective discovery, sculpt mode and single-target operations."""
from contextlib import nullcontext
from adv_py.core.corrective_shapes import (CorrectiveShapeOptions,CorrectiveTarget,
    corrective_round,corrective_alias,corrective_object_name)
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_original_build import MayaOriginalFaceBuildHost
from .maya_corrective_apply import MayaCorrectiveApplyMixin
from .maya_corrective_softmods import MayaCorrectiveSoftModsMixin
from .maya_corrective_catalog import MayaCorrectiveCatalogMixin
from .maya_corrective_curves import MayaCorrectiveCurvesMixin
from .maya_corrective_identity import MayaCorrectiveIdentityMixin


class MayaCorrectiveShapesHost(MayaCorrectiveIdentityMixin,MayaCorrectiveCurvesMixin,MayaCorrectiveApplyMixin,MayaCorrectiveSoftModsMixin,
                               MayaCorrectiveCatalogMixin,MayaOriginalFaceBuildHost):
    def _corrective_raw(self):
        return getattr(self._cmds,"raw",self._cmds)

    def _corrective_creation_context(self):
        return self._cmds._creation_namespace() if hasattr(self._cmds,"_creation_namespace") else nullcontext()

    def _corrective_mesh(self, name):
        c=self._cmds
        raw=self._corrective_raw()
        if name=="FaceCorrective" and c.objExists(name):
            return self.scene_address(name)
        bs=name+"Corrective"
        if c.objExists(bs):
            # Query the actual deformer attachment: Maya updates this graph on
            # import, reference and rename, unlike a stored string path.
            raw=self._corrective_raw()
            shapes=raw.blendShape(self.scene_address(bs),query=True,geometry=True) or []
            if len(shapes)==1:
                parents=raw.listRelatives(shapes[0],parent=True,fullPath=True) or []
                if len(parents)==1:
                    return self._original_bs_physical_address(parents[0])
            if c.objExists(bs+".advPyOriginalDeformObject"):
                return c.getAttr(bs+".advPyOriginalDeformObject")
        paths=raw.ls(self.scene_address(name),long=True,type="transform") or []
        if len(paths)!=1:
            raise FitSkeletonValidationError("Corrective 来源网格不存在或不唯一："+name)
        return self._original_bs_physical_address(paths[0])

    def _corrective_shape(self, mesh):
        shapes=self._corrective_raw().listRelatives(mesh,shapes=True,noIntermediate=True,fullPath=True,type="mesh") or []
        if len(shapes)!=1:
            raise FitSkeletonValidationError("Corrective 需要唯一可见 Mesh Shape")
        return shapes[0]

    def _corrective_source_object(self, deform):
        c=self._cmds
        if deform=="FaceCorrective":
            plugs=c.listConnections("FaceCorrective.originalDeformObj",source=True,destination=False) or []
            if len(plugs)!=1:
                raise FitSkeletonValidationError("FaceCorrective 缺少原始网格来源")
            return self.scene_address(plugs[0])
        return self._corrective_mesh(deform)

    def capture_original_corrective_create(self, options):
        c=self._cmds
        raw=self._corrective_raw()
        selected=raw.ls(selection=True,objectsOnly=True,long=True) or []
        if len(selected)!=1:
            raise FitSkeletonValidationError("请选择一个需要修正的角色网格")
        mesh=selected[0]
        if raw.nodeType(mesh)=="mesh":
            mesh=raw.listRelatives(mesh,parent=True,fullPath=True)[0]
        if "__" in mesh.rsplit("|",1)[-1]:
            raise FitSkeletonValidationError("选择的是 Corrective 目标，请选择角色网格")
        self._corrective_shape(mesh)
        drivers=[]
        for plug,neutral in self.original_corrective_build_pose_rows():
            if not c.objExists(plug):
                continue
            node,attr=plug.rsplit(".",1)
            attr=c.attributeQuery(attr,node=node,longName=True)
            node=self._original_restore_leaf(node)
            if node.startswith(("FKExtra","FKIK")):
                continue
            if abs(float(c.getAttr(plug))-neutral)>.001:
                drivers.append(node+"."+attr)
        if drivers[:2] in (["ctrlMouthCorner_R.tx","ctrlMouthCorner_R.ty"], ["ctrlMouthCorner_R.translateX","ctrlMouthCorner_R.translateY"]):
            drivers=[]
            for attr in ("smile","frown","narrowSmile","narrowFrown"):
                if c.getAttr("ctrlMouthCorner_R."+attr)>0:
                    drivers=["ctrlMouthCorner_R."+attr]
        if not drivers:
            raise FitSkeletonValidationError("没有驱动属性，当前仍是构建姿态")
        if not c.objExists("CustomOrientsDisabled"):
            for plug in drivers:
                node=plug.split(".",1)[0]
                if c.objExists("CustomOrient"+node):
                    raise FitSkeletonValidationError("请先禁用控制器自定义朝向："+node)
        q_rotations=options.q_rotations
        if not q_rotations and (drivers[0].endswith(".rotateX") or len(drivers)>1):
            fit_control=drivers[0].split(".",1)[0]
            fit_joint=self.original_corrective_joint_for_fk(fit_control)[:-2]
            if c.objExists(fit_joint+".twistJoints") or c.objExists(fit_joint+".inbetweenJoints"):
                q_rotations=True
        key=self._original_restore_leaf(mesh)
        return {"mesh":self._original_bs_physical_address(mesh),"deform":key,"drivers":tuple(drivers),
                "options":CorrectiveShapeOptions(q_rotations,options.use_soft_mods,options.mirror)}

    def create_original_corrective_shape(self, source):
        self._require_transaction()
        c=self._cmds
        self._transaction_changed=True
        options=source["options"]
        raw=self._corrective_raw()
        raw.dgdirty(allPlugs=True)
        self.prepare_original_corrective_softmods(options.use_soft_mods)
        drivers=[]
        for plug in source["drivers"]:
            control,channel=plug.rsplit(".",1)
            non_fk=self.original_corrective_joint_for_fk(control)+"."+channel
            if c.objExists(non_fk):
                # Resolve the deformed Body receiver before sampling. Native
                # Twist/Part constraints can otherwise leave a cached FK
                # rotation in driver discovery during viewport-free baking.
                c.getAttr(non_fk)
                plug=non_fk
            node,attr=plug.rsplit(".",1)
            attr=self.original_opm_compatible_driver_attr(node,attr)
            drivers.append(node+"."+attr)
        node,attribute=drivers[0].rsplit(".",1)
        direct_attribute=attribute
        value=c.getAttr(drivers[0]);indirect=0.
        if options.q_rotations and attribute.startswith("rotate"):
            self.create_original_q_rotate_attrs(node)
            raw.dgdirty(allPlugs=True)
            c.getAttr(node+".matrix")
            for index,plug in enumerate(drivers):
                if ".rotate" in plug:
                    drivers[index]=plug.replace(".rotate",".qRotate",1)
                    attribute=attribute.replace("rotate","qRotate",1)
                    indirect=value
                    value=c.getAttr(node+"."+attribute)
                    if attribute.endswith("X") and c.objExists("TwistBalancer"+node):
                        indirect=c.getAttr("TwistBalancer"+node+"."+direct_attribute)
            if len(drivers)>1:
                for axis in "XYZ":
                    plug=node+".qRotate"+axis
                    if abs(c.getAttr(plug))>.001 and plug not in drivers:
                        drivers.append(plug)
                        drivers.sort()
        if len(drivers)>1:
            attribute=self.create_original_blended_attribute(drivers,"")
            value=c.getAttr(node+"."+attribute)
        value=corrective_round(value)
        if abs(value)<.001:
            raise FitSkeletonValidationError("当前姿态的 Corrective 驱动为零："+node+"."+attribute+
                "。请核对 Twist／FKIK 的原版驱动；未创建零范围 SDK。")
        name=corrective_object_name(source["deform"],node,attribute,value)
        if c.objExists(name):
            raise FitSkeletonValidationError("Corrective 目标已存在："+name)
        inbetween=self.original_corrective_inbetween(source["deform"],node,attribute,value)
        self.duplicate_original_corrective(name,source["mesh"])
        self._corrective_target_metadata(name,value,inbetween,indirect,source["mesh"])
        return {"target":name,"driver":node+"."+attribute,"value":value,"inbetween":inbetween,"q_rotations":options.q_rotations}

    def _corrective_target_metadata(self, name, value, inbetween, indirect, geometry):
        c=self._cmds
        c.addAttr(name,longName="CorrectiveShapes",attributeType="bool",defaultValue=True)
        for attr,amount in (("driverValue",value),("inbetweenValue",inbetween),("indirectDriverValue",indirect)):
            c.addAttr(name,longName=attr,attributeType="double",defaultValue=amount,keyable=True)
        c.addAttr(name,longName="advPyOriginalDeformObject",dataType="string")
        c.setAttr(name+".advPyOriginalDeformObject",geometry,type="string")
        c.addAttr(name,longName="advPyOriginalDeformNode",attributeType="message")
        self._corrective_raw().connectAttr(geometry+".message",
            self.scene_address(name)+".advPyOriginalDeformNode")

    def original_corrective_wip_geometry(self, corrective, deform):
        c=self._cmds
        raw=self._corrective_raw()
        if c.objExists(corrective+".advPyOriginalDeformNode"):
            nodes=raw.listConnections(self.scene_address(corrective)+".advPyOriginalDeformNode",
                                     source=True,destination=False) or []
            if len(nodes)==1:
                paths=raw.ls(nodes[0],long=True,type="transform") or []
                if len(paths)==1:
                    return self._original_bs_physical_address(paths[0])
        # Existing saved Python WIPs used only a string path. A bound native
        # corrective deformer provides the authoritative mesh for those scenes.
        if c.objExists(deform+"Corrective"):
            return self._corrective_mesh(deform)
        if c.objExists(corrective+".advPyOriginalDeformObject"):
            stored=c.getAttr(corrective+".advPyOriginalDeformObject")
            if raw.objExists(stored):
                return stored
        return self._corrective_mesh(deform)

    def duplicate_original_corrective(self, name, source):
        c=self._cmds
        raw=self._corrective_raw()
        soft=c.objExists("CorrectiveSoftModsSystem")
        bs=self._original_restore_leaf(source)+"Corrective"
        if soft and c.objExists(bs):
            c.setAttr(bs+".envelope",0)
        copied=source
        if self._original_restore_leaf(source)=="FaceCorrective":
            copied=self._corrective_source_object("FaceCorrective")
        # Source duplicates the currently evaluated mesh after posing and
        # muting its corrective. Pull that graph before copying the output;
        # native parentConstraint/skin caches can otherwise retain the pose
        # used by the preceding batch target in standalone Maya.
        raw.dgdirty(allPlugs=True)
        c.duplicate(copied,name=name)
        if soft and c.objExists(bs):
            c.setAttr(bs+".envelope",1)
        for kind in ("t","r","s"):
            for axis in "xyz":
                c.setAttr(name+"."+kind+axis,lock=False,keyable=True)
        c.setAttr(name+".v",lock=False,keyable=True)
        c.setAttr(name+".v",1)
        if c.listRelatives(name,parent=True):
            c.parent(name,world=True)
        for shape in c.listRelatives(name,shapes=True,fullPath=True) or []:
            if c.nodeType(shape)=="mesh" and c.getAttr(shape+".intermediateObject"):
                c.delete(shape)
        # Duplicated meshes initially share the original Shape's short name.
        # Resolve through the new transform so rename cannot address another
        # model (or fail on the ambiguous polySurfaceShape1 default name).
        shape=c.listRelatives(name,shapes=True,noIntermediate=True,fullPath=True)[0]
        c.rename(shape,name+"Shape")
        group="Group" if c.objExists("Group") else "FaceGroup"
        c.setAttr(group+".v",0)
        physical=raw.ls(copied,long=True)[0]
        body_group=self.scene_address("Group")
        group_paths=raw.ls(body_group,long=True) or []
        if not group_paths or not physical.startswith(group_paths[0]+"|"):
            raw.setAttr(copied+".v",0)
            if not c.objExists(group+".correctiveShapeModeHidden"):
                c.addAttr(group,longName="correctiveShapeModeHidden",dataType="string")
            c.setAttr(group+".correctiveShapeModeHidden",copied,type="string")
            if not c.objExists(group+".advPyCorrectiveHiddenSource"):
                c.addAttr(group,longName="advPyCorrectiveHiddenSource",attributeType="message")
            raw.connectAttr(copied+".message",
                self.scene_address(group)+".advPyCorrectiveHiddenSource",force=True)
        c.select(name,replace=True)
        if soft:
            self.restore_original_corrective_softmod_chain(name)
        else:
            from maya import mel
            mel.eval("SculptGeometryTool;")
        if not raw.headsUpDisplay("HUDCSMMode",query=True,exists=True):
            raw.headsUpDisplay("HUDCSMMode",section=2,block=0,blockSize="medium",label="Corrective 形状编辑模式",labelFontSize="large")
            raw.scriptJob(runOnce=True,event=("deleteAll",self.exit_original_corrective_mode))

    def original_corrective_inbetween(self, deform, driver, attribute, value):
        c=self._cmds
        bs=deform+"Corrective"
        if not c.objExists(bs):
            return 1.
        alias=corrective_alias(driver,attribute,value)
        if alias not in self.original_face_bs_aliases(bs):
            return 1.
        sdk=c.listConnections(bs+"."+alias,source=True,destination=False)[0]
        xs=c.keyframe(sdk,query=True,floatChange=True)
        ys=c.keyframe(sdk,query=True,valueChange=True)
        maximum=xs[-1]
        for x,y in zip(xs,ys):
            if y==1:
                maximum=x
        if abs(maximum)<.001:
            raise FitSkeletonValidationError("已有 Corrective SDK 的完整驱动范围为零："+bs+"."+alias)
        return corrective_round(value/maximum)

    def go_to_original_corrective_pose(self, driver, attribute, value):
        self._require_transaction()
        c=self._cmds
        fk=self.original_corrective_fk_for_joint(driver) if not driver.startswith("IK") else driver
        fit=driver[:-2]
        if c.objExists(fit+".inbetweenJoints"):
            value*=c.getAttr(fit+".inbetweenJoints")+1
        if attribute.startswith("opm"):
            c.setAttr(fk+"."+attribute.removeprefix("opm"),value)
        elif attribute in ("smile","frown","narrowSmile","narrowFrown"):
            x,y={"smile":(1,1),"frown":(1,-1),"narrowSmile":(-1,1),"narrowFrown":(-1,-1)}[attribute]
            c.setAttr(fk+".tx",x);c.setAttr(fk+".ty",y)
        elif not c.getAttr(driver+"."+attribute,settable=True):
            self.set_original_blended_attribute(driver,attribute,value)
            if attribute.startswith("qRotate") and "_" not in attribute:
                controller=self.original_corrective_fk_for_joint(driver)
                c.setAttr(controller+".rotate"+attribute.removeprefix("qRotate"),value)
        else:
            c.setAttr(fk+"."+attribute,value)
        if all(c.objExists(prefix+driver) for prefix in ("FK","FKX","IKX","FKOffset")):
            control=self.find_original_fkik_control("FK"+driver)
            if control and c.objExists(control+".FKIKBlend"):
                c.setAttr(control+".FKIKBlend",0)
        self._transaction_changed=True

    def edit_original_corrective_shape(self, target):
        self._require_transaction()
        c=self._cmds;raw=self._corrective_raw()
        auto=raw.autoKeyframe(query=True,state=True)
        raw.autoKeyframe(state=False)
        try:
            self.go_to_original_corrective_build_pose()
            self.go_to_original_corrective_pose(target.driver_object,target.driver_attribute,target.value)
            geometry=self._corrective_mesh(target.deform_object)
            name=corrective_object_name(target.deform_object,target.driver_object,target.driver_attribute,target.value)
            inbetween=self.original_corrective_inbetween(target.deform_object,target.driver_object,target.driver_attribute,target.value)
            self.duplicate_original_corrective(name,geometry)
            self._corrective_target_metadata(name,target.value,inbetween,0.,geometry)
            raw.dgdirty(allPlugs=True)
            return {"target":name,"inbetween":inbetween}
        finally:
            raw.autoKeyframe(state=auto)
