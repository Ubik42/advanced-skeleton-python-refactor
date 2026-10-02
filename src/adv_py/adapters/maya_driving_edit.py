"""Original time-axis SDK editing, symmetry preview, apply and cancel."""
import json
import re
from fnmatch import fnmatchcase
from adv_py.core.corrective_shapes import corrective_round
from adv_py.core.driving_systems import DrivingCreateOptions,original_sdk_control,original_sdk_attribute
from .maya_original_control_identity import (
    source_control_name,source_fk_control,source_mirror_control,
)

class MayaDrivingEditMixin:
    def _original_driving_connect(self, source, destination, *, force=False):
        c=self._cmds;raw=self._corrective_raw()
        target=self.scene_address(destination)
        if hasattr(c,"identity") and not c.identity.owns(target):raise ValueError("驱动编辑目标不属于当前角色")
        raw.connectAttr(":time1.outTime" if self._original_restore_leaf(source.split(".",1)[0])=="time1" else self.scene_address(source),target,force=force)

    def auto_find_and_edit_original_driving(self, *, test_symmetry=True, show_only_affected=False):
        """asDsAutoFindAndEdit retains its nonzero, corner and blended-source rules."""
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;driver="";attribute=""
        for control in self.original_driving_systems():
            for attr in self.original_driving_attributes(control):
                value=corrective_round(c.getAttr(control+"."+attr))
                combined=fnmatchcase(attr,"*tx*_ty*")
                if combined and ((c.getAttr(control+".tx")==0 and c.getAttr(control+".ty")==0) or value in (.5,-.5)):continue
                mouth=fnmatchcase(control,"ctrlMouthCorner_*")
                if mouth and (fnmatchcase(attr,"translate[A-Z]") or (c.getAttr(control+".tx")==0 and c.getAttr(control+".ty")==0)):continue
                if value==0:continue
                if (source_control_name(self,control).endswith("_L") or attr.endswith("Left")) and attr not in ("mouthLeft","jawLeft"):
                    raise ValueError("请仅修改右侧或中间驱动属性："+control+"."+attr)
                if driver:
                    if driver==control and attribute=="translateX" and attr=="translateY":
                        if not mouth:raise ValueError("此控制器暂不支持组合驱动编辑，请只修改 X 或 Y")
                        attr=self.original_blended_driver_name((control+".tx",control+".ty"))
                        c.addAttr(control,longName=attr,attributeType="double",defaultValue=1,keyable=False)
                        if c.objExists("BlendedCorrectiveDriver"):c.delete("BlendedCorrectiveDriver")
                        if source_control_name(self,control).endswith("_R"):
                            left=source_mirror_control(self,control,"L")
                            c.setAttr(left+".tx",c.getAttr(control+".tx"));c.setAttr(left+".ty",c.getAttr(control+".ty"))
                            if c.objExists("BlendedCorrectiveDriver"):c.delete("BlendedCorrectiveDriver")
                            c.setAttr(left+".tx",0);c.setAttr(left+".ty",0)
                    elif fnmatchcase(driver,"ctrlMouthCorner_*"):raise ValueError("请把嘴角控制器移动到一个角落，再编辑 Driving System")
                    else:raise ValueError("同时发现多个驱动值："+driver+"."+attribute+" 和 "+control+"."+attr)
                driver=control;attribute=attr
                if driver=="ctrlMouth_M" and attribute=="translateX":raise ValueError("请编辑嘴角属性，而不是 ctrlMouth_M.translateX")
                if "_" in attribute and not c.getAttr(driver+"."+attribute,settable=True):break
        if not driver:raise ValueError("请先设置一个驱动值，或从列表选择具体驱动属性")
        return self.edit_original_driving_attribute(driver,attribute,test_symmetry=test_symmetry,show_only_affected=show_only_affected)

    def remove_original_driving_symmetry_preview(self):
        c=self._cmds
        if not c.objExists("TestSymmetry"):return
        nodes=[node for node in c.listConnections("TestSymmetry",source=True,destination=False,type="multiplyDivide") or []
               if self._original_restore_leaf(node).startswith("TestSymmetry_")]
        c.delete("TestSymmetry")
        if nodes:c.delete(list(dict.fromkeys(nodes)))

    def update_original_driving_curve_versions(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;converted=0
        for curve in c.ls("SDK*","bw*",type="animCurve") or []:
            kind=c.nodeType(curve)
            if not kind.startswith("animCurveT") or "_Editing" in curve:continue
            if not c.listConnections(curve+".input",source=True,destination=False):
                c.delete(curve);continue
            source=c.rename(curve,"TEMP_"+self._original_restore_leaf(curve))
            c.createNode(kind.replace("animCurveT","animCurveU",1),name=curve)
            for attr in c.listAttr(source,userDefined=True) or []:
                c.addAttr(curve,longName=attr,attributeType="message" if attr=="drivingSystemOut" else "double",keyable=False)
            inputs=c.listConnections(source,source=True,destination=False,plugs=True,connections=True,skipConversionNodes=True) or []
            outputs=c.listConnections(source,source=False,destination=True,plugs=True,connections=True,skipConversionNodes=True) or []
            for target,driver in zip(inputs[::2],inputs[1::2]):
                target=curve+"."+target.split(".",1)[1]
                self._original_driving_connect(driver,target)
            for driver,target in zip(outputs[::2],outputs[1::2]):
                driver=curve+"."+driver.split(".",1)[1]
                self._original_driving_connect(driver,target,force=True)
            self.copy_original_driving_curve(source,curve);c.delete(source);converted+=1
        for node in c.ls(type="unitToTimeConversion") or []:
            if not c.listConnections(node+".output",source=False,destination=True):c.delete(node)
        return converted

    def check_original_driving_control_keys(self):
        c=self._cmds
        if not c.objExists("FaceControlSet"):return
        for control in c.sets("FaceControlSet",query=True) or []:
            if c.listConnections(control,source=True,destination=False,type="animCurve"):
                raise ValueError("控制器存在关键帧，不能进入 SDK 编辑："+control)

    def _original_driving_symmetry_preview(self, *, face):
        c=self._cmds
        group="FaceControlSet" if face else "ControlSet"
        if not c.objExists(group):return
        c.createNode("transform",name="TestSymmetry")
        restore=[]
        for control in c.sets(group,query=True) or []:
            control=self._original_restore_leaf(control)
            role=source_control_name(self,control)
            right=source_mirror_control(self,control,'R')
            if not role.endswith("_L") or not c.objExists(right):continue
            stem=role[:-2]
            path=(c.ls(control,long=True) or [control])[0]
            custom="CustomSystem|" in path
            custom_local=custom and c.objExists(control+".localOrient") and bool(c.getAttr(control+".localOrient"))
            for attr in c.listAttr(control,keyable=True,multi=True,shortNames=True) or []:
                if "_" in attr or c.getAttr(control+"."+attr,lock=True):continue
                value=c.getAttr(control+"."+attr)
                if not isinstance(value,(int,float)):continue
                stored=stem+"_"+attr
                c.addAttr("TestSymmetry",longName=stored,attributeType="double",keyable=True)
                mpd=c.createNode("multiplyDivide",name="TestSymmetry_"+stored+"_MultiplyDivide")
                c.connectAttr(right+"."+attr,mpd+".input1X")
                local=role.startswith(("FK","Bend")) or c.objExists(control+".ikLocal") or custom_local
                flip=-1 if attr in (("tx","ty","tz") if local else ("tx","ry","rz")) else 1
                if face and not custom:flip=1
                c.setAttr(mpd+".input2X",flip)
                c.connectAttr(mpd+".outputX","TestSymmetry."+stored)
                c.connectAttr("TestSymmetry."+stored,control+"."+attr)
                restore.append((control+"."+attr,c.getAttr(control+"."+attr)))
        c.addAttr("TestSymmetry",longName="udAttr",dataType="string")
        c.setAttr("TestSymmetry.udAttr","".join("setAttr "+plug+" "+str(value)+";" for plug,value in restore),type="string")

    def edit_original_driving_attribute(self, control, attribute, *, test_symmetry=True, show_only_affected=False):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        from maya import mel
        slider=mel.eval("global string $gPlayBackSlider; $gPlayBackSlider;")
        timeline={"preEditSnap":bool(raw.timeControl(slider,query=True,snap=True)) if slider else True,
                  "preEditMin":raw.playbackOptions(query=True,minTime=True),"preEditMax":raw.playbackOptions(query=True,maxTime=True),
                  "preEditAst":raw.playbackOptions(query=True,animationStartTime=True),"preEditAet":raw.playbackOptions(query=True,animationEndTime=True)}
        self.update_original_driving_curve_versions()
        self.check_original_driving_control_keys()
        raw.autoKeyframe(state=True)
        current=c.getAttr(control+"."+attribute)
        self.remove_original_driving_test_animation()
        face=c.objExists("FaceControlSet") and c.sets(control,isMember="FaceControlSet")
        if control=="ctrlMouth_M" and attribute in ("tx","translateX"):control="ctrlMouthCorner_R"
        path=(c.ls(control,long=True) or [control])[0]
        path=path.replace(self.namespace+":" if self.namespace else "","")
        other=not face and "|DrivingSystem|" not in path
        self.go_to_original_corrective_build_pose()
        curves=self.original_driving_curves(control,attribute)
        if not curves:raise ValueError("驱动属性没有可编辑的 SDK 曲线")
        raw.refresh()
        if not c.objExists("CustomOrientsDisabled"):
            from .maya_original_control_identity import original_custom_orient_node
            for curve in curves:
                target=original_sdk_control(curve)
                if original_custom_orient_node(self, target):
                    raise ValueError("请先禁用自定义朝向："+target)
        affected=[];minimum=0.;maximum=0.;editing=[]
        for curve in curves:
            if "_L_" in curve:continue
            target=original_sdk_control(curve);attr=original_sdk_attribute(curve)
            if target not in affected:affected.append(target)
            name=curve+"_Editing"
            c.createNode(c.nodeType(curve).replace("animCurveU","animCurveT",1),name=name)
            self.copy_original_driving_curve(curve,name)
            c.connectAttr(name+".output",target+"."+attr)
            keys=c.keyframe(curve,query=True,floatChange=True) or []
            if keys:minimum=min(minimum,keys[0]);maximum=max(maximum,keys[-1])
            if len(keys)<2:c.warning('Less then 2 keys in SDK AnimCurve "'+curve+'"')
            editing.append(name)
        raw.playbackOptions(minTime=minimum,animationStartTime=minimum,animationEndTime=maximum,maxTime=maximum)
        if maximum<=1 and slider:raw.timeControl(slider,edit=True,snap=False)
        # asDsEdit completes all preview connections before shifting additive
        # scale curves. Query only downstream blendWeighted plugs, as in MEL.
        for curve in curves:
            if "_L_" in curve:continue
            destinations=c.listConnections(curve+".output",source=False,destination=True,
                                           skipConversionNodes=True,plugs=True,type="blendWeighted") or []
            if destinations and re.search(r"_scale.*\.input\[[1-9][0-9]*\]$",destinations[0]):
                c.keyframe(curve+"_Editing",edit=True,relative=True,option="over",valueChange=1)
            keys=c.keyframe(curve,query=True,floatChange=True) or []
            if keys:minimum=min(minimum,keys[0]);maximum=max(maximum,keys[-1])
            if len(keys)<2:c.warning('Less then 2 keys in SDK AnimCurve "'+curve+'"')
        raw.playbackOptions(minTime=minimum,animationStartTime=minimum,animationEndTime=maximum,maxTime=maximum)
        if maximum<=1 and slider:raw.timeControl(slider,edit=True,snap=False)
        raw.currentTime(current if current else maximum)
        if other:
            driver=control+"."+attribute
            fk=source_fk_control(self,control)
            if not source_control_name(self,control).startswith("IK") and c.objExists(fk+"."+attribute):driver=fk+"."+attribute
            if attribute.startswith("qRotate"):driver=fk+"."+attribute.replace("qRotate","rotate",1)
            if attribute.startswith("opm"):driver=fk+"."+attribute.removeprefix("opm")
            if c.objExists(driver):self._original_driving_connect("time1.outTime",driver)
            self.mute_original_driving_sdks(curves)
        if test_symmetry:self._original_driving_symmetry_preview(face=bool(face))
        c.createNode("transform",name="EditingDrivingSystem")
        c.addAttr("EditingDrivingSystem",longName="DrivingSystems",attributeType="bool",defaultValue=True)
        for attr,value in (("DrivingSystem",control),("DrivingAttr",attribute)):
            c.addAttr("EditingDrivingSystem",longName=attr,dataType="string")
            c.setAttr("EditingDrivingSystem."+attr,value,type="string")
        for attr,value in timeline.items():
            c.addAttr("EditingDrivingSystem",longName=attr,attributeType="bool" if attr=="preEditSnap" else "double",defaultValue=value)
        c.addAttr("EditingDrivingSystem",longName="advPyEditingCurves",dataType="string")
        c.setAttr("EditingDrivingSystem.advPyEditingCurves",json.dumps(editing),type="string")
        if show_only_affected:self.show_original_driving_affected_controls(tuple(affected),affected_only=True)
        from .maya_original_control_identity import registration,leaf
        saved=registration(self)
        fk=source_fk_control(self,control)
        has_source_limb=saved is not None and any(
            leaf(row.control)==leaf(fk) for limb in saved.source_limbs for row in limb.joints)
        if has_source_limb or all(c.objExists(prefix+control) for prefix in ("FK","FKX","IKX","FKOffset")):
            self.set_original_corrective_fk(fk)
        if raw.headsUpDisplay("HUDEDSMode",query=True,exists=True):raw.headsUpDisplay("HUDEDSMode",remove=True)
        raw.headsUpDisplay("HUDEDSMode",section=2,block=0,blockSize="medium",label="Editing Driving System: "+control+"."+attribute,labelFontSize="large")
        raw.displayColor("headsUpDisplayLabels",16)
        c.select(clear=True)
        return {"driver":control+"."+attribute,"curves":tuple(editing),"range":(minimum,maximum)}

    def cancel_original_driving_edit(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        curves=c.ls("*_Editing*",type="animCurve") or []
        if curves:c.delete(curves)
        self.remove_original_driving_test_animation()
        self.unmute_original_driving_sdks()
        return {"cancelled":True}

    def apply_original_driving_edit(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        if not c.objExists("EditingDrivingSystem"):raise ValueError("当前没有编辑中的 Driving System")
        control=c.getAttr("EditingDrivingSystem.DrivingSystem");attribute=c.getAttr("EditingDrivingSystem.DrivingAttr")
        self.unmute_original_driving_sdks()
        self.remove_original_driving_symmetry_preview()
        plan=self.capture_original_driving_create(DrivingCreateOptions(control,attribute,True,False))
        result=self.create_original_driving_system(plan)
        self.remove_original_driving_test_animation()
        stale=c.ls("CancelRestore*",type="animCurve") or []
        if stale:c.delete(stale)
        self.normalize_original_driving_scales()
        if c.objExists("FitSkeleton"):
            fit=self.plan_body_driving_fit_sync(self.scene_address("FitSkeleton"))
            if fit:self.apply_body_driving_fit_sync(fit)
        self.update_original_driving_soft_range(control,attribute)
        if not source_control_name(self,control).endswith("_L"):
            left=source_mirror_control(self,control,'L')
            if c.objExists(left):self.mirror_original_driving_attribute(left,attribute)
        return result

    def delete_original_driving_attribute(self, control, attribute):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        self.remove_original_driving_test_animation();self.go_to_original_corrective_build_pose()
        curves=self.original_driving_curves(control,attribute)
        self._corrective_raw().refresh()
        face=c.objExists("FaceControlSet") and c.sets(control,isMember="FaceControlSet")
        path=(c.ls(control,long=True) or [control])[0].replace(self.namespace+":" if self.namespace else "","")
        other=not face and "|DrivingSystem|" not in path
        if not other:
            try:c.deleteAttr(control+"."+attribute)
            except RuntimeError:pass
        if curves:c.delete(curves)
        self.update_original_driving_pose_attributes();self.go_to_original_corrective_build_pose()
        from .maya_driving_registration import refresh_registered_sdks
        refresh_registered_sdks(self)
        return len(curves)
