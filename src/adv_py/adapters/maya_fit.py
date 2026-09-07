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
    FitOrientationChange,
    FitOrientationSnapshot,
)
from adv_py.core.fit_settings import (
    FitSkeletonField,
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    FitSkeletonValue,
)
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
        if any(
            not self._cmds.getAttr(
                f"{child}.jointOrient{axis.upper()}", settable=True
            )
            for axis in ("x", "y", "z")
        ):
            raise FitSkeletonValidationError("子 joint jointOrient 在执行前变为不可写")
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

        self._cmds.joint(
            joint,
            edit=True,
            orientJoint="xyz",
            secondaryAxisOrient=f"{change.secondary_world_axis.value}up",
            children=False,
            zeroScaleOrient=True,
        )
        self._transaction_changed = True
        self._cmds.setAttr(
            f"{child}.jointOrient",
            *change.child_before_joint_orient,
        )
        for descendant, position in descendant_paths:
            self._cmds.xform(
                descendant,
                worldSpace=True,
                translation=position,
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

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        if self._transaction_active:
            raise RuntimeError("MayaFitJointHost 不支持嵌套事务")
        self._transaction_active = True
        self._transaction_changed = False
        self._cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
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

    def _require_transaction(self) -> None:
        if not self._transaction_active:
            raise RuntimeError("Maya Fit 修改必须发生在事务内")


MayaJointLabelHost = MayaFitJointHost
