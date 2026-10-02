"""Original Driving Systems catalogue, SDK layers and mirror operations."""
from fnmatch import fnmatchcase
from adv_py.core.driving_systems import DrivingAttribute,original_sdk_control,original_sdk_attribute
from adv_py.core.corrective_shapes import corrective_round
from .maya_corrective_shapes import MayaCorrectiveShapesHost
from .maya_driving_curves import MayaDrivingCurvesMixin
from .maya_driving_catalog import MayaDrivingCatalogMixin
from .maya_driving_fit_restore import MayaDrivingFitRestoreMixin
from .maya_driving_create import MayaDrivingCreateMixin
from .maya_driving_optimize import MayaDrivingOptimizeMixin
from .maya_driving_edit import MayaDrivingEditMixin
from .maya_original_pose_functions import MayaOriginalPoseFunctionsMixin
from .maya_original_control_identity import source_control_name,source_mirror_control


class MayaDrivingSystemsHost(MayaDrivingFitRestoreMixin,MayaDrivingCatalogMixin,MayaOriginalPoseFunctionsMixin,MayaDrivingEditMixin,MayaDrivingCreateMixin,MayaDrivingCurvesMixin,MayaDrivingOptimizeMixin,MayaCorrectiveShapesHost):
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
        driven=self._original_restore_leaf(driven)
        before=self.original_corrective_body_registration()
        child=driven;parent=c.listRelatives(driven,parent=True)[0]
        for marker in ("Extra","CustomOrient"):
            if marker in self._original_restore_leaf(parent):
                child=parent;parent=c.listRelatives(parent,parent=True)[0]
        face=c.objExists("FaceControlSet") and c.sets(driven,isMember="FaceControlSet")
        bindings=self.original_corrective_fk_bindings()
        registered_joint=next((joint for joint,control in bindings.items() if control==driven),None)
        custom=not driven.startswith("FK") and registered_joint is None
        if custom:
            tokens=driven.split("_");deform=tokens[0]+"Joint_"+(tokens[1] if len(tokens)>1 else "")
        else:deform=registered_joint or driven[2:]
        sdk="SDK"+driven
        if c.objExists(sdk):return sdk
        children=c.ls(child,long=True) or []
        if len(children)!=1:raise ValueError("SDK 控制层不存在或不唯一："+child)
        old_child=children[0]
        child_uuid=c.ls(old_child,uuid=True)[0]
        c.createNode("transform",name=sdk,parent=parent)
        owned=c.objExists("AllSet") and c.sets(driven,isMember="AllSet")
        if owned:c.sets(sdk,add="AllSet")
        c.setAttr(sdk+".rotateOrder",c.getAttr(driven+".rotateOrder"))
        c.xform(sdk,objectSpace=True,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1))
        c.parent(child,sdk,absolute=True)
        scale_edges=[]
        if c.objExists(deform) and not face and not self.original_driver_uses_opm():
            mpd=sdk+"ScaleMPD"
            if c.objExists(mpd):c.delete(mpd)
            c.createNode("multiplyDivide",name=mpd);c.setAttr(mpd+".isHistoricallyInteresting",0)
            if owned:c.sets(mpd,add="AllSet")
            if custom:
                outputs=c.listConnections(driven+".s",source=False,destination=True,plugs=True,type="joint") or []
                c.connectAttr(driven+".s",mpd+".input1");c.connectAttr(sdk+".s",mpd+".input2")
                if outputs:
                    c.connectAttr(mpd+".output",outputs[0],force=True)
                    scale_edges.append((driven+".scale",outputs[0],mpd+".output"))
            else:
                for axis in "XYZ":
                    outputs=c.listConnections(driven+".scale"+axis,source=False,destination=True,plugs=True) or []
                    c.connectAttr(driven+".scale"+axis,mpd+".input1"+axis)
                    c.connectAttr(sdk+".scale"+axis,mpd+".input2"+axis)
                    if outputs:
                        c.connectAttr(mpd+".output"+axis,outputs[0],force=True)
                        scale_edges.append((driven+".scale"+axis,outputs[0],mpd+".output"+axis))
        if before is not None:
            raw=self._corrective_raw()
            actual=raw.ls(child_uuid,long=True) or []
            if len(actual)!=1:raise ValueError("SDK 插层后的原节点身份丢失")
            new_child=(c.identity.to_local(actual[0]) if hasattr(c,"identity") else actual[0])
            from .maya_driving_registration import rebase_after_sdk
            rebase_after_sdk(self,before,old_child,new_child,sdk,scale_edges=tuple(scale_edges))
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
        left_role=source_control_name(self,left_control)
        if left_role.endswith("_L"):
            right_control=source_mirror_control(self,left_control,'R')
            if not c.objExists(right_control):return 0
        elif left_role.endswith("_M"):right_control=left_control
        else:raise ValueError("请选择左侧或中心驱动控制器")
        mirrored=0
        for right_curve in self.original_driving_curves(right_control,attribute):
            leaf=self._original_restore_leaf(right_curve)
            if left_role.endswith("_M") and "_R" not in leaf:continue
            left_curve=right_curve.replace("_R_","_L_",1)
            if leaf.startswith('SDK'):
                target=original_sdk_control(leaf)
                mirror=source_mirror_control(self,target,'L')
                if target!=mirror:
                    left_curve='SDK'+mirror+leaf[len('SDK'+target):]
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
