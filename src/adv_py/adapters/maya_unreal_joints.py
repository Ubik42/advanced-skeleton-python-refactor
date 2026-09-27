"""Maya host for ADV's generic UnrealRoot and IK marker hierarchy."""
from __future__ import annotations

from adv_py.core.unreal_joints import UnrealJointPlan, UnrealJointSpec
from .maya_custom_controller import MayaCustomControllerHost


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
            parent = (c.listRelatives(root, parent=True,
                                      fullPath=True) or [None])[0]
            unreal = self._node("UnrealRoot")
            if c.objExists(unreal):
                unreal = self._unique(unreal, "joint")
                if parent != unreal:
                    raise ValueError("UnrealRoot 已存在但不拥有 Root_M")
            elif parent != deformation:
                raise ValueError("Root_M 不在 DeformationSystem 直属层级")
            if not plan.opm:
                self._unique("Main", "transform")
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
        unreal = c.createNode("joint", name=self._node("UnrealRoot"),
                              parent=deformation, skipSelect=True)
        c.parent(root, unreal)
        if not opm:
            constraint = c.parentConstraint(
                self._unique("Main", "transform"), unreal,
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
        marker = c.createNode("joint", name=self._node(spec.name),
                              parent=parent, skipSelect=True)
        if spec.align_to:
            landmark = self._unique(spec.align_to, "joint")
            position = c.xform(landmark, query=True, worldSpace=True,
                               translation=True)
            c.xform(marker, worldSpace=True, translation=position)

    def delete_unreal_joints(self) -> None:
        self._require_transaction()
        c = self._cmds
        for name in ("ik_foot_root", "ik_hand_root"):
            address = self._node(name)
            if c.objExists(address):
                marker = self._unique(address, "joint")
                parent = (c.listRelatives(marker, parent=True,
                                          fullPath=True) or [None])[0]
                if parent is None or self._leaf(parent) not in ("root", "UnrealRoot"):
                    raise ValueError("Unreal 标记关节不属于当前角色：" + name)
                self._transaction_changed = True
                c.delete(marker)
        unreal = self._node("UnrealRoot")
        if c.objExists(unreal):
            joint = self._unique(unreal, "joint")
            if (c.listRelatives(self._unique("Root_M", "joint"),
                                parent=True, fullPath=True) or [None])[0] != joint:
                raise ValueError("UnrealRoot 不拥有 Root_M，拒绝删除")
            deformation = self._unique("DeformationSystem", "transform")
            for child in c.listRelatives(joint, children=True,
                                         fullPath=True) or []:
                c.parent(child, deformation)
            self._transaction_changed = True
            c.delete(joint)
        constraint = self._node("UnrealRoot_parentConstraint1")
        if c.objExists(constraint):
            self._transaction_changed = True
            c.delete(constraint)

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
