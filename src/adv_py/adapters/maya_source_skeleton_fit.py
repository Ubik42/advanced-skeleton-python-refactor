"""Read a selected Maya joint hierarchy without changing the source rig."""
from __future__ import annotations

from adv_py.application.source_skeleton_fit import SourceSkeletonJoint
from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_metadata import FitJointField, FitJointFieldEdit

from .maya_face import MayaFaceHost


class MayaSourceSkeletonFitHost(MayaFaceHost):
    def capture_name_matcher_skin_boundary(self, root: str) -> tuple:
        """Track source skins by UUID so DAG renames cannot disguise a break."""
        c=getattr(self._cmds,'raw',self._cmds)
        paths = c.ls(root, long=True) or []
        if len(paths) != 1 or c.nodeType(paths[0]) not in ('joint','transform'):
            raise ValueError('NameMatcher 来源骨架不唯一')
        joints = [*(c.listRelatives(paths[0],
            allDescendents=True, fullPath=True, type='joint') or ())]
        if c.nodeType(paths[0])=='joint':joints.insert(0,paths[0])
        ids = {item for joint in joints
            for item in (c.ls(joint, uuid=True) or ())}
        rows = []
        for skin in c.ls(type='skinCluster') or ():
            influences = c.skinCluster(skin, query=True,
                                       influence=True) or ()
            influence_ids = tuple(sorted(item for joint in influences
                for item in (c.ls(joint, uuid=True) or ())))
            if not ids.intersection(influence_ids):
                continue
            shapes = c.skinCluster(skin, query=True, geometry=True) or ()
            shape_ids = tuple(sorted(item for shape in shapes
                for item in (c.ls(shape, uuid=True) or ())))
            rows.append(((c.ls(skin, uuid=True) or [None])[0],
                         influence_ids, shape_ids))
        return tuple(sorted(rows))

    def namespace_name_matcher_source(self, root: str) -> str:
        """Move a clashing imported hierarchy into MEL's NameMatcher namespace."""
        from maya import cmds as c

        self._require_transaction()
        matches = c.ls(root, long=True, type='joint') or []
        if len(matches) != 1:
            raise ValueError('NameMatcher 来源根关节不存在或名称不唯一')
        root = matches[0]
        if c.namespace(exists=':NameMatcher'):
            raise ValueError('NameMatcher 命名空间已存在，拒绝覆盖来源骨架')
        nodes = c.listRelatives(root, allDescendents=True,
            fullPath=True) or []
        nodes = [path for path in nodes
                 if c.nodeType(path) in ('transform', 'joint')]
        nodes.append(root)
        if any(c.referenceQuery(path, isNodeReferenced=True)
                or any(c.lockNode(path, query=True, lock=True) or ())
                for path in nodes):
            raise ValueError('NameMatcher 来源层级被引用或锁定，不能改名')
        root_id = (c.ls(root, uuid=True) or [None])[0]
        self._transaction_changed = True
        c.namespace(addNamespace=':NameMatcher')
        for path in sorted(nodes, key=lambda item: item.count('|'),
                           reverse=True):
            leaf = path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            c.rename(path, ':NameMatcher:' + leaf)
        resolved = c.ls(root_id, long=True) or []
        if len(resolved) != 1 or c.nodeType(resolved[0]) != 'joint':
            raise RuntimeError('NameMatcher 来源骨架改名后身份丢失')
        return resolved[0]

    def set_name_matcher_fit_world_position(self, joint: str,
            position: tuple[float, float, float]) -> None:
        self._require_transaction()
        if (self._cmds.ls(joint, long=True, type='joint') or []) != [joint]:
            raise ValueError('NameMatcher Fit 关节不存在或名称不唯一：' + joint)
        self._transaction_changed = True
        self._cmds.xform(joint, worldSpace=True, translation=position)

    def capture_name_matcher_fit_world_position(self, joint: str
            ) -> tuple[float, float, float]:
        if (self._cmds.ls(joint, long=True, type='joint') or []) != [joint]:
            raise ValueError('NameMatcher Fit 关节不存在或名称不唯一：' + joint)
        return tuple(float(value) for value in self._cmds.xform(
            joint, query=True, worldSpace=True, translation=True))

    def capture_source_skeleton(self, root: str) -> tuple[SourceSkeletonJoint, ...]:
        from maya import cmds

        # A selected source can live outside the target character namespace.
        # Read its physical DAG paths with an unscoped adapter; the receiving
        # host remains scoped for all Fit/Body writes.
        source_reader = (self if self.namespace is None else
                         MayaSourceSkeletonFitHost(namespace=None))
        matches = cmds.ls(root, long=True, type="joint") or []
        if len(matches) != 1:
            raise ValueError("请选择唯一的来源根关节")
        root_path = matches[0]
        paths = [root_path] + (cmds.listRelatives(root_path,
            allDescendents=True, type="joint", fullPath=True) or [])
        paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        path_set = set(paths)
        joints = []
        def optional_int(path: str, attribute: str) -> int | None:
            return (int(cmds.getAttr(path + "." + attribute))
                    if cmds.attributeQuery(attribute, node=path, exists=True)
                    else None)

        def optional_bool(path: str, attribute: str) -> bool | None:
            return (bool(cmds.getAttr(path + "." + attribute))
                    if cmds.attributeQuery(attribute, node=path, exists=True)
                    else None)

        def optional_profile(path: str) -> FitDeformProfile | None:
            def read(*names: str) -> float:
                for name in names:
                    if cmds.attributeQuery(name, node=path, exists=True):
                        return float(cmds.getAttr(path + "." + name))
                return 1.0
            if not any(cmds.attributeQuery(name, node=path, exists=True)
                       for name in ("fat", "fatFront", "fatY",
                                    "fatWidth", "fatZ")):
                return None
            return FitDeformProfile(read("fat"), read("fatFront", "fatY"),
                                    read("fatWidth", "fatZ"))

        primary_fields = frozenset((
            FitJointField.TWIST_JOINTS,
            FitJointField.INBETWEEN_JOINTS,
            FitJointField.UNTWISTER,
        ))

        def additional_fit_edits(metadata) -> tuple[FitJointFieldEdit, ...]:
            return tuple(FitJointFieldEdit(
                field,
                metadata.local_no_flip if field is FitJointField.NO_FLIP
                else getattr(metadata, field.value))
                for field in FitJointField
                if field in metadata.present_fields and field not in primary_fields)

        for path in paths:
            immediate_parent = (cmds.listRelatives(
                path, parent=True, fullPath=True) or [None])[0]
            siblings = (cmds.listRelatives(
                immediate_parent, children=True, type="joint",
                fullPath=True) or [] if immediate_parent else [path])
            sibling_index = siblings.index(path) if path in siblings else 0
            parent = immediate_parent
            while parent and parent not in path_set:
                parent = (cmds.listRelatives(parent, parent=True,
                                            fullPath=True) or [None])[0]
            position = tuple(float(value) for value in cmds.xform(
                path, query=True, worldSpace=True, translation=True))
            metadata = source_reader.read_fit_joint_metadata(path)
            joints.append(SourceSkeletonJoint(path,
                path.rsplit("|", 1)[-1], parent, position,
                optional_int(path, "twistJoints"),
                optional_int(path, "inbetweenJoints"),
                optional_bool(path, "unTwister"),
                optional_profile(path),
                int(cmds.getAttr(path + ".rotateOrder")),
                additional_fit_edits(metadata),
                metadata.no_flip,
                source_reader.read_fit_skin_enabled(path),
                source_reader.read_joint_label(path),
                sibling_index))
        return tuple(joints)

    def write_fit_no_skin(self, joint: str) -> None:
        self._require_transaction()
        if not self._cmds.attributeQuery("noSkin", node=joint, exists=True):
            self._transaction_changed = True
            self._cmds.addAttr(joint, longName="noSkin",
                               attributeType="bool", keyable=True)
        self._transaction_changed = True
        self._cmds.setAttr(joint + ".noSkin", True)

    def write_fit_rotation_order(self, joint: str, order: int) -> None:
        self._require_transaction()
        if type(order) is not int or not 0 <= order <= 5:
            raise ValueError("Fit 旋转顺序无效")
        orders = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
        self._transaction_changed = True
        self._cmds.xform(joint, preserve=True, rotateOrder=orders[order])
        if int(self._cmds.getAttr(joint + ".rotateOrder")) != order:
            raise RuntimeError("Fit 旋转顺序写入失败：" + joint)
