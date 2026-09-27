"""Maya port of ADV's reversible Unreal rename/export hierarchy."""
from __future__ import annotations

from adv_py.core.unreal_rename import UnrealRenamePlan
from .maya_custom_controller import MayaCustomControllerHost


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
        self._unique("Main", "transform")
        self._unique("MainSystem", "transform")
        self._unique("RootSystem", "transform")
        self._unique("ConstraintSystem", "transform")
        self._unique("MainScaleMultiplyDivide", "multiplyDivide")
        self._unique("ControlSet", "objectSet")
        if c.objExists("|root") or c.objExists(self._node("root")):
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
        for source, target in plan.names:
            self._unique(source, "joint")
            if c.objExists(self._node(target)):
                raise ValueError("Unreal 目标名称已占用：" + target)
        for name in ("root", "FKOffsetroot_M", "FKFollowroot_M",
                     "FKExtraroot_M", "FKroot_M", "rootRange"):
            if c.objExists(self._node(name)):
                raise ValueError("Root Motion 名称已占用：" + name)
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

    def create_export_root(self) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        deformation = self._unique("DeformationSystem", "transform")
        original_children = c.listRelatives(deformation, children=True,
                                             type="joint", fullPath=True) or []
        root = c.createNode("joint", name=self._node("root"),
                            parent=deformation, skipSelect=True)
        for joint in original_children:
            c.parent(joint, root, absolute=True)
        control_parent = c.createNode("transform",
            name=self._node("FKOffsetroot_M"),
            parent=self._unique("RootSystem", "transform"))
        follow = c.createNode("transform", name=self._node("FKFollowroot_M"),
                              parent=control_parent)
        extra = c.createNode("transform", name=self._node("FKExtraroot_M"),
                             parent=follow)
        head = self._node("HeadEnd_M") if c.objExists(
            self._node("HeadEnd_M")) else self._node("Head_M")
        radius = max(abs(c.xform(head, query=True, worldSpace=True,
                                  translation=True)[1]) / 20.0, 0.01)
        control = c.circle(name=self._node("FKroot_M"), normal=(0, 1, 0),
                           radius=radius, degree=3, sections=8,
                           constructionHistory=False)[0]
        c.parent(control, extra, absolute=True)
        for shape in c.listRelatives(control, shapes=True, fullPath=True) or []:
            c.setAttr(shape + ".overrideEnabled", 1)
            c.setAttr(shape + ".overrideColor", 17)
        c.sets(control, extra, add=self._node("ControlSet"))
        constraint = c.parentConstraint(
            control, root, maintainOffset=False,
            name=self._node("root_parentConstraint1"))[0]
        c.parent(constraint, self._unique("ConstraintSystem", "transform"))
        follow_constraint = c.parentConstraint(
            self._node("Main"), self._node("MainSystem"), follow,
            maintainOffset=False)[0]
        c.addAttr(control, longName="followMain", attributeType="double",
                  minValue=0, maxValue=10, defaultValue=0, keyable=True)
        curve = c.createNode("setRange", name=self._node("rootRange"))
        for attr, value in (("maxX", 1), ("minY", 1),
                            ("oldMaxX", 10), ("oldMaxY", 10)):
            c.setAttr(curve + "." + attr, value)
        for axis in ("X", "Y"):
            c.connectAttr(control + ".followMain", curve + ".value" + axis)
        aliases = c.parentConstraint(follow_constraint, query=True,
                                     weightAliasList=True) or []
        if len(aliases) != 2:
            raise RuntimeError("Root Motion 跟随约束目标数量异常")
        c.connectAttr(curve + ".outValueX",
                      follow_constraint + "." + aliases[0], force=True)
        c.connectAttr(curve + ".outValueY",
                      follow_constraint + "." + aliases[1], force=True)
        c.setAttr(root + ".jointOrientX", -90)
        c.addAttr(root, longName="noRootMotionJointBeforeRename",
                  attributeType="bool", defaultValue=True)
        c.addAttr(root, longName="advPyUnrealRenamed", attributeType="bool",
                  defaultValue=True)
        c.parent(root, world=True, absolute=True)
        c.connectAttr(self._node("MainScaleMultiplyDivide") + ".output",
                      root + ".scale", force=True)

    def rename_joints(self, plan: UnrealRenamePlan) -> None:
        self._require_transaction()
        c = self._cmds
        mapping = dict(plan.names)
        descendants = self._export_joints()
        for old in descendants:
            source = self._leaf(old)
            target = mapping.get(source)
            if target is None:
                continue
            joint = self._unique(source, "joint")
            if not c.attributeQuery("asName", node=joint, exists=True):
                c.addAttr(joint, longName="asName", dataType="string")
            c.setAttr(joint + ".asName", source, type="string")
            c.rename(joint, self._node(target))

    def _remember_parent(self, joint: str, parent: str,
                         *, reset_opm: bool = False) -> None:
        c = self._cmds
        if not c.attributeQuery("asParent", node=joint, exists=True):
            c.addAttr(joint, longName="asParent", dataType="string")
        c.setAttr(joint + ".asParent", parent, type="string")
        if reset_opm:
            if not c.attributeQuery("asParentRestoreCmd", node=joint,
                                    exists=True):
                c.addAttr(joint, longName="asParentRestoreCmd",
                          dataType="string")
            c.setAttr(joint + ".asParentRestoreCmd", "resetOffsetParentMatrix",
                      type="string")

    def flatten_twist_hierarchy(self, plan: UnrealRenamePlan) -> None:
        self._require_transaction()
        c = self._cmds
        for family in plan.twist_families:
            for side in ("r", "l"):
                above = None
                for index in range(1, 10):
                    name = f"{family}_twist_{index:02d}_{side}"
                    if not c.objExists(self._node(name)):
                        continue
                    joint = self._unique(name, "joint")
                    parent = (c.listRelatives(joint, parent=True,
                                              fullPath=True) or [None])[0]
                    if not parent:
                        continue
                    if index == 1:
                        above = parent
                    elif above:
                        local_matrix = c.getAttr(joint + ".matrix")
                        self._remember_parent(joint, self._leaf(parent),
                                              reset_opm=True)
                        c.parent(joint, above, absolute=True)
                        c.setAttr(self._node(name) + ".offsetParentMatrix",
                                  *local_matrix, type="matrix")
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
        deformation = self._unique("DeformationSystem", "transform")
        root = self._unique("root", "joint")
        c.parent(root, deformation, absolute=True)
        for path in self._export_joints():
            name = path.rsplit("|", 1)[-1]
            joint = self._unique(name, "joint")
            if not c.attributeQuery("asParent", node=joint, exists=True):
                continue
            parent = c.getAttr(joint + ".asParent")
            if c.attributeQuery("asParentRestoreCmd", node=joint,
                                exists=True):
                c.setAttr(joint + ".offsetParentMatrix",
                          1, 0, 0, 0, 0, 1, 0, 0,
                          0, 0, 1, 0, 0, 0, 0, 1, type="matrix")
                c.deleteAttr(joint, attribute="asParentRestoreCmd")
            moved = c.parent(joint, self._unique(parent, "joint"),
                             absolute=True)[0]
            c.deleteAttr(moved, attribute="asParent")

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
            restored = c.rename(joint, self._node(original))
            c.deleteAttr(restored, attribute="asName")

    def restore_export_root(self) -> None:
        self._require_transaction()
        c = self._cmds
        root = self._unique("root", "joint")
        deformation = self._unique("DeformationSystem", "transform")
        for child in c.listRelatives(root, children=True, type="joint",
                                     fullPath=True) or []:
            c.parent(child, deformation, absolute=True)
        c.delete(root)
        constraint = self._node("root_parentConstraint1")
        if c.objExists(constraint):
            c.delete(constraint)
        control = self._node("FKOffsetroot_M")
        if c.objExists(control):
            c.delete(control)
        curve = self._node("rootRange")
        if c.objExists(curve):
            c.delete(curve)

    def reparent_export_geometry(self) -> None:
        self._require_transaction()
        c = self._cmds
        c.parent("|Geometry", self._unique("Group", "transform"),
                 absolute=True)
        c.select(clear=True)

    def is_renamed(self) -> bool:
        c = self._cmds
        return bool(c.objExists("|root") and
                    c.attributeQuery("advPyUnrealRenamed", node="|root",
                                     exists=True) and
                    c.objExists("|root|pelvis"))
