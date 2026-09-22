"""Conservative namespace takeover after original Skin influence handoff."""
from dataclasses import dataclass
import re

from adv_py.core.character_identity import CharacterIdentity, SHARED_NODES
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.body_spline import BodySplinePlan

from .maya_body import MayaBodyBuildHost
from .maya_spine_skin_handoff import MayaSpineSkinHandoffHost
from .maya_character_preservation import capture_curve, capture_extension


def _uuid(cmds, node):
    values = cmds.ls(node, uuid=True) or []
    if len(values) != 1:
        raise CharacterRegistryError('角色节点 UUID 缺失或歧义：' + node)
    return values[0]


def _name(cmds, uuid):
    values = cmds.ls(uuid, long=True) or []
    if len(values) != 1:
        raise CharacterRegistryError('原位接管节点 UUID 已变化：' + uuid)
    return values[0]


def _plug_uuid(cmds, plug):
    matches = cmds.ls(plug, long=True) or []
    if len(matches) != 1:
        raise CharacterRegistryError('角色连接端点不唯一：' + plug)
    return _uuid(cmds, matches[0].split('.', 1)[0])


def _namespace_nodes(cmds, namespace):
    names = cmds.namespaceInfo(':' + namespace,
        listOnlyDependencyNodes=True, recurse=True) or []
    return {_uuid(cmds, name): (cmds.ls(name, long=True) or [name])[0]
            for name in names}


def _rig_role(cmds, node, registered, fit_root):
    if node in registered or node == fit_root or node.startswith(fit_root + '|'):
        return True
    leaf = node.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    return leaf.startswith('AdvPy_') or bool(re.fullmatch(r'effector[1-9][0-9]*', leaf))


@dataclass(frozen=True, slots=True)
class OriginalSpineRetainedSkin:
    skin_name: str
    mesh_path: str
    state: object
    boundary: tuple


@dataclass(frozen=True, slots=True)
class OriginalSpineExtensionMove:
    uuid: str
    old_path: str
    target_parent: str
    old_parent_uuid: str
    target_parent_uuid: str
    snapshot: object
    member_uuids: tuple[str, ...]
    member_snapshots: tuple[object, ...]
    world_samples: tuple[tuple[float, tuple[float, ...]], ...] = ()
    parent_world_samples: tuple[tuple[float, tuple[float, ...]], ...] = ()
    curves: tuple[object, ...] = ()
    curve_outputs: tuple[tuple[str, str, str], ...] = ()
    internal_connections: tuple[tuple[str, str, str, str], ...] = ()
    requires_compensation: bool = False


@dataclass(frozen=True, slots=True)
class InstalledSpineExtension:
    move: OriginalSpineExtensionMove
    compensator_uuid: str | None


@dataclass(frozen=True, slots=True)
class OriginalSpinePromotionPlan:
    source_namespace: str
    target_namespace: str
    source_registration: object
    target_registration: object
    assets: tuple[OriginalSpineRetainedSkin, ...]
    deletion_uuids: tuple[str, ...]
    retained_uuids: tuple[str, ...]
    target_uuids: tuple[str, ...]
    extension_uuids: tuple[str, ...] = ()

    @property
    def skin_name(self):
        return self.assets[0].skin_name

    @property
    def mesh_path(self):
        return self.assets[0].mesh_path

    @property
    def skin_state(self):
        return self.assets[0].state

    @property
    def boundary(self):
        return self.assets[0].boundary


class MayaOriginalSpinePromotionHost(MayaSpineSkinHandoffHost):
    """Move a replacement Rig into the original namespace without touching Skin."""

    def plan_original_spine_retained_assets(self, source_namespace, roots):
        from maya import cmds

        roots=tuple(roots)
        if not roots:return ()
        source=MayaBodyBuildHost(namespace=source_namespace)
        registration=source.read_character_registration()
        registered={source.scene_address(row.path) for row in registration.nodes}
        owner=CharacterIdentity(source_namespace)
        used=set()
        for root in roots:
            matches=cmds.ls(root,long=True,type='transform') or []
            if (matches!=[root] or not owner.owns(root)
                    or cmds.listRelatives(root,parent=True,fullPath=True)):
                raise CharacterRegistryError('保留资产须为原角色的独立完整 DAG 根：'
                                             +str(root))
            nodes=(root,*(cmds.listRelatives(root,allDescendents=True,
                                              fullPath=True) or ()))
            if any(node in registered or not owner.owns(node)
                   or cmds.referenceQuery(node,isNodeReferenced=True)
                   or any(cmds.lockNode(node,query=True,lock=True) or [])
                   for node in nodes):
                raise CharacterRegistryError('保留资产不能包含原 Rig 或不可写节点：'
                                             +root)
            uuids={_uuid(cmds,node) for node in nodes}
            if used.intersection(uuids):
                raise CharacterRegistryError('保留资产根相互重复或嵌套：'+root)
            used.update(uuids)
        return tuple(sorted(used))

    def plan_original_spine_extensions(self, source_namespace,
                                       target_namespace, extensions, frames=()):
        from maya import cmds
        source = MayaBodyBuildHost(namespace=source_namespace)
        target = MayaBodyBuildHost(namespace=target_namespace)
        source_reg = source.read_character_registration()
        target_reg = target.read_character_registration()
        if (not isinstance(source_reg.spine,BodySplinePlan)
                or not isinstance(target_reg.spine,BodySplinePlan)):
            raise CharacterRegistryError('附件变拓扑映射要求两个可变脊柱角色')
        old_roles = {row.path for row in source_reg.nodes}
        new_roles = {row.path for row in target_reg.nodes}
        source_body_paths = {row.path for row in source_reg.body}
        source_spine_body = set(source_reg.spine.body_joints)
        source_body_names = [row.path.rsplit('|', 1)[-1]
                             for row in source_reg.body]
        if len(source_body_names) != len(set(source_body_names)):
            raise CharacterRegistryError('来源 Body 关节短名不唯一')
        target_body_by_name = {}
        for row in target_reg.body:
            name = row.path.rsplit('|', 1)[-1]
            if name in target_body_by_name:
                raise CharacterRegistryError('目标 Body 关节短名不唯一：' + name)
            target_body_by_name[name] = row.path
        def target_role(logical):
            if logical in source_reg.spine.fk_controls:
                source_index = source_reg.spine.fk_controls.index(logical)
                def normalized(lengths):
                    total=sum(lengths)
                    return tuple(sum(lengths[:index])/total
                                 for index in range(len(lengths)+1))
                source_positions=normalized(source_reg.spine.lengths)
                target_positions=normalized(target_reg.spine.lengths)
                position=source_positions[source_index]
                target_index=min(range(len(target_positions)),
                    key=lambda index:(abs(target_positions[index]-position),index))
                return target_reg.spine.fk_controls[target_index]
            if logical in source_body_paths and logical not in source_spine_body:
                return target_body_by_name.get(logical.rsplit('|', 1)[-1], logical)
            return logical
        moves = []
        used = set()
        current_time = cmds.currentTime(query=True)
        for path in tuple(extensions):
            matches = cmds.ls(path, long=True, type='transform') or []
            if len(matches) != 1 or matches[0] != path:
                raise CharacterRegistryError('附件须是唯一的完整 transform 路径：' + path)
            if not CharacterIdentity(source_namespace).owns(path):
                raise CharacterRegistryError('附件不属于原角色：' + path)
            parent = (cmds.listRelatives(path, parent=True, fullPath=True) or [None])[0]
            logical = CharacterIdentity(source_namespace).to_local(parent)
            destination = target_role(logical)
            if logical not in old_roles or destination not in new_roles:
                raise CharacterRegistryError('附件父控制在目标角色没有同一路径：' + str(parent))
            target_parent = CharacterIdentity(target_namespace).to_scene(destination)
            if not cmds.objExists(target_parent):
                raise CharacterRegistryError('目标附件父控制缺失：' + target_parent)
            source_matrix = cmds.xform(parent, query=True, worldSpace=True, matrix=True)
            target_matrix = cmds.xform(target_parent, query=True,
                                       worldSpace=True, matrix=True)
            members = (path, *(cmds.listRelatives(path, allDescendents=True,
                                                  fullPath=True) or []))
            member_uuids = tuple(_uuid(cmds, node) for node in members)
            member_set = set(member_uuids)
            if used.intersection(member_uuids):
                raise CharacterRegistryError('附件根相互嵌套或重复')
            used.update(member_uuids)
            snapshots = []
            curves = {}
            curve_outputs = {}
            internal_connections = set()
            for node in members:
                if (not CharacterIdentity(source_namespace).owns(node)
                        or cmds.referenceQuery(node, isNodeReferenced=True)
                        or any(cmds.lockNode(node, query=True, lock=True) or [])):
                    raise CharacterRegistryError('附件子节点不可迁移：' + node)
                inputs = cmds.listConnections(node, source=True,
                    destination=False, plugs=True, connections=True) or []
                for local, incoming in zip(inputs[::2], inputs[1::2]):
                    curve = incoming.rsplit('.',1)[0]
                    incoming_uuid = _plug_uuid(cmds,incoming)
                    if incoming_uuid in member_set:
                        internal_connections.add((incoming_uuid,
                            incoming.split('.',1)[1], _plug_uuid(cmds,local),
                            local.split('.',1)[1]))
                        continue
                    if (not cmds.nodeType(curve).startswith('animCurve')
                            or not incoming.endswith('.output')
                            or len(cmds.listConnections(curve + '.output',
                                source=False, destination=True,
                                plugs=True) or []) != 1):
                        raise CharacterRegistryError('附件输入需要独占的原生动画曲线：'
                                                     + node)
                    driver = cmds.connectionInfo(curve + '.input',
                                                  sourceFromDestination=True)
                    if driver and driver != 'time1.outTime':
                        raise CharacterRegistryError('附件动画曲线不是原生时间驱动：'
                                                     + curve)
                    curves[_uuid(cmds,curve)] = capture_curve(self,curve)
                    curve_outputs[_uuid(cmds,curve)] = (
                        _uuid(cmds,curve),_plug_uuid(cmds,local),
                        local.rsplit('.',1)[-1])
                snapshots.append(capture_extension(self,node))
            requires_compensation = (destination != logical
                or max(abs(a-b) for a,b in
                       zip(source_matrix,target_matrix)) > 1e-4)
            world_samples = []
            parent_samples = []
            try:
                for frame in frames:
                    cmds.currentTime(frame, edit=True)
                    world_samples.append((float(frame),tuple(cmds.xform(
                        path, query=True, worldSpace=True, matrix=True))))
                    parent_samples.append((float(frame),tuple(cmds.xform(
                        parent, query=True, worldSpace=True, matrix=True))))
            finally:
                cmds.currentTime(current_time, edit=True)
            moves.append(OriginalSpineExtensionMove(_uuid(cmds,path),path,
                target_parent,_uuid(cmds,parent),_uuid(cmds,target_parent),
                snapshots[0],member_uuids,tuple(snapshots),
                tuple(world_samples),tuple(parent_samples),
                tuple(curves.values()),tuple(curve_outputs.values()),
                tuple(sorted(internal_connections)),requires_compensation))
        # Explicit attachments cannot retain hidden connections to the old Rig.
        old_uuids = {_uuid(cmds, source.scene_address(row.path))
                     for row in source_reg.nodes}
        for move in moves:
            for uuid in move.member_uuids:
                node = _name(cmds,uuid)
                for plug in cmds.listConnections(node, source=True,
                    destination=True, plugs=True) or []:
                    if _plug_uuid(cmds,plug) in old_uuids:
                        raise CharacterRegistryError('附件仍连接旧 Rig：' + node)
        return tuple(moves)

    def apply_original_spine_extensions(self, moves):
        from maya import cmds
        self._require_transaction()
        installed = []
        for move in moves:
            if (_name(cmds,move.uuid) != move.old_path
                    or _uuid(cmds,move.target_parent) != move.target_parent_uuid
                    or _uuid(cmds,move.old_path.rsplit('|',1)[0])
                    != move.old_parent_uuid
                    or capture_extension(self,move.old_path) != move.snapshot):
                raise CharacterRegistryError('附件在迁移前发生变化：' + move.old_path)
            self._transaction_changed = True
            group_uuid = None
            parent = move.target_parent
            if move.curves or move.requires_compensation:
                owner = move.old_path.rsplit('|',1)[-1].split(':',1)[0]
                group = cmds.createNode('transform',
                    name=owner + ':AdvPy_Extension_'
                    + move.uuid[:8].replace('-','') + '_Compensator',
                    parent=move.target_parent)
                group_uuid = _uuid(cmds,group)
                parent = group
            cmds.parent(move.old_path, parent, relative=True)
            current = capture_extension(self,_name(cmds,move.uuid))
            if (current.uuid != move.uuid
                    or current.attributes != move.snapshot.attributes
                    or current.matrix != move.snapshot.matrix):
                raise RuntimeError('附件迁移改变属性或局部变换：' + move.old_path)
            row = InstalledSpineExtension(move,group_uuid)
            installed.append(row)
            self.verify_promoted_spine_extensions((row,))
        return tuple(installed)

    def bake_original_spine_extensions(self, installed):
        from maya import cmds
        self._require_transaction()
        current_time = cmds.currentTime(query=True)
        attributes = ('translateX','translateY','translateZ',
                      'rotateX','rotateY','rotateZ',
                      'scaleX','scaleY','scaleZ')
        curves = []
        try:
            for row in installed:
                move = row.move
                node = _name(cmds,row.compensator_uuid or move.uuid)
                desired = (move.parent_world_samples if row.compensator_uuid
                           else move.world_samples)
                for frame, matrix in desired:
                    cmds.currentTime(frame, edit=True)
                    self._transaction_changed = True
                    cmds.xform(node, worldSpace=True, matrix=matrix)
                    for attribute in attributes:
                        cmds.setKeyframe(node, attribute=attribute, time=frame)
                    actual = tuple(cmds.xform(node, query=True,
                                              worldSpace=True, matrix=True))
                    if max(abs(a-b) for a,b in zip(actual,matrix)) > 1e-4:
                        raise RuntimeError('附件世界轨迹在采样帧无法复现：' + node)
                for frame, matrix in move.world_samples:
                    cmds.currentTime(frame, edit=True)
                    actual = tuple(cmds.xform(_name(cmds,move.uuid), query=True,
                                              worldSpace=True, matrix=True))
                    if max(abs(a-b) for a,b in zip(actual,matrix)) > 1e-4:
                        raise RuntimeError('附件关键帧写入改变先前世界轨迹：' + node)
                for attribute in attributes:
                    drivers = cmds.listConnections(node + '.' + attribute,
                        source=True, destination=False, type='animCurve') or []
                    if len(drivers) != 1:
                        raise RuntimeError('附件烘焙曲线缺失或歧义：' + node)
                    curve = drivers[0]
                    outputs = cmds.listConnections(curve + '.output',
                        source=False, destination=True, plugs=True) or []
                    if (len(outputs) != 1
                            or _plug_uuid(cmds,outputs[0])
                            != (row.compensator_uuid or move.uuid)
                            or outputs[0].rsplit('.',1)[-1] != attribute):
                        raise RuntimeError('附件烘焙曲线被其他通道共享：' + curve)
                    uuid = _uuid(cmds,curve)
                    owner = node.rsplit('|',1)[-1].split(':',1)[0]
                    cmds.rename(curve, ':' + owner + ':AdvPy_Extension_'
                                + move.uuid[:8].replace('-','') + '_' + attribute)
                    curves.append(uuid)
        finally:
            cmds.currentTime(current_time, edit=True)
        return tuple(curves)

    def verify_promoted_spine_extensions(self, installed):
        from maya import cmds
        from dataclasses import replace
        for row in installed:
            move = row.move
            for uuid, snapshot in zip(move.member_uuids,
                                      move.member_snapshots):
                actual = capture_extension(self,_name(cmds,uuid))
                if (actual.uuid != uuid or actual.node_type != snapshot.node_type
                        or actual.attributes != snapshot.attributes
                        or ((uuid != move.uuid or row.compensator_uuid)
                            and actual.matrix != snapshot.matrix)):
                    raise RuntimeError('附件子节点属性或局部变换变化：'
                                       + snapshot.path)
            for original in move.curves:
                current = capture_curve(self,_name(cmds,original.uuid))
                if replace(current,node=original.node,input=original.input,
                           outputs=original.outputs) != original:
                    raise RuntimeError('附件原有动画曲线被修改：' + original.node)
            for curve_uuid,member_uuid,attribute in move.curve_outputs:
                outputs = cmds.listConnections(_name(cmds,curve_uuid)+'.output',
                    source=False, destination=True, plugs=True) or []
                if (len(outputs) != 1
                        or _plug_uuid(cmds,outputs[0]) != member_uuid
                        or outputs[0].rsplit('.',1)[-1] != attribute):
                    raise RuntimeError('附件原有动画曲线连接被修改：'
                                       + _name(cmds,curve_uuid))
            for source_uuid,source_attr,dest_uuid,dest_attr in move.internal_connections:
                destination = _name(cmds,dest_uuid)+'.'+dest_attr
                actual = cmds.connectionInfo(destination,
                                             sourceFromDestination=True)
                if (not actual or _plug_uuid(cmds,actual) != source_uuid
                        or actual.split('.',1)[1] != source_attr):
                    raise RuntimeError('附件内部驱动连接被修改：'+destination)

    def original_spine_extension_curve_uuids(self, moves, source_namespace):
        from maya import cmds
        owner = CharacterIdentity(source_namespace)
        return tuple(curve.uuid for move in moves for curve in move.curves
                     if owner.owns(_name(cmds,curve.uuid)))

    def plan_original_spine_promotion(self, source_namespace, target_namespace,
                                       skin_name, mesh_path):
        return self.plan_original_spine_promotion_many(source_namespace,
            target_namespace, ((skin_name, mesh_path),))

    def plan_original_spine_promotion_many(self, source_namespace,
                                            target_namespace, skins,
                                            extension_uuids=()):
        from maya import cmds
        skins = tuple(skins)
        if (not skins or len(skins) != len({row[0] for row in skins})
                or len(skins) != len({row[1] for row in skins})):
            raise CharacterRegistryError('原位接管需要非空且唯一的 Skin／网格清单')
        if (not source_namespace or not target_namespace
                or source_namespace == target_namespace
                or ':' in source_namespace or ':' in target_namespace):
            raise CharacterRegistryError('原位接管要求两个不同的顶层角色命名空间')
        if (cmds.namespaceInfo(':' + source_namespace,
                listOnlyNamespaces=True, recurse=True)
                or cmds.namespaceInfo(':' + target_namespace,
                listOnlyNamespaces=True, recurse=True)):
            raise CharacterRegistryError('原位接管尚不处理嵌套命名空间')
        source = MayaBodyBuildHost(namespace=source_namespace)
        target = MayaBodyBuildHost(namespace=target_namespace)
        source_reg = source.read_character_registration()
        target_reg = target.read_character_registration()
        if source_reg.container != target_reg.container:
            raise CharacterRegistryError('新旧角色 Fit 容器路径不同')
        source_nodes = _namespace_nodes(cmds, source_namespace)
        target_nodes = _namespace_nodes(cmds, target_namespace)
        if not source_nodes or not target_nodes:
            raise CharacterRegistryError('新旧角色命名空间缺少节点')
        retained = set()
        assets = []
        for skin_name, mesh_path in skins:
            owner = CharacterIdentity(source_namespace)
            if not owner.owns(skin_name) or not owner.owns(mesh_path):
                raise CharacterRegistryError('保留的 Skin 与网格须归属原角色：'
                                             + skin_name)
            state = self.capture_all_skin_weights(skin_name, mesh_path)
            if (state.skin_name != skin_name or state.geometry_path != mesh_path
                    or not state.influence_paths
                    or any(not CharacterIdentity(target_namespace).owns(p)
                           for p in state.influence_paths)):
                raise CharacterRegistryError('原 Skin 尚未完整交给目标角色：'
                                             + skin_name)
            boundary = self.capture_skin_handoff_boundary(skin_name, mesh_path)
            mesh = (cmds.ls(mesh_path, long=True, type='transform') or [None])[0]
            if mesh != mesh_path:
                raise CharacterRegistryError('原网格路径不唯一：' + mesh_path)
            retained.update((_uuid(cmds, mesh), _uuid(cmds, skin_name)))
            retained.update(_uuid(cmds, node) for node in
                (cmds.listRelatives(mesh, allDescendents=True, fullPath=True) or []))
            retained.update(_uuid(cmds, node) for node in
                (cmds.listHistory(mesh, pruneDagObjects=True) or []))
            pose = cmds.listConnections(skin_name + '.bindPose', source=True,
                                        destination=False, type='dagPose') or []
            if len(pose) > 1:
                raise CharacterRegistryError('原 Skin 绑定姿态不唯一')
            retained.update(_uuid(cmds, node) for node in pose)
            assets.append(OriginalSpineRetainedSkin(
                skin_name, mesh_path, state, boundary))
        retained &= set(source_nodes)
        extension_uuids = tuple(sorted(set(extension_uuids)))
        for uuid in extension_uuids:
            if uuid not in source_nodes:
                raise CharacterRegistryError('附件 UUID 不在原角色命名空间：' + uuid)
            node = source_nodes[uuid]
            parent = (cmds.listRelatives(node, parent=True,
                        fullPath=True) or [None])[0] if 'dagNode' in (
                            cmds.nodeType(node, inherited=True) or []) else None
            if parent and (CharacterIdentity(source_namespace).owns(parent)
                           and _uuid(cmds,parent) not in extension_uuids):
                raise CharacterRegistryError('附件尚未挂到目标 Rig：' + node)
        retained.update(extension_uuids)
        deletion = set(source_nodes) - retained
        source_registered = {source.scene_address(row.path)
                             for row in source_reg.nodes}
        target_registered = {target.scene_address(row.path)
                             for row in target_reg.nodes}
        source_fit = source.scene_address(source_reg.container)
        target_fit = target.scene_address(target_reg.container)
        for uuid in deletion:
            node = source_nodes[uuid]
            if not _rig_role(cmds, node, source_registered, source_fit):
                raise CharacterRegistryError('旧角色存在未声明的用户节点：' + node)
        for uuid, node in target_nodes.items():
            if not _rig_role(cmds, node, target_registered, target_fit):
                raise CharacterRegistryError('目标角色暂存空间含额外资产：' + node)
        # Maya inserts unitConversion nodes at scene root for keyed channels.
        # They are owned only when every input and output stays in the old Rig.
        conversion_nodes = {}
        for uuid in tuple(deletion):
            node = source_nodes[uuid]
            for peer in cmds.listConnections(node, source=True,
                destination=True) or []:
                if (cmds.nodeType(peer) == 'unitConversion'
                        and not CharacterIdentity(source_namespace).owns(peer)):
                    conversion_nodes[_uuid(cmds, peer)] = peer
        for uuid, node in conversion_nodes.items():
            peers = cmds.listConnections(node, source=True,
                                         destination=True) or []
            if not peers or any(_uuid(cmds, peer) not in deletion
                                for peer in peers):
                raise CharacterRegistryError('旧 Rig 的单位转换节点由外部共享：' + node)
        deletion.update(conversion_nodes)
        candidates = {**source_nodes, **conversion_nodes}
        for uuid in (*deletion, *target_nodes):
            node = candidates.get(uuid, target_nodes.get(uuid))
            if (cmds.referenceQuery(node, isNodeReferenced=True)
                    or any(cmds.lockNode(node, query=True, lock=True) or [])):
                raise CharacterRegistryError('原位接管节点被引用或锁定：' + node)
        shared = set(SHARED_NODES) | {'initialShadingGroup', 'initialParticleSE',
            'defaultLightSet', 'defaultObjectSet'}
        for uuid in deletion:
            node = candidates[uuid]
            if 'dagNode' in (cmds.nodeType(node, inherited=True) or []):
                for child in cmds.listRelatives(node, children=True,
                                                fullPath=True) or []:
                    if _uuid(cmds, child) not in deletion:
                        raise CharacterRegistryError('旧 Rig 下含保留子节点：' + child)
            pairs = cmds.listConnections(node, source=True, destination=True,
                                         plugs=True, connections=True) or []
            for connected in pairs[1::2]:
                peer = connected.rsplit('.', 1)[0]
                if peer.lstrip(':') in shared:
                    continue
                if _plug_uuid(cmds, connected) not in deletion:
                    raise CharacterRegistryError('旧 Rig 仍连接外部或保留数据：'
                                                 + node + ' -> ' + connected)
        source_kept_names = {node.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
                             for uuid, node in source_nodes.items() if uuid in retained}
        target_names = {node.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
                        for node in target_nodes.values()}
        if source_kept_names & target_names:
            raise CharacterRegistryError('接管后保留节点与目标 Rig 名称冲突')
        return OriginalSpinePromotionPlan(source_namespace, target_namespace,
            source_reg, target_reg, tuple(assets),
            tuple(sorted(deletion)), tuple(sorted(retained)),
            tuple(sorted(target_nodes)), extension_uuids)

    def apply_original_spine_promotion(self, plan):
        from maya import cmds
        self._require_transaction()
        current = self.plan_original_spine_promotion_many(
            plan.source_namespace, plan.target_namespace,
            ((asset.skin_name, asset.mesh_path) for asset in plan.assets),
            plan.extension_uuids)
        if current != plan:
            raise CharacterRegistryError('原位接管输入在写入前发生变化')
        self._transaction_changed = True
        nodes = [_name(cmds, uuid) for uuid in plan.deletion_uuids]
        cmds.delete(sorted(nodes, key=lambda item: item.count('|'), reverse=True))
        if set(_namespace_nodes(cmds, plan.source_namespace)) != set(plan.retained_uuids):
            raise RuntimeError('旧 Rig 清理后仍存在未归属节点')
        cmds.namespace(moveNamespace=[':' + plan.target_namespace,
                                      ':' + plan.source_namespace])
        if _namespace_nodes(cmds, plan.target_namespace):
            raise RuntimeError('目标 Rig 命名空间未清空')
        cmds.namespace(removeNamespace=':' + plan.target_namespace)
        promoted = MayaBodyBuildHost(namespace=plan.source_namespace)
        registration = promoted.read_character_registration()
        if registration != plan.target_registration:
            raise RuntimeError('原位接管后的登记与目标角色不一致')
        expected = CharacterIdentity(plan.source_namespace)
        for asset in plan.assets:
            if (self.capture_skin_handoff_boundary(asset.skin_name, asset.mesh_path)
                    != asset.boundary):
                raise RuntimeError('原位接管改变原网格或变形历史 UUID：'
                                   + asset.mesh_path)
            state = self.capture_all_skin_weights(asset.skin_name, asset.mesh_path)
            if (state.vertex_count != asset.state.vertex_count
                    or any(not expected.owns(p) for p in state.influence_paths)):
                raise RuntimeError('接管后原 Skin 未跟随目标骨架：'
                                   + asset.skin_name)
        if set(_namespace_nodes(cmds, plan.source_namespace)) != set(
                (*plan.retained_uuids, *plan.target_uuids)):
            raise RuntimeError('接管后的角色节点归属与预检不一致')
        return registration
