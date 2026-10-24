"""Maya host for ADV's generic UnrealRoot and IK marker hierarchy."""
from __future__ import annotations

from adv_py.core.unreal_joints import UnrealJointPlan, UnrealJointSpec
from .maya_custom_controller import MayaCustomControllerHost
from .maya_original_control_identity import source_main, leaf
from .maya_original_control_orient import _by_uuid
from .maya_original_transform_channels import align_original_transform
from .maya_game_registration import (
    source_registration, refresh_hierarchy, scene_ids, remember_generated_nodes,
)

NAMES = ('UnrealRoot', 'ik_foot_root', 'ik_foot_l', 'ik_foot_r',
         'ik_hand_root', 'ik_hand_gun', 'ik_hand_l', 'ik_hand_r')


class MayaUnrealJointsHost(MayaCustomControllerHost):
    def __init__(self, *, namespace: str | None = None) -> None:
        super().__init__(namespace=namespace, face=False)

    def _node(self, name: str) -> str:
        return self.scene_address(name)

    @staticmethod
    def _leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def capture_unreal_inputs(self) -> tuple[bool, bool, dict[str, bool]]:
        c = self._cmds
        fit = self._node("FitSkeleton")
        opm = bool(c.objExists(fit) and c.attributeQuery(
            "useOffsetParentMatrix", node=fit, exists=True)
            and c.getAttr(fit + ".useOffsetParentMatrix"))
        landmarks = {name: bool(c.objExists(self._node(name)))
                     for name in ("Wrist_R", "Wrist_L", "Ankle_R", "Ankle_L")}
        return bool(c.objExists(self._node("root"))), opm, landmarks

    def preflight_unreal_joints(self, plan: UnrealJointPlan) -> None:
        c = self._cmds
        deformation = self._unique("DeformationSystem", "transform")
        root = self._unique("Root_M", "joint")
        if plan.create_root:
            unreal = self._node("UnrealRoot")
            if c.objExists(unreal):
                self._unique(unreal, "joint")
            if not plan.opm:
                self._unique(source_main(self), "transform")
                self._unique("ConstraintSystem", "transform")
                self._unique("MainScaleMultiplyDivide", "multiplyDivide")
        else:
            self._unique("root", "joint")
        for spec in plan.joints:
            address = self._node(spec.name)
            if not c.objExists(address):
                continue
            marker = self._unique(address, "joint")
            parent = (c.listRelatives(marker, parent=True,
                                      fullPath=True) or [None])[0]
            if parent is None or self._leaf(parent) != spec.parent:
                raise ValueError("同名 Unreal 节点不属于原版层级：" + spec.name)

    def create_unreal_root(self, *, opm: bool) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        deformation = self._unique("DeformationSystem", "transform")
        root = self._unique("Root_M", "joint")
        c.select(deformation, replace=True)
        unreal = c.joint(name='UnrealRoot')
        c.parent(root, unreal)
        if not opm:
            constraint = c.parentConstraint(
                self._unique(source_main(self), "transform"), unreal,
                maintainOffset=False,
                name=self._node("UnrealRoot_parentConstraint1"))[0]
            c.parent(constraint, self._unique("ConstraintSystem", "transform"))
            c.connectAttr(self._node("MainScaleMultiplyDivide") + ".output",
                          unreal + ".scale")

    def create_unreal_marker(self, spec: UnrealJointSpec) -> None:
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        parent = self._unique(spec.parent, "joint")
        c.select(parent, replace=True)
        c.joint(name=spec.name)

    def begin_unreal_joints(self):
        self._require_transaction()
        self._unreal_registration_before = source_registration(self)
        self._unreal_scene_before = scene_ids(self)
        before = self._unreal_registration_before
        self._unreal_removable_ids = frozenset(node.uuid for node in before.nodes
            if leaf(node.path) in NAMES) if before else frozenset()

    def finish_unreal_joints(self, plan):
        self._require_transaction()
        c = self._cmds
        if plan is not None:
            # Source creates the complete native hierarchy first, then aligns
            # gun, left hand, right foot and left foot in that exact order.
            by_name = {row.name: row for row in plan.joints}
            for name in ('ik_hand_gun', 'ik_hand_l', 'ik_foot_r', 'ik_foot_l'):
                spec = by_name[name]
                if spec.align_to:
                    align_original_transform(c, self._unique(name, 'joint'),
                        self._unique(spec.align_to, 'joint'), True, False, False, False)
        before = self._unreal_registration_before
        removed = set()
        if before is not None:
            for identity in self._unreal_removable_ids:
                try:
                    _by_uuid(self, identity)
                except ValueError:
                    removed.add(identity)
        added = tuple(self._unique(name, 'joint') for name in NAMES if c.objExists(name))
        refresh_hierarchy(self, before, removed_ids=frozenset(removed), added_paths=added)
        remember_generated_nodes(self, self._unreal_scene_before)
        c.select(clear=True)

    def delete_unreal_joints(self) -> None:
        self._require_transaction()
        c = self._cmds
        # Source moves all direct children out before deleting UnrealRoot,
        # including the marker branches and any native additional children.
        if c.objExists('UnrealRoot'):
            joint = self._unique('UnrealRoot', 'joint')
            children = c.listRelatives(joint, children=True, fullPath=True) or []
            if children:
                self._transaction_changed = True
                c.parent(children, self._unique('DeformationSystem', 'transform'))
        for name in ('UnrealRoot', 'UnrealRoot_parentConstraint1',
                     'ik_foot_root', 'ik_hand_root'):
            if c.objExists(name):
                self._transaction_changed = True
                c.delete(name)
        c.select(clear=True)

    def capture_unreal_hierarchy(self) -> dict[str, str]:
        c = self._cmds
        result = {}
        for name in ("UnrealRoot", "ik_foot_root", "ik_foot_l", "ik_foot_r",
                     "ik_hand_root", "ik_hand_gun", "ik_hand_l", "ik_hand_r"):
            node = self._node(name)
            if not c.objExists(node):
                continue
            unique = self._unique(node, "joint")
            parent = (c.listRelatives(unique, parent=True,
                                      fullPath=True) or [None])[0]
            result[name] = self._leaf(parent) if parent else ""
        return result
