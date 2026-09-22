"""Maya operations for retaining one skinCluster while changing spine influences."""
from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistryError

from .maya_body import MayaBodyBuildHost
from .maya_face import MayaFaceHost


class MayaSpineSkinHandoffHost(MayaFaceHost):
    def read_registration_in_namespace(self, namespace):
        return MayaBodyBuildHost(namespace=namespace).read_character_registration()

    def capture_registered_body_matrices(self, registration, namespace):
        from maya import cmds
        identity = CharacterIdentity(namespace)
        return tuple(tuple(float(value) for value in cmds.xform(
            identity.to_scene(joint.path), query=True, worldSpace=True,
            matrix=True)) for joint in registration.body)

    def capture_skin_handoff_boundary(self, skin_name, mesh_path):
        from maya import cmds
        skin = cmds.ls(skin_name, type='skinCluster') or []
        mesh = cmds.ls(mesh_path, long=True, type='transform') or []
        if len(skin) != 1 or len(mesh) != 1:
            raise CharacterRegistryError('原位 Skin 交接需要唯一 skinCluster 和网格')
        if (cmds.referenceQuery(skin[0], isNodeReferenced=True)
                or cmds.referenceQuery(mesh[0], isNodeReferenced=True)
                or any(cmds.lockNode(skin[0], query=True, lock=True) or [])
                or any(cmds.lockNode(mesh[0], query=True, lock=True) or [])):
            raise CharacterRegistryError('原位 Skin 交接要求未引用且未锁定的网格和 skinCluster')
        history = cmds.listHistory(mesh[0], pruneDagObjects=True) or []
        return (cmds.ls(skin[0], uuid=True)[0],
                cmds.ls(mesh[0], uuid=True)[0],
                tuple(cmds.ls(node, uuid=True)[0] for node in history))

    def add_skin_handoff_influences(self, skin_name, influences):
        from maya import cmds
        self._require_transaction()
        self._transaction_changed = True
        for joint in influences:
            cmds.skinCluster(skin_name, edit=True, addInfluence=joint, weight=0.)

    def verify_skin_handoff_bind_matrices(self, skin_name, registration,
                                          namespace, influences):
        from maya import cmds
        from maya.api.OpenMaya import MMatrix
        identity = CharacterIdentity(namespace)
        expected = {identity.to_scene(row.path): tuple(MMatrix(row.matrix).inverse())
                    for row in registration.body}
        observed = {}
        for index in cmds.getAttr(skin_name + '.matrix', multiIndices=True) or []:
            plug = cmds.connectionInfo(skin_name + f'.matrix[{index}]',
                                       sourceFromDestination=True)
            path = (cmds.ls(plug.rsplit('.', 1)[0], long=True) or [None])[0]
            if path in influences:
                observed[path] = tuple(cmds.getAttr(
                    skin_name + f'.bindPreMatrix[{index}]'))
        if set(observed) != set(influences):
            raise RuntimeError('目标 Skin 影响关节绑定矩阵来源不完整')
        for path, matrix in observed.items():
            if max(abs(a-b) for a, b in zip(matrix, expected[path])) > 1e-4:
                raise RuntimeError('目标 Skin 影响关节绑定逆矩阵与角色登记不一致：'
                                   + path)

    def remove_skin_handoff_influences(self, skin_name, influences):
        from maya import cmds
        self._require_transaction()
        self._transaction_changed = True
        for joint in influences:
            cmds.skinCluster(skin_name, edit=True, removeInfluence=joint)

    def release_old_bind_pose_members(self, skin_name, source_namespace,
                                      allowed_skins=None):
        from maya import cmds
        self._require_transaction()
        poses = cmds.listConnections(skin_name + '.bindPose', source=True,
                                     destination=False, type='dagPose') or []
        if len(poses) > 1:
            raise CharacterRegistryError('原 Skin 连接多个 bindPose，不能自动清理旧骨架')
        if not poses:
            return
        pose = poses[0]
        consumers = cmds.listConnections(pose + '.message', source=False,
                                         destination=True, type='skinCluster') or []
        allowed = {skin_name} if allowed_skins is None else set(allowed_skins)
        if not consumers or not set(consumers) <= allowed:
            raise CharacterRegistryError('bindPose 被其他 Skin 共享，不能清理旧骨架')
        outputs = cmds.listConnections(pose + '.message', source=False,
                                       destination=True, plugs=True) or []
        if set(outputs) != {name + '.bindPose' for name in consumers}:
            raise CharacterRegistryError('bindPose 还连接其他对象，不能清理旧骨架')
        identity = CharacterIdentity(source_namespace)
        pairs = cmds.listConnections(pose, source=True, destination=False,
                                     plugs=True, connections=True) or []
        members = []
        for destination, source in zip(pairs[::2], pairs[1::2]):
            if '.members[' not in destination or not source.endswith('.message'):
                continue
            paths = cmds.ls(source.rsplit('.', 1)[0], long=True) or []
            if len(paths) == 1 and identity.owns(paths[0]):
                members.append(paths[0])
        if members:
            self._transaction_changed = True
            for joint in sorted(members, key=lambda path: path.count('|'),
                                reverse=True):
                cmds.dagPose(joint, remove=True, name=pose)
        pairs = cmds.listConnections(pose, source=True, destination=False,
                                     plugs=True, connections=True) or []
        if any(identity.owns(source.rsplit('.', 1)[0])
               for source in pairs[1::2] if ':' in source):
            raise RuntimeError('旧骨架仍连接原 Skin 的 bindPose')
