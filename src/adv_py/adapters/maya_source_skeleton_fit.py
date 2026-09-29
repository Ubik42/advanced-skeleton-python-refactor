"""Read a selected Maya joint hierarchy without changing the source rig."""
from __future__ import annotations

from adv_py.application.source_skeleton_fit import SourceSkeletonJoint
from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_metadata import FitJointField, FitJointFieldEdit

from .maya_face import MayaFaceHost


class MayaSourceSkeletonFitHost(MayaFaceHost):
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
            parent = (cmds.listRelatives(path, parent=True,
                                        fullPath=True) or [None])[0]
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
                source_reader.read_joint_label(path)))
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
