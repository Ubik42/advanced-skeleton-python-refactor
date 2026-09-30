"""Native QRotation, OPM and combined driver attributes, MEL 66017–66281."""
from math import sqrt
import shlex
from adv_py.core.corrective_shapes import corrective_pose_command_rows


class MayaOriginalDriverAttributesMixin:
    def capture_original_control_pose(self):
        c=self._cmds
        rows=[]
        for name in ("ControlSet","FaceControlSet"):
            if not c.objExists(name):
                continue
            for control in c.sets(name,query=True) or []:
                for attr in c.listAttr(control,keyable=True) or []:
                    plug=control+"."+attr
                    if not c.getAttr(plug,lock=True) and c.getAttr(plug,settable=True):
                        value=c.getAttr(plug)
                        if isinstance(value,(int,float)):
                            rows.append((plug,value))
        return tuple(rows)

    def restore_original_control_pose(self, rows):
        for plug,value in rows:
            self._cmds.setAttr(plug,value)

    def original_corrective_build_pose_rows(self):
        c=self._cmds
        rows=[]
        for node,pose_reader in (("buildPose",self.read_body_build_pose),("faceBuildPose",self.read_face_build_pose)):
            if not c.objExists(node):
                continue
            if c.objExists(node+".advPyPoseData"):
                rows.extend((value.node+"."+value.attribute,value.value) for value in pose_reader().values)
            elif c.objExists(node+".udAttr"):
                rows.extend(corrective_pose_command_rows(c.getAttr(node+".udAttr")))
            if c.objExists(node+".udExtraAttr"):
                rows.extend(corrective_pose_command_rows(c.getAttr(node+".udExtraAttr")))
        overrides=[]
        for fit in ("FitSkeleton","FaceFitSkeleton"):
            if c.objExists(fit+".run"):
                overrides.extend(corrective_pose_command_rows(c.getAttr(fit+".run")))
        replacements=dict(overrides)
        rows.extend(overrides)
        return tuple((plug,replacements.get(plug,value)) for plug,value in rows)

    def _original_apply_pose_commands(self, text):
        c=self._cmds
        for statement in (text or "").split(";"):
            tokens=shlex.split(statement)
            if not tokens:
                continue
            if tokens[0]=="setAttr" and len(tokens)==3:
                c.setAttr(tokens[1],float(tokens[2]))
            elif tokens[0]=="xform":
                options={}
                for flags,key in ((("-t","-translation"),"translation"),(("-ro","-rotation"),"rotation"),(("-s","-scale"),"scale")):
                    index=next((tokens.index(flag) for flag in flags if flag in tokens),None)
                    if index is not None:
                        options[key]=tuple(float(v) for v in tokens[index+1:index+4])
                options["worldSpace" if "-ws" in tokens or "-worldSpace" in tokens else "objectSpace"]=True
                c.xform(tokens[-1],**options)

    def go_to_original_corrective_build_pose(self):
        """asGoToBuildPose catches each failed channel and continues the pose."""
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;failed=[]
        def apply(text):
            for statement in (text or "").split(";"):
                try:self._original_apply_pose_commands(statement)
                except RuntimeError:failed.append(statement)
        for node,reader in (("buildPose",self.read_body_build_pose),("faceBuildPose",self.read_face_build_pose)):
            if not c.objExists(node):continue
            if c.objExists(node+".advPyPoseData"):
                for item in reader().values:
                    plug=item.node+"."+item.attribute
                    try:c.setAttr(plug,item.value)
                    except RuntimeError:failed.append(plug)
            elif c.objExists(node+".udAttr"):apply(c.getAttr(node+".udAttr"))
            if c.objExists(node+".udExtraAttr"):apply(c.getAttr(node+".udExtraAttr"))
        for fit in ("FitSkeleton","FaceFitSkeleton"):
            if c.objExists(fit+".run"):apply(c.getAttr(fit+".run"))
        if c.objExists("GRP_faceGUI"):
            for control in c.listRelatives("GRP_faceGUI",allDescendents=True,type="transform") or []:
                leaf=self._original_restore_leaf(control)
                if not leaf.startswith("CTRL_") or leaf in ("CTRL_faceTweakersGUI","CTRL_expressions","CTRL_GUIswitch"):continue
                for attr in c.listAttr(control,keyable=True) or []:
                    plug=control+"."+attr
                    if c.getAttr(plug,settable=True):c.setAttr(plug,1 if attr.startswith("scale") or attr=="visibility" else 0)
        return tuple(failed)

    def original_driver_uses_opm(self):
        c=self._cmds
        return bool(c.getAttr("FitSkeleton.useOffsetParentMatrix")) if c.objExists("FitSkeleton.useOffsetParentMatrix") else False

    def original_opm_compatible_driver_attr(self, node, attribute):
        c=self._cmds
        if attribute.startswith("qRotate") or not c.objExists(node+".opm") or not c.listConnections(node+".opm"):
            return attribute
        attribute=attribute.removeprefix("opm")
        if attribute in (c.listAttr(node,userDefined=True) or []):
            return attribute
        if not self.original_driver_uses_opm():
            return attribute
        compatible="opm"+attribute
        if c.objExists(node+"."+compatible):
            return compatible
        self._require_transaction()
        self._transaction_changed=True
        pose=self.capture_original_control_pose()
        c.addAttr(node,longName=compatible,attributeType="double")
        dm=c.createNode("decomposeMatrix",name=node+"DM"+attribute)
        c.setAttr(dm+".inputRotateOrder",c.getAttr(node+".rotateOrder"))
        mm=c.createNode("multMatrix",name=node+"DMMM"+attribute)
        c.connectAttr(node+".offsetParentMatrix",mm+".matrixIn[0]")
        parent=c.listRelatives(node,parent=True)[0]
        c.setAttr(mm+".matrixIn[1]",*c.getAttr(parent+".worldMatrix[0]"),type="matrix")
        self.go_to_original_corrective_build_pose()
        inverse=c.getAttr(node+".worldInverseMatrix[0]")
        self.restore_original_control_pose(pose)
        c.setAttr(mm+".matrixIn[2]",*inverse,type="matrix")
        c.connectAttr(mm+".matrixSum",dm+".inputMatrix")
        if attribute.startswith("rotate"):
            c.connectAttr(dm+".outputRotate"+attribute[-1],node+"."+compatible)
        if attribute.startswith("translate"):
            c.connectAttr(dm+".outputTranslate"+attribute[-1],node+"."+compatible)
        return compatible

    def create_original_q_rotate_attrs(self, joint):
        self._require_transaction()
        c=self._cmds
        if c.objExists(joint+".qRotateX"):
            return
        from maya.api import OpenMaya as om
        pose=self.capture_original_control_pose()
        selection=c.ls(selection=True,long=True) or []
        self.go_to_original_corrective_build_pose()
        name,side=joint.rsplit("_",1)
        side="_"+side
        mm=c.createNode("multMatrix",name=name+"QRotateMMTwist"+side)
        c.connectAttr(joint+".matrix",mm+".matrixIn[0]")
        upstream=c.listConnections(joint+".offsetParentMatrix",source=True,destination=False,plugs=True) or []
        if upstream:
            c.connectAttr(upstream[0],mm+".matrixIn[0]",force=True)
        matrix=c.getAttr(mm+".matrixIn[0]")
        c.setAttr(mm+".matrixIn[2]",*tuple(om.MMatrix(matrix).inverse()),type="matrix")
        dm=c.createNode("decomposeMatrix",name=name+"QRotateDMTwist"+side)
        c.connectAttr(mm+".matrixSum",dm+".inputMatrix")
        for axis in "XYZ":
            c.addAttr(joint,longName="qRotate"+axis,attributeType="double",keyable=True)
            qe=c.createNode("quatToEuler",name=name+"QRotate"+axis+"QTETwist"+side)
            c.connectAttr(dm+".outputQuat"+axis,qe+".inputQuatX")
            c.connectAttr(dm+".outputQuatW",qe+".inputQuatW")
            c.connectAttr(qe+".outputRotateX",joint+".qRotate"+axis)
        self.restore_original_control_pose(pose)
        c.select(selection,replace=True) if selection else c.select(clear=True)

    def original_blended_driver_name(self, drivers):
        c=self._cmds
        return "_".join(plug.rsplit(".",1)[1]+("Pos" if c.getAttr(plug)>=0 else "Neg") for plug in drivers)

    def create_original_blended_attribute(self, drivers, attribute=""):
        self._require_transaction()
        c=self._cmds
        selection=c.ls(selection=True,long=True) or []
        node=drivers[0].rsplit(".",1)[0]
        values=[c.getAttr(plug) for plug in drivers]
        if not attribute:
            attribute=self.original_blended_driver_name(drivers)
        if c.objExists(node+"."+attribute):
            return attribute
        c.addAttr(node,longName=attribute,attributeType="double")
        c.setAttr(node+"."+attribute,channelBox=True)
        if not self._original_restore_leaf(node).startswith("FK") and c.objExists("FK"+node):
            c.addAttr("FK"+node,longName=attribute,attributeType="double")
            c.setAttr("FK"+node+"."+attribute,channelBox=True)
            c.connectAttr(node+"."+attribute,"FK"+node+"."+attribute)
        mpd=c.createNode("multiplyDivide",name=node+attribute+"MPD")
        # The source constructs a two-input graph even if discovery names more
        # rotation components. Preserve that graph and its stored two dv values.
        for plug,axis,value in zip(drivers,"XY",values):
            c.connectAttr(self.original_face_output_bw(plug),mpd+".input1"+axis)
            if value==-1:
                c.setAttr(mpd+".input2"+axis,-1)
        pma=c.createNode("plusMinusAverage",name=node+attribute+"PlusMinusAverage")
        for index,axis in enumerate("XY"):
            c.connectAttr(mpd+".output"+axis,pma+".input1D["+str(index)+"]")
        sr=c.createNode("setRange",name=node+attribute+"SetRange")
        c.connectAttr(pma+".output1D",sr+".valueX",force=True)
        c.setAttr(sr+".max",100,100,100,type="float3")
        c.setAttr(sr+".oldMax",200,200,200,type="float3")
        for axis,value in zip("XY",values):
            c.addAttr(sr,longName="dv"+axis,attributeType="double",defaultValue=value,keyable=True)
        qrows=[]
        for plug in drivers:
            fk="FK"+plug.replace("qRotate","rotate")
            if c.objExists(fk):
                qrows.append((fk,c.getAttr(fk)))
        c.addAttr(sr,longName="setQRotatesCmd",dataType="string")
        c.setAttr(sr+".setQRotatesCmd","".join("setAttr "+plug+" "+str(value)+";" for plug,value in qrows),type="string")
        clamp=c.createNode("clamp",name=node+attribute+"Clamp")
        c.connectAttr(sr+".outValueX",clamp+".inputR")
        c.addAttr(node,longName=attribute+"MaxValue",attributeType="double",defaultValue=10)
        c.connectAttr(node+"."+attribute+"MaxValue",clamp+".maxR")
        c.connectAttr(clamp+".outputR",node+"."+attribute)
        self.original_face_output_bw(node+"."+attribute)
        c.select(selection,replace=True) if selection else c.select(clear=True)
        self._transaction_changed=True
        return attribute

    def set_original_blended_attribute(self, control, attribute, value, *, drivers_only=False):
        c=self._cmds
        plug=control+"."+attribute
        drivers=[]; dvs=[]; qcommands=""
        while True:
            nodes=c.listConnections(plug,source=True,destination=False,skipConversionNodes=True) or []
            if not nodes:
                break
            node=nodes[0]
            if c.nodeType(node)=="clamp":
                plug=node+".inputR"
                continue
            if c.nodeType(node)=="multiplyDivide":
                plug=node+".input1X"
                if c.objExists(node+".setQRotatesCmd"):
                    qcommands=c.getAttr(node+".setQRotatesCmd") or ""
                continue
            if c.nodeType(node)=="setRange":
                dvs=[c.getAttr(node+".dvX"),c.getAttr(node+".dvY")]
                if c.objExists(node+".setQRotatesCmd"):
                    qcommands=c.getAttr(node+".setQRotatesCmd") or ""
                pma=c.listConnections(node+".valueX",source=True,destination=False,skipConversionNodes=True)[0]
                mpd=c.listConnections(pma+".input1D[0]",source=True,destination=False,skipConversionNodes=True)[0]
                for axis in "XY":
                    source=c.listConnections(mpd+".input1"+axis,source=True,destination=False,skipConversionNodes=True)[0]
                    source_plug=source+".input[0]" if c.nodeType(source)=="blendWeighted" else mpd+".input1"+axis
                    drivers.append(c.listConnections(source_plug,source=True,destination=False,plugs=True,skipConversionNodes=True)[0])
            break
        if not drivers_only:
            self._require_transaction()
            for driver,dv in zip(drivers,dvs):
                if ".qRotate" in driver:
                    self.restore_original_control_pose(corrective_pose_command_rows(qcommands))
                else:
                    target="FK"+driver if c.objExists("FK"+driver) else driver
                    c.setAttr(target,sqrt(dv*dv*value) if value<1 else dv)
        return tuple(sorted(drivers))

    def find_original_fkik_control(self, obj):
        """asFindFKIKCtrl: ancestor visibility, then shape visibility."""
        c=self._cmds
        if "FKIK" in obj:
            return obj
        current=obj
        for _ in range(99):
            parents=c.listRelatives(current,parent=True) or []
            if not parents:
                break
            current=parents[0]
            condition=c.listConnections(current+".v",source=True,destination=False,type="condition",skipConversionNodes=True) or []
            if condition:
                controls=c.listConnections(condition[0]+".firstTerm",source=True,destination=False,skipConversionNodes=True) or []
                if controls:
                    return controls[0]
        shapes=c.listRelatives(obj,shapes=True) or []
        if shapes:
            nodes=c.listConnections(shapes[0]+".v",source=True,destination=False,skipConversionNodes=True) or []
            if nodes and c.nodeType(nodes[0])=="plusMinusAverage":
                nodes=c.listConnections(nodes[0]+".input1D[0]",source=True,destination=False,skipConversionNodes=True) or []
            if nodes and c.nodeType(nodes[0])=="condition":
                controls=c.listConnections(nodes[0]+".firstTerm",source=True,destination=False,skipConversionNodes=True) or []
                if controls:
                    return controls[0]
        return ""

    def show_original_driving_affected_controls(self, controls, *, affected_only):
        c=self._cmds
        for name in ("ControlSet","FaceControlSet"):
            if not c.objExists(name):continue
            for control in c.sets(name,query=True) or []:
                for shape in c.listRelatives(control,shapes=True,noIntermediate=True) or []:
                    try:c.setAttr(shape+".v",int(not affected_only or control in controls))
                    except RuntimeError:pass

    def remove_original_driving_test_animation(self):
        """asDsRemoveTestAnimation restores the original timeline and visibility."""
        c=self._cmds;raw=getattr(c,"raw",c)
        if c.objExists("EditingDrivingSystem"):
            from maya import mel
            slider=mel.eval("global string $gPlayBackSlider; $gPlayBackSlider;")
            if slider:raw.timeControl(slider,edit=True,snap=bool(c.getAttr("EditingDrivingSystem.preEditSnap")))
            raw.playbackOptions(minTime=c.getAttr("EditingDrivingSystem.preEditMin"),maxTime=c.getAttr("EditingDrivingSystem.preEditMax"),
                animationStartTime=c.getAttr("EditingDrivingSystem.preEditAst"),animationEndTime=c.getAttr("EditingDrivingSystem.preEditAet"))
        if c.objExists("AllSet"):
            for plug in raw.listConnections(":time1.outTime",source=False,destination=True,plugs=True,skipConversionNodes=True) or []:
                node=plug.rsplit(".",1)[0]
                if hasattr(c,"identity") and not c.identity.owns(node):
                    continue
                if c.sets(node,isMember="AllSet"):
                    raw.disconnectAttr(":time1.outTime",plug)
        if raw.headsUpDisplay("HUDEDSMode",query=True,exists=True):
            raw.headsUpDisplay("HUDEDSMode",remove=True)
            raw.displayColor("headsUpDisplayLabels",16)
        if c.objExists("TestSymmetry"):
            temporary=[node for node in c.listConnections("TestSymmetry",source=True,destination=False,type="multiplyDivide") or []
                       if self._original_restore_leaf(node).startswith("TestSymmetry_")]
            c.delete("TestSymmetry")
            if temporary:c.delete(list(dict.fromkeys(temporary)))
        if c.objExists("EditingDrivingSystem"):c.delete("EditingDrivingSystem")
        self.show_original_driving_affected_controls((),affected_only=False)
        for node in ("SmilePullOffset_R","SmilePullOffset_L"):
            if c.objExists(node):c.setAttr(node+".v",1)
        if c.objExists("buildPose") or c.objExists("faceBuildPose"):
            self.go_to_original_corrective_build_pose()
        if c.objExists("MetaHumanControlPanelToggle.MetaHumanControlPanelVis"):
            c.setAttr("MetaHumanControlPanelToggle.MetaHumanControlPanelVis",1)
        raw.dgdirty(allPlugs=True)

    def mute_original_driving_sdks(self, curves):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;raw=getattr(c,"raw",c)
        time=raw.currentTime(query=True);raw.currentTime(0)
        try:
            for curve in curves:
                for node in c.listHistory(curve,future=True) or []:
                    if c.nodeType(node)=="transform":
                        c.mute(node);break
        finally:raw.currentTime(time)

    def unmute_original_driving_sdks(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        nodes=[node for node in c.ls(type="mute") or [] if self._original_restore_leaf(node).startswith("mute_SDK")]
        if nodes:c.delete(nodes)
        return len(nodes)
