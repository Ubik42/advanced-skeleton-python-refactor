"""Native Fit duplicate names retain associated DrivingSystems."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.source_fit_unique_names import (
    legacy_driving_curve_name, source_fit_driving_copy, source_fit_unique_order,
)


class MayaSourceFitUniqueNamesMixin:
    def _source_fit_driving_curves(self, container):
        return tuple(self._cmds.listConnections(container, source=True,
                                               destination=False, type='animCurve') or ())

    def _source_fit_upgrade_driving_names(self, container):
        c = self._cmds
        for curve in self._source_fit_driving_curves(container):
            target = legacy_driving_curve_name(curve)
            if target is None:
                continue
            self._transaction_changed = True
            # Native rename resolves a collision itself. Its returned name
            # is subsequently read through the Fit connections, not guessed.
            c.rename(curve, target)

    def _source_fit_copy_driving_systems(self, container, old, new, suffix):
        c = self._cmds
        for curve in self._source_fit_driving_curves(container):
            if old.rsplit(':', 1)[-1] not in curve.rsplit(':', 1)[-1]:
                continue
            sources = tuple(c.listConnections(curve, source=True,
                                              destination=False, plugs=True) or ())
            if not sources:
                raise FitSkeletonValidationError('重名 Fit DrivingSystem 缺少输入：'+curve)
            recipe = source_fit_driving_copy(curve, old, new, suffix, sources[0])
            if c.objExists(recipe.target):
                raise FitSkeletonValidationError('重名 Fit DrivingSystem 目标名已存在：'+recipe.target)
            connections = tuple(c.listConnections(curve, source=True,
                    destination=False, plugs=True, connections=True) or ())
            if not connections or '.' not in connections[0]:
                raise FitSkeletonValidationError('重名 Fit DrivingSystem 缺少接收属性：'+curve)
            receiver_attribute = connections[0].split('.', 1)[1]
            self._transaction_changed = True
            duplicated = tuple(c.duplicate(curve, name=recipe.target) or ())
            if len(duplicated) != 1:
                raise RuntimeError('重名 Fit DrivingSystem 复制失败：'+curve)
            target = duplicated[0]
            if target.rsplit('|', 1)[-1].rsplit(':', 1)[-1] != recipe.target.rsplit(':', 1)[-1]:
                raise RuntimeError('重名 Fit DrivingSystem 复制名称发生变化：'+recipe.target)
            if not c.attributeQuery(recipe.attribute, node=container, exists=True):
                c.addAttr(container, longName=recipe.attribute, attributeType='bool',
                          defaultValue=True, keyable=False, multi=True)
            index = c.getAttr(container+'.'+recipe.attribute, size=True)
            c.connectAttr(container+'.'+recipe.attribute+'['+str(index)+']',
                          target+'.'+receiver_attribute)
            c.select(target, curve, replace=True)

    def normalize_fit_joint_names(self, container_name):
        """asUniqueNameAll, including SDK compatibility and hand ordering."""
        self._require_transaction()
        container = self._resolve_transform(container_name, FitSkeletonValidationError)
        c = self._cmds
        self._source_fit_upgrade_driving_names(container)
        joints = tuple(c.listRelatives(container, allDescendents=True,
                                       type='joint', fullPath=True) or ())
        duplicated_hand = any('IndexFinger' in joint.rsplit('|', 1)[-1]
                             and len(c.ls(joint.rsplit('|', 1)[-1], long=True) or ()) > 1
                             for joint in joints)
        ordered = source_fit_unique_order(joints, duplicated_index_finger=duplicated_hand)
        # The native hand reordering can put a parent before its children.
        # UUIDs keep those pending identities valid when a parent is renamed.
        identities = tuple(self._fit_node_uuid(joint) for joint in ordered)
        for identity in identities:
            joint = self._fit_node_from_uuid(identity)
            short = joint.rsplit('|', 1)[-1]
            matches = tuple(c.ls(short, long=True) or ())
            if len(matches) <= 1:
                continue
            for suffix in range(1, 99):
                candidate = short+str(suffix)
                if c.objExists(candidate):
                    continue
                self._transaction_changed = True
                # asUniqueName renames the first ls match, rather than the
                # particular ambiguous item from the descendant array.
                renamed = c.rename(matches[0], candidate)
                resolved = tuple(c.ls(renamed, long=True, type='joint') or ())
                if len(resolved) != 1 or resolved[0].rsplit('|', 1)[-1] != candidate:
                    raise RuntimeError('Fit 重名关节重命名后路径不唯一：'+short)
                self._source_fit_copy_driving_systems(container, short, candidate, suffix)
                break
            else:
                raise FitSkeletonValidationError('Fit 重名关节没有可用的数字后缀：'+short)
