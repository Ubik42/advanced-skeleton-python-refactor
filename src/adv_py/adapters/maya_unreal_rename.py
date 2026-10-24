"""Maya port of ADV's reversible Unreal rename/export hierarchy."""
from __future__ import annotations

from adv_py.core.unreal_rename import UnrealRenamePlan, unknown_unreal_name
from .maya_custom_controller import MayaCustomControllerHost
from .maya_original_control_identity import source_main


class MayaUnrealRenameHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    @staticmethod
    def _leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _export_joints(self) -> list[str]:
        c = self._cmds
        address = self._node("root")
        if not c.objExists(address):
            return []
        root = self._unique("root", "joint")
        return c.listRelatives(root, allDescendents=True,
                               type="joint", fullPath=True) or []

    def capture_joint_names(self) -> tuple[str, ...]:
        c = self._cmds
        deformation = self._unique("DeformationSystem", "transform")
        descendants = c.listRelatives(deformation, allDescendents=True,
                                      type="joint", fullPath=True) or []
        return tuple(self._leaf(node) for node in descendants)

    def capture_spine_names(self) -> tuple[str, ...]:
        c = self._cmds
        current = self._unique("Chest_M", "joint")
        root = self._unique("Root_M", "joint")
        result = []
        while current != root:
            result.append(self._leaf(current))
            current = (c.listRelatives(current, parent=True,
                                       fullPath=True) or [None])[0]
            if current is None:
                raise ValueError("Chest_M 不在 Root_M 的脊柱链下")
        result.reverse()
        return tuple(result)

    def preflight_rename(self, plan: UnrealRenamePlan) -> None:
        c = self._cmds
        self._unique("Group", "transform")
        deformation = self._unique("DeformationSystem", "transform")
        self._unique(source_main(self), "transform")
        self._unique("MainSystem", "transform")
        self._unique("RootSystem", "transform")
        self._unique("ConstraintSystem", "transform")
        self._unique("MainScaleMultiplyDivide", "multiplyDivide")
        self._unique("ControlSet", "objectSet")
        if c.objExists("|root"):
            raise ValueError("场景已有 root 关节，无法重命名为 Unreal")
        if c.objExists(self._node("FitSkeleton")):
            fit = self._node("FitSkeleton")
            if c.attributeQuery("useOffsetParentMatrix", node=fit,
                                exists=True) and c.getAttr(
                                    fit + ".useOffsetParentMatrix"):
                raise ValueError("原版不支持对 OPM 角色执行 Unreal 重命名")
        geometry = self._unique("Geometry", "transform")
        group = self._unique("Group", "transform")
        if (c.listRelatives(geometry, parent=True,
                            fullPath=True) or [None])[0] != group:
            raise ValueError("Geometry 不在 Group 直属层级")
        for target in ('pelvis', 'thigh_r', 'calf_r', 'foot_r', 'ball_r',
                       'clavicle_r', 'upperarm_r', 'lowerarm_r', 'hand_r', 'neck_01', 'head'):
            if c.objExists(self._node(target)):
                raise ValueError("Unreal 目标名称已占用：" + target)
        if not c.objExists(self._node("buildPose")):
            raise ValueError("缺少 buildPose，无法登记 Unreal Root Motion 控制")
        if c.objExists('root'):
            self._unique('root', 'joint')
        if not c.listRelatives(deformation, children=True, type="joint"):
            raise ValueError("DeformationSystem 下没有 Body 关节")

    def preflight_restore(self) -> None:
        c = self._cmds
        if not self.is_renamed():
            raise ValueError("场景没有本工具重命名的 Unreal 骨架")
        self._unique("DeformationSystem", "transform")
        self._unique("Group", "transform")
        if not c.objExists("|Geometry"):
            raise ValueError("根级 Geometry 不存在，无法恢复 ADV 层级")
        for joint in self._export_joints():
            if c.attributeQuery("asParent", node=joint, exists=True):
                parent = c.getAttr(joint + ".asParent")
                if not c.objExists(parent):
                    raise ValueError("原始关节父级缺失：" + parent)

    def begin_unreal_rename(self) -> None:
        self._require_transaction()
        from .maya_game_registration import source_registration
        before = source_registration(self)
        if before is not None:
            before = self.read_character_registration()

    def create_export_root(self) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        created = not c.objExists('root')
        if created:
            from adv_py.core.body_game_root_motion import plan_game_root_motion
            option = c.createNode('transform', name='asCreateGameEngineRootMotionOptions')
            c.addAttr(option, longName='useOldRootName', attributeType='bool', defaultValue=True, keyable=True)
            plan = plan_game_root_motion(self.capture_game_root_motion_creation_input(), create=True)
            self.preflight_game_root_motion(plan)
            self.apply_game_root_motion(plan)
            c.setAttr('root.jointOrientX', -90)
            c.setAttr('root_parentConstraint1.target[0].targetOffsetRotateX', -90)
            c.addAttr('root', longName='noRootMotionJointBeforeRename',
                      attributeType='bool', defaultValue=True)
        # Preserve a closed checkpoint before the source enters its export
        # naming state. Native DG connections continue to follow the same
        # Maya objects; original rig editing resumes after source Restore.
        from .maya_game_registration import source_registration
        staged = source_registration(self)
        if staged is not None:
            from adv_py.core.character_registry import REGISTRY_NAME, canonical, encode_registration
            from .maya_driving_registration import _write_string
            plug = REGISTRY_NAME + '.advPySourceUnrealRename'
            if c.objExists(plug):
                raise ValueError('Unreal 重命名交接记录已经存在')
            c.addAttr(REGISTRY_NAME, longName='advPySourceUnrealRename', dataType='string')
            _write_string(c, plug, canonical(dict(version=1,
                staged=encode_registration(staged), created_root=created)))
        root = self._unique('root', 'joint')
        c.parent(root, world=True, absolute=True)
        c.connectAttr('MainScaleMultiplyDivide.output', 'root.scale')

    def rename_joints(self, plan: UnrealRenamePlan) -> None:
        self._require_transaction()
        c = self._cmds
        mapping = dict(plan.names)
        for source in (*plan.spine, *plan.known_names):
            if c.objExists(source):
                self._rename_native_joint(source, mapping[source])
        # Native reads the actual descendants after both known-name passes.
        # Other DeformationSystem branches are not this suffix pass's scope.
        for old in self._export_joints():
            source = self._leaf(old)
            target = unknown_unreal_name(source)
            if target is not None:
                self._rename_native_joint(source, target)

    def _rename_native_joint(self, source, target):
        c = self._cmds
        joint = self._unique(source, "joint")
        if not c.attributeQuery("asName", node=joint, exists=True):
            c.addAttr(joint, longName="asName", dataType="string")
        c.setAttr(joint + ".asName", source, type="string")
        c.rename(joint, self._node(target))

    def _remember_parent(self, joint: str, parent: str,
                         *, reconnect_source: str | None = None) -> None:
        c = self._cmds
        if not c.attributeQuery("asParent", node=joint, exists=True):
            c.addAttr(joint, longName="asParent", dataType="string")
        c.setAttr(joint + ".asParent", parent, type="string")
        if reconnect_source:
            if not c.attributeQuery("asParentRestoreCmd", node=joint,
                                    exists=True):
                c.addAttr(joint, longName="asParentRestoreCmd",
                          dataType="string")
            c.setAttr(joint + ".asParentRestoreCmd",
                      "reconnect:" + reconnect_source,
                      type="string")

    def flatten_twist_hierarchy(self, plan: UnrealRenamePlan) -> None:
        self._require_transaction()
        c = self._cmds
        for family in plan.twist_families:
            for side in ("r", "l"):
                indices = [index for index in range(1, 10) if c.objExists(
                    self._node(f"{family}_twist_{index:02d}_{side}"))]
                if not indices:
                    continue
                first = (plan.right_knee_parts if family == 'calf' else
                         plan.right_elbow_parts if family == 'lowerarm' else 1)
                first_name = f"{family}_twist_{first:02d}_{side}"
                above = None
                for index in indices:
                    name = f"{family}_twist_{index:02d}_{side}"
                    if not c.objExists(self._node(name)):
                        continue
                    joint = self._unique(name, "joint")
                    parent = (c.listRelatives(joint, parent=True,
                                              fullPath=True) or [None])[0]
                    if not parent:
                        continue
                    if family in ('thigh', 'upperarm') and index == 1:
                        above = parent
                    # Preserve MEL precedence: calf on every iteration;
                    # lowerarm only on i==1, both using the right-side count.
                    if family == 'calf' or (family == 'lowerarm' and index == 1):
                        above = (c.listRelatives(self._unique(first_name, 'joint'),
                                                parent=True, fullPath=True) or [None])[0]
                    if above is None:
                        raise ValueError('原版 Unreal Twist 缺少首个 Part 的父级：' + name)
                    if index != first:
                        c.getAttr(joint + '.matrix')
                        self._remember_parent(joint, self._leaf(parent))
                        c.parent(joint, above, absolute=True)
                        joint = self._unique(name, 'joint')
                        source = (c.listConnections(joint + '.translate', source=True,
                            destination=False, plugs=True) or [None])[0]
                        if source is None:
                            raise ValueError('原版 Unreal Twist 平移补偿缺少输入：' + name)
                        scaled = c.createNode('multiplyDivide', name=name + '_TempMPD')
                        c.connectAttr(source, scaled + '.input1')
                        c.setAttr(scaled + '.input2', 2, 2, 2, type='float3')
                        c.connectAttr(scaled + '.output', joint + '.translate', force=True)
                        plug = joint + '.asParentRestoreCmd'
                        if not c.objExists(plug):
                            c.addAttr(joint, longName='asParentRestoreCmd', dataType='string')
                        c.setAttr(plug, 'delete ' + name + '_TempMPD;connectAttr ' + source
                            + ' ' + name + '.t;', type='string')
                        getattr(c, 'raw', c).dgdirty(allPlugs=True)
                    child = (c.listRelatives(self._node(name), children=True,
                                             type="joint", fullPath=True) or [None])[0]
                    if child and "_twist_" not in self._leaf(child) and above:
                        self._remember_parent(child, name)
                        c.parent(child, above, absolute=True)

    def unparent_export_geometry(self) -> None:
        self._require_transaction()
        c = self._cmds
        c.parent(self._unique("Geometry", "transform"), world=True,
                 absolute=True)
        c.select("|root", "|Geometry", replace=True)

    def restore_twist_hierarchy(self) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        deformation = self._unique('DeformationSystem', 'transform')
        root = self._unique('root', 'joint')
        c.parent(root, deformation, absolute=True)
        # Source removes only a root that Rename itself created, before the
        # Part parent and name loops. A user's prior Root Motion survives.
        if c.objExists('root.noRootMotionJointBeforeRename'):
            self._delete_rename_root()
        from .maya_original_control_orient import _uuid, _by_uuid
        identities = tuple(_uuid(c, path) for path in c.listRelatives(deformation,
            allDescendents=True, type='joint', fullPath=True) or [])
        for identity in identities:
            joint = _by_uuid(self, identity)
            if not c.objExists(joint + '.asParent'):
                continue
            if c.objExists(joint + '.asParentRestoreCmd'):
                instruction = c.getAttr(joint + '.asParentRestoreCmd')
                self._restore_parent_driver(joint, instruction)
                getattr(c, 'raw', c).dgdirty(allPlugs=True)
            c.parent(joint, self._unique(c.getAttr(joint + '.asParent'), 'joint'), absolute=True)

    def _restore_parent_driver(self, joint, instruction):
        import re
        c = self._cmds
        if instruction.startswith('reconnect:'):
            # Already-written Python scenes remain readable.
            source = instruction[len('reconnect:'):]
            temporary = self._leaf(joint) + '_TempMPD'
            target = joint + '.translate'
        else:
            match = re.fullmatch(r'delete ([^;\s]+);connectAttr ([^;\s]+) ([^;\s]+);', instruction)
            if match is None:
                raise ValueError('原版 Unreal 父级恢复命令格式无效')
            temporary, source, target = match.groups()
            if (self._leaf(temporary) != self._leaf(joint) + '_TempMPD'
                    or self._leaf(target.split('.', 1)[0]) != self._leaf(joint)
                    or target.split('.', 1)[-1] not in ('t', 'translate')):
                raise ValueError('Unreal 父级恢复命令改变了目标对象')
        if c.objExists(temporary):
            c.delete(temporary)
        c.connectAttr(source, target)

    def _delete_rename_root(self):
        c = self._cmds
        # asDeleteGameEngineRootMotion itself chooses modern first, then root.
        name = 'RootMotion_M' if c.objExists('RootMotion_M') else 'root'
        root = self._unique(name, 'joint')
        deformation = self._unique('DeformationSystem', 'transform')
        children = c.listRelatives(root, children=True, type='joint', fullPath=True) or []
        if children:
            c.parent(children, deformation, absolute=True)
        self._rename_removed_ids = set()
        offset = 'FKOffset' + name
        controls = ((c.listRelatives(offset, allDescendents=True, fullPath=True) or [])
            + (c.ls(offset, long=True) or [])) if c.objExists(offset) else []
        for node in (root, *controls):
            self._rename_removed_ids.update(c.ls(node, uuid=True) or [])
        c.delete(root)
        for target in ('root_parentConstraint1', 'RootMotion_parentConstraint1', offset):
            if c.objExists(target):
                c.delete(target)
        # Range and the buildPose's literal TRS command deliberately remain.
        pose = 'buildPose.advPyPoseData'
        if c.objExists(pose):
            import json
            rows = json.loads(c.getAttr(pose))
            c.setAttr(pose, json.dumps([row for row in rows
                if self._leaf(row[0]) not in ('FK' + name, 'FKExtra' + name)], separators=(',', ':')), type='string')

    def restore_joint_names(self) -> None:
        self._require_transaction()
        c = self._cmds
        deformation = self._unique("DeformationSystem", "transform")
        paths = c.listRelatives(deformation, allDescendents=True,
                                type="joint", fullPath=True) or []
        for path in paths:
            name = path.rsplit("|", 1)[-1]
            joint = self._unique(name, "joint")
            if not c.attributeQuery("asName", node=joint, exists=True):
                continue
            original = c.getAttr(joint + ".asName")
            c.rename(joint, self._node(original))

    def restore_export_root(self) -> None:
        # Native Restore handles this before its parent/name passes above.
        self._require_transaction()

    def finish_unreal_restore(self) -> None:
        self._require_transaction()
        c = self._cmds
        from adv_py.core.character_registry import REGISTRY_NAME, safe_json, exact, decode_registration
        plug = REGISTRY_NAME + '.advPySourceUnrealRename'
        if not c.objExists(plug):
            return
        if not c.getAttr(plug, lock=True):
            raise ValueError('Unreal 重命名交接记录已解锁')
        record = exact(safe_json(c.getAttr(plug)), ('version', 'staged', 'created_root'))
        if type(record['version']) is not int or record['version'] != 1 or type(record['created_root']) is not bool:
            raise ValueError('Unreal 重命名交接记录无效')
        staged = decode_registration(record['staged'])
        from .maya_original_control_orient import _by_uuid
        from .maya_source_body_matrix import rebase_fk_records
        root = next(node for node in staged.nodes if node.path == staged.body_root)
        current_root = _by_uuid(self, root.uuid)
        rebase_fk_records(self, staged, ((staged.body_root, current_root),),
            root_parent_inverse=(self._unique('DeformationSystem', 'transform') + '.worldInverseMatrix[0]'
                if record['created_root'] else None))
        from .maya_game_registration import refresh_hierarchy
        refresh_hierarchy(self, staged, removed_ids=frozenset(getattr(self, '_rename_removed_ids', ())))
        c.setAttr(plug, lock=False)
        c.deleteAttr(REGISTRY_NAME, attribute='advPySourceUnrealRename')
        self.read_character_registration()

    def reparent_export_geometry(self) -> None:
        self._require_transaction()
        c = self._cmds
        c.parent("|Geometry", self._unique("Group", "transform"),
                 absolute=True)
        c.select(clear=True)

    def is_renamed(self) -> bool:
        c = self._cmds
        return bool(c.objExists("|root"))
