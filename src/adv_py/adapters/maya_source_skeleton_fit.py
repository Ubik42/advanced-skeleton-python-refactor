"""Read a selected Maya joint hierarchy without changing the source rig."""
from __future__ import annotations

from adv_py.application.source_skeleton_fit import SourceSkeletonJoint
from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_metadata import FitJointField, FitJointFieldEdit

from .maya_face import MayaFaceHost


class MayaSourceSkeletonFitHost(MayaFaceHost):
    def capture_source_skeleton(self, root: str) -> tuple[SourceSkeletonJoint, ...]:
        from maya import cmds

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
            metadata = self.read_fit_joint_metadata(path)
            joints.append(SourceSkeletonJoint(path,
                path.rsplit("|", 1)[-1], parent, position,
                optional_int(path, "twistJoints"),
                optional_int(path, "inbetweenJoints"),
                optional_bool(path, "unTwister"),
                optional_profile(path),
                int(cmds.getAttr(path + ".rotateOrder")),
                additional_fit_edits(metadata),
                metadata.no_flip,
                self.read_fit_skin_enabled(path)))
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

    def write_fit_deform_profile(self, joint: str,
                                 profile: FitDeformProfile) -> None:
        self._require_transaction()
        if not isinstance(profile, FitDeformProfile):
            raise ValueError("Fit 体积参数无效")
        fat_node = joint.rsplit("|", 1)[-1] + "Fat"
        if self._cmds.objExists(fat_node):
            raise ValueError("Fit 派生体积节点名称已占用：" + fat_node)
        for attribute in ("fatFrontAbs", "fatWidthAbs"):
            if self._cmds.attributeQuery(attribute, node=joint, exists=True):
                raise ValueError("Fit 派生体积属性已存在：" + joint)
        self._transaction_changed = True
        for name, value in (("fat", profile.fat),
                            ("fatFront", profile.fat_front),
                            ("fatWidth", profile.fat_width)):
            if not self._cmds.attributeQuery(name, node=joint, exists=True):
                self._cmds.addAttr(joint, longName=name,
                                   attributeType="double", minValue=0,
                                   defaultValue=value, keyable=True)
            self._cmds.setAttr(joint + "." + name, value)
        for attribute in ("fatFrontAbs", "fatWidthAbs"):
            self._cmds.addAttr(joint, longName=attribute,
                               attributeType="double", keyable=False)
        self._cmds.createNode("multiplyDivide", name=fat_node)
        connections = (
            (joint + ".fat", fat_node + ".input1Y"),
            (joint + ".fat", fat_node + ".input1Z"),
            (joint + ".fatFront", fat_node + ".input2Y"),
            (joint + ".fatWidth", fat_node + ".input2Z"),
            (fat_node + ".outputY", joint + ".fatFrontAbs"),
            (fat_node + ".outputZ", joint + ".fatWidthAbs"),
        )
        for source, target in connections:
            self._cmds.connectAttr(source, target)
        if (int(self._cmds.getAttr(fat_node + ".operation")) != 1
                or any(abs(float(self._cmds.attributeQuery(
                    name, node=joint, listDefault=True)[0]) - value) > 1e-6
                    for name, value in (("fat", profile.fat),
                                        ("fatFront", profile.fat_front),
                                        ("fatWidth", profile.fat_width)))
                or any(self._cmds.connectionInfo(target,
                sourceFromDestination=True) != source
                for source, target in connections)
                or abs(float(self._cmds.getAttr(joint + ".fatFrontAbs"))
                       - profile.fat * profile.fat_front) > 1e-6
                or abs(float(self._cmds.getAttr(joint + ".fatWidthAbs"))
                       - profile.fat * profile.fat_width) > 1e-6):
            raise RuntimeError("Fit 派生体积节点写后回读不一致：" + joint)

    def write_missing_fit_deform_profiles(
        self, container: str, joints: tuple[str, ...],
    ) -> None:
        """Initialize every generated Fit joint using asEnsureFitJointAttrs defaults."""
        self._require_transaction()
        c = self._cmds
        joint_set = set(joints)
        if len(joint_set) != len(joints) or any(
            (c.ls(joint, long=True, type="joint") or []) != [joint]
            for joint in joints
        ):
            raise ValueError("Fit 默认体积需要唯一且已创建的关节路径")
        fit = c.ls(container, long=True, type="transform") or []
        if len(fit) != 1:
            raise ValueError("Fit 默认体积需要唯一的 Fit 容器")
        axis = "X"
        if c.attributeQuery("primaryAxis", node=fit[0], exists=True):
            axis = c.getAttr(fit[0] + ".primaryAxis", asString=True).upper()
        if axis not in ("X", "Y", "Z"):
            raise ValueError("Fit 主轴无效")
        positions = {joint: tuple(float(value) for value in c.xform(
            joint, query=True, worldSpace=True, translation=True))
            for joint in joints}
        maximum_y = max((position[1] for position in positions.values()),
                        default=0.0)
        scale = max(0.01, maximum_y / 17.176163) if maximum_y > 0 else 1.0
        child_tolerance = 0.01 * float(c.getAttr(fit[0] + ".scaleX"))
        center_tolerance = 0.01 * scale

        def matching_child(joint: str) -> str | None:
            children = [child for child in (c.listRelatives(
                joint, children=True, type="joint", fullPath=True) or [])
                if child in joint_set]
            center = abs(positions[joint][0]) < child_tolerance
            selected = next((child for child in children
                             if (abs(positions[child][0]) < child_tolerance)
                             == center), None)
            name = joint.rsplit("|", 1)[-1]
            preferred = (("Head", "Head"), ("Ankle", "Toes"),
                         ("Toes", "Toes"), ("Root", "Spine"))
            for marker, child_marker in preferred:
                if marker in name:
                    selected = next((child for child in reversed(children)
                                     if child_marker in child.rsplit("|", 1)[-1]),
                                    selected)
            return selected

        for joint in sorted(joints, key=lambda path: path.count("|")):
            if c.attributeQuery("fat", node=joint, exists=True):
                # Explicit source values were written first. Their derivation
                # graph is already checked by write_fit_deform_profile.
                continue
            child = matching_child(joint)
            if child:
                length = abs(float(c.getAttr(child + ".translate" + axis)))
                fat = length / 4.0
                if abs(positions[joint][0]) < center_tolerance:
                    fat *= 2.0
                if fat < 0.0001:
                    fat = scale
            else:
                parent = (c.listRelatives(joint, parent=True, type="joint",
                                          fullPath=True) or [None])[0]
                fat = (float(c.getAttr(parent + ".fat"))
                       if parent in joint_set
                       and c.attributeQuery("fat", node=parent, exists=True)
                       else 1.0)
            self.write_fit_deform_profile(
                joint, FitDeformProfile(fat, 1.0, 1.0))
