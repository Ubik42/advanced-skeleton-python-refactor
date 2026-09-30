"""Original Driving Systems catalogue, SDK layers and mirror operations."""
from fnmatch import fnmatchcase
from adv_py.core.driving_systems import DrivingAttribute,original_sdk_control,original_sdk_attribute
from adv_py.core.corrective_shapes import corrective_round
from .maya_corrective_shapes import MayaCorrectiveShapesHost


class MayaDrivingSystemsHost(MayaCorrectiveShapesHost):
    def original_driving_attributes(self, control):
        c=self._cmds
        face=c.objExists("FaceControlSet") and c.sets(control,isMember="FaceControlSet")
        path=(c.ls(control,long=True) or [control])[0]
        metahuman=face and "|GRP_faceGUI|" in path
        ordinary=not face and "|DrivingSystem|" not in path.replace((self.namespace+":") if self.namespace else "","")
        if face or metahuman:
            attrs=list(c.listAttr(control,keyable=True) or []) if metahuman else ([] if c.getAttr(control+".tx",lock=True) else ["translateX","translateY"])
            attrs.extend(attr for attr in c.listAttr(control,userDefined=True) or [] if not c.getAttr(control+"."+attr,lock=True)
                and (c.getAttr(control+"."+attr,keyable=True) or c.getAttr(control+"."+attr,channelBox=True)))
            if self._original_restore_leaf(control)=="ctrlPhonemes_M":attrs=[a for a in attrs if a not in ("multipliers","jaw","lip")]
        elif ordinary:
            attrs=[]
            destinations=c.listConnections(control,source=False,destination=True,skipConversionNodes=True,plugs=True,type="blendWeighted") or []
            for destination in destinations:
                sources=c.listConnections(destination,source=True,destination=False,skipConversionNodes=True,plugs=True) or []
                if sources:attrs.append(sources[0].rsplit(".",1)[1])
        else:attrs=c.listAttr(control,userDefined=True) or []
        return tuple(dict.fromkeys(a for a in attrs if a!="optimizedDS"))

    def original_driving_curves(self, control, attribute):
        c=self._cmds
        if control.startswith("FK") and c.objExists(control[2:]+"."+attribute):control=control[2:]
        bw="bw"+control+"_"+attribute
        plug=bw+".output" if c.objExists(bw) else control+"."+attribute
        return tuple(curve for curve in c.listConnections(plug,source=False,destination=True,skipConversionNodes=True,type="animCurve") or []
                     if self._original_restore_leaf(curve).startswith(("SDK","bw")))

    def original_driving_systems(self):
        c=self._cmds
        controls=list(c.listRelatives("DrivingSystem",children=True) or []) if c.objExists("DrivingSystem") else []
        if c.objExists("ctrlBox") and not c.objExists("asFaceBS"):
            for control in c.listRelatives("ctrlBox",allDescendents=True,type="transform") or []:
                if any(c.objExists("bw"+control+"_"+attr) for attr in self.original_driving_attributes(control)):controls.append(control)
        for bw in c.ls("bw*",type="blendWeighted") or []:
            output=c.listConnections(bw+".output",skipConversionNodes=True) or []
            if not output or c.nodeType(output[0]).startswith("animCurve"):continue
            curves=c.listConnections(bw+".input",skipConversionNodes=True,type="animCurve") or []
            if not curves:continue
            driver_bw=c.listConnections(curves[0]+".input",skipConversionNodes=True,type="blendWeighted") or []
            if not driver_bw:continue
            sources=c.listConnections(driver_bw[0]+".input",skipConversionNodes=True,type="transform") or []
            if not sources:continue
            control=sources[0];leaf=self._original_restore_leaf(control)
            parents=c.listRelatives(control,parent=True) or []
            if parents and self._original_restore_leaf(parents[0])=="DrivingSystem":continue
            if fnmatchcase(leaf,"SmilePull_[A-Z]") or fnmatchcase(leaf,"Lip_[A-Z]") or fnmatchcase(leaf,"CTRL_*_*"):continue
            controls.append(control)
        if c.objExists("MetaHumanControlPanelToggle.MetaHumanControlPanelVis") and c.getAttr("MetaHumanControlPanelToggle.MetaHumanControlPanelVis"):
            for control in c.listRelatives("FRM_faceGUI",allDescendents=True,type="transform") or []:
                leaf=self._original_restore_leaf(control)
                if not leaf.startswith("CTRL_") or "followhead" in leaf.lower() or leaf in ("CTRL_expressions","CTRL_faceTweakersGUI","CTRL_GUIswitch"):continue
                shapes=c.listRelatives(control,shapes=True) or []
                materials=c.listConnections(shapes[0]+".instObjGroups",source=False,destination=True) or [] if shapes else []
                if materials and self._original_restore_leaf(materials[0])=="asBlackSG":continue
                controls.append(control)
        return tuple(dict.fromkeys(controls))

    def original_driving_catalog(self):
        c=self._cmds;result=[]
        for control in self.original_driving_systems():
            for attr in self.original_driving_attributes(control):
                curves=self.original_driving_curves(control,attr)
                values=tuple(sorted({corrective_round(value) for curve in curves for value in c.keyframe(curve,query=True,floatChange=True) or []}))
                result.append(DrivingAttribute(control,attr,curves,values))
        return tuple(result)

    def update_original_driving_soft_range(self, control, attribute):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        minimum=0.;maximum=0.
        for curve in self.original_driving_curves(control,attribute):
            values=c.keyframe(curve,query=True,floatChange=True) or []
            if values:minimum=min(minimum,values[0]);maximum=max(maximum,values[-1])
        maximum=max(maximum,1.)
        if attribute in (c.listAttr(control,userDefined=True) or []):
            c.addAttr(control+"."+attribute,edit=True,hasSoftMaxValue=True,softMaxValue=maximum,hasSoftMinValue=True,softMinValue=minimum)
        return minimum,maximum

    def create_original_driving_sdk_layer(self, driven):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        child=driven;parent=c.listRelatives(driven,parent=True)[0]
        for marker in ("Extra","CustomOrient"):
            if marker in parent:
                child=parent;parent=c.listRelatives(parent,parent=True)[0]
        face=c.objExists("FaceControlSet") and c.sets(driven,isMember="FaceControlSet")
        custom=not driven.startswith("FK")
        if custom:
            stem,side=driven.rsplit("_",1);deform=stem+"Joint_"+side
        else:deform=driven[2:]
        sdk="SDK"+driven
        if c.objExists(sdk):return sdk
        c.createNode("transform",name=sdk,parent=parent)
        owned=c.objExists("AllSet") and c.sets(driven,isMember="AllSet")
        if owned:c.sets(sdk,add="AllSet")
        c.setAttr(sdk+".rotateOrder",c.getAttr(driven+".rotateOrder"))
        c.xform(sdk,objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
        c.parent(child,sdk)
        if c.objExists(deform) and not face and not self.original_driver_uses_opm():
            mpd=sdk+"ScaleMPD"
            if c.objExists(mpd):c.delete(mpd)
            c.createNode("multiplyDivide",name=mpd);c.setAttr(mpd+".isHistoricallyInteresting",0)
            if owned:c.sets(mpd,add="AllSet")
            if custom:
                outputs=c.listConnections(driven+".s",source=False,destination=True,plugs=True,type="joint") or []
                c.connectAttr(driven+".s",mpd+".input1");c.connectAttr(sdk+".s",mpd+".input2")
                for output in outputs:c.connectAttr(mpd+".output",output,force=True)
            else:
                for axis in "XYZ":
                    outputs=c.listConnections(driven+".scale"+axis,source=False,destination=True,plugs=True) or []
                    c.connectAttr(driven+".scale"+axis,mpd+".input1"+axis)
                    c.connectAttr(sdk+".scale"+axis,mpd+".input2"+axis)
                    if outputs:c.connectAttr(mpd+".output"+axis,outputs[0],force=True)
        return sdk

    def graph_original_driving_attribute(self, control, attribute):
        curves=self.original_driving_curves(control,attribute)
        self._cmds.select(curves,replace=True)
        from maya import mel
        mel.eval("GraphEditor;")
        return curves

    def mirror_original_driving_attribute(self, left_control, attribute):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=self._corrective_raw()
        if left_control.endswith("_L"):
            right_control=left_control[:-2]+"_R"
            if not c.objExists(right_control):return 0
        elif left_control.endswith("_M"):right_control=left_control
        else:raise ValueError("请选择左侧或中心驱动控制器")
        mirrored=0
        for right_curve in self.original_driving_curves(right_control,attribute):
            leaf=self._original_restore_leaf(right_curve)
            if left_control.endswith("_M") and "_R" not in leaf:continue
            left_curve=right_curve.replace("_R_","_L_")
            if not c.objExists(left_curve):continue
            raw.copyKey(self.scene_address(right_curve),hierarchy="none",controlPoints=False,shape=False)
            raw.pasteKey(self.scene_address(left_curve),option="replaceCompletely",copies=1,connect=False,timeOffset=0,floatOffset=0,valueOffset=0)
            self.update_original_driving_soft_range(left_control,attribute);mirrored+=1
            if self._original_restore_leaf(left_curve)=="SDKEye_L_rotateY":
                values=c.keyframe(left_curve,query=True,valueChange=True) or []
                if len(values)>=3:
                    c.keyframe(left_curve,edit=True,index=(0,0),valueChange=-values[2])
                    c.keyframe(left_curve,edit=True,index=(2,2),valueChange=-values[0])
                continue
            if self._original_restore_leaf(left_control)=="ctrlEye_L" and attribute=="translateX":
                raw.scaleKey(self.scene_address(left_curve),includeUpperBound=False,floatScale=-1,floatPivot=0,valueScale=1,valuePivot=0)
                continue
            if self._original_restore_leaf(left_control)=="ctrlLips_M" and attribute=="translateX":
                raw.scaleKey(self.scene_address(left_curve),includeUpperBound=False,floatScale=-1,floatPivot=0,valueScale=1,valuePivot=0)
            right=original_sdk_control(right_curve);left=original_sdk_control(left_curve)
            scales=c.xform(right,query=True,worldSpace=True,scale=True)+c.xform(left,query=True,worldSpace=True,scale=True)
            if any(value<0 for value in scales) or leaf.startswith(("bw","SDKIris_","SDKPupil_")):continue
            parents=c.listRelatives(right,parent=True) or []
            orientation=c.xform(parents[0],query=True,worldSpace=True,rotation=True) if parents else (0,0,0)
            world=all(value==0 for value in orientation) or (c.objExists(right+".localOrient") and not c.getAttr(right+".localOrient")) or "Pivot" in leaf
            attr=original_sdk_attribute(right_curve)
            if attr.startswith("scale"):continue
            if world and attr.startswith(("translateY","translateZ","rotateX")):continue
            if not world and not attr.startswith("translate"):continue
            raw.scaleKey(self.scene_address(left_curve),includeUpperBound=False,floatScale=1,floatPivot=0,valueScale=-1,valuePivot=0)
        return mirrored
