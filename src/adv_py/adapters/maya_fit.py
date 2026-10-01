from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Sequence

from adv_py.core.body_skeleton import FitDeformProfile
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
    fit_build_scale,
)
from adv_py.core.fit_metadata import (
    FitJointField,
    FitJointFieldEdit,
    FitJointMetadata,
    FitJointValidationError,
)
from adv_py.core.fit_orientation import (
    FitLocalDirection,
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
    FitJointField.CONTROL: _MayaFitAttribute("control", "bool"),
    FitJointField.TWEAKER_CONTROL: _MayaFitAttribute("tweakerControl", "bool"),
    FitJointField.NO_CONTROL: _MayaFitAttribute("noControl", "bool"),
    FitJointField.NO_SKIN: _MayaFitAttribute("noSkin", "bool"),
    FitJointField.SEG_SCALE_COMP: _MayaFitAttribute("segScaleComp", "bool"),
    FitJointField.HIP_SWINGER: _MayaFitAttribute("hipSwinger", "bool"),
    FitJointField.COG: _MayaFitAttribute("cog", "bool"),
    FitJointField.AIM: _MayaFitAttribute("aim", "bool"),
    FitJointField.FOOT_PIVOTS: _MayaFitAttribute("footPivots", "bool"),
    FitJointField.WHEEL: _MayaFitAttribute("wheel", "bool"),
    FitJointField.ROLLING_BALL: _MayaFitAttribute("rollingBall", "bool"),
    FitJointField.CURVE_GUIDE: _MayaFitAttribute("curveGuide", "string"),
    FitJointField.FREE_ORIENT: _MayaFitAttribute("freeOrient", "bool"),
    FitJointField.FLIP_ORIENT: _MayaFitAttribute("flipOrient", "bool"),
    FitJointField.NO_MIRROR: _MayaFitAttribute("noMirror", "bool"),
    FitJointField.NO_MIRROR_LEFT: _MayaFitAttribute("noMirrorLeft", "bool"),
    FitJointField.NO_FLIP: _MayaFitAttribute("noFlip", "bool"),
    FitJointField.CHILD_OF_PART: _MayaFitAttribute("childOfPart", "long", 1, 10),
    FitJointField.GLOBAL_WEIGHT: _MayaFitAttribute("global", "double", 0, 10),
    FitJointField.GLOBAL_TRANSLATE: _MayaFitAttribute("globalTranslate", "bool"),
    FitJointField.PARENT_CONSTRAINT: _MayaFitAttribute("parentConstraint", "string"),
    FitJointField.POINT_CONSTRAINT: _MayaFitAttribute("pointConstraint", "string"),
    FitJointField.ORIENT_CONSTRAINT: _MayaFitAttribute("orientConstraint", "string"),
    FitJointField.ORIENT_CONSTRAINT_MAINTAIN_OFFSET: _MayaFitAttribute(
        "orientConstraintMaintainOffset", "bool"),
    FitJointField.SCALE_CONSTRAINT: _MayaFitAttribute("scaleConstraint", "string"),
    FitJointField.FOLLOW: _MayaFitAttribute("follow", "string"),
    FitJointField.FOLLOW_LEFT_RIGHT: _MayaFitAttribute("followLeftRight", "bool"),
    FitJointField.FOLLOW_WORLD: _MayaFitAttribute("followWorld", "bool"),
    FitJointField.FOLLOW_SPACES: _MayaFitAttribute("followSpaces", "bool"),
    FitJointField.IK_FOLLOW: _MayaFitAttribute("ikFollow", "string"),
    FitJointField.AIM_AT: _MayaFitAttribute("aimAt", "string"),
    FitJointField.GEO_ATTACH: _MayaFitAttribute("geoAttach", "string"),
    FitJointField.PROXIMITY_PIN: _MayaFitAttribute("proximityPin", "string"),
    FitJointField.LEG_LOCK: _MayaFitAttribute("legLock", "bool"),
    FitJointField.NUM_MAIN_EXTRAS: _MayaFitAttribute("numMainExtras", "long", 0),
    FitJointField.CENTER_BETWEEN_FEET: _MayaFitAttribute(
        "centerBetweenFeet", "bool"),
    FitJointField.GEO_ATTACH_MODE: _MayaFitAttribute(
        "geoAttachMode", "enum", enum_names=("point", "orient", "parent")),
    FitJointField.AIM_AXIS: _MayaFitAttribute(
        "aimAxis", "enum", enum_names=("x", "y", "z")),
    FitJointField.AIM_UP_AXIS: _MayaFitAttribute(
        "aimUpAxis", "enum", enum_names=("x", "y", "z")),
    FitJointField.AIM_UP_OBJECT: _MayaFitAttribute(
        "aimUpObject", "enum", enum_names=("self", "target")),
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

    def __init__(self, *, namespace: str | None = None) -> None:
        from maya import cmds  # type: ignore[import-not-found]

        if namespace is None:
            self._cmds = cmds
        else:
            from .maya_namespace import MayaCharacterCommands
            self._cmds = MayaCharacterCommands(cmds, namespace)
        self.namespace = namespace
        self._transaction_active = False
        self._transaction_changed = False

    def scene_address(self, address: str) -> str:
        """Resolve an internal node/plug address for external Maya consumers."""
        if self.namespace is None:
            return address
        return self._cmds.identity.to_scene(address)

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
        sibling_orders: dict[str, tuple[str, ...]] = {}
        for path in joint_paths:
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            parent = parents[0] if parents else None
            if parent is not None and parent not in sibling_orders:
                sibling_orders[parent] = tuple(self._cmds.listRelatives(
                    parent, children=True, type="joint", fullPath=True
                ) or ())
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
                    dag_parent=parent,
                    local_position=tuple(float(value) for value in local),
                    world_position=tuple(float(value) for value in world),
                    locked_translation_axes=locked_axes,
                    writable_translation_axes=writable_axes,
                    sibling_index=(sibling_orders[parent].index(path)
                                   if parent is not None else 0),
                )
            )
        return FitHierarchySnapshot(container=container, joints=tuple(nodes))

    def collapse_fit_generated_transforms(self, container_name: str) -> None:
        """Remove Maya-generated transform wrappers around Fit joints."""
        self._require_transaction()
        container = self._resolve_transform(
            container_name, FitHierarchyValidationError
        )
        descendants = self._cmds.listRelatives(
            container, allDescendents=True, fullPath=True
        ) or []
        wrappers = [path for path in descendants
                    if self._cmds.nodeType(path) == "transform"
                    and path.rsplit("|", 1)[-1].startswith("transform")]
        for wrapper in wrappers:
            current = self._cmds.ls(wrapper, long=True, type="transform") or []
            if len(current) != 1:
                raise RuntimeError("Fit 自动生成的中间层路径不唯一：" + wrapper)
            parent = self._cmds.listRelatives(
                current[0], parent=True, fullPath=True
            ) or []
            if len(parent) != 1:
                raise RuntimeError("Fit 自动生成的中间层缺少父级：" + wrapper)
            children = self._cmds.listRelatives(
                current[0], children=True, fullPath=True
            ) or []
            if any(self._cmds.nodeType(child) not in ("joint", "transform")
                   for child in children):
                raise FitSkeletonValidationError(
                    "Fit 自动生成的中间层包含非关节对象：" + wrapper
                )
            if any(self._cmds.nodeType(child) == "transform" for child in children):
                raise FitSkeletonValidationError(
                    "Fit 自动生成的中间层包含其他 transform：" + wrapper
                )
            self._transaction_changed = True
            for child in children:
                result = self._cmds.parent(child, parent[0], absolute=True)
                moved = self._cmds.ls(result[0], long=True, type="joint") or []
                if len(moved) != 1 or (self._cmds.listRelatives(
                        moved[0], parent=True, fullPath=True) or []) != parent:
                    raise RuntimeError(
                        "Fit 自动生成的中间层移除时再次产生中间层：" + wrapper
                    )
            self._cmds.delete(current[0])

    def prepare_fit_root(self, container_name: str) -> str:
        """Apply the root naming/insertion pass from asBuildAdvancedSkeleton."""
        self._require_transaction()
        container = self._resolve_transform(
            container_name, FitHierarchyValidationError
        )
        roots = self._cmds.listRelatives(
            container, children=True, type="joint", fullPath=True
        ) or []
        if not roots:
            # The original retries after manual update when generated Maya
            # transforms hide the direct joint children of FitSkeleton.
            self.normalize_fit_joint_names(container)
            self.normalize_fit_ik_labels(container)
            self.bake_fit_container_scale(container)
            roots = self._cmds.listRelatives(
                container, children=True, type="joint", fullPath=True) or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                "FitSkeleton 必须恰有一个顶层 joint 才能准备 Root"
            )
        first = roots[0]
        name = first.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        position = tuple(float(value) for value in self._cmds.xform(
            first, query=True, worldSpace=True, translation=True
        ))
        scale = fit_build_scale(self.capture_fit_hierarchy(container))
        centered = abs(position[0]) < 0.01 * scale
        if centered or name == "Root" and abs(position[0]) <= 0.01 * scale:
            if name == "Root":
                if any(path != first and not path.startswith(container + "|")
                       for path in self.find_name_collisions("Root")):
                    raise FitSkeletonValidationError(
                        "场景中有其他 Root，无法保留顶层 Fit 根关节名称"
                    )
                return first
            if self.find_name_collisions("Root"):
                raise FitSkeletonValidationError("场景中已有 Root，无法重命名顶层 Fit joint")
            self._transaction_changed = True
            renamed = self._cmds.rename(first, "Root")
            return (self._cmds.ls(renamed, long=True, type="joint") or [renamed])[0]
        if name == "Root":
            root_matches = self.find_name_collisions("Root")
            if set(root_matches) != {first}:
                raise FitSkeletonValidationError("Root 名称不唯一，无法准备 Fit 根关节")
            if self.find_name_collisions("RootSide"):
                raise FitSkeletonValidationError("RootSide 名称已被占用")
            self._transaction_changed = True
            renamed = self._cmds.rename(first, "RootSide")
            first = (self._cmds.ls(renamed, long=True, type="joint") or [renamed])[0]
        elif self.find_name_collisions("Root"):
            raise FitSkeletonValidationError("场景中已有 Root，无法插入中心根关节")
        self._transaction_changed = True
        root = self._cmds.createNode(
            "joint", name="Root", parent=container, skipSelect=True
        )
        root = (self._cmds.ls(root, long=True, type="joint") or [root])[0]
        self._cmds.xform(
            root, worldSpace=True,
            translation=(0.0, position[1], position[2]),
        )
        self._cmds.parent(first, root, absolute=True)
        return root

    def normalize_fit_ik_labels(self, container_name: str) -> None:
        """Disambiguate the IK-start labels adjusted by asFitModeManualUpdate."""
        self._require_transaction()
        container = self._resolve_transform(
            container_name, FitHierarchyValidationError
        )
        joints = self._cmds.listRelatives(
            container, allDescendents=True, type="joint", fullPath=True
        ) or []
        labels = {joint: self.read_joint_label(joint) for joint in joints}
        counts: dict[str, int] = {}
        used: set[str] = set()
        for label in labels.values():
            if label is not None:
                counts[label.text] = counts.get(label.text, 0) + 1
                used.add(label.text)
        for joint in joints:
            label = labels[joint]
            if label is None or not (
                    "Shoulder" in label.text or "Hip" in label.text
                    or "Root" in label.text or label.text.startswith("0")):
                continue
            if counts[label.text] <= 1:
                continue
            candidate = None
            for index in range(1, 99):
                suffix = (chr(ord("A") + index - 1)
                          if label.text.startswith("0") and index <= 26
                          else str(index) if not label.text.startswith("0")
                          else "")
                if not suffix:
                    break
                proposed = label.text + suffix
                if proposed not in used:
                    candidate = proposed
                    break
            if candidate is None:
                raise FitSkeletonValidationError(
                    "无法给重复的 Fit IK 标签分配唯一名称：" + label.text
                )
            self.set_joint_label(joint, JointLabel.parse(candidate))
            used.add(candidate)

    def normalize_fit_joint_names(self, container_name: str) -> None:
        """Give Fit joints unique short names before name-based rig generation."""
        self._require_transaction()
        container = self._resolve_transform(
            container_name, FitHierarchyValidationError
        )
        joints = self._cmds.listRelatives(
            container, allDescendents=True, type="joint", fullPath=True
        ) or []
        # Maya returns descendants before their parents. Renaming in this
        # order keeps the remaining full paths valid throughout the pass.
        for joint in joints:
            short = joint.rsplit("|", 1)[-1]
            if len(self._cmds.ls(short, long=True) or []) <= 1:
                continue
            for index in range(1, 99):
                candidate = short + str(index)
                if not self._cmds.objExists(candidate):
                    self._transaction_changed = True
                    renamed = self._cmds.rename(joint, candidate)
                    resolved = self._cmds.ls(
                        renamed, long=True, type="joint"
                    ) or []
                    if len(resolved) != 1 or resolved[0].rsplit("|", 1)[-1] != candidate:
                        raise RuntimeError(
                            "Fit 重名关节重命名后路径不唯一：" + joint
                        )
                    break
            else:
                raise FitSkeletonValidationError(
                    "Fit 重名关节没有可用的数字后缀：" + short
                )

    def _fit_node_uuid(self, path: str) -> str:
        values = self._cmds.ls(path, uuid=True) or []
        if len(values) != 1:
            raise FitSkeletonValidationError("Fit 节点身份不唯一：" + path)
        return values[0]

    def _fit_node_from_uuid(self, identifier: str) -> str:
        c = getattr(self._cmds, "raw", self._cmds)
        values = c.ls(identifier, long=True) or []
        if len(values) != 1:
            raise FitSkeletonValidationError("Fit 节点身份已失效：" + identifier)
        identity = getattr(self._cmds, "identity", None)
        return identity.to_local(values[0]) if identity is not None else values[0]

    @contextmanager
    def fit_manual_update_channels(self, container_name: str):
        """Temporarily release Fit TRS locks/drivers as manual update does."""
        self._require_transaction()
        c = self._cmds
        container = self._resolve_transform(container_name, FitHierarchyValidationError)
        joints = c.listRelatives(container, allDescendents=True,
                                 type="joint", fullPath=True) or []
        states = []
        try:
            for joint in joints:
                identifier = self._fit_node_uuid(joint)
                for channel in ("tx", "ty", "tz", "rx", "ry", "rz",
                                "sx", "sy", "sz"):
                    plug = joint + "." + channel
                    locked = bool(c.getAttr(plug, lock=True))
                    source = c.connectionInfo(plug, sourceFromDestination=True)
                    value = c.getAttr(plug)
                    source_identity = None
                    if source:
                        source_node, source_attribute = source.split(".", 1)
                        source_identity = (self._fit_node_uuid(source_node),
                                           source_attribute)
                    states.append((identifier, channel, locked, source_identity))
                    if locked:
                        self._transaction_changed = True
                        c.setAttr(plug, lock=False)
                    if source:
                        self._transaction_changed = True
                        c.disconnectAttr(source, plug)
                        c.setAttr(plug, value)
            yield
        finally:
            for identifier, channel, locked, source in states:
                plug = self._fit_node_from_uuid(identifier) + "." + channel
                if source is not None:
                    source_plug = self._fit_node_from_uuid(source[0]) + "." + source[1]
                    if not c.isConnected(source_plug, plug):
                        c.connectAttr(source_plug, plug, force=True)
                if bool(c.getAttr(plug, lock=True)) != locked:
                    c.setAttr(plug, lock=locked)

    def bake_fit_container_scale(self, container_name: str) -> None:
        """Port asFitModeUpdateScale's detach/reset/reparent build pass."""
        self._require_transaction()
        container = self._resolve_transform(
            container_name, FitHierarchyValidationError
        )
        scale = tuple(float(value) for value in self._cmds.getAttr(
            container + ".scale"
        )[0])
        c = self._cmds
        joints = c.listRelatives(
            container, allDescendents=True, type="joint", fullPath=True
        ) or []
        records = []
        for joint in joints:
            parent = (c.listRelatives(joint, parent=True, fullPath=True) or [None])[0]
            wrapper = None
            if parent != container and parent is not None and c.nodeType(parent) == "transform":
                wrapper = self._fit_node_uuid(parent)
                parent = (c.listRelatives(parent, parent=True, fullPath=True) or [None])[0]
            locks = tuple(bool(c.getAttr(joint + ".t" + axis, lock=True))
                          for axis in "xyz")
            records.append((self._fit_node_uuid(joint),
                            self._fit_node_uuid(parent) if parent else None,
                            wrapper, locks))
        self._transaction_changed = True
        c.setAttr(container + ".scale", 1.0, 1.0, 1.0)
        expected_positions = {}
        try:
            for identifier, _, _, _ in records:
                joint = self._fit_node_from_uuid(identifier)
                for axis in "xyz":
                    c.setAttr(joint + ".t" + axis, lock=False)
            for identifier, _, wrapper, _ in records:
                joint = self._fit_node_from_uuid(identifier)
                c.parent(joint, world=True, absolute=True)
                if wrapper is not None:
                    old_wrapper = self._fit_node_from_uuid(wrapper)
                    if c.listRelatives(old_wrapper, children=True, fullPath=True):
                        raise FitSkeletonValidationError("Fit 中间层含其他对象，不能移除")
                    c.delete(old_wrapper)
                joint = self._fit_node_from_uuid(identifier)
                generated = c.listRelatives(joint, parent=True, fullPath=True) or []
                if generated:
                    position = c.xform(joint, query=True, worldSpace=True, translation=True)
                    c.setAttr(generated[0] + ".scale", 1.0, 1.0, 1.0)
                    c.parent(joint, world=True, absolute=True)
                    c.xform(self._fit_node_from_uuid(identifier), worldSpace=True,
                            translation=position)
                    if c.listRelatives(generated[0], children=True, fullPath=True):
                        raise FitSkeletonValidationError("Fit 新生成中间层仍有对象")
                    c.delete(generated[0])
            for identifier, _, _, _ in records:
                joint = self._fit_node_from_uuid(identifier)
                position = c.xform(joint, query=True, worldSpace=True, translation=True)
                expected = tuple(float(value) * factor for value, factor in zip(position, scale))
                c.xform(joint, worldSpace=True, translation=expected)
                c.setAttr(joint + ".scale", 1.0, 1.0, 1.0)
                c.setAttr(joint + ".inverseScale", 1.0, 1.0, 1.0)
                expected_positions[identifier] = expected
                if c.attributeQuery("fat", node=joint, exists=True):
                    c.setAttr(joint + ".fat", float(c.getAttr(joint + ".fat")) * scale[1])
            for identifier, parent, _, _ in records:
                if parent is not None:
                    c.parent(self._fit_node_from_uuid(identifier),
                             self._fit_node_from_uuid(parent), absolute=True)
            if any(value != 1.0 for value in scale):
                shapes = c.listRelatives(container, shapes=True, type="nurbsCurve",
                                         noIntermediate=True, fullPath=True) or []
                for shape in shapes:
                    c.scale(scale[1], scale[1], scale[1], shape + ".cv[0:7]",
                            relative=True, pivot=(0.0, 0.0, 0.0))
            for identifier, expected in expected_positions.items():
                joint = self._fit_node_from_uuid(identifier)
                actual = c.xform(joint, query=True, worldSpace=True, translation=True)
                if any(abs(float(value) - target) > 1e-5 * max(1.0, abs(target))
                       for value, target in zip(actual, expected)):
                    raise RuntimeError("Fit 缩放准备后关节世界位置不一致：" + joint)
                if any(abs(float(value) - 1.0) > 1e-6
                       for value in c.getAttr(joint + ".scale")[0]):
                    raise RuntimeError("Fit 缩放准备后关节未恢复单位缩放：" + joint)
        finally:
            for identifier, _, _, locks in records:
                joint = self._fit_node_from_uuid(identifier)
                for axis, locked in zip("xyz", locks):
                    c.setAttr(joint + ".t" + axis, lock=locked)

    def snap_fit_ik_chain_centers(self, container_name: str) -> None:
        """Port the center-start snap in asFitModeUpdateJoints before aiming.

        This intentionally moves authored joints, so it runs before the
        orientation snapshot whose writer preserves descendant positions.
        """
        from adv_py.core.fit_ik import fit_joint_ik_info
        self._require_transaction()
        snapshot = self.capture_fit_orientation(container_name)
        hierarchy = snapshot.hierarchy
        labels = dict(snapshot.labels)
        children = {node.dag_parent for node in hierarchy.joints}
        tolerance = 0.01 * snapshot.fit_scale
        c = self._cmds
        # The recursive MEL pass follows parents before their children. Read
        # current positions each time because snapping a parent moves its tree.
        for node in sorted(hierarchy.joints,
                           key=lambda item: (item.path.count("|"), item.path)):
            if node.path not in children:
                continue
            info = fit_joint_ik_info(hierarchy, labels, node.path)
            if info is None:
                continue
            start = c.xform(info.start, query=True, worldSpace=True,
                            translation=True)
            position = c.xform(node.path, query=True, worldSpace=True,
                               translation=True)
            if abs(float(start[0])) < tolerance and abs(float(position[0])) >= tolerance:
                self._transaction_changed = True
                c.xform(node.path, worldSpace=True,
                        translation=(0.0, float(position[1]), float(position[2])))

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
            fit_scale=float(self._cmds.getAttr(f"{hierarchy.container}.scaleX")),
            labels=tuple((node.path, self.read_joint_label(node.path))
                         for node in hierarchy.joints),
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
        for path,delta in change.position_adjustments:
            matches=self._cmds.ls(path,long=True,type='joint') or []
            if len(matches)!=1 or any(not self._cmds.getAttr(path+'.t'+axis,settable=True)
                                      for axis in 'xyz'):
                raise FitSkeletonValidationError('零弯曲 IK 中间关节在执行前不可写：'+path)
            self._transaction_changed=True
            self._cmds.move(*delta,path+'.rotatePivot',worldSpace=True,relative=True)
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
        if (len(preserved_children) > 1
                or change.use_explicit_world_axes):
            if change.desired_world_axes is not None:
                axes = change.desired_world_axes
            else:
                primary = change.desired_primary_world
                secondary = change.desired_secondary_world
                tertiary = (
                    primary[1] * secondary[2] - primary[2] * secondary[1],
                    primary[2] * secondary[0] - primary[0] * secondary[2],
                    primary[0] * secondary[1] - primary[1] * secondary[0],
                )
                axes = (primary, secondary, tertiary)
            self._set_joint_world_axes(joint, axes)
        else:
            self._cmds.joint(
                joint,
                edit=True,
                orientJoint="xyz",
                secondaryAxisOrient=f"{change.secondary_world_axis.value}up",
                children=False,
                zeroScaleOrient=True,
            )
        if change.preserved_child_world_axes:
            for child_path, axes in change.preserved_child_world_axes:
                self._set_joint_world_axes(child_path, axes)
        else:
            for child_path, orientation in preserved_children:
                self._cmds.setAttr(f"{child_path}.jointOrient", *orientation)
        for descendant, position in descendant_paths:
            self._cmds.xform(
                descendant,
                worldSpace=True,
                translation=position,
            )
        if change.world_match_axes is not None:
            self._write_fit_axis_enums(joint, change.world_match_axes)
            if not (self._cmds.listRelatives(
                child, children=True, type="joint", fullPath=True
            ) or []):
                self._write_fit_axis_enums(child, change.world_match_axes)

    def _write_fit_axis_enums(
        self,
        joint: str,
        axes: tuple[FitLocalDirection, FitLocalDirection],
    ) -> None:
        values = {"+x": 0, "+y": 1, "+z": 2,
                  "-x": 3, "-y": 4, "-z": 5}
        for attribute, direction in zip(("primaryAxis", "secondaryAxis"), axes):
            if not self._cmds.attributeQuery(attribute, node=joint, exists=True):
                self._cmds.addAttr(
                    joint, longName=attribute, attributeType="enum",
                    enumName="X:Y:Z:-X:-Y:-Z:",
                )
            self._cmds.setAttr(f"{joint}.{attribute}", values[direction.value])

    def zero_fit_terminal_joint(self, joint: str) -> None:
        self._require_transaction()
        matches = self._cmds.ls(joint, long=True, type="joint") or []
        if len(matches) != 1:
            raise FitSkeletonValidationError("末端 Fit joint 在执行前失效")
        path = matches[0]
        if (self._cmds.listRelatives(
                path, children=True, type="joint", fullPath=True) or []):
            raise FitSkeletonValidationError("Fit joint 已不再是末端关节")
        if self._cmds.attributeQuery("control", node=path, exists=True):
            raise FitSkeletonValidationError("Fit 末端关节已添加 control 属性")
        plugs = tuple(f"{path}.{name}{axis}" for name in (
            "jointOrient", "rotate") for axis in "XYZ")
        locked = tuple(bool(self._cmds.getAttr(plug, lock=True))
                       for plug in plugs)
        self._transaction_changed = True
        try:
            for plug, was_locked in zip(plugs, locked):
                if was_locked:
                    self._cmds.setAttr(plug, lock=False)
            self._cmds.setAttr(f"{path}.jointOrient", 0, 0, 0)
            self._cmds.setAttr(f"{path}.rotate", 0, 0, 0)
        finally:
            for plug, was_locked in zip(plugs, locked):
                if was_locked:
                    self._cmds.setAttr(plug, lock=True)

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
        if change.preserved_child_world_axes:
            for child_path, axes in change.preserved_child_world_axes:
                self._set_joint_world_axes(child_path, axes)
        else:
            for child_path, orientation in preserved_children:
                self._cmds.setAttr(f"{child_path}.jointOrient", *orientation)
        for descendant, descendant_position in descendants:
            self._cmds.xform(
                descendant,
                worldSpace=True,
                translation=descendant_position,
            )
        if change.world_match_axes is not None:
            self._write_fit_axis_enums(joint, change.world_match_axes)
            if not (self._cmds.listRelatives(
                child, children=True, type="joint", fullPath=True
            ) or []):
                self._write_fit_axis_enums(child, change.world_match_axes)
        if change.corrected_world_orient_forward is not None:
            # MEL writes the next Forward enum when Up and Forward coincide.
            enum_names = _FIT_ATTRIBUTES[
                FitJointField.WORLD_ORIENT_FORWARD
            ].enum_names
            self._cmds.setAttr(
                f"{joint}.worldOrientForward",
                enum_names.index(change.corrected_world_orient_forward),
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
        present = {
            field
            for field, spec in _FIT_ATTRIBUTES.items()
            if self._attribute_exists(joint, spec.name)
        }
        follow_names = tuple(
            attr for attr in (self._cmds.listAttr(
                joint, userDefined=True) or ())
            if attr.startswith("follow") and attr not in (
                "follow", "followLeftRight", "followWorld", "followSpaces",
                "followTranslate", "followPivot", "followScale"))
        follow_by_name = tuple(
            (attr[len("follow"):],
             float(self._cmds.getAttr(joint + "." + attr)))
            for attr in follow_names)
        if follow_by_name:
            present.add(FitJointField.FOLLOW_BY_NAME)
        twist_joints = self._optional_number(joint, "twistJoints", int)
        bendy_controls = self._optional_number(joint, "bendyCtrls", int)
        if (bendy_controls is None
                and twist_joints is not None and twist_joints > 0
                and self._optional_bool(joint, "bendyJoints")):
            # ADV 6.925 maps the old boolean to one controller when no
            # bendyCtrls attribute overrides it and a Twist chain exists.
            bendy_controls = 1
            present.add(FitJointField.BENDY_CONTROLS)
        inherited_no_flip, no_flip = self._inherited_fit_bool(joint, "noFlip")
        return FitJointMetadata(
            joint=joint,
            twist_joints=twist_joints,
            bendy_controls=bendy_controls,
            inbetween_joints=self._optional_number(joint, "inbetweenJoints", int),
            untwister=self._optional_bool(joint, "unTwister"),
            control=self._optional_bool(joint, "control"),
            tweaker_control=self._optional_bool(joint, "tweakerControl"),
            no_control=self._optional_bool(joint, "noControl"),
            no_skin=self._optional_bool(joint, "noSkin"),
            seg_scale_comp=(self._optional_bool(joint, "segScaleComp")
                            if self._attribute_exists(joint, "segScaleComp")
                            else None),
            hip_swinger=(self._optional_bool(joint, "hipSwinger")
                         if self._attribute_exists(joint, "hipSwinger")
                         else None),
            cog=self._optional_bool(joint, "cog"),
            aim=self._optional_bool(joint, "aim"),
            foot_pivots=self._optional_bool(joint, "footPivots"),
            wheel=FitJointField.WHEEL in present,
            rolling_ball=FitJointField.ROLLING_BALL in present,
            curve_guide=self._optional_mesh_target(joint, "curveGuide"),
            free_orient=self._optional_bool(joint, "freeOrient"),
            flip_orient=self._optional_bool(joint, "flipOrient"),
            no_mirror=self._optional_bool(joint, "noMirror"),
            no_mirror_left=self._optional_bool(joint, "noMirrorLeft"),
            no_flip=no_flip,
            inherited_no_flip=inherited_no_flip,
            local_no_flip=(self._optional_bool(joint, "noFlip")
                           if FitJointField.NO_FLIP in present else None),
            child_of_part=self._optional_number(joint, "childOfPart", int),
            global_weight=self._optional_number(joint, "global", float),
            global_translate=self._optional_bool(joint, "globalTranslate"),
            parent_constraint=self._optional_constraint_target(
                joint, "parentConstraint"),
            point_constraint=self._optional_constraint_target(
                joint, "pointConstraint"),
            orient_constraint=self._optional_constraint_target(
                joint, "orientConstraint"),
            orient_constraint_maintain_offset=self._optional_bool(
                joint, "orientConstraintMaintainOffset"),
            scale_constraint=self._optional_constraint_target(
                joint, "scaleConstraint"),
            follow=self._optional_constraint_target(joint, "follow"),
            follow_left_right=self._optional_bool(joint, "followLeftRight"),
            follow_world=self._optional_bool(joint, "followWorld"),
            follow_by_name=follow_by_name,
            follow_spaces=self._optional_bool(joint, "followSpaces"),
            ik_follow=self._optional_constraint_target(joint, "ikFollow"),
            aim_at=self._optional_constraint_target(joint, "aimAt"),
            aim_axis=self._optional_enum(joint, "aimAxis") or "x",
            aim_up_axis=self._optional_enum(joint, "aimUpAxis") or "y",
            aim_up_object=self._optional_enum(joint, "aimUpObject") or "self",
            geo_attach=self._optional_mesh_target(joint, "geoAttach"),
            proximity_pin=self._optional_mesh_target(joint, "proximityPin"),
            leg_lock=(self._optional_bool(joint, "legLock")
                      if self._attribute_exists(joint, "legLock")
                      else None),
            center_between_feet=(
                self._optional_bool(joint, "centerBetweenFeet")
                if self._attribute_exists(joint, "centerBetweenFeet")
                else None),
            num_main_extras=(
                self._optional_number(joint, "numMainExtras", int)
                if self._attribute_exists(joint, "numMainExtras")
                else None),
            geo_attach_mode=self._optional_enum(
                joint, "geoAttachMode") or "parent",
            world_orient_up=self._optional_enum(joint, "worldOrientUp"),
            world_orient_forward=self._optional_enum(joint, "worldOrientForward"),
            ik_local_mode=self._optional_enum(joint, "ikLocal"),
            present_fields=frozenset(present),
        )

    def apply_fit_joint_edit(self, joint: str, edit: FitJointFieldEdit) -> None:
        self._require_transaction()
        if edit.field is FitJointField.FOLLOW_BY_NAME:
            existing = tuple(
                attr for attr in (self._cmds.listAttr(
                    joint, userDefined=True) or ())
                if attr.startswith("follow") and attr not in (
                    "follow", "followLeftRight", "followWorld",
                    "followSpaces", "followTranslate", "followPivot",
                    "followScale"))
            for attr in existing:
                self._transaction_changed = True
                self._cmds.deleteAttr(joint + "." + attr)
            for name, weight in edit.value or ():
                attr = "follow" + name
                self._transaction_changed = True
                self._cmds.addAttr(
                    joint, longName=attr, attributeType="double",
                    minValue=0, maxValue=10, defaultValue=float(weight),
                    keyable=True)
            return
        spec = _FIT_ATTRIBUTES[edit.field]
        exists = self._attribute_exists(joint, spec.name)
        if (edit.value is None
                or (edit.field is FitJointField.AIM and edit.value is False)
                or (edit.field in (FitJointField.WHEEL,
                                   FitJointField.ROLLING_BALL)
                    and edit.value is False)):
            if exists:
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.{spec.name}")
            if edit.field is FitJointField.FOLLOW:
                for companion in ("followLeftRight", "followWorld"):
                    if self._attribute_exists(joint, companion):
                        self._transaction_changed = True
                        self._cmds.deleteAttr(f"{joint}.{companion}")
            if edit.field is FitJointField.AIM_AT:
                for companion in ("aimAxis", "aimUpAxis", "aimUpObject"):
                    if self._attribute_exists(joint, companion):
                        self._transaction_changed = True
                        self._cmds.deleteAttr(f"{joint}.{companion}")
            if (edit.field is FitJointField.GEO_ATTACH
                    and self._attribute_exists(joint, "geoAttachMode")):
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.geoAttachMode")
            if (edit.field is FitJointField.CURVE_GUIDE
                    and self._attribute_exists(joint, "curveGuideMode")):
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.curveGuideMode")
            if (edit.field is FitJointField.PROXIMITY_PIN
                    and self._attribute_exists(joint, "proximityPinMode")):
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.proximityPinMode")
            if (edit.field is FitJointField.BENDY_CONTROLS
                    and self._attribute_exists(joint, "bendyJoints")):
                self._transaction_changed = True
                self._cmds.deleteAttr(f"{joint}.bendyJoints")
            return

        if not exists:
            options = {
                "longName": spec.name,
                "keyable": True,
            }
            if spec.kind == "string":
                options["dataType"] = "string"
            else:
                options["attributeType"] = spec.kind
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
        if spec.kind == "string":
            plug = f"{joint}.{spec.name}"
            if self._cmds.getAttr(plug, type=True) == "enum":
                names = self._cmds.attributeQuery(
                    spec.name, node=joint, listEnum=True) or []
                choices = names[0].split(":") if names else []
                enum_value = (str(value).replace(":", "__")
                              if edit.field in (FitJointField.GEO_ATTACH,
                                                FitJointField.PROXIMITY_PIN,
                                                FitJointField.CURVE_GUIDE)
                              else value)
                if enum_value not in choices:
                    raise FitJointValidationError(
                        f"原版 {plug} 的可选目标中没有 {value}")
                self._cmds.setAttr(plug, choices.index(enum_value))
            else:
                self._cmds.setAttr(plug, value, type="string")
        else:
            self._cmds.setAttr(f"{joint}.{spec.name}", value)
        if edit.field is FitJointField.AIM_AT:
            for field, default in (
                    (FitJointField.AIM_AXIS, 0),
                    (FitJointField.AIM_UP_AXIS, 1),
                    (FitJointField.AIM_UP_OBJECT, 0)):
                companion = _FIT_ATTRIBUTES[field]
                if not self._attribute_exists(joint, companion.name):
                    self._cmds.addAttr(
                        joint, longName=companion.name,
                        attributeType="enum",
                        enumName=":".join(companion.enum_names),
                        defaultValue=default, keyable=True)
        if (edit.field is FitJointField.GEO_ATTACH
                and not self._attribute_exists(joint, "geoAttachMode")):
            self._cmds.addAttr(
                joint, longName="geoAttachMode", attributeType="enum",
                enumName="point:orient:parent", defaultValue=2,
                keyable=True)
        if (edit.field is FitJointField.CURVE_GUIDE
                and not self._attribute_exists(joint, "curveGuideMode")):
            self._cmds.addAttr(
                joint, longName="curveGuideMode", attributeType="enum",
                enumName="point:aim", defaultValue=1,
                keyable=True)

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
                    if (c.objExists(plug)
                            and (c.getAttr(plug, settable=True)
                                 or c.getAttr(plug, lock=True))
                            and not c.listConnections(
                                plug, source=True, destination=False)):
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

    def _inherited_fit_bool(self, joint: str, attribute: str) -> tuple[bool, bool]:
        inherited = False
        enabled = False
        node = joint
        while node:
            if self._attribute_exists(node, attribute):
                value = bool(self._cmds.getAttr(f"{node}.{attribute}"))
                enabled |= value
                if node != joint:
                    inherited |= value
            parents = self._cmds.listRelatives(
                node, parent=True, fullPath=True) or []
            node = parents[0] if parents else ""
        return inherited, enabled

    def _optional_enum(self, joint: str, attribute: str) -> str | None:
        if not self._attribute_exists(joint, attribute):
            return None
        if attribute == "ikLocal" and self._cmds.getAttr(joint+"."+attribute,type=True)=="bool":
            # The MEL analyser marks an existing legacy bool as enabled and
            # uses its numeric value as the ikLocalType (0 / 1).
            return ("addCtrl","nonZero")[int(bool(self._cmds.getAttr(joint+"."+attribute)))]
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

    def _optional_constraint_target(
        self, joint: str, attribute: str,
    ) -> str | None:
        if not self._attribute_exists(joint, attribute):
            return None
        plug = f"{joint}.{attribute}"
        if self._cmds.getAttr(plug, type=True) == "enum":
            return self._optional_enum(joint, attribute) or None
        if self._cmds.getAttr(plug, type=True) != "string":
            raise FitJointValidationError(
                f"{plug} 需要原版 enum 或 Python 字符串属性")
        return str(self._cmds.getAttr(plug) or "") or None

    def _optional_mesh_target(self, joint: str, attribute: str) -> str | None:
        value = self._optional_constraint_target(joint, attribute)
        if value is None:
            return None
        decoded = value.replace("__", ":")
        return decoded if decoded != value and self._cmds.objExists(decoded) else value

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
        # Maya makeIdentity enables segmentScaleCompensate on the whole
        # descendant joint tree, even for a rotation-only freeze. Retain the
        # source/Body policy (Root and OPM Body explicitly disable it).
        joints=(joint,*(self._cmds.listRelatives(joint,allDescendents=True,
                                                type='joint',fullPath=True) or ()))
        compensation=tuple((node,bool(self._cmds.getAttr(node+'.segmentScaleCompensate')))
                           for node in joints)
        self._cmds.xform(joint, worldSpace=True, matrix=matrix)
        try:
            self._cmds.makeIdentity(
                joint,apply=True,translate=False,rotate=True,scale=False,normal=False)
        finally:
            for node,value in compensation:
                if bool(self._cmds.getAttr(node+'.segmentScaleCompensate'))!=value:
                    self._cmds.setAttr(node+'.segmentScaleCompensate',value)

    def write_fit_deform_profile(self, joint: str,
                                 profile: FitDeformProfile) -> None:
        self._require_transaction()
        if not isinstance(profile, FitDeformProfile):
            raise ValueError("Fit 体积参数无效")
        fat_node = joint.rsplit("|", 1)[-1] + "Fat"
        existing = self._cmds.objExists(fat_node)
        if existing and (self._cmds.nodeType(fat_node) != "multiplyDivide"
                         or any(not self._cmds.attributeQuery(
                             attribute, node=joint, exists=True)
                             for attribute in ("fatFrontAbs", "fatWidthAbs"))):
            raise ValueError("Fit 派生体积节点被其他对象占用：" + fat_node)
        if not existing and any(self._cmds.attributeQuery(
                attribute, node=joint, exists=True)
                for attribute in ("fatFrontAbs", "fatWidthAbs")):
            raise ValueError("Fit 派生体积属性已存在但缺少节点：" + joint)
        self._transaction_changed = True
        for name, value in (("fat", profile.fat),
                            ("fatFront", profile.fat_front),
                            ("fatWidth", profile.fat_width)):
            if not self._cmds.attributeQuery(name, node=joint, exists=True):
                self._cmds.addAttr(joint, longName=name,
                                   attributeType="double", minValue=0,
                                   defaultValue=value, keyable=True)
            else:
                self._cmds.addAttr(joint + "." + name, edit=True,
                                   defaultValue=value)
            self._cmds.setAttr(joint + "." + name, value)
        if not existing:
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
        if not existing:
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
        """Complete old and new Fit volume channels before Body construction."""
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
        if axis not in ("X", "Y", "Z", "-X", "-Y", "-Z"):
            raise ValueError("Fit 主轴无效")
        translate_axis = axis[-1]
        positions = {joint: tuple(float(value) for value in c.xform(
            joint, query=True, worldSpace=True, translation=True))
            for joint in joints}
        scale = fit_build_scale(self.capture_fit_hierarchy(fit[0]))
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
                fat = float(c.getAttr(joint + ".fat"))
            else:
                child = matching_child(joint)
                if child:
                    length = abs(float(c.getAttr(child + ".translate"
                                                 + translate_axis)))
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
            front = (float(c.getAttr(joint + ".fatY"))
                     if c.attributeQuery("fatY", node=joint, exists=True)
                     else float(c.getAttr(joint + ".fatFront"))
                     if c.attributeQuery("fatFront", node=joint, exists=True)
                     else 1.0)
            width = (float(c.getAttr(joint + ".fatZ"))
                     if c.attributeQuery("fatZ", node=joint, exists=True)
                     else float(c.getAttr(joint + ".fatWidth"))
                     if c.attributeQuery("fatWidth", node=joint, exists=True)
                     else 1.0)
            FitDeformProfile(fat, front, width)
            for attribute, value in (("fat", fat), ("fatFront", front),
                                     ("fatWidth", width)):
                if not c.attributeQuery(attribute, node=joint, exists=True):
                    self._transaction_changed = True
                    c.addAttr(joint, longName=attribute,
                              attributeType="double", minValue=0,
                              defaultValue=value, keyable=True)
                elif abs(float(c.getAttr(joint + "." + attribute)) - value) > 1e-8:
                    self._transaction_changed = True
                    c.setAttr(joint + "." + attribute, value)
            for old in ("fatY", "fatZ", "fatYAbs", "fatZAbs", "fatZabs"):
                if c.attributeQuery(old, node=joint, exists=True):
                    self._transaction_changed = True
                    c.deleteAttr(joint + "." + old)
            for attribute in ("fatFrontAbs", "fatWidthAbs"):
                if not c.attributeQuery(attribute, node=joint, exists=True):
                    self._transaction_changed = True
                    c.addAttr(joint, longName=attribute,
                              attributeType="double", keyable=False)
            fat_node = joint.rsplit("|", 1)[-1] + "Fat"
            if c.objExists(fat_node):
                if c.nodeType(fat_node) != "multiplyDivide":
                    raise ValueError("Fit 体积节点名称被其他对象占用：" + fat_node)
            else:
                self._transaction_changed = True
                c.createNode("multiplyDivide", name=fat_node)
            if int(c.getAttr(fat_node + ".operation")) != 1:
                self._transaction_changed = True
                c.setAttr(fat_node + ".operation", 1)
            connections = (
                (joint + ".fat", fat_node + ".input1Y"),
                (joint + ".fat", fat_node + ".input1Z"),
                (joint + ".fatFront", fat_node + ".input2Y"),
                (joint + ".fatWidth", fat_node + ".input2Z"),
                (fat_node + ".outputY", joint + ".fatFrontAbs"),
                (fat_node + ".outputZ", joint + ".fatWidthAbs"),
            )
            for source, destination in connections:
                if c.connectionInfo(destination,
                                    sourceFromDestination=True) != source:
                    self._transaction_changed = True
                    c.connectAttr(source, destination, force=True)

    def _require_transaction(self) -> None:
        if not self._transaction_active:
            raise RuntimeError("Maya Fit 修改必须发生在事务内")


MayaJointLabelHost = MayaFitJointHost
