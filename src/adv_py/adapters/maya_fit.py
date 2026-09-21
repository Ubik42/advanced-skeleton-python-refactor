from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Sequence

from adv_py.core.fit_container import (
    FitContainerDisplayStyle,
    FitContainerShape,
    FitContainerSpec,
    FitContainerState,
    FitUpAxis,
)
from adv_py.core.fit_hierarchy import (
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitHierarchyValidationError,
)
from adv_py.core.fit_metadata import (
    FitJointField,
    FitJointFieldEdit,
    FitJointMetadata,
    FitJointValidationError,
)
from adv_py.core.fit_orientation import (
    FitJointOrientationState,
    FitOrientationAxisConfiguration,
    FitOrientationChange,
    FitOrientationSnapshot,
    FitWorldOrientationChange,
    parse_fit_axis_direction,
)
from adv_py.core.fit_settings import (
    FitSkeletonField,
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    FitSkeletonValue,
)
from adv_py.core.fit_skeleton_io import FitSkeletonSettingChannelState
from adv_py.core.fit_template import FitJointSpec
from adv_py.core.joint_labels import JointLabel


_MAYA_LABEL_NAMES = {
    0: "None",
    1: "Root",
    2: "Hip",
    3: "Knee",
    4: "Foot",
    5: "Toe",
    6: "Spine",
    7: "Neck",
    8: "Head",
    9: "Collar",
    10: "Shoulder",
    11: "Elbow",
    12: "Hand",
    13: "Finger",
    14: "Thumb",
    15: "PropA",
    16: "PropB",
    17: "PropC",
    18: "Other",
}
_MAYA_LABEL_TYPES = {name.casefold(): code for code, name in _MAYA_LABEL_NAMES.items()}


@dataclass(frozen=True, slots=True)
class _MayaFitAttribute:
    name: str
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    enum_names: tuple[str, ...] = ()


_FIT_ATTRIBUTES = {
    FitJointField.TWIST_JOINTS: _MayaFitAttribute("twistJoints", "long", 0),
    FitJointField.BENDY_CONTROLS: _MayaFitAttribute("bendyCtrls", "long", 0),
    FitJointField.INBETWEEN_JOINTS: _MayaFitAttribute("inbetweenJoints", "long", 0),
    FitJointField.UNTWISTER: _MayaFitAttribute("unTwister", "bool"),
    FitJointField.NO_MIRROR: _MayaFitAttribute("noMirror", "bool"),
    FitJointField.NO_MIRROR_LEFT: _MayaFitAttribute("noMirrorLeft", "bool"),
    FitJointField.CHILD_OF_PART: _MayaFitAttribute("childOfPart", "long", 1, 10),
    FitJointField.GLOBAL_WEIGHT: _MayaFitAttribute("global", "double", 0, 10),
    FitJointField.GLOBAL_TRANSLATE: _MayaFitAttribute("globalTranslate", "bool"),
    FitJointField.WORLD_ORIENT_UP: _MayaFitAttribute(
        "worldOrientUp",
        "enum",
        enum_names=("xUp", "yUp", "zUp", "xDown", "yDown", "zDown"),
    ),
    FitJointField.WORLD_ORIENT_FORWARD: _MayaFitAttribute(
        "worldOrientForward",
        "enum",
        enum_names=(
            "xForward",
            "yForward",
            "zForward",
            "xBackward",
            "yBackward",
            "zBackward",
            "free",
        ),
    ),
    FitJointField.IK_LOCAL_MODE: _MayaFitAttribute(
        "ikLocal",
        "enum",
        enum_names=("addCtrl", "nonZero", "localOrient"),
    ),
}

_FIT_SKELETON_ATTRIBUTES = {
    FitSkeletonField.VIS_GEOMETRY: _MayaFitAttribute("visGeo", "bool"),
    FitSkeletonField.VIS_GEOMETRY_TYPE: _MayaFitAttribute(
        "visGeoType",
        "enum",
        enum_names=("cylinders", "boxes", "spheres", "bones"),
    ),
    FitSkeletonField.VIS_CYLINDERS: _MayaFitAttribute("visCylinders", "bool"),
    FitSkeletonField.VIS_BOXES: _MayaFitAttribute("visBoxes", "bool"),
    FitSkeletonField.VIS_SPHERES: _MayaFitAttribute("visSpheres", "bool"),
    FitSkeletonField.VIS_BONES: _MayaFitAttribute("visBones", "bool"),
    FitSkeletonField.LOCK_CENTER_JOINTS: _MayaFitAttribute(
        "lockCenterJoints", "bool"
    ),
    FitSkeletonField.VIS_GAP: _MayaFitAttribute("visGap", "double", 0, 1),
    FitSkeletonField.VIS_POLE_VECTOR: _MayaFitAttribute("visPoleVector", "bool"),
    FitSkeletonField.VIS_JOINT_ORIENT: _MayaFitAttribute("visJointOrient", "bool"),
    FitSkeletonField.VIS_JOINT_AXIS: _MayaFitAttribute("visJointAxis", "bool"),
    FitSkeletonField.OBJECTS_SKIN: _MayaFitAttribute("objectsSkin", "string"),
    FitSkeletonField.OBJECTS_ALL: _MayaFitAttribute("objectsAll", "string"),
    FitSkeletonField.OBJECTS_RIGHT_EYE: _MayaFitAttribute(
        "objectsRightEye", "string"
    ),
    FitSkeletonField.OBJECTS_LEFT_EYE: _MayaFitAttribute(
        "objectsLeftEye", "string"
    ),
    FitSkeletonField.GAME_ENGINE: _MayaFitAttribute("gameEngine", "bool"),
    FitSkeletonField.USE_OFFSET_PARENT_MATRIX: _MayaFitAttribute(
        "useOffsetParentMatrix", "bool"
    ),
    FitSkeletonField.SUB_CONTROLLERS: _MayaFitAttribute("subControllers", "bool"),
    FitSkeletonField.EXTRA_CONTROLLERS: _MayaFitAttribute(
        "extraControllers", "bool"
    ),
    FitSkeletonField.PRE_REBUILD_SCRIPT: _MayaFitAttribute(
        "preRebuildScript", "string"
    ),
    FitSkeletonField.POST_REBUILD_SCRIPT: _MayaFitAttribute(
        "postRebuildScript", "string"
    ),
}

_KEYABLE_FIT_SKELETON_FIELDS = frozenset(
    {
        FitSkeletonField.VIS_GEOMETRY,
        FitSkeletonField.VIS_GEOMETRY_TYPE,
        FitSkeletonField.LOCK_CENTER_JOINTS,
        FitSkeletonField.VIS_GAP,
        FitSkeletonField.VIS_POLE_VECTOR,
        FitSkeletonField.VIS_JOINT_ORIENT,
        FitSkeletonField.VIS_JOINT_AXIS,
    }
)

_FIT_AXIS_ENUM_NAMES = ("X", "Y", "Z", "-X", "-Y", "-Z")
_FIT_AXIS_ENUM_INDEX = {
    "+x": 0,
    "+y": 1,
    "+z": 2,
    "-x": 3,
    "-y": 4,
    "-z": 5,
}


class MayaFitJointHost:
    """Maya adapter for FitSkeleton and explicit Fit joint operations."""

    def __init__(self) -> None:
        from maya import cmds  # type: ignore[import-not-found]

        self._cmds = cmds
        self._transaction_active = False
        self._transaction_changed = False

    def resolve_joints(self, names: Sequence[str]) -> tuple[str, ...]:
        resolved: list[str] = []
        errors: list[str] = []
        for name in names:
            matches = self._cmds.ls(name, long=True) or []
            if not matches:
                errors.append(f"关节不存在：{name}")
                continue
            if len(matches) != 1:
                errors.append(f"关节名称不唯一：{name}")
                continue
            joint = matches[0]
            if self._cmds.nodeType(joint) != "joint":
                errors.append(f"节点不是 joint：{name}")
                continue
            resolved.append(joint)
        if errors:
            raise FitJointValidationError("；".join(errors))
        if len(resolved) != len(set(resolved)):
            raise FitJointValidationError("多个名称解析到了同一个关节")
        return tuple(resolved)

    def scene_up_axis(self) -> FitUpAxis:
        try:
            return FitUpAxis(self._cmds.upAxis(query=True, axis=True))
        except ValueError as error:
            raise FitSkeletonValidationError(
                "当前 Maya Up Axis 不是受支持的 Y 或 Z"
            ) from error

    def find_name_collisions(self, name: str) -> tuple[str, ...]:
        return tuple(sorted(set(self._cmds.ls(name, long=True) or [])))

    def create_fit_container(self, spec: FitContainerSpec) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(
                f"同名节点已存在，拒绝创建或覆盖：{spec.name}"
            )

        selection = self._cmds.ls(selection=True, long=True) or []
        normal = (0.0, 1.0, 0.0)
        if spec.up_axis is FitUpAxis.Z:
            normal = (0.0, 0.0, 1.0)
        try:
            created = self._cmds.circle(
                name=spec.name,
                center=(0.0, 0.0, 0.0),
                normal=normal,
                radius=float(spec.display_radius),
                degree=3,
                sections=8,
                constructionHistory=False,
            )
            self._transaction_changed = True
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

        if not created:
            raise RuntimeError("Maya 未返回新建的 FitSkeleton 容器")
        container = (self._cmds.ls(created[0], long=True) or [created[0]])[0]
        shapes = self._cmds.listRelatives(
            container,
            shapes=True,
            noIntermediate=True,
            fullPath=True,
        ) or []
        if len(shapes) != 1:
            raise RuntimeError("FitSkeleton 圆环没有生成唯一 shape")
        self._cmds.setAttr(f"{shapes[0]}.overrideEnabled", True)
        self._cmds.setAttr(f"{shapes[0]}.overrideColor", 29)
        for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
            self._cmds.setAttr(
                f"{container}.{channel}",
                lock=True,
                keyable=False,
                channelBox=False,
            )
        return container

    def add_fit_orientation_axis_configuration(
        self,
        container: str,
        configuration: FitOrientationAxisConfiguration,
    ) -> None:
        self._require_transaction()
        if not isinstance(configuration, FitOrientationAxisConfiguration):
            raise FitSkeletonValidationError(
                "FitSkeleton 轴配置类型无效"
            )
        container_path = self._resolve_transform(
            container,
            FitSkeletonValidationError,
        )
        attributes = ("primaryAxis", "secondaryAxis", "worldmatch")
        existing = tuple(
            attribute
            for attribute in attributes
            if self._attribute_exists(container_path, attribute)
        )
        if existing:
            raise FitSkeletonValidationError(
                "FitSkeleton 轴配置属性已存在，拒绝覆盖："
                + "、".join(existing)
            )
        self._transaction_changed = True
        enum_names = ":".join(_FIT_AXIS_ENUM_NAMES)
        self._cmds.addAttr(
            container_path,
            longName="primaryAxis",
            attributeType="enum",
            enumName=enum_names,
            defaultValue=_FIT_AXIS_ENUM_INDEX[configuration.primary.value],
            keyable=True,
        )
        self._cmds.addAttr(
            container_path,
            longName="secondaryAxis",
            attributeType="enum",
            enumName=enum_names,
            defaultValue=_FIT_AXIS_ENUM_INDEX[configuration.secondary.value],
            keyable=True,
        )
        self._cmds.addAttr(
            container_path,
            longName="worldmatch",
            attributeType="bool",
            defaultValue=configuration.world_match,
            keyable=True,
        )

    def inspect_fit_container(self, name: str) -> FitContainerState:
        container = self._resolve_transform(name, FitSkeletonValidationError)
        shapes = self._cmds.listRelatives(
            container,
            shapes=True,
            noIntermediate=True,
            fullPath=True,
        ) or []
        shape = None
        display_style = None
        if (
            len(shapes) == 1
            and self._cmds.nodeType(shapes[0]) == "nurbsCurve"
            and int(self._cmds.getAttr(f"{shapes[0]}.form")) in (1, 2)
        ):
            shape = FitContainerShape.RING
        if len(shapes) == 1 and (
            bool(self._cmds.getAttr(f"{shapes[0]}.overrideEnabled"))
            and int(self._cmds.getAttr(f"{shapes[0]}.overrideColor")) == 29
        ):
            display_style = FitContainerDisplayStyle.FIT

        locked = frozenset(
            channel
            for channel in ("tx", "ty", "tz", "rx", "ry", "rz")
            if self._cmds.getAttr(f"{container}.{channel}", lock=True)
        )
        translation = self._cmds.getAttr(f"{container}.translate")[0]
        rotation = self._cmds.getAttr(f"{container}.rotate")[0]
        scale = self._cmds.getAttr(f"{container}.scale")[0]
        bounds = self._cmds.exactWorldBoundingBox(container)
        bounding_size = tuple(
            float(bounds[index + 3] - bounds[index]) for index in range(3)
        )
        leaf = container.rsplit("|", 1)[-1]
        return FitContainerState(
            path=container,
            short_name=leaf.rsplit(":", 1)[-1],
            shape=shape,
            display_style=display_style,
            locked_channels=locked,
            local_translation=tuple(float(value) for value in translation),
            local_rotation=tuple(float(value) for value in rotation),
            bounding_size=bounding_size,
            local_scale=tuple(float(value) for value in scale),
        )

    def create_fit_joint(self, parent: str, spec: FitJointSpec) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(
                f"同名节点已存在，拒绝创建 Fit joint：{spec.name}"
            )
        parent_matches = self._cmds.ls(parent, long=True) or []
        if len(parent_matches) != 1:
            raise FitSkeletonValidationError(f"Fit joint 父级无效：{parent}")
        if self._cmds.nodeType(parent_matches[0]) not in ("transform", "joint"):
            raise FitSkeletonValidationError(f"Fit joint 父级类型无效：{parent}")

        joint = self._cmds.createNode(
            "joint",
            name=spec.name,
            parent=parent_matches[0],
            skipSelect=True,
        )
        self._transaction_changed = True
        path = (self._cmds.ls(joint, long=True) or [joint])[0]
        self._cmds.setAttr(f"{path}.translate", *spec.local_position)
        return path

    def capture_fit_hierarchy(self, container_name: str) -> FitHierarchySnapshot:
        container = self._resolve_transform(
            container_name,
            FitHierarchyValidationError,
        )
        joint_paths = self._cmds.listRelatives(
            container,
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        joint_paths = sorted(set(joint_paths), key=lambda path: (path.count("|"), path))
        nodes: list[FitHierarchyNode] = []
        for path in joint_paths:
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            local = self._cmds.getAttr(f"{path}.translate")[0]
            world = self._cmds.xform(
                path, query=True, worldSpace=True, translation=True
            )
            leaf = path.rsplit("|", 1)[-1]
            locked_axes = frozenset(
                axis
                for axis in ("x", "y", "z")
                if self._cmds.getAttr(f"{path}.t{axis}", lock=True)
            )
            writable_axes = frozenset(
                axis
                for axis in ("x", "y", "z")
                if self._cmds.getAttr(f"{path}.t{axis}", settable=True)
            )
            nodes.append(
                FitHierarchyNode(
                    path=path,
                    short_name=leaf.rsplit(":", 1)[-1],
                    dag_parent=parents[0] if parents else None,
                    local_position=tuple(float(value) for value in local),
                    world_position=tuple(float(value) for value in world),
                    locked_translation_axes=locked_axes,
                    writable_translation_axes=writable_axes,
                )
            )
        return FitHierarchySnapshot(container=container, joints=tuple(nodes))

    def set_fit_joint_local_position(
        self,
        joint: str,
        position: tuple[float, float, float],
        changed_axes: tuple[str, ...],
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(joint, long=True) or []
        if len(matches) != 1 or self._cmds.nodeType(matches[0]) != "joint":
            raise FitSkeletonValidationError(f"Fit joint 无效：{joint}")
        if len(changed_axes) != len(set(changed_axes)) or any(
            axis not in ("x", "y", "z") for axis in changed_axes
        ):
            raise FitSkeletonValidationError("Fit joint 位置轴列表无效")

        values = dict(zip(("x", "y", "z"), position))
        for axis in changed_axes:
            attribute = f"{matches[0]}.t{axis}"
            if not self._cmds.getAttr(attribute, settable=True):
                raise FitSkeletonValidationError(
                    f"Fit joint 位置轴在执行前变为不可写：{attribute}"
                )
        for axis in changed_axes:
            self._transaction_changed = True
            self._cmds.setAttr(f"{matches[0]}.t{axis}", values[axis])

    def capture_fit_orientation(
        self, container_name: str
    ) -> FitOrientationSnapshot:
        hierarchy = self.capture_fit_hierarchy(container_name)
        states: list[FitJointOrientationState] = []
        for node in hierarchy.joints:
            joint_orient = self._cmds.getAttr(f"{node.path}.jointOrient")[0]
            rotation = self._cmds.getAttr(f"{node.path}.rotate")[0]
            matrix = self._cmds.xform(
                node.path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            world_axes = tuple(
                self._normalized_vector(
                    tuple(float(value) for value in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            )
            writable_axes = frozenset(
                axis
                for axis in ("x", "y", "z")
                if self._cmds.getAttr(
                    f"{node.path}.jointOrient{axis.upper()}",
                    settable=True,
                )
            )
            states.append(
                FitJointOrientationState(
                    joint=node.path,
                    joint_orient=tuple(float(value) for value in joint_orient),
                    rotation=tuple(float(value) for value in rotation),
                    world_axes=world_axes,
                    writable_joint_orient_axes=writable_axes,
                )
            )
        return FitOrientationSnapshot(
            hierarchy=hierarchy,
            up_axis=self.scene_up_axis(),
            joints=tuple(states),
            metadata=tuple(
                self.read_fit_joint_metadata(node.path) for node in hierarchy.joints
            ),
            axis_configuration=FitOrientationAxisConfiguration(
                primary=parse_fit_axis_direction(
                    self._optional_enum(hierarchy.container, "primaryAxis") or "X",
                    field="FitSkeleton.primaryAxis",
                ),
                secondary=parse_fit_axis_direction(
                    self._optional_enum(hierarchy.container, "secondaryAxis") or "Y",
                    field="FitSkeleton.secondaryAxis",
                ),
                world_match=self._optional_bool(hierarchy.container, "worldmatch"),
            ),
        )

    def orient_fit_joint(self, change: FitOrientationChange) -> None:
        self._require_transaction()
        joint_matches = self._cmds.ls(change.joint, long=True, type="joint") or []
        child_matches = self._cmds.ls(change.child, long=True, type="joint") or []
        if len(joint_matches) != 1 or len(child_matches) != 1:
            raise FitSkeletonValidationError("朝向目标 joint 在执行前失效")
        joint = joint_matches[0]
        child = child_matches[0]
        if (self._cmds.listRelatives(child, parent=True, fullPath=True) or []) != [
            joint
        ]:
            raise FitSkeletonValidationError("朝向目标的直接父子关系已变化")
        if any(
            not self._cmds.getAttr(
                f"{joint}.jointOrient{axis.upper()}", settable=True
            )
            for axis in ("x", "y", "z")
        ):
            raise FitSkeletonValidationError("jointOrient 在执行前变为不可写")
        if any(
            not self._cmds.getAttr(f"{child}.t{axis}", settable=True)
            for axis in ("x", "y", "z")
        ):
            raise FitSkeletonValidationError("子 joint translate 在执行前变为不可写")
        preserved_children: list[tuple[str, tuple[float, float, float]]] = []
        for child_path, orientation in change.preserved_child_joint_orients:
            matches = self._cmds.ls(child_path, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError("待保护的直接子 joint 在执行前失效")
            if (self._cmds.listRelatives(
                matches[0], parent=True, fullPath=True
            ) or []) != [joint]:
                raise FitSkeletonValidationError("待保护的直接子 joint 父级已变化")
            if any(
                not self._cmds.getAttr(
                    f"{matches[0]}.jointOrient{axis.upper()}", settable=True
                )
                for axis in ("x", "y", "z")
            ):
                raise FitSkeletonValidationError(
                    "直接子 joint jointOrient 在执行前变为不可写"
                )
            preserved_children.append((matches[0], orientation))
        descendant_paths: list[tuple[str, tuple[float, float, float]]] = []
        for descendant, position in change.descendant_world_positions:
            matches = self._cmds.ls(descendant, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError("朝向补偿后代 joint 在执行前失效")
            if any(
                not self._cmds.getAttr(f"{matches[0]}.t{axis}", settable=True)
                for axis in ("x", "y", "z")
            ):
                raise FitSkeletonValidationError(
                    f"朝向补偿后代 translate 在执行前变为不可写：{matches[0]}"
                )
            descendant_paths.append((matches[0], position))

        self._transaction_changed = True
        if len(preserved_children) > 1:
            primary = change.desired_primary_world
            secondary = change.desired_secondary_world
            tertiary = (
                primary[1] * secondary[2] - primary[2] * secondary[1],
                primary[2] * secondary[0] - primary[0] * secondary[2],
                primary[0] * secondary[1] - primary[1] * secondary[0],
            )
            self._set_joint_world_axes(
                joint,
                (primary, secondary, tertiary),
            )
        else:
            self._cmds.joint(
                joint,
                edit=True,
                orientJoint="xyz",
                secondaryAxisOrient=f"{change.secondary_world_axis.value}up",
                children=False,
                zeroScaleOrient=True,
            )
        for child_path, orientation in preserved_children:
            self._cmds.setAttr(f"{child_path}.jointOrient", *orientation)
        for descendant, position in descendant_paths:
            self._cmds.xform(
                descendant,
                worldSpace=True,
                translation=position,
            )

    def orient_world_fit_joint(self, change: FitWorldOrientationChange) -> None:
        self._require_transaction()
        joint_matches = self._cmds.ls(change.joint, long=True, type="joint") or []
        child_matches = self._cmds.ls(change.child, long=True, type="joint") or []
        if len(joint_matches) != 1 or len(child_matches) != 1:
            raise FitSkeletonValidationError("worldOrient 目标 joint 在执行前失效")
        joint = joint_matches[0]
        child = child_matches[0]
        if (self._cmds.listRelatives(child, parent=True, fullPath=True) or []) != [
            joint
        ]:
            raise FitSkeletonValidationError("worldOrient 目标的父子关系已变化")
        if any(
            not self._cmds.getAttr(
                f"{joint}.jointOrient{axis.upper()}", settable=True
            )
            for axis in ("x", "y", "z")
        ):
            raise FitSkeletonValidationError("worldOrient jointOrient 在执行前不可写")
        preserved_children: list[tuple[str, tuple[float, float, float]]] = []
        for child_path, orientation in change.preserved_child_joint_orients:
            matches = self._cmds.ls(child_path, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError("待保护的直接子 joint 在执行前失效")
            if (self._cmds.listRelatives(
                matches[0], parent=True, fullPath=True
            ) or []) != [joint]:
                raise FitSkeletonValidationError("待保护的直接子 joint 父级已变化")
            if any(
                not self._cmds.getAttr(
                    f"{matches[0]}.jointOrient{axis.upper()}", settable=True
                )
                for axis in ("x", "y", "z")
            ):
                raise FitSkeletonValidationError(
                    "直接子 joint jointOrient 在执行前不可写"
                )
            preserved_children.append((matches[0], orientation))

        descendants: list[tuple[str, tuple[float, float, float]]] = []
        for descendant, position in change.descendant_world_positions:
            matches = self._cmds.ls(descendant, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError("worldOrient 补偿后代在执行前失效")
            if any(
                not self._cmds.getAttr(f"{matches[0]}.t{axis}", settable=True)
                for axis in ("x", "y", "z")
            ):
                raise FitSkeletonValidationError(
                    f"worldOrient 补偿 translate 在执行前不可写：{matches[0]}"
                )
            descendants.append((matches[0], position))

        self._transaction_changed = True
        self._set_joint_world_axes(joint, change.desired_world_axes)
        for child_path, orientation in preserved_children:
            self._cmds.setAttr(f"{child_path}.jointOrient", *orientation)
        for descendant, descendant_position in descendants:
            self._cmds.xform(
                descendant,
                worldSpace=True,
                translation=descendant_position,
            )

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings:
        container = self._resolve_transform(
            container_name,
            FitSkeletonValidationError,
        )
        settings: list[FitSkeletonSetting] = []
        for field, spec in _FIT_SKELETON_ATTRIBUTES.items():
            if not self._attribute_exists(container, spec.name):
                continue
            settings.append(
                FitSkeletonSetting(
                    field=field,
                    value=self._read_fit_skeleton_value(container, spec),
                )
            )
        return FitSkeletonSettings(container=container, settings=tuple(settings))

    def capture_fit_skeleton_setting_channels(
        self,
        container_name: str,
    ) -> tuple[FitSkeletonSettingChannelState, ...]:
        container = self._resolve_transform(
            container_name,
            FitSkeletonValidationError,
        )
        channels = []
        for field, spec in _FIT_SKELETON_ATTRIBUTES.items():
            if not self._attribute_exists(container, spec.name):
                continue
            attribute = f"{container}.{spec.name}"
            channels.append(
                FitSkeletonSettingChannelState(
                    field,
                    self._read_fit_skeleton_value(container, spec),
                    bool(self._cmds.getAttr(attribute, settable=True)),
                    tuple(
                        sorted(
                            set(
                                self._cmds.listConnections(
                                    attribute,
                                    source=True,
                                    destination=False,
                                    plugs=True,
                                )
                                or []
                            )
                        )
                    ),
                )
            )
        return tuple(channels)

    def set_fit_skeleton_setting(
        self,
        container: str,
        setting: FitSkeletonSetting,
    ) -> None:
        self._require_transaction()
        container_path = self._resolve_transform(
            container,
            FitSkeletonValidationError,
        )
        spec = _FIT_SKELETON_ATTRIBUTES.get(setting.field)
        if spec is None or not self._attribute_exists(container_path, spec.name):
            raise FitSkeletonValidationError(
                f"FitSkeleton 设置不存在：{setting.field.value}"
            )
        attribute = f"{container_path}.{spec.name}"
        if not self._cmds.getAttr(attribute, settable=True) or (
            self._cmds.listConnections(
                attribute,
                source=True,
                destination=False,
                plugs=True,
            )
            or []
        ):
            raise FitSkeletonValidationError(
                f"FitSkeleton 设置在执行前变为不可写：{setting.field.value}"
            )
        self._transaction_changed = True
        if spec.kind == "string":
            self._cmds.setAttr(attribute, setting.value, type="string")
        elif spec.enum_names:
            try:
                value = spec.enum_names.index(str(setting.value))
            except ValueError as error:
                raise FitSkeletonValidationError(
                    f"FitSkeleton enum 设置无效：{setting.field.value}"
                ) from error
            self._cmds.setAttr(attribute, value)
        else:
            self._cmds.setAttr(attribute, setting.value)

    def add_fit_skeleton_setting(
        self,
        container: str,
        setting: FitSkeletonSetting,
    ) -> None:
        self._require_transaction()
        spec = _FIT_SKELETON_ATTRIBUTES[setting.field]
        if self._attribute_exists(container, spec.name):
            raise FitSkeletonValidationError(
                f"FitSkeleton 设置已存在，拒绝覆盖：{spec.name}"
            )

        options = {
            "longName": spec.name,
            "keyable": setting.field in _KEYABLE_FIT_SKELETON_FIELDS,
        }
        if spec.kind == "string":
            options["dataType"] = "string"
        else:
            options["attributeType"] = spec.kind
            if spec.enum_names:
                options["enumName"] = ":".join(spec.enum_names)
                options["defaultValue"] = spec.enum_names.index(str(setting.value))
            else:
                options["defaultValue"] = setting.value
            if spec.minimum is not None:
                options["minValue"] = spec.minimum
            if spec.maximum is not None:
                options["maxValue"] = spec.maximum
        self._transaction_changed = True
        self._cmds.addAttr(container, **options)

    def read_fit_joint_metadata(self, joint: str) -> FitJointMetadata:
        present = frozenset(
            field
            for field, spec in _FIT_ATTRIBUTES.items()
            if self._attribute_exists(joint, spec.name)
        )
        return FitJointMetadata(
            joint=joint,
            twist_joints=self._optional_number(joint, "twistJoints", int),
            bendy_controls=self._optional_number(joint, "bendyCtrls", int),
            inbetween_joints=self._optional_number(joint, "inbetweenJoints", int),
            untwister=self._optional_bool(joint, "unTwister"),
            no_mirror=self._optional_bool(joint, "noMirror"),
            no_mirror_left=self._optional_bool(joint, "noMirrorLeft"),
            child_of_part=self._optional_number(joint, "childOfPart", int),
            global_weight=self._optional_number(joint, "global", float),
            global_translate=self._optional_bool(joint, "globalTranslate"),
            world_orient_up=self._optional_enum(joint, "worldOrientUp"),
            world_orient_forward=self._optional_enum(joint, "worldOrientForward"),
            ik_local_mode=self._optional_enum(joint, "ikLocal"),
            present_fields=present,
        )

    def apply_fit_joint_edit(self, joint: str, edit: FitJointFieldEdit) -> None:
        self._require_transaction()
        spec = _FIT_ATTRIBUTES[edit.field]
        exists = self._attribute_exists(joint, spec.name)
        if edit.value is None:
            if exists:
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.{spec.name}")
            return

        if not exists:
            options = {
                "longName": spec.name,
                "attributeType": spec.kind,
                "keyable": True,
            }
            if spec.minimum is not None:
                options["minValue"] = spec.minimum
            if spec.maximum is not None:
                options["maxValue"] = spec.maximum
            if spec.enum_names:
                options["enumName"] = ":".join(spec.enum_names)
            self._transaction_changed = True
            self._cmds.addAttr(joint, **options)

        self._transaction_changed = True
        if spec.enum_names:
            value = spec.enum_names.index(str(edit.value))
        else:
            value = edit.value
        self._cmds.setAttr(f"{joint}.{spec.name}", value)

    def set_fit_joint_world_axes(
        self,
        joint: str,
        world_axes: tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ],
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(joint, long=True, type="joint") or []
        if len(matches) != 1:
            raise FitSkeletonValidationError(
                "Fit joint 朝向目标在执行前失效"
            )
        path = matches[0]
        if self._cmds.listRelatives(path, children=True, fullPath=True) or []:
            raise FitSkeletonValidationError(
                "Fit joint 必须在创建子级前恢复世界轴"
            )
        if len(world_axes) != 3 or any(len(axis) != 3 for axis in world_axes):
            raise FitSkeletonValidationError("Fit joint 世界轴格式无效")
        required = tuple(
            f"{path}.{attribute}{axis.upper()}"
            for attribute in ("translate", "rotate", "jointOrient")
            for axis in ("x", "y", "z")
        )
        if any(
            not self._cmds.getAttr(attribute, settable=True)
            for attribute in required
        ):
            raise FitSkeletonValidationError(
                "Fit joint 朝向通道在执行前变为不可写"
            )
        self._transaction_changed = True
        self._set_joint_world_axes(path, world_axes)

    def _checkpoint_new_transform_channels(self, previous_uuids):
        """Record final local values so redo does not depend on world-xform order.

        Maya may reevaluate world-space construction commands against a partly
        restored hierarchy during redo. Only newly created, unconnected local
        transform channels are checkpointed; driven channels remain untouched.
        """
        c = self._cmds
        channels = ("translate", "rotate", "scale", "shear", "rotateAxis", "jointOrient")
        rows = []
        for node in sorted(c.ls(type="transform", long=True) or []):
            if c.nodeType(node) not in ("transform", "joint") or set(c.ls(node, uuid=True) or []) & previous_uuids:
                continue
            for channel in channels:
                for axis in ("XY", "XZ", "YZ") if channel == "shear" else "XYZ":
                    plug = node + "." + channel + axis
                    if c.objExists(plug) and not c.listConnections(plug, source=True, destination=False):
                        rows.append((plug, c.getAttr(plug), c.getAttr(plug, lock=True)))
        for plug, value, locked in rows:
            if locked:
                c.setAttr(plug, lock=False)
            c.setAttr(plug, value)
            if locked:
                c.setAttr(plug, lock=True)

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        if self._transaction_active:
            raise RuntimeError("MayaFitJointHost 不支持嵌套事务")
        previous_uuids = set(self._cmds.ls(type="transform", uuid=True) or [])
        self._transaction_active = True
        self._transaction_changed = False
        self._cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
            if self._transaction_changed:
                self._checkpoint_new_transform_channels(previous_uuids)
        except Exception:
            self._cmds.undoInfo(closeChunk=True)
            if self._transaction_changed:
                self._cmds.undo()
            raise
        else:
            self._cmds.undoInfo(closeChunk=True)
        finally:
            self._transaction_active = False
            self._transaction_changed = False

    def set_joint_label(self, joint: str, label: JointLabel) -> None:
        self._require_transaction()
        code = _MAYA_LABEL_TYPES.get(label.text.casefold(), 18)
        self._transaction_changed = True
        self._cmds.setAttr(f"{joint}.drawLabel", True)
        self._cmds.setAttr(f"{joint}.type", code)
        if code == 18:
            self._cmds.setAttr(f"{joint}.otherType", label.text, type="string")

    def clear_joint_label(self, joint: str) -> None:
        self._require_transaction()
        self._transaction_changed = True
        self._cmds.setAttr(f"{joint}.drawLabel", False)

    def read_joint_label(self, joint: str) -> JointLabel | None:
        if not self._cmds.getAttr(f"{joint}.drawLabel"):
            return None
        code = int(self._cmds.getAttr(f"{joint}.type"))
        if code == 18:
            text = self._cmds.getAttr(f"{joint}.otherType") or "Other"
        else:
            text = _MAYA_LABEL_NAMES.get(code)
            if text is None:
                raise RuntimeError(f"不支持的 Maya joint label type：{code}")
        return JointLabel.parse(text)

    def _attribute_exists(self, joint: str, attribute: str) -> bool:
        return bool(self._cmds.attributeQuery(attribute, node=joint, exists=True))

    def _optional_number(self, joint: str, attribute: str, cast):
        if not self._attribute_exists(joint, attribute):
            return None
        value = self._cmds.getAttr(f"{joint}.{attribute}")
        try:
            return cast(value)
        except (TypeError, ValueError) as error:
            raise FitJointValidationError(
                f"{joint}.{attribute} 不是有效数值：{value!r}"
            ) from error

    def _optional_bool(self, joint: str, attribute: str) -> bool:
        if not self._attribute_exists(joint, attribute):
            return False
        return bool(self._cmds.getAttr(f"{joint}.{attribute}"))

    def _optional_enum(self, joint: str, attribute: str) -> str | None:
        if not self._attribute_exists(joint, attribute):
            return None
        names = self._cmds.attributeQuery(attribute, node=joint, listEnum=True)
        if not names:
            raise FitJointValidationError(f"{joint}.{attribute} 不是 enum 属性")
        options = names[0].split(":")
        index = int(self._cmds.getAttr(f"{joint}.{attribute}"))
        if not 0 <= index < len(options):
            raise FitJointValidationError(
                f"{joint}.{attribute} 的 enum 值越界：{index}"
            )
        return options[index]

    def _read_fit_skeleton_value(
        self,
        container: str,
        spec: _MayaFitAttribute,
    ) -> FitSkeletonValue:
        attribute = f"{container}.{spec.name}"
        actual_kind = self._cmds.getAttr(attribute, type=True)
        if actual_kind != spec.kind:
            raise FitSkeletonValidationError(
                f"FitSkeleton.{spec.name} 类型应为 {spec.kind}，当前为 {actual_kind}"
            )
        if spec.kind == "bool":
            return bool(self._cmds.getAttr(attribute))
        if spec.kind == "double":
            return float(self._cmds.getAttr(attribute))
        if spec.kind == "string":
            return self._cmds.getAttr(attribute) or ""

        names = self._cmds.attributeQuery(
            spec.name,
            node=container,
            listEnum=True,
        )
        if not names:
            raise FitSkeletonValidationError(
                f"FitSkeleton.{spec.name} 缺少 enum 定义"
            )
        options = names[0].split(":")
        index = int(self._cmds.getAttr(attribute))
        if not 0 <= index < len(options):
            raise FitSkeletonValidationError(
                f"FitSkeleton.{spec.name} 的 enum 值越界：{index}"
            )
        return options[index]

    def _resolve_transform(
        self,
        name: str,
        error_type: type[ValueError],
    ) -> str:
        matches = self._cmds.ls(name, long=True, type="transform") or []
        if not matches:
            raise error_type(f"FitSkeleton 容器不存在：{name}")
        if len(matches) != 1:
            raise error_type(f"FitSkeleton 容器名称不唯一：{name}")
        return matches[0]

    @staticmethod
    def _normalized_vector(
        value: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        length = sum(component * component for component in value) ** 0.5
        if length <= 1e-10:
            raise FitSkeletonValidationError("Maya joint 世界轴长度无效")
        return tuple(component / length for component in value)

    def _set_joint_world_axes(
        self,
        joint: str,
        axes: tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ],
    ) -> None:
        position = self._cmds.xform(
            joint,
            query=True,
            worldSpace=True,
            translation=True,
        )
        x_axis, y_axis, z_axis = axes
        matrix = (
            *x_axis,
            0.0,
            *y_axis,
            0.0,
            *z_axis,
            0.0,
            float(position[0]),
            float(position[1]),
            float(position[2]),
            1.0,
        )
        self._cmds.xform(joint, worldSpace=True, matrix=matrix)
        self._cmds.makeIdentity(
            joint,
            apply=True,
            translate=False,
            rotate=True,
            scale=False,
            normal=False,
        )

    def _require_transaction(self) -> None:
        if not self._transaction_active:
            raise RuntimeError("Maya Fit 修改必须发生在事务内")


MayaJointLabelHost = MayaFitJointHost
