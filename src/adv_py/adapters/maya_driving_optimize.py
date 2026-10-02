"""Original DrivingSystem controller placement and obsolete pose cleanup."""
from dataclasses import replace
from math import dist
import json
from adv_py.core.body_parent_constraint import plan_body_parent_constraint
from .maya_original_control_identity import source_fk_joint
from .maya_original_transform_channels import lock_original_transform_channels

class MayaDrivingOptimizeMixin:
    def _original_driving_rla_child(self, joint):
        from .maya_original_rla_child import original_rla_child
        return original_rla_child(self._cmds, joint)

    def _original_driving_lock_transform(self, control, locked):
        lock_original_transform_channels(self._cmds,control,locked,locked,locked,True)

    def optimize_original_driving_controllers(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds
        selection=c.ls(selection=True,long=True) or []
        c.createNode("transform",name="tempSamplerOffset")
        c.createNode("transform",name="tempSampler",parent="tempSamplerOffset")
        optimized=[]
        try:
            for control in c.listRelatives("DrivingSystem",children=True) or [] if c.objExists("DrivingSystem") else []:
                if c.objExists(control+".optimizedDS"):continue
                c.addAttr(control,longName="optimizedDS",attributeType="bool",defaultValue=True)
                old=c.listConnections(control+".tx",source=True,destination=False) or []
                if old and c.nodeType(old[0])=="parentConstraint":c.delete(old[0])
                self._original_driving_lock_transform(control,False)
                curves=list(c.listConnections(control,source=False,destination=True,type="animCurve") or [])
                for bw in c.listConnections(control,source=False,destination=True,type="blendWeighted") or []:
                    curves.extend(c.listConnections(bw,source=False,destination=True,skipConversionNodes=True,type="animCurve") or [])
                joints=[]
                for curve in curves:
                    # asDsOptimizeControllers intentionally resolves SDK*
                    # names only. asGetControlNameFromDSAnimCurve additionally
                    # unwraps bw* names, changing which ancestors are used.
                    leaf=self._original_restore_leaf(curve)
                    node=leaf[3:].rsplit("_",1)[0] if leaf.startswith("SDK") else leaf
                    if node[:1].isdigit():node=node[1:]
                    if not c.objExists(node) or c.nodeType(node) not in ("joint","transform"):continue
                    deform=source_fk_joint(self,node)
                    if c.objExists(deform) and deform not in joints:joints.append(deform)
                joint_paths=[]
                for joint in joints:
                    if c.nodeType(joint)=="joint":joint_paths.append(c.ls(joint,long=True)[0])
                    c.select(control,replace=True)
                    c.aimConstraint(joint,control,offset=(0,0,0),weight=1,aimVector=(1,0,0),upVector=(0,0,1),worldUpType="vector",worldUpVector=(0,1,0))
                common=""
                if joint_paths:
                    for candidate in reversed(joint_paths[0].split("|")[1:-1]):
                        if all("|"+candidate+"|" in path for path in joint_paths):common=candidate;break
                if not common:
                    self._original_driving_lock_transform(control,True)
                    continue
                if common=="DeformationSystem":common="RootX_M"
                c.delete(c.parentConstraint(control,"tempSamplerOffset"))
                position=c.xform(common,query=True,worldSpace=True,translation=True)
                maximum=0.
                for joint in joints:
                    end=self._original_driving_rla_child(joint) or joint
                    maximum=max(maximum,dist(position,c.xform(end,query=True,worldSpace=True,translation=True)))
                    c.delete(c.pointConstraint(end,"tempSampler"))
                if maximum<.01:maximum=.5
                c.delete(c.pointConstraint(common,control))
                aim=control+"_aimConstraint1"
                if c.objExists(aim):c.delete(aim)
                c.setAttr(control+".s",maximum*1.2,maximum*.5,1,type="float3")
                c.makeIdentity(control,apply=True,translate=False,rotate=False,scale=True,normal=0)
                source=c.ls(common,long=True)[0];target=c.ls(control,long=True)[0]
                inputs=self.capture_parent_constraint_input(source,target,True)
                inputs=replace(inputs,use_offset_parent_matrix=self.original_driver_uses_opm(),use_decompose_matrix=True)
                plan=plan_body_parent_constraint(inputs)
                self.preflight_parent_constraint(plan);self.create_parent_constraint(plan)
                nodes=[node for node,kind in plan.create_nodes]
                for plug in (control+".tx",control+".sx"):
                    nodes.extend(c.listConnections(plug,source=True,destination=False,type="constraint") or [])
                if nodes and c.objExists("AllSet"):c.sets(list(dict.fromkeys(nodes)),add="AllSet")
                self._original_driving_lock_transform(control,True);optimized.append(control)
            return tuple(optimized)
        finally:
            if c.objExists("tempSamplerOffset"):c.delete("tempSamplerOffset")
            c.select(selection,replace=True) if selection else c.select(clear=True)

    def update_original_driving_pose_attributes(self):
        self._require_transaction();self._transaction_changed=True
        c=self._cmds;removed=0
        pose=self._capture_original_driving_restore_pose()
        try:
            for plug in ("buildPose.udAttr","faceBuildPose.udAttr","FitSkeleton.run","FaceFitSkeleton.run","buildPose.udExtraAttr","faceBuildPose.udExtraAttr"):
                if not c.objExists(plug):continue
                statements=[]
                for statement in (c.getAttr(plug) or "").split(";"):
                    if not statement.strip():continue
                    try:self._original_apply_pose_commands(statement)
                    except RuntimeError:removed+=1;continue
                    statements.append(statement)
                c.setAttr(plug,";".join(statements)+(";" if statements else ""),type="string")
            for node in ("buildPose","faceBuildPose"):
                if not c.objExists(node+".advPyPoseData"):continue
                rows=json.loads(c.getAttr(node+".advPyPoseData"))
                valid=[row for row in rows if c.objExists(row[0]+"."+row[1])]
                c.setAttr(node+".advPyPoseData",json.dumps(valid),type="string")
            for fit in ("FitSkeleton","FaceFitSkeleton"):
                if c.objExists(fit+".advPyBuildPoseOverrides"):
                    rows=json.loads(c.getAttr(fit+".advPyBuildPoseOverrides"))
                    c.setAttr(fit+".advPyBuildPoseOverrides",json.dumps([row for row in rows if c.objExists(row[0]+"."+row[1])]),type="string")
        finally:self.restore_original_control_pose(tuple((plug,value) for plug,value in pose if c.objExists(plug) and c.getAttr(plug,settable=True)))
        return removed
