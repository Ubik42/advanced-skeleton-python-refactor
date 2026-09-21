from dataclasses import replace

from adv_py.core.character_registry import (
    FORMAT, REGISTRY_NAME, CharacterRegistryError, CharacterNode, CharacterBindJoint,
    CharacterRegistration, encode_registration, decode_registration,
)
from adv_py.application.body_rig_validation import body_bind_pose_matches
from adv_py.core.body_skeleton import audit_body_provenance, oriented_body_provenance


class MayaCharacterRegistryMixin:
    def _registry_node(self, path):
        c = self._cmds
        if (c.ls(path,long=True) or []) != [path] or c.nodeType(path) not in ("transform","joint"):
            raise CharacterRegistryError("登记节点缺失、歧义或类型无效："+path)
        if c.referenceQuery(path,isNodeReferenced=True) or any(c.lockNode(path,q=True,lock=True) or []):
            raise CharacterRegistryError("登记暂不支持引用或锁定节点："+path)
        inputs=[]
        for attribute in tuple(kind+axis for kind in ("translate","rotate","scale","jointOrient","rotateAxis") for axis in "XYZ")+("offsetParentMatrix",):
            plug=path+"."+attribute
            if not c.objExists(plug):
                continue
            source=c.connectionInfo(plug,sourceFromDestination=True)
            if source:
                node,attr=source.split(".",1)
                inputs.append((attribute,self._resolve_connected_node(node)+"."+attr))
        return CharacterNode(path,c.ls(path,uuid=True)[0],c.nodeType(path),
                             (c.listRelatives(path,parent=True,fullPath=True) or [None])[0],tuple(inputs))

    def _character_direct_animation(self, source):
        """Only native time-input curves may replace an editable user input."""
        c=self._cmds
        node,attribute=source.rsplit(".",1)
        if attribute!="output" or c.nodeType(node) not in ("animCurveTA","animCurveTL","animCurveTU"):
            return False
        driver=c.connectionInfo(node+".input",sourceFromDestination=True)
        if not driver or driver.rsplit(".",1)[1]!="outTime" or c.nodeType(driver.rsplit(".",1)[0])!="time":
            return False
        return True

    def describe_character_registration(self, rig, channels):
        c = self._cmds
        body = self.capture_body_skeleton(rig.body.root)
        if not body_bind_pose_matches(rig.body,body):
            raise CharacterRegistryError("角色必须在构建后的绑定姿态登记")
        spine = rig.plan.torso.torso.spine
        spaces = rig.plan.control_spaces
        self.validate_body_spine(spine)
        for spec in spaces.spaces:
            self.capture_control_space_mode(spec)
        container = rig.plan.arm.safety.symmetry.source.hierarchy.container
        paths = {body.root,container,*(j.path for j in body.joints),*(ch.node for ch in channels)}
        paths.update((spine.root_path,spine.pelvis_control,*spine.fk_controls,*spine.body_joints,
                      spine.ik_offset,spine.ik_control,spine.pole_offset,spine.pole_control,
                      spine.waist_output,spine.chest_space,*(j.path for j in spine.joints)))
        paths.update(p for spec in spaces.spaces for p in (*spec.targets,spec.body_source,spec.global_source))
        for node in tuple(paths):
            parent = node.rsplit("|",1)[0]
            while parent:
                paths.add(parent)
                parent = parent.rsplit("|",1)[0]
        nodes = tuple(self._registry_node(p) for p in sorted(paths))
        resolved = []
        for ch in channels:
            plug = ch.node+"."+ch.attribute
            if not c.objExists(plug) or c.getAttr(plug,lock=True) or c.listConnections(plug,s=True,d=False):
                raise CharacterRegistryError("登记控制通道被占用："+plug)
            minimum = c.attributeQuery(ch.attribute,node=ch.node,minimum=True) if c.attributeQuery(ch.attribute,node=ch.node,minExists=True) else None
            maximum = c.attributeQuery(ch.attribute,node=ch.node,maximum=True) if c.attributeQuery(ch.attribute,node=ch.node,maxExists=True) else None
            resolved.append(replace(ch,minimum=minimum[0] if minimum else None,maximum=maximum[0] if maximum else None))
        plan = CharacterRegistration(body.root,container,tuple(resolved),tuple(
            CharacterBindJoint(j.path,j.parent_path,self._spine_world_frame(j.path)[0]) for j in body.joints),nodes,spine,spaces)
        encode_registration(plan)
        return plan

    def preflight_character_registration(self, plan):
        if self.find_name_collisions(REGISTRY_NAME) or self.discover_character_registrations():
            raise CharacterRegistryError("场景已有登记或登记名称被占用")
        self._validate_character_registration(plan)

    def _validate_character_registration(self, plan):
        c = self._cmds
        user_plugs={channel.node+"."+channel.attribute for channel in plan.channels}
        for node in plan.nodes:
            current=self._registry_node(node.path)
            retained=[]
            for attribute,source in current.inputs:
                if node.path+"."+attribute in user_plugs and self._character_direct_animation(source):
                    continue
                retained.append((attribute,source))
            if replace(current,inputs=tuple(retained)) != node:
                raise CharacterRegistryError("登记节点身份或父级变化："+node.path)
        body = self.capture_body_skeleton(plan.body_root)
        if {(j.path,j.parent_path) for j in body.joints} != {(j.path,j.parent) for j in plan.body}:
            raise CharacterRegistryError("登记 Body 拓扑变化")
        if audit_body_provenance(oriented_body_provenance(plan.container,len(plan.body)),body.provenance):
            raise CharacterRegistryError("Body 所有权无效")
        for channel in plan.channels:
            if not c.objExists(channel.node+"."+channel.attribute):
                raise CharacterRegistryError("登记控制通道缺失")
            source=c.connectionInfo(channel.node+"."+channel.attribute,sourceFromDestination=True)
            if source and not self._character_direct_animation(source):
                raise CharacterRegistryError("登记控制通道有非动画外部输入")
        self.validate_body_spine(plan.spine)
        for spec in plan.spaces.spaces:
            self.capture_control_space_mode(spec)

    def create_character_registration(self, plan):
        self._require_transaction()
        self.preflight_character_registration(plan)
        c = self._cmds
        self._transaction_changed = True
        node = c.createNode("network",name=REGISTRY_NAME,skipSelect=True)
        for attr,value in (("advPyRegistryOwner",FORMAT),("advPyRegistryDocument",encode_registration(plan))):
            c.addAttr(node,longName=attr,dataType="string")
            c.setAttr(node+"."+attr,value,type="string",lock=True)
        c.addAttr(node,longName="members",attributeType="message",multi=True)
        for index,member in enumerate(plan.nodes):
            c.connectAttr(member.path+".message",node+f".members[{index}]")
        c.setAttr(node+".members",lock=True)

    def discover_character_registrations(self):
        c = self._cmds
        return tuple(sorted(n for n in c.ls(type="network") or []
                            if c.objExists(n+".advPyRegistryOwner") and c.getAttr(n+".advPyRegistryOwner")==FORMAT))

    def read_character_registration(self, name=REGISTRY_NAME):
        c = self._cmds
        if name != REGISTRY_NAME or (c.ls(name,long=True) or []) != [name] or c.nodeType(name)!="network":
            raise CharacterRegistryError("当前仅支持明确的标准单角色登记节点")
        if c.referenceQuery(name,isNodeReferenced=True) or self.discover_character_registrations() != (name,):
            raise CharacterRegistryError("角色登记归属、数量或引用状态无效")
        if not c.objExists(name+".advPyRegistryDocument"):
            raise CharacterRegistryError("角色登记文档缺失")
        plan = decode_registration(c.getAttr(name+".advPyRegistryDocument"))
        indices = c.getAttr(name+".members",multiIndices=True) or []
        if indices != list(range(len(plan.nodes))):
            raise CharacterRegistryError("角色登记成员列表不完整")
        for index,member in enumerate(plan.nodes):
            inputs = c.listConnections(name+f".members[{index}]",source=True,destination=False,plugs=True) or []
            if len(inputs)!=1:
                raise CharacterRegistryError("登记成员连接缺失或歧义")
            node,attr = inputs[0].rsplit(".",1)
            if attr!="message" or self._resolve_connected_node(node)!=member.path:
                raise CharacterRegistryError("登记成员连接被替换")
        self._validate_character_registration(plan)
        return plan
