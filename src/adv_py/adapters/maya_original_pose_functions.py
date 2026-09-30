"""Native asPoseAdd/Store and CustomOrient enable/disable (MEL 68503–68686)."""
import json
import re
from adv_py.core.driving_systems import DrivingCreateOptions
from adv_py.core.corrective_shapes import corrective_round

_POSE_RESERVED=frozenset(("run","preRebuildScript","postRebuildScript","objectsSkin","objectsAll","objectsRightEye","objectsLeftEye"))

class MayaOriginalPoseFunctionsMixin:
    def original_stored_pose_names(self):
        c=self._cmds
        if not c.objExists("FitSkeleton"):return ()
        return tuple(attr for attr in c.listAttr("FitSkeleton",userDefined=True) or []
                     if attr not in _POSE_RESERVED and not attr.startswith("advPy") and c.getAttr("FitSkeleton."+attr,type=True)=="string")

    def store_original_named_pose(self, name, *, overwrite=False):
        self._require_transaction();c=self._cmds
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name) or name in _POSE_RESERVED or name.startswith("advPy"):
            raise ValueError("姿态名称须为有效属性名，且不能覆盖构建或工程元数据")
        if not c.objExists("FitSkeleton"):raise ValueError("没有 FitSkeleton，无法保存原版姿态")
        plug="FitSkeleton."+name
        if c.objExists(plug) and (c.getAttr(plug,type=True)!="string" or not overwrite):raise ValueError("姿态名称已存在，请启用覆盖或换一个名称")
        self._transaction_changed=True
        self.remove_original_driving_symmetry_preview()
        plan=self.capture_original_driving_create(DrivingCreateOptions())
        commands="".join("setAttr "+row.plug+" "+str(corrective_round(row.value))+";" for row in plan["channels"])
        self._transaction_changed=True
        if not c.objExists(plug):c.addAttr("FitSkeleton",longName=name,dataType="string")
        c.setAttr(plug,commands,type="string")
        self._corrective_raw().optionVar(stringValue=("asStorePoseName",name))
        return {"pose":name,"channels":len(plan["channels"])}

    def apply_original_named_pose(self, name):
        self._require_transaction();c=self._cmds
        if name not in self.original_stored_pose_names():raise ValueError("原版保存姿态不存在："+name)
        self._transaction_changed=True
        self.go_to_original_corrective_build_pose()
        self._original_apply_pose_commands(c.getAttr("FitSkeleton."+name))
        return name

    def delete_original_named_pose(self, name):
        self._require_transaction();c=self._cmds
        if name not in self.original_stored_pose_names():raise ValueError("原版保存姿态不存在："+name)
        self._transaction_changed=True;c.deleteAttr("FitSkeleton."+name)
        return name

    def add_original_build_pose_channels(self, objects, attributes=()):
        self._require_transaction();c=self._cmds
        if not objects:raise ValueError("请先选择需要加入构建姿态的对象")
        if not c.objExists("FitSkeleton"):raise ValueError("当前角色没有 FitSkeleton")
        rows=[]
        for node in objects:
            if "." in node:plugs=[node]
            else:plugs=[node+"."+attr for attr in (attributes or c.listAttr(node,keyable=True) or [])]
            for plug in plugs:
                value=c.getAttr(plug)
                if not isinstance(value,(int,float)):raise ValueError("构建姿态只支持数值通道："+plug)
                node,attr=plug.rsplit(".",1)
                rows.append((self._original_restore_leaf(node),c.attributeQuery(attr,node=node,longName=True),value))
        source=(c.getAttr("FitSkeleton.run") or "") if c.objExists("FitSkeleton.run") else ""
        existing={part.strip() for part in source.split(";") if part.strip()}
        self._transaction_changed=True
        for node,attr,value in rows:
            statement="setAttr "+node+"."+attr+" "+str(value)
            if statement not in existing:source+=(";" if source and not source.endswith(";") else "")+statement+";";existing.add(statement)
        if not c.objExists("FitSkeleton.run"):c.addAttr("FitSkeleton",longName="run",dataType="string")
        c.setAttr("FitSkeleton.run",source,type="string")
        plug="FitSkeleton.advPyBuildPoseOverrides"
        overrides=json.loads(c.getAttr(plug)) if c.objExists(plug) else []
        values={(self._original_restore_leaf(row[0]),row[1]):row[2] for row in overrides}
        values.update({(node,attr):value for node,attr,value in rows})
        if not c.objExists(plug):c.addAttr("FitSkeleton",longName="advPyBuildPoseOverrides",dataType="string")
        c.setAttr(plug,json.dumps([(node,attr,value) for (node,attr),value in values.items()]),type="string")
        return len(rows)

    def toggle_original_custom_orients(self, enabled):
        self._require_transaction();c=self._cmds
        exists=c.objExists("CustomOrientsDisabled")
        if enabled and not exists:raise ValueError("自定义朝向已经启用")
        if not enabled and exists:raise ValueError("自定义朝向已经禁用")
        nonneutral=[plug for plug,neutral in self.original_driving_build_pose_rows()
                    if c.objExists(plug) and abs(c.getAttr(plug)-neutral)>.001]
        if nonneutral:raise ValueError("请先返回构建姿态，再切换自定义朝向："+nonneutral[0])
        self._transaction_changed=True;count=0
        if enabled:
            for attr in c.listAttr("CustomOrientsDisabled",userDefined=True) or []:
                node,channel=attr.rsplit("_",1)
                c.setAttr(node+"."+channel,c.getAttr("CustomOrientsDisabled."+attr));count+=1
            c.delete("CustomOrientsDisabled")
        else:
            nodes=c.ls("CustomOrient*",type="transform") or []
            c.createNode("transform",name="CustomOrientsDisabled")
            for channel in "trs":
                for axis in "xyz":c.setAttr("CustomOrientsDisabled."+channel+axis,lock=True,keyable=False)
            c.setAttr("CustomOrientsDisabled.v",lock=True,keyable=False)
            for node in nodes:
                for channel,neutral in (("r",0),("s",1)):
                    for axis in "xyz":
                        plug=node+"."+channel+axis;value=c.getAttr(plug)
                        if value==neutral:continue
                        attr=self._original_restore_leaf(node)+"_"+channel+axis
                        c.addAttr("CustomOrientsDisabled",longName=attr,attributeType="double",defaultValue=value,keyable=True)
                        c.setAttr(plug,neutral);count+=1
        return count
