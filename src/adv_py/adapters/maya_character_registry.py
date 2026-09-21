from dataclasses import replace

from adv_py.core.character_registry import (
    FORMAT, REGISTRY_NAME, CharacterRegistryError, CharacterNode, CharacterBindJoint,
    CharacterRegistration, encode_registration, decode_registration,
)
from adv_py.application.body_rig_validation import body_bind_pose_matches
from adv_py.core.body_skeleton import audit_body_provenance, oriented_body_provenance


class MayaCharacterRegistryMixin:
    def preflight_character_transfer(self,staged):
        from .maya_character_transfer import preflight
        preflight(self,staged)

    def sample_character_transfer(self,staged,frames,*,target=False):
        from .maya_character_transfer import sample
        return sample(self,staged,frames,target)

    def transfer_character_data(self,staged):
        from .maya_character_transfer import transfer
        transfer(self,staged)

    def verify_character_retained_data(self,staged):
        from .maya_character_transfer import verify_retained
        verify_retained(self,staged)

    def preflight_character_rebuild_namespace(self,namespace):
        from maya import cmds
        from adv_py.core.character_identity import CharacterIdentity
        if self.namespace is None:
            raise CharacterRegistryError('重建必须显式选择角色 namespace；根命名空间使用空字符串')
        identity=CharacterIdentity(namespace)
        if not identity.namespace:
            raise CharacterRegistryError('重建暂存需要非根命名空间')
        if cmds.namespace(exists=namespace) and (cmds.namespaceInfo(namespace,listOnlyDependencyNodes=True,recurse=True)
                or cmds.namespaceInfo(namespace,listOnlyNamespaces=True,recurse=True)):
            raise CharacterRegistryError('重建暂存命名空间已有内容')
        if ':' in namespace and not cmds.namespace(exists=namespace.rsplit(':',1)[0]):
            raise CharacterRegistryError('重建暂存的父命名空间不存在')

    def create_character_rebuild_host(self,namespace):
        self._require_transaction()
        self.preflight_character_rebuild_namespace(namespace)
        from maya import cmds
        from .maya_body import MayaBodyBuildHost
        from contextlib import contextmanager
        parent=self
        class RebuildStageHost(MayaBodyBuildHost):
            @contextmanager
            def transaction(stage,label):
                # The source host owns the one native Undo chunk. A stage
                # failure must propagate before that chunk is rolled back.
                parent._require_transaction()
                if stage._transaction_active:raise RuntimeError('重建暂存不允许嵌套应用事务')
                previous=set(stage._cmds.ls(type='transform',uuid=True) or [])
                stage._transaction_active=True;stage._transaction_changed=False
                try:
                    yield
                    if stage._transaction_changed:stage._checkpoint_new_transform_channels(previous)
                finally:
                    parent._transaction_changed|=stage._transaction_changed
                    stage._transaction_active=False;stage._transaction_changed=False
        self._transaction_changed=True
        if not cmds.namespace(exists=namespace):cmds.namespace(addNamespace=namespace)
        return RebuildStageHost(namespace=namespace)

    def capture_character_preservation(self,registration,extensions=()):
        from .maya_character_preservation import capture
        return capture(self,registration,extensions)

    @staticmethod
    def discover_scene_characters():
        """Physical identities for explicit host selection; never edits a scene."""
        from maya import cmds
        from adv_py.core.character_identity import CharacterIdentity, SceneCharacter
        rows=[]
        for node in cmds.ls(type='network') or []:
            if (node.rsplit(':',1)[-1]!=REGISTRY_NAME or not cmds.objExists(node+'.advPyRegistryOwner')
                    or cmds.getAttr(node+'.advPyRegistryOwner')!=FORMAT):
                continue
            namespace=node.rsplit(':',1)[0] if ':' in node else ''
            rows.append(SceneCharacter(CharacterIdentity(namespace),node,cmds.ls(node,uuid=True)[0],
                                       bool(cmds.referenceQuery(node,isNodeReferenced=True))))
        return tuple(sorted(rows,key=lambda row:row.identity.namespace))

    def preflight_character_space_animation(self, registration):
        from .maya_animated_spaces import preflight
        preflight(self, registration)

    def install_character_space_animation(self, registration):
        from .maya_animated_spaces import install
        return install(self, registration)

    def switch_character_space(self, registration, key, mode, frame):
        from .maya_animated_spaces import switch
        return switch(self, registration, key, mode, frame)

    def describe_character_stretch_matching(self,registration):
        from .maya_limb_shape import describe
        return describe(self,registration)

    def install_character_stretch_matching(self,before,after):
        from .maya_limb_shape import install,describe
        self._require_transaction()
        if self.read_character_registration()!=before or describe(self,before)!=after:
            raise CharacterRegistryError('拉伸匹配扩展计划失效')
        install(self,before,after)
        self.write_character_registration_extension(before,after)

    def sample_character_limb_helpers(self,registration,frames,limb,side):
        from .maya_limb_shape import sample_helpers
        return sample_helpers(self,registration,frames,limb,side)

    def capture_character_stretch_world(self,registration):
        from .maya_limb_shape import bindings
        lengths,volumes=bindings(self,registration)
        paths=[b.target.rsplit('.',1)[0] for b in lengths]+[p for b in volumes for p,_ in b.helpers]
        return tuple((p,self._spine_world_frame(p)[0]) for p in paths)

    def describe_character_limb_animation(self,registration):
        from adv_py.application.body_arm_ik_to_fk import MatchBodyArmIkToFk
        from adv_py.application.body_leg_ik_to_fk import MatchBodyLegIkToFk
        from adv_py.core.character_registry import CharacterChannel
        from adv_py.core.fit_symmetry import FitBuildSide
        self._validate_character_registration(registration)
        c=self._cmds
        from .maya_limb_orientation import preflight_orientation_install, orientation_channels
        preflight_orientation_install(self,registration)
        channels=list(registration.channels)
        existing={ch.key:ch for ch in channels}
        nodes=list(registration.nodes)
        known={n.path for n in nodes}
        for label,service in (("arm",MatchBodyArmIkToFk),("leg",MatchBodyLegIkToFk)):
            for side in (FitBuildSide.RIGHT,FitBuildSide.LEFT):
                # The read-only matching plan resolves actual driver paths and
                # the signed primary axis, including non-X leg constructions.
                plan=service(self).plan(side,registration.container,body_root_name=registration.body_root)
                if plan.provenance_issues or plan.blend_issues or plan.fk_issues:
                    raise CharacterRegistryError("四肢结构无法登记为动画骨段")
                for index,plug in enumerate(plan.match.fk_segment_plugs):
                    path,attribute=plug.rsplit('.',1)
                    channel=CharacterChannel(f"{label}.fkLength.{side.value}.{index}",path,attribute)
                    if channel.key in existing:
                        if existing[channel.key]!=channel:
                            raise CharacterRegistryError("已登记的四肢骨段通道被替换")
                        continue
                    if (c.nodeType(path)!="joint" or c.getAttr(plug,lock=True)
                            or not c.getAttr(plug,keyable=True) or c.listConnections(plug,s=True,d=False)):
                        raise CharacterRegistryError("新增骨段通道锁定、不可写键或已有输入")
                    if any(ch.node==path and ch.attribute==attribute for ch in channels):
                        raise CharacterRegistryError("四肢骨段通道已经以其他语义登记")
                    channels.append(channel)
                    while path:
                        if path not in known:
                            nodes.append(self._registry_node(path));known.add(path)
                        path=path.rsplit('|',1)[0]
        for ch in orientation_channels(registration):
            if ch.key not in existing:
                channels.append(ch)
        result=replace(registration,channels=tuple(channels),nodes=tuple(nodes))
        encode_registration(result)
        return result

    def extend_character_limb_registration(self,before,after):
        self._require_transaction()
        if self.read_character_registration()!=before or self.describe_character_limb_animation(before)!=after:
            raise CharacterRegistryError("角色骨段扩展计划已经失效")
        c=self._cmds
        self._transaction_changed=True
        from .maya_limb_orientation import install_orientation
        install_orientation(self,before)
        self.write_character_registration_extension(before,after)

    def write_character_registration_extension(self,before,after):
        self._require_transaction()
        self._validate_character_registration(after)
        c=self._cmds
        self._transaction_changed=True
        document=REGISTRY_NAME+".advPyRegistryDocument"
        c.setAttr(document,lock=False)
        c.setAttr(document,encode_registration(after),type="string")
        c.setAttr(document,lock=True)
        c.setAttr(REGISTRY_NAME+".members",lock=False)
        for index,member in enumerate(after.nodes[len(before.nodes):],start=len(before.nodes)):
            c.connectAttr(member.path+".message",REGISTRY_NAME+f".members[{index}]")
        c.setAttr(REGISTRY_NAME+".members",lock=True)

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
        if self.namespace is not None and not c.identity.owns(self.scene_address(node)):
            return False
        if attribute!="output" or c.nodeType(node) not in ("animCurveTA","animCurveTL","animCurveTU"):
            return False
        driver=c.connectionInfo(node+".input",sourceFromDestination=True)
        # Maya can use the implicit scene clock without a visible input edge,
        # including curves restored from its native scene format.
        if driver and (driver.rsplit(".",1)[1]!="outTime" or c.nodeType(driver.rsplit(".",1)[0])!="time"):
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
        from .maya_limb_orientation import audit_orientation
        audit_orientation(self,plan)
        from .maya_limb_shape import audit as audit_shape
        audit_shape(self,plan)
        from .maya_animated_spaces import audit as audit_spaces
        audit_spaces(self,plan)
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
        # Undoing a Maya multi-message connection may leave an empty logical
        # array slot. Only trailing, unconnected capacity is permitted.
        if indices[:len(plan.nodes)] != list(range(len(plan.nodes))) or any(
                c.listConnections(name+f".members[{index}]",source=True,destination=False)
                for index in indices[len(plan.nodes):]):
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
