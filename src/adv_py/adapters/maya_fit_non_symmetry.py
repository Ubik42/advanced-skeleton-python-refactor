"""Maya implementation of asCreateNonSymmetryJoints for authored Fit trees."""
from __future__ import annotations

from adv_py.core.fit_non_symmetry import plan_fit_non_symmetry
from adv_py.core.fit_hierarchy import fit_build_scale
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaFitNonSymmetryMixin:
    @staticmethod
    def _non_symmetry_leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    def _non_symmetry_joint_tree(self, root: str) -> tuple[str, ...]:
        c = self._cmds
        descendants = c.listRelatives(root, allDescendents=True,
                                      type="joint", fullPath=True) or ()
        return (root, *sorted(descendants,
                              key=lambda path: (path.count("|"), path)))

    def _non_symmetry_pairs(self, source: str, mirrored: str
                            ) -> tuple[tuple[str, str], ...]:
        """Pair mirrored joints by branch structure, not Maya's short names."""
        c = self._cmds
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
        by_source = dict(pairs)
        order = tuple(c.listRelatives(source, allDescendents=True,
                                      type="joint", fullPath=True) or ())
        if set(order) != set(by_source) - {source}:
            raise RuntimeError("非对称镜像分支遍历身份不一致：" + source)
        return tuple((node, by_source[node]) for node in (*order, source))

    def _non_symmetry_write_root_attributes(self, joint: str) -> None:
        c = self._cmds
        # asAddFitJointAttribute skips the complete joint when noMirror is
        # already present. Authored False/Left values are not new defaults.
        if c.attributeQuery("noMirror", node=joint, exists=True):
            return
        c.addAttr(joint, longName="noMirror", attributeType="bool",
                  defaultValue=True, keyable=True)
        c.addAttr(joint, longName="noMirrorLeft", attributeType="bool",
                  defaultValue=False, keyable=True)

    def _non_symmetry_manual_update(self):
        """The shared Fit update, without the Body builder's extra root gate."""
        self.manual_update_fit('FitSkeleton')

    def _remove_non_symmetry_joints(self, generated):
        """Native early-return branch also covers detached legacy joints."""
        c = self._cmds
        if any(c.referenceQuery(node, isNodeReferenced=True) for node in generated):
            raise FitSkeletonValidationError('引用中的非对称 Fit 关节不能删除')
        descendants = tuple(self._cmds.listRelatives('Root', allDescendents=True,
                                                     type='joint', fullPath=True) or ())
        retained = tuple(node for node in descendants if node not in generated
                         and not any(node.startswith(root+'|') for root in generated))
        if any(c.referenceQuery(node, isNodeReferenced=True) and any(
                c.attributeQuery(attr, node=node, exists=True) for attr in ('noMirror', 'noMirrorLeft'))
                for node in retained):
            raise FitSkeletonValidationError('引用中的 Fit 关节不能删除非对称属性')
        self._transaction_changed = True
        c.delete(generated)
        for joint in self._cmds.listRelatives('Root', allDescendents=True,
                                             type='joint', fullPath=True) or ():
            for attribute in ('noMirror', 'noMirrorLeft'):
                if c.attributeQuery(attribute, node=joint, exists=True):
                    c.deleteAttr(joint+'.'+attribute)
        return tuple(generated)

    def toggle_fit_non_symmetry_joints(self) -> tuple[str, ...]:
        """Create mirrored independent branches, or remove them on next use."""
        c = self._cmds
        self._resolve_transform("FitSkeleton", FitSkeletonValidationError)
        roots = self._cmds.ls('Root', long=True, type='joint') or []
        if len(roots) != 1:
            raise FitSkeletonValidationError('Root joint not found')
        result = []
        with self.transaction("切换 Fit 非对称关节"):
            # Use the character command boundary for the source wildcard.
            # This sees legacy detached joints without deleting another rig.
            generated = tuple(self._cmds.ls('*_NonSymmetry', long=True, type='joint') or ())
            if generated:
                return self._remove_non_symmetry_joints(generated)
            hierarchy = self.capture_fit_hierarchy("FitSkeleton")
            scale = fit_build_scale(hierarchy)
            # asFitModeManualUpdate runs before mirrorJoint only on
            # the creation path; its delete path returns immediately.
            self._non_symmetry_manual_update()
            hierarchy = self.capture_fit_hierarchy("FitSkeleton")
            # Maya's allDescendents order is part of the native loop.
            ordered = tuple(self._cmds.listRelatives('Root', allDescendents=True,
                                                     type='joint', fullPath=True) or ())
            plan = plan_fit_non_symmetry(hierarchy, scale=scale, ordered_paths=ordered)
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
                self._transaction_changed = True
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
                renamed_root = None
                for right, left in pairs:
                    target = (self._non_symmetry_leaf(right)
                              + "_NonSymmetry")
                    renamed = c.rename(left,
                                       self.scene_address(target))
                    if self._non_symmetry_leaf(renamed) != target:
                        raise RuntimeError(
                            "Fit 非对称关节改名失败：" + target)
                    label = self.read_joint_label(right)
                    if label is not None and label.text:
                        c.setAttr(renamed + ".type", 18)
                        c.setAttr(renamed + ".otherType",
                                  label.text + "_NonSymmetry",
                                  type="string")
                    if right == branch:
                        renamed_root = renamed
                if renamed_root is None:
                    raise RuntimeError("Fit 非对称根关节映射丢失")
                self._non_symmetry_write_root_attributes(branch)
                self._non_symmetry_write_root_attributes(
                    renamed_root)
                result.append(renamed_root)
            self._non_symmetry_manual_update()
            c.select(clear=True)
        return tuple(result)
