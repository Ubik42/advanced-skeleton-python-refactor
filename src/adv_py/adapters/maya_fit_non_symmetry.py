"""Maya implementation of asCreateNonSymmetryJoints for authored Fit trees."""
from __future__ import annotations

from adv_py.core.fit_non_symmetry import plan_fit_non_symmetry
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFitNonSymmetryMixin:
    @property
    def _non_symmetry_cmds(self):
        return getattr(self._cmds, "raw", self._cmds)

    @staticmethod
    def _non_symmetry_leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _non_symmetry_joint_tree(self, root: str) -> tuple[str, ...]:
        c = self._non_symmetry_cmds
        descendants = c.listRelatives(root, allDescendents=True,
                                      type="joint", fullPath=True) or ()
        return (root, *sorted(descendants,
                              key=lambda path: (path.count("|"), path)))

    def _non_symmetry_pairs(self, source: str, mirrored: str
                            ) -> tuple[tuple[str, str], ...]:
        """Pair mirrored joints by branch structure, not Maya's short names."""
        c = self._non_symmetry_cmds
        pairs = []
        pending = [(source, mirrored)]
        while pending:
            right, left = pending.pop(0)
            pairs.append((right, left))
            right_children = tuple(c.listRelatives(
                right, children=True, type="joint", fullPath=True) or ())
            left_children = tuple(c.listRelatives(
                left, children=True, type="joint", fullPath=True) or ())
            if len(right_children) != len(left_children):
                raise RuntimeError(
                    "非对称镜像分支拓扑与原 Fit 关节不一致：" + source)
            pending.extend(zip(right_children, left_children))
        return tuple(pairs)

    def _non_symmetry_write_root_attributes(self, joint: str) -> None:
        c = self._non_symmetry_cmds
        if not c.attributeQuery("noMirror", node=joint, exists=True):
            c.addAttr(joint, longName="noMirror", attributeType="bool",
                      defaultValue=True, keyable=True)
        else:
            if not c.getAttr(joint + ".noMirror", settable=True):
                raise FitSkeletonValidationError(
                    "非对称根关节 noMirror 属性不可写：" + joint)
            c.setAttr(joint + ".noMirror", True)
        if not c.attributeQuery("noMirrorLeft", node=joint, exists=True):
            c.addAttr(joint, longName="noMirrorLeft", attributeType="bool",
                      defaultValue=False, keyable=True)
        else:
            if not c.getAttr(joint + ".noMirrorLeft", settable=True):
                raise FitSkeletonValidationError(
                    "非对称根关节 noMirrorLeft 属性不可写：" + joint)
            c.setAttr(joint + ".noMirrorLeft", False)

    def toggle_fit_non_symmetry_joints(self) -> tuple[str, ...]:
        """Create mirrored independent branches, or remove them on next use."""
        c = self._non_symmetry_cmds
        fit = self._resolve_transform(
            "FitSkeleton", FitSkeletonValidationError)
        selection = tuple(c.ls(selection=True, long=True) or ())
        result = []
        with self.transaction("切换 Fit 非对称关节"):
            try:
                # asFitModeManualUpdate flattens generated transforms before
                # mirrorJoint reads the authored joint positions.
                self.collapse_fit_generated_transforms("FitSkeleton")
                hierarchy = self.capture_fit_hierarchy("FitSkeleton")
                max_y = max((joint.world_position[1]
                             for joint in hierarchy.joints), default=0.0)
                scale = max(max_y / 17.176163, .01) if max_y > 0 else 1.0
                plan = plan_fit_non_symmetry(hierarchy, scale=scale)
                if plan.remove_existing:
                    generated = set(plan.generated_joints)
                    roots = tuple(path for path in generated if not any(
                        path.startswith(parent + "|")
                        for parent in generated if parent != path))
                    if any(c.referenceQuery(path, isNodeReferenced=True)
                           for path in roots):
                        raise FitSkeletonValidationError(
                            "引用中的非对称 Fit 关节不能删除")
                    self._transaction_changed = True
                    c.delete(*roots)
                    for joint in hierarchy.joints:
                        if joint.path in generated or not c.objExists(
                                joint.path):
                            continue
                        for attribute in ("noMirror", "noMirrorLeft"):
                            if c.attributeQuery(attribute, node=joint.path,
                                                exists=True):
                                c.deleteAttr(joint.path + "." + attribute)
                    result.extend(roots)
                else:
                    reserved = set()
                    for branch in plan.branch_roots:
                        for joint in self._non_symmetry_joint_tree(branch):
                            target = (self._non_symmetry_leaf(joint)
                                      + "_NonSymmetry")
                            if (target in reserved
                                    or c.objExists(self.scene_address(target))):
                                raise FitSkeletonValidationError(
                                    "非对称 Fit 目标关节名已存在：" + target)
                            reserved.add(target)
                            if c.referenceQuery(joint,
                                                isNodeReferenced=True):
                                raise FitSkeletonValidationError(
                                    "引用中的 Fit 分支不能镜像：" + joint)
                    for branch in plan.branch_roots:
                        created = c.mirrorJoint(branch, mirrorYZ=True,
                                                mirrorBehavior=True) or ()
                        if not created:
                            raise RuntimeError("Fit 分支镜像失败：" + branch)
                        mirror_roots = c.ls(created[0], long=True,
                                            type="joint") or ()
                        if len(mirror_roots) != 1:
                            raise RuntimeError("Fit 镜像根关节不唯一：" + branch)
                        mirror_root = mirror_roots[0]
                        pairs = self._non_symmetry_pairs(branch, mirror_root)
                        self._transaction_changed = True
                        renamed_root = None
                        for right, left in sorted(
                                pairs, key=lambda pair: pair[1].count("|"),
                                reverse=True):
                            target = (self._non_symmetry_leaf(right)
                                      + "_NonSymmetry")
                            renamed = c.rename(left,
                                               self.scene_address(target))
                            if self._non_symmetry_leaf(renamed) != target:
                                raise RuntimeError(
                                    "Fit 非对称关节改名失败：" + target)
                            if right == branch:
                                renamed_root = renamed
                        if renamed_root is None:
                            raise RuntimeError("Fit 非对称根关节映射丢失")
                        self._non_symmetry_write_root_attributes(branch)
                        self._non_symmetry_write_root_attributes(
                            renamed_root)
                        result.append(renamed_root)
            finally:
                remaining = tuple(item for item in selection if
                                  c.objExists(item))
                c.select(remaining, replace=True) if remaining else c.select(
                    clear=True)
        return tuple(result)
