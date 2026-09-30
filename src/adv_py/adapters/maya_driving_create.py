"""asDsCreate: discover pose/animation, build SDK layers and persist drivers."""
from dataclasses import replace
from math import dist
from fnmatch import fnmatchcase
import json
from adv_py.core.driving_systems import DrivenChannel,DrivingCreateOptions,driving_pose_command_rows
from adv_py.core.corrective_shapes import corrective_round

class MayaDrivingCreateMixin:
    def original_driving_build_pose_rows(self):
        c=self._cmds;rows=[]
        for node,reader in (("buildPose",self.read_body_build_pose),("faceBuildPose",self.read_face_build_pose)):
            if not c.objExists(node):continue
            if c.objExists(node+".advPyPoseData"):
                rows.extend((value.node+"."+value.attribute,value.value) for value in reader().values)
            elif c.objExists(node+".udAttr"):
                rows.extend(driving_pose_command_rows(c.getAttr(node+".udAttr")))
            if c.objExists(node+".udExtraAttr"):rows.extend(driving_pose_command_rows(c.getAttr(node+".udExtraAttr")))
        overrides=[]
        for fit in ("FitSkeleton","FaceFitSkeleton"):
            if c.objExists(fit+".run"):overrides.extend(driving_pose_command_rows(c.getAttr(fit+".run")))
        def canonical(plug):
            node,attr=plug.rsplit(".",1)
            return self._original_restore_leaf(node)+"."+c.attributeQuery(attr,node=node,longName=True) if c.objExists(plug) else plug
        replacements={canonical(plug):value for plug,value in overrides}
        values={canonical(plug):value for plug,value in (*rows,*overrides)}
        return tuple((plug,replacements.get(plug,value)) for plug,value in values.items())

    def capture_original_driving_create(self, options):
        c=self._cmds;raw=self._corrective_raw()
        editing=c.objExists("EditingDrivingSystem")
        if editing:
            options=replace(options,control=c.getAttr("EditingDrivingSystem.DrivingSystem"),attribute=c.getAttr("EditingDrivingSystem.DrivingAttr"),mirror=True)
        channels=[];minimum=0.;maximum=10.;mirror=options.mirror
        for plug,neutral in self.original_driving_build_pose_rows():
            if not c.objExists(plug):continue
            node,attr=plug.rsplit(".",1)
            if "FKIK" in node or "Extra" in node:continue
            if editing and options.control.endswith("_R") and "_L" in node:continue
            sources=c.listConnections(plug,source=True,destination=False,skipConversionNodes=True) or []
            if sources and self._original_restore_leaf(sources[0])=="time1":continue
            animations=c.listConnections(plug,source=True,destination=False,skipConversionNodes=True,type="animCurve") or []
            if animations and c.listConnections(animations[0],source=False,destination=True,type="mute"):continue
            if editing and node.endswith("_L"):
                right=node[:-2]+"_R."+attr
                if c.objExists(right) and c.listConnections(right,source=True,destination=False,skipConversionNodes=True,type="animCurve"):continue
            value=c.getAttr(plug)
            if abs(value-neutral)<=.001 and not animations:continue
            if node.startswith("SmilePull_"):raise ValueError("SmilePull 控制器不能作为被驱动对象，请先归零")
            if "_L" in node:mirror=False
            animation=animations[0] if animations and not c.nodeType(animations[0]).startswith("animCurveU") else ""
            if animation:
                keys=c.keyframe(animation,query=True,timeChange=True) or []
                if len(keys)==1:raise ValueError("动画通道至少需要两个关键帧："+plug)
                if keys:minimum=min(minimum,keys[0]);maximum=max(maximum,keys[-1])
            channels.append(DrivenChannel(node,attr,float(neutral),float(value),animation,bool(animation and "_Editing" in animation)))
        if not channels and not editing:raise ValueError("没有被驱动通道，当前所有控制器仍在构建姿态")
        if not c.objExists("CustomOrientsDisabled"):
            for channel in channels:
                if c.objExists("CustomOrient"+channel.control):raise ValueError("请先禁用控制器自定义朝向："+channel.control)
        right=any(row.control.endswith("_R") for row in channels)
        left=any(row.control.endswith("_L") for row in channels)
        middle=not (right or left)
        if middle:mirror=False
        face=bool(channels and c.objExists("FaceControlSet") and c.sets(channels[0].control,isMember="FaceControlSet"))
        value=maximum
        if editing and raw.currentTime(query=True)!=0:value=raw.currentTime(query=True)
        driver=options.control+"."+options.attribute
        selected_driver=bool(options.control and options.attribute and any(row.plug==driver for row in channels))
        if options.drive_from_selected and not selected_driver:raise ValueError("所选驱动通道必须在当前姿态中具有修改值")
        if selected_driver:value=corrective_round(c.getAttr(driver))
        parents=c.listRelatives(options.control,parent=True) or [] if selected_driver else []
        other=selected_driver and (not parents or self._original_restore_leaf(parents[0])!="DrivingSystem")
        return {"options":replace(options,mirror=mirror),"channels":tuple(channels),"value":value,"minimum":minimum,
                "maximum":maximum,"editing":editing,"middle":middle,"both_sides":right and left,"face":face,"other_driver":other}

    def _original_create_driving_controller(self, name, drivens):
        c=self._cmds
        c.circle(name=name,center=(0,0,0),normal=(0,0,1),sweep=180,radius=1,degree=3,useTolerance=False,
                 tolerance=.000393701,sections=8,constructionHistory=False)
        c.scale(-1,1,1,name+".cv[0:10]",relative=True)
        for node in (name,*c.listRelatives(name,shapes=True)):
            if c.objExists("AllSet"):c.sets(node,add="AllSet")
        c.sets(name,add="ControlSet")
        for shape in c.listRelatives(name,shapes=True):
            c.setAttr(shape+".overrideEnabled",1);c.setAttr(shape+".overrideColor",17)
        if not c.objExists("DrivingSystem"):
            c.createNode("transform",name="DrivingSystem",parent="MotionSystem")
            if c.objExists("AllSet"):c.sets("DrivingSystem",add="AllSet")
        if not c.isConnected("Main.drvSysVis","DrivingSystem.v"):c.connectAttr("Main.drvSysVis","DrivingSystem.v")
        c.parent(name,"DrivingSystem")
        if drivens:
            deform=drivens[0].removeprefix("FK")
            if not c.objExists(deform) or c.nodeType(deform) not in ("joint","transform"):deform="Root_M"
            c.delete(c.parentConstraint(deform,name))
            child=self._original_driving_rla_child(deform)
            children=[child] if child else []
            if children:
                a=c.xform(deform,query=True,worldSpace=True,translation=True)
                b=c.xform(children[0],query=True,worldSpace=True,translation=True)
                length=dist(a,b);c.setAttr(name+".s",length,length,length,type="float3")
        return name

    def _original_driving_sdk_destination(self, driven, driver):
        c=self._cmds
        node,attr=driven.rsplit(".",1)
        if node.startswith("SDK"):return driven
        if c.objExists("SDK"+node+"."+attr):return "SDK"+node+"."+attr
        output=c.listConnections(driven,source=False,destination=True,type="blendWeighted") or []
        if output:
            weighted=output[0]
            driver_output=c.listConnections(driver,source=False,destination=True,type="blendWeighted") or []
            driven_curves=c.listConnections(weighted+".input",source=True,destination=False,type="animCurve") or []
            driver_curves=c.listConnections(driver_output[0]+".output",source=False,destination=True,type="animCurve") or [] if driver_output else []
            for curve in driven_curves:
                if curve in driver_curves:return self._original_driving_curve_destination(curve)
            return weighted+".input["+str(c.getAttr(weighted+".input",size=True))+"]"
        return self.create_original_driving_sdk_layer(node)+"."+attr

    def _original_driving_pose_registration(self, control, attribute, *, face):
        c=self._cmds
        pose="faceBuildPose" if face else "buildPose"
        if not c.objExists(pose):return
        if not c.objExists(pose+".udAttr"):c.addAttr(pose,longName="udAttr",dataType="string")
        source=c.getAttr(pose+".udAttr") or ""
        c.setAttr(pose+".udAttr",source+";setAttr "+self.scene_address(control)+"."+attribute+" 0;",type="string")
        if c.objExists(pose+".advPyPoseData"):
            rows=json.loads(c.getAttr(pose+".advPyPoseData"))
            rows=[row for row in rows if not (self._original_restore_leaf(row[0])==control and row[1]==attribute)]
            rows.append([control,attribute,0.])
            c.setAttr(pose+".advPyPoseData",json.dumps(rows),type="string")

    def create_original_driving_system(self, plan):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        auto=raw.autoKeyframe(query=True,state=True);raw.autoKeyframe(state=False)
        opts=plan["options"];channels=plan["channels"]
        generated=[];curves=[];reused=False
        if not channels and plan["editing"]:
            raw.autoKeyframe(state=auto)
            return {"drivers":(),"curves":(),"channels":0}
        try:
            if c.objExists("TestSymmetry"):self.remove_original_driving_symmetry_preview()
            for side_index in (0,1):
                if side_index and (not opts.mirror or plan["middle"] or plan["both_sides"]):continue
                side="_L" if side_index else "_R"
                controller_side="_M" if plan["middle"] or plan["both_sides"] else side
                rows=[replace(row,control=row.control.replace("_R","_L",1)) if side_index else row for row in channels]
                if side_index and any(not c.objExists(row.control) for row in rows):continue
                control=opts.control
                if not control:
                    control=next(("DrivingSystem"+str(i)+controller_side for i in range(1,99) if not c.objExists("DrivingSystem"+str(i)+controller_side)),"")
                elif not (control.endswith(("_L","_R","_M")) or "_R_" in control or "_L_" in control or "_C_" in control):control+=controller_side
                if side_index:control=control.replace("_R","_L",1)
                if c.objExists(control):reused=True
                else:self._original_create_driving_controller(control,list(dict.fromkeys(row.control for row in rows)))
                attribute=opts.attribute.replace("Right","Left",1) if side_index and opts.attribute.endswith("Right") else opts.attribute
                if not attribute:attribute=next(("driver"+str(i) for i in range(1,99) if not c.objExists(control+".driver"+str(i))),"")
                other=plan["other_driver"]
                if other and control.startswith("FK") and c.objExists(control[2:]):control=control[2:]
                if not c.objExists(control+"."+attribute):c.addAttr(control,longName=attribute,attributeType="double",keyable=True)
                driver_value=plan["value"]
                if other:
                    if opts.q_rotations and attribute.startswith("rotate"):
                        self.create_original_q_rotate_attrs(control);attribute=attribute.replace("rotate","qRotate",1)
                    else:attribute=self.original_opm_compatible_driver_attr(control,attribute)
                    # The direct driver is temporarily neutralized in asDsCreate.
                    direct=opts.control+"."+opts.attribute
                    if c.objExists(direct) and c.getAttr(direct,settable=True):c.setAttr(direct,0)
                bw=self.original_face_output_bw(control+"."+attribute).rsplit(".",1)[0]
                all_set="FaceAllSet" if plan["face"] else "AllSet"
                if other and c.objExists(all_set):c.sets(bw,remove=all_set)
                generated.append((control,attribute))
                for row in rows:
                    if row.plug==opts.control+"."+opts.attribute:continue
                    if side_index and not row.control.endswith("_L") and not row.attribute.endswith("Side"):continue
                    destination=self._original_driving_sdk_destination(row.plug,control+"."+attribute)
                    sdk_node=destination.split(".",1)[0]
                    if other and sdk_node.startswith("SDK") and c.objExists(all_set):c.sets(sdk_node,remove=all_set)
                    value=row.value
                    if row.control.endswith("_M") and control.endswith(("_R","_L")) and not plan["middle"] and (not fnmatchcase(row.attribute,"s[x-z]") or fnmatchcase(row.attribute,"scale[X-Z]")):value/=2
                    if side_index and plan["face"] and row.attribute.endswith("Side"):value=-value
                    key_value=-driver_value if side_index and opts.control=="ctrlLips_M" and opts.attribute=="translateX" and not row.control.endswith("_M") else driver_value
                    if row.control=="Eye_L" and row.attribute in ("ry","rotateY") and c.objExists("SDKEye_R_rotateY"):
                        keys=c.keyframe("SDKEye_R_rotateY",query=True,floatChange=True) or []
                        if keys and keys[0]==-1:key_value=-driver_value;value=-value
                    weighted=self.ensure_original_driving_weighted_input(destination)
                    before=set(c.ls(type="animCurve") or [])
                    c.setDrivenKeyframe(destination,currentDriver=bw+".output",driverValue=key_value,value=value,inTangentType="spline",outTangentType="spline")
                    new=[node for node in c.ls(type="animCurve") or [] if node not in before]
                    if new:
                        name=destination.replace(".","_").replace("[","_").replace("]","_")
                        curve=c.rename(new[0],name)
                        c.setAttr(curve+".preInfinity",1);c.setAttr(curve+".postInfinity",1)
                        if c.objExists(all_set) and c.sets(sdk_node,isMember=all_set):c.sets(curve,add=all_set)
                    else:
                        existing=c.listConnections(weighted+".input",source=True,destination=False,skipConversionNodes=True,type="animCurve") or []
                        curve=next((node for node in existing if bw+".output" in (c.listConnections(node+".input",source=True,destination=False,skipConversionNodes=True,plugs=True) or [])),"")
                    c.setDrivenKeyframe(destination,currentDriver=bw+".output",driverValue=0,value=row.neutral,inTangentType="spline",outTangentType="spline")
                    if row.animation and not side_index and curve:
                        if not row.editing:
                            c.setAttr(row.animation+".preInfinity",1);c.setAttr(row.animation+".postInfinity",1)
                            c.keyTangent(row.animation,inTangentType="spline",outTangentType="spline")
                        self.copy_original_driving_curve(row.animation,curve)
                        c.delete(row.animation)
                    if curve:curves.append(curve)
                    if c.getAttr(row.plug,settable=True):c.setAttr(row.plug,row.neutral)
                if plan["editing"] and plan["face"]:
                    if not c.objExists("FaceSetupEditHistory"):
                        c.createNode("transform",name="FaceSetupEditHistory",parent="ControlsSetup")
                        c.sets("FaceSetupEditHistory",add="FaceAllSet")
                    marker=control+"_"+attribute+"_tweaked"
                    if not c.objExists("FaceSetupEditHistory."+marker):c.addAttr("FaceSetupEditHistory",longName=marker,attributeType="bool",defaultValue=True)
                if not plan["editing"] and not other and not self._original_face_is_blended_attr(control,attribute):
                    self._original_driving_pose_registration(control,attribute,face=plan["face"])
                self.update_original_driving_soft_range(control,attribute)
                if side_index:self.mirror_original_driving_attribute(control,attribute)
            if not plan["editing"]:self.normalize_original_driving_scales()
            self.go_to_original_corrective_build_pose()
            if not reused:self.optimize_original_driving_controllers()
            if not plan["editing"] and c.objExists("FitSkeleton"):
                fit=self.plan_body_driving_fit_sync(self.scene_address("FitSkeleton"))
                if fit:self.apply_body_driving_fit_sync(fit)
            c.select(clear=True)
            return {"drivers":tuple(generated),"curves":tuple(curves),"channels":len(channels)}
        finally:raw.autoKeyframe(state=auto)
