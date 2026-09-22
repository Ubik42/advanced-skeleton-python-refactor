"""Conservative namespace takeover after original Skin influence handoff."""
from dataclasses import dataclass
import re

from adv_py.core.character_identity import CharacterIdentity, SHARED_NODES
from adv_py.core.character_registry import CharacterRegistryError

from .maya_body import MayaBodyBuildHost
from .maya_spine_skin_handoff import MayaSpineSkinHandoffHost


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
class OriginalSpinePromotionPlan:
    source_namespace: str
    target_namespace: str
    source_registration: object
    target_registration: object
    assets: tuple[OriginalSpineRetainedSkin, ...]
    deletion_uuids: tuple[str, ...]
    retained_uuids: tuple[str, ...]
    target_uuids: tuple[str, ...]

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

    def plan_original_spine_promotion(self, source_namespace, target_namespace,
                                       skin_name, mesh_path):
        return self.plan_original_spine_promotion_many(source_namespace,
            target_namespace, ((skin_name, mesh_path),))

    def plan_original_spine_promotion_many(self, source_namespace,
                                            target_namespace, skins):
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
            tuple(sorted(target_nodes)))

    def apply_original_spine_promotion(self, plan):
        from maya import cmds
        self._require_transaction()
        current = self.plan_original_spine_promotion_many(
            plan.source_namespace, plan.target_namespace,
            ((asset.skin_name, asset.mesh_path) for asset in plan.assets))
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
