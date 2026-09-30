"""Source component reversal, inverse deformation, mirror and SDK application."""
from adv_py.core.corrective_shapes import corrective_alias,corrective_round
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_corrective_legacy import MayaCorrectiveLegacyMixin

class MayaCorrectiveApplyMixin(MayaCorrectiveLegacyMixin):
    def _corrective_front_blendshape(self, inputs, name):
        raw=self._corrective_raw()
        with self._corrective_creation_context():
            try:
                return raw.blendShape([self.scene_address(node) for node in inputs],name=self.scene_address(name),
                                      frontOfChain=True,suppressDialog=True)[0]
            except (TypeError,RuntimeError):
                return raw.blendShape([self.scene_address(node) for node in inputs],name=self.scene_address(name),frontOfChain=True)[0]

    def _corrective_connect_blendshape(self, delta, deform, geometry):
        c=self._cmds;raw=self._corrective_raw()
        driver,attribute,_=self._original_restore_leaf(delta).split("__")
        value=c.getAttr(delta+".driverValue")
        inbetween=c.getAttr(delta+".inbetweenValue")
        alias=corrective_alias(driver,attribute,value)
        bs=deform+"Corrective"
        if c.objExists(bs):
            aliases=self.original_face_bs_aliases(bs)
            groups=c.getAttr(bs+".inputTarget[0].inputTargetGroup",multiIndices=True) or []
            existing=aliases.index(alias) if alias in aliases else -1
            if existing!=-1 and inbetween==1:
                c.connectAttr(delta+".worldMesh[0]",bs+".inputTarget[0].inputTargetGroup["+str(groups[existing])+"].inputTargetItem[6000].inputGeomTarget",force=True)
                index=groups[existing]
            elif inbetween!=1:
                if existing==-1:
                    raise FitSkeletonValidationError("过渡 Corrective 缺少完整目标："+alias)
                index=groups[existing]
                raw.blendShape(self.scene_address(bs),edit=True,inBetween=True,
                    target=(geometry,index,self.scene_address(delta),inbetween))
                c.setDrivenKeyframe(bs+"."+alias,value=inbetween,driverValue=value,currentDriver=driver+"."+attribute)
            else:
                index=max(groups,default=-1)+1
                raw.blendShape(self.scene_address(bs),edit=True,target=(geometry,index,self.scene_address(delta),1))
        else:
            self._corrective_front_blendshape((delta,geometry),bs)
            c.addAttr(bs,longName="CorrectiveShapes",attributeType="bool",defaultValue=True)
            index=0
        if not c.objExists(bs+".advPyOriginalDeformObject"):
            c.addAttr(bs,longName="advPyOriginalDeformObject",dataType="string")
            c.setAttr(bs+".advPyOriginalDeformObject",geometry,type="string")
        return bs,index,alias

    def _corrective_history_envelopes(self, geometry, *, blendshapes_only=False):
        raw=self._corrective_raw()
        restored=[]
        for node in raw.listHistory(geometry,pruneDagObjects=True) or []:
            if blendshapes_only and raw.nodeType(node)!="blendShape":
                continue
            if raw.objExists(node+".envelope") and (blendshapes_only or raw.getAttr(node+".envelope")):
                raw.setAttr(node+".envelope",0)
                # Original restores active deformation envelopes to one.
                restored.append(node+".envelope")
        return tuple(restored)

    def _corrective_restore_envelopes(self, plugs):
        raw=self._corrective_raw()
        for plug in plugs:
            raw.setAttr(plug,1)

    def _corrective_delta_duplicate(self, geometry, name, value, inbetween):
        c=self._cmds
        c.duplicate(geometry,name=name)
        for kind in ("t","r","s"):
            for axis in "xyz":
                c.setAttr(name+"."+kind+axis,lock=False,keyable=True)
        c.setAttr(name+".v",lock=False,keyable=True)
        if c.listRelatives(name,parent=True):
            c.parent(name,world=True)
        for attr,amount in (("driverValue",value),("inbetweenValue",inbetween)):
            c.addAttr(name,longName=attr,attributeType="double",defaultValue=amount,keyable=True)

    def _corrective_sdk_rotation_tangents(self, destination):
        c=self._cmds
        if "rotate" not in destination and "qRotate" not in destination:
            return
        sdk=c.listConnections(destination,source=True,destination=False)[0]
        values=c.keyframe(sdk,query=True,floatChange=True)
        negative=values[0]<0
        sign=-1 if negative else 1
        if "qRotate" not in destination:
            c.setAttr(sdk+".preInfinity",int(negative))
            c.setAttr(sdk+".postInfinity",int(not negative))
            c.keyTangent(sdk,index=(int(negative),int(negative)),inTangentType="fixed",outTangentType="fixed",inAngle=0,outAngle=0)
        c.keyTangent(sdk,index=(int(not negative),int(not negative)),inTangentType="fixed",outTangentType="fixed",inAngle=.06*sign,outAngle=.06*sign)

    def _corrective_mirror_drivers(self, driver, attribute, value, options):
        c=self._cmds
        side="_L" if driver.endswith("_L") else "_R"
        opposite="_R" if side=="_L" else "_L"
        mirror_driver=driver.replace(side,opposite,1)
        lips_case=driver=="ctrlLips_M" and attribute in ("tx","translateX")
        if not options.mirror or (not lips_case and (mirror_driver==driver or not c.objExists(mirror_driver))):
            return None
        path=(c.ls(driver,long=True) or [driver])[0]
        joystick="|ctrlBox|" in path or "|ctrlBox|" in path.replace(self.namespace+":" if self.namespace else "","")
        mirror_value=value
        if (attribute=="translateX" and not joystick) or (driver.startswith("FK") and attribute.startswith("translate")) or lips_case:
            mirror_value=-value
        mirror_attribute=self.original_opm_compatible_driver_attr(mirror_driver,attribute)
        if attribute.startswith("qRotate") and not c.objExists(mirror_driver+".qRotateX"):
            self.create_original_q_rotate_attrs(mirror_driver)
        if "_" in attribute:
            drivers=self.set_original_blended_attribute(driver,attribute,0,drivers_only=True)
            pose=self.capture_original_control_pose()
            mirrored=[]
            for index,plug in enumerate(drivers):
                mirror_plug=plug.replace(side,opposite,1)
                amount=c.getAttr(plug)
                if attribute.startswith("qRotate"):
                    obj=plug.rsplit(".",1)[0]
                    fk="FK"+obj if c.objExists("FK"+obj) else obj
                    other=fk.replace(side,opposite,1)
                    if index==0:
                        rotation=c.getAttr(fk+".r")[0]
                        c.setAttr(fk+".r",0,0,0,type="float3")
                        c.setAttr(other+".r",*rotation,type="float3")
                else:
                    c.setAttr(plug,0)
                    if (mirror_plug.endswith(".translateX") and not joystick) or (c.objExists("FK"+driver) and ".translate" in mirror_plug):
                        amount=-amount
                    c.setAttr(mirror_plug,amount)
                mirrored.append(mirror_plug)
            mirror_attribute=self.create_original_blended_attribute(mirrored,"")
            self.restore_original_control_pose(pose)
        return mirror_driver,mirror_attribute,mirror_value

    def connect_original_corrective_shape(self, options):
        self._require_transaction()
        c=self._cmds;raw=self._corrective_raw()
        roots=c.ls(assemblies=True) or []
        wips=[node for node in roots if c.objExists(node+".driverValue")]
        if not wips:
            raise FitSkeletonValidationError("场景中没有待应用的 Corrective 网格")
        corrective=wips[-1]
        if c.ls("asDSDriverEdit_*",type="animCurve") and raw.currentTime(query=True)!=30:
            raise FitSkeletonValidationError("Corrective 带测试动画，请先切到第 30 帧")
        deform,driver,attribute,_=self._original_restore_leaf(corrective).split("__")
        self._transaction_changed=True
        attribute=self.original_opm_compatible_driver_attr(driver,attribute)
        geometry=c.getAttr(corrective+".advPyOriginalDeformObject") if c.objExists(corrective+".advPyOriginalDeformObject") else self._corrective_mesh(deform)
        original=self._corrective_source_object(deform) if deform=="FaceCorrective" else geometry
        value=c.getAttr(corrective+".driverValue")
        inbetween=c.getAttr(corrective+".inbetweenValue")
        delete_mode=c.objExists("DeleteCorrectiveShape")
        delta=corrective_alias(driver,attribute,value)
        self._transaction_changed=True
        auto=raw.autoKeyframe(query=True,state=True)
        raw.autoKeyframe(state=False)
        raw.setToolTo("selectSuperContext")
        try:
            mirror=self._corrective_mirror_drivers(driver,attribute,value,options)
            mirror_delta=corrective_alias(*mirror) if mirror else None
            self.store_original_corrective_softmod_chain(corrective)
            restore=self._corrective_history_envelopes(geometry)
            if "asFaceBS" in [self._original_restore_leaf(node) for node in raw.listHistory(geometry,pruneDagObjects=True) or []]:
                if not c.objExists("FaceCorrective"):
                    c.duplicate(geometry,name="FaceCorrective")
                    aliases=self.original_face_bs_aliases("asFaceBS")
                    raw.blendShape(self.scene_address("asFaceBS"),edit=True,target=(geometry,len(aliases),self.scene_address("FaceCorrective"),1))
                    if not c.objExists("asFaceBS.CorrectiveShapes"):
                        c.addAttr("asFaceBS",longName="CorrectiveShapes",attributeType="bool",defaultValue=True)
                    c.setAttr("asFaceBS.FaceCorrective",1)
                    c.addAttr("FaceCorrective",longName="originalDeformObj",attributeType="message")
                    raw.connectAttr(original+".message",self.scene_address("FaceCorrective.originalDeformObj"))
                deform="FaceCorrective"
                geometry=self.scene_address("FaceCorrective")
            self._corrective_delta_duplicate(geometry,delta,value,inbetween)
            if mirror and not delete_mode:
                self._corrective_delta_duplicate(geometry,mirror_delta,mirror[2],inbetween)
            self._corrective_restore_envelopes(restore)
            reverse=delta+"_componentReverse"
            c.duplicate(original,name=reverse)
            if c.listRelatives(reverse,parent=True):
                c.parent(reverse,world=True)
            self._corrective_front_blendshape((corrective,original,reverse),reverse+"BS")
            c.setAttr(reverse+"BS.w[0]",1);c.setAttr(reverse+"BS.w[1]",1)
            bs=deform+"Corrective"
            if "_" in attribute and c.objExists(bs):
                for alias in self.original_face_bs_aliases(bs):
                    if alias!=delta:
                        c.setAttr(bs+"."+alias,0)
            raw.delete(self.scene_address(reverse),constructionHistory=True)
            self._corrective_front_blendshape((reverse,corrective),reverse+"BS2")
            c.setAttr(reverse+"BS2.w[0]",1)
            raw.delete(self.scene_address(corrective),constructionHistory=True)
            self._corrective_restore_envelopes(restore)
            c.delete(reverse)
            raw.dgdirty(allPlugs=True)
            bs,index,alias=self._corrective_connect_blendshape(delta,deform,geometry)
            if alias in self.original_face_bs_aliases(bs):
                c.setAttr(bs+"."+alias,1)
            position=c.xform(corrective,query=True,worldSpace=True,translation=True)
            c.xform(corrective,worldSpace=True,translation=raw.xform(geometry,query=True,worldSpace=True,translation=True))
            pose=self.capture_original_control_pose()
            blends=[(plug,value) for plug,value in pose if plug.endswith(".FKIKBlend")]
            self.go_to_original_corrective_build_pose()
            neutral=corrective_round(c.getAttr(driver+"."+attribute))
            mirror_neutral=corrective_round(c.getAttr(mirror[0]+"."+mirror[1])) if mirror else None
            self.restore_original_control_pose(blends)
            self.restore_original_control_pose(pose)
            raw.dgdirty(allPlugs=True)
            envelopes=self._corrective_history_envelopes(geometry,blendshapes_only=True)
            history=raw.listHistory(geometry,pruneDagObjects=True) or []
            skin=next((node for node in history if raw.nodeType(node)=="skinCluster"),None)
            for before in (skin,self.scene_address("asFaceBS") if c.objExists("asFaceBS") else None):
                if before:
                    try:raw.reorderDeformers(before,self.scene_address(bs),geometry)
                    except RuntimeError:pass
            # The source's Maya >=2017 path uses the native deformer inversion.
            # The legacy sampled-Jacobian path is kept separately for older hosts.
            try:
                inverter=getattr(raw,"invertShape")
            except AttributeError:
                inverter=None
            if inverter is not None:
                raw.select((geometry,self.scene_address(corrective)),replace=True)
                with self._corrective_creation_context():
                    inverted=inverter()
                if isinstance(inverted,(tuple,list)):
                    inverted=inverted[0]
                inverted=raw.rename(inverted,self.scene_address("asInvertedShape"))
                self._corrective_front_blendshape((inverted,delta),"asInvertedShapeTempBS")
                c.setAttr("asInvertedShapeTempBS.asInvertedShape",1)
                raw.delete(inverted)
                raw.delete(self.scene_address(delta),constructionHistory=True)
            else:
                self.calculate_original_corrective_legacy_delta(original,corrective,delta,geometry,delete_mode=delete_mode)
            c.xform(corrective,worldSpace=True,translation=position)
            self._corrective_restore_envelopes(envelopes)
            self.go_to_original_corrective_build_pose()
            self.restore_original_control_pose(pose)
            raw.dgdirty(allPlugs=True)
            if mirror and not delete_mode:
                group=c.createNode("transform",name=delta+"MirrorGroup")
                c.parent(delta,group)
                c.scale(-1,1,1,group,relative=True,pivot=(0,0,0))
                c.duplicate(mirror_delta,name=mirror_delta+"Default")
                self._corrective_front_blendshape((mirror_delta+"Default",delta),"tempMirrorCorrectiveBS")
                c.setAttr("tempMirrorCorrectiveBS."+mirror_delta+"Default",1)
                self._original_bs_native_wrap(mirror_delta,delta)
                c.setAttr("tempMirrorCorrectiveBS."+mirror_delta+"Default",0)
                raw.delete(self.scene_address(mirror_delta),constructionHistory=True)
                c.delete(mirror_delta+"Default")
                self._corrective_connect_blendshape(mirror_delta,deform,geometry)
                c.scale(-1,1,1,group,relative=True,pivot=(0,0,0))
            sdk=self._original_restore_leaf(deform)+"Corrective_"+delta
            if delete_mode:
                # Preserve the source removal call, including its target ordinal.
                raw.blendShape(self.scene_address(bs),edit=True,topologyCheck=False,remove=True,
                    target=(geometry,1,self.scene_address(delta),1))
                if c.objExists(sdk):
                    c.cutKey(sdk,float=(value,value),clear=True)
            c.delete([delta,corrective])
            if mirror and not delete_mode:
                c.delete([mirror_delta,delta+"MirrorGroup"])
            if delete_mode:
                c.delete("DeleteCorrectiveShape")
            if inbetween==1 and not delete_mode and alias in self.original_face_bs_aliases(bs):
                for obj,attr,amount,zero,target in [(driver,attribute,value,neutral,delta)]+([(mirror[0],mirror[1],mirror[2],mirror_neutral,mirror_delta)] if mirror else []):
                    sdk_name=deform+"Corrective_"+target
                    if c.objExists(sdk_name) and len(c.keyframe(sdk_name,query=True,floatChange=True) or [])<2:
                        c.delete(sdk_name)
                    for dv,weight in ((zero,0),(amount,1)):
                        c.setDrivenKeyframe(bs+"."+target,currentDriver=obj+"."+attr,driverValue=dv,value=weight,
                                             inTangentType="linear",outTangentType="linear")
                    self._corrective_sdk_rotation_tangents(bs+"."+target)
            if c.objExists("BlendedCorrectiveDriver"):
                c.delete("BlendedCorrectiveDriver")
            group="Group" if c.objExists("Group") else "FaceGroup"
            c.setAttr(group+".v",1)
            self.exit_original_corrective_mode()
            raw.select(original,replace=True)
            return {"blendshape":bs,"target":delta,"inbetween":inbetween,"mirrored":bool(mirror and not delete_mode),"deleted":delete_mode}
        finally:
            raw.autoKeyframe(state=auto)
