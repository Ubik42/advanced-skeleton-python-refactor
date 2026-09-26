from __future__ import annotations

from .maya_character_pose import MayaCharacterPoseMixin
from .maya_character_registry import MayaCharacterRegistryMixin
from .maya_torso import MayaBodyTorsoMixin
from .maya_spine import MayaBodySpineMixin
from .maya_control_spaces import MayaBodyControlSpacesMixin

import json
from dataclasses import replace
from pathlib import Path

from adv_py.core.body_arm_mechanisms import (
    BodyArmMechanismJointSpec,
    BodyArmMechanismJointState,
    BodyArmMechanismPlan,
    BodyArmMechanismSnapshot,
)
from adv_py.core.body_arm_ik import (
    BodyArmIkPlan,
    BodyArmIkSnapshot,
    BodyArmIkSpec,
    BodyArmIkState,
)
from adv_py.core.body_arm_blend import (
    BodyArmBlendJointState,
    BodyArmBlendPlan,
    BodyArmBlendSideState,
    BodyArmBlendSnapshot,
)
from adv_py.core.body_leg_blend import (
    BodyLegBlendPlan,
    BodyLegBlendSnapshot,
)
from adv_py.core.body_arm_visibility import (
    BodyArmVisibilityPlan,
    BodyArmVisibilitySideState,
    BodyArmVisibilitySnapshot,
)
from adv_py.core.body_leg_visibility import (
    BodyLegVisibilityInputState,
    BodyLegVisibilityPlan,
    BodyLegVisibilitySideState,
    BodyLegVisibilitySnapshot,
)
from adv_py.core.body_arm_match import (
    BodyArmFkToIkPlan,
    BodyArmFkToIkSceneState,
    BodyArmIkToFkPlan,
    BodyArmIkToFkSceneState,
)
from adv_py.core.body_leg_match import (
    BodyLegFkToIkPlan,
    BodyLegFkToIkSceneState,
    BodyLegIkToFkPlan,
    BodyLegIkToFkSceneState,
    audit_body_leg_fk_to_ik_preflight,
    audit_body_leg_ik_to_fk_preflight,
)
from adv_py.core.body_arm_stretch import (
    BodyArmStretchPlan,
    BodyArmStretchSideState,
    BodyArmStretchSnapshot,
)
from adv_py.core.body_leg_stretch import (
    BodyLegStretchPlan,
    BodyLegStretchSnapshot,
)
from adv_py.core.body_leg_stretch_bias import (
    BodyLegStretchBiasPlan,
    BodyLegStretchBiasSideState,
    BodyLegStretchBiasSnapshot,
)
from adv_py.core.body_leg_knee_pin import (
    BodyLegKneePinPlan,
    BodyLegKneePinSideState,
    BodyLegKneePinSnapshot,
)
from adv_py.core.body_character_global import (
    BodyCharacterDrivenRootState,
    BodyCharacterGlobalPlan,
    BodyCharacterGlobalSnapshot,
)
from adv_py.core.body_root_motion import (
    BodyRootMotionBakePlan,
    BodyRootMotionBakedChannelState,
    BodyRootMotionBakedSnapshot,
    BodyRootMotionKeyState,
    BodyRootMotionPlan,
    BodyRootMotionSample,
    BodyRootMotionSnapshot,
)
from adv_py.core.body_export_skeleton import (
    BODY_EXPORT_BAKE_SCHEMA_VERSION,
    BODY_EXPORT_CHANNEL_ATTRIBUTES,
    BODY_EXPORT_KIND,
    BODY_EXPORT_OWNER,
    BODY_EXPORT_SCHEMA_VERSION,
    BodyExportBakedJointState,
    BodyExportJointSample,
    BodyExportJointState,
    BodyExportSkeletonBakePlan,
    BodyExportSkeletonBakedSnapshot,
    BodyExportSkeletonPlan,
    BodyExportSkeletonSample,
    BodyExportSkeletonSnapshot,
)
from adv_py.core.body_fbx_export import (
    BodyFbxAppliedProfile,
    BodyFbxCurvePolicy,
    BodyFbxExportProfile,
    BodyFbxExportSelection,
    BodyFbxLinearUnit,
    fbx_curve_verification_times,
    redundant_linear_key_frames,
)
from adv_py.core.body_hand_controls import (
    BodyHandFkControlPlan,
    BodyHandFkControlSnapshot,
    BodyHandFkControlSpec,
    BodyHandFkInputSnapshot,
    BodyHandFkJointInputState,
    BodyHandFkRootSpec,
    BodyHandFkRootState,
    BodyHandCurlState,
    BodyHandPoseAttributeState,
    BodyHandPoseLayerState,
    BodyHandPosePlan,
    BodyHandPoseSnapshot,
    BodyHandSpreadState,
)
from adv_py.core.body_hand_pose_io import (
    BODY_HAND_POSE_FK_SEGMENTS,
    BodyHandAggregatePoseChannelState,
    BodyHandFkPoseChannelState,
    BodyHandPoseChangeSet,
    BodyHandPoseChannelSnapshot,
)
from adv_py.core.body_hand_fit import BODY_HAND_DIGITS
from adv_py.core.body_arm_twist import (
    BodyArmTwistJointSpec,
    BodyArmTwistPlan,
    BodyArmTwistSegmentSpec,
    BodyArmTwistSnapshot,
)
from adv_py.core.body_limb_twist import (
    BodyLimbTwistJointSpec,
    BodyLimbTwistJointState,
    BodyLimbTwistPlan,
    BodyLimbTwistSegmentSpec,
    BodyLimbTwistSegmentState,
    BodyLimbTwistSnapshot,
)
from adv_py.core.body_leg_twist import (
    BodyLegTwistJointSpec,
    BodyLegTwistPlan,
    BodyLegTwistSegmentSpec,
    BodyLegTwistSnapshot,
)
from adv_py.core.body_arm_volume import (
    BodyArmVolumePlan,
    BodyArmVolumeSnapshot,
)
from adv_py.core.body_limb_volume import (
    BodyLimbVolumePlan,
    BodyLimbVolumeSideState,
    BodyLimbVolumeSnapshot,
)
from adv_py.core.body_leg_volume import (
    BodyLegVolumePlan,
    BodyLegVolumeSnapshot,
)
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismJointSpec,
    BodyLegMechanismPlan,
    BodyLegMechanismSnapshot,
)
from adv_py.core.body_leg_controls import (
    BodyLegFkControlPlan,
    BodyLegFkControlSnapshot,
    BodyLegFkControlSpec,
)
from adv_py.core.body_leg_ik import (
    BodyLegIkPlan,
    BodyLegIkSnapshot,
    BodyLegIkSpec,
    BodyLegIkState,
)
from adv_py.core.body_leg_foot import (
    BodyLegFootInputState,
    BodyLegFootPlan,
    BodyLegFootPivotRole,
    BodyLegFootPivotState,
    BodyLegFootRollNodeState,
    BodyLegFootRollState,
    BodyLegFootSideSpec,
    BodyLegFootSideState,
    BodyLegFootSnapshot,
)
from adv_py.core.skin_bind import (
    SkinBindInputState,
    SkinBindMethod,
    SkinBindPlan,
    SkinBindSnapshot,
    SkinWeightNormalization,
)
from adv_py.core.skin_weights import (
    SKIN_WEIGHT_VISIBLE_THRESHOLD,
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightChange,
    SkinWeightEditRequest,
    SkinWeightInputState,
)
from adv_py.core.skin_weight_geometry import (
    SkinMeshGeometryState,
    SkinMeshVertexPosition,
)
from adv_py.core.body_controls import (
    BodyArmFkControlPlan,
    BodyArmFkControlSnapshot,
    BodyArmFkControlSpec,
    BodyArmFkControlState,
)
from adv_py.core.body_rebuild import (
    BodyExternalDependency,
    BodyExternalDependencyKind,
    BodyRebuildSceneState,
)
from adv_py.core.body_skeleton import (
    BodyJointOrientationChange,
    BodyJointSpec,
    BodyJointState,
    BodySkeletonProvenance,
    BodySkeletonProvenanceState,
    BodySkeletonSnapshot,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .maya_fit import MayaFitJointHost
from .maya_control_curves import MayaControlCurveMixin


_MAYA_SIDE_FROM_CORE = {
    FitBuildSide.MIDDLE: 0,
    FitBuildSide.LEFT: 1,
    FitBuildSide.RIGHT: 2,
}
_CORE_SIDE_FROM_MAYA = {value: key for key, value in _MAYA_SIDE_FROM_CORE.items()}
_BODY_PROVENANCE_ATTRIBUTES = {
    "owner": "advPyOwner",
    "artifact_kind": "advPyArtifactKind",
    "schema_version": "advPySchemaVersion",
    "source_container": "advPySourceContainer",
    "body_joint_count": "advPyBodyJointCount",
}

_BODY_EXPORT_SOURCE_ATTRIBUTE = "advPyExportSource"
_BODY_EXPORT_PROVENANCE_ATTRIBUTES = {
    "owner": "advPyOwner",
    "artifact_kind": "advPyArtifactKind",
    "schema_version": "advPySchemaVersion",
    "source_body_root": "advPySourceBodyRoot",
    "joint_count": "advPyExportJointCount",
}
_BODY_EXPORT_BAKE_ATTRIBUTES = {
    "bake_schema_version": "advPyBakeSchemaVersion",
    "start_frame": "advPyBakeStartFrame",
    "end_frame": "advPyBakeEndFrame",
    "sample_by": "advPyBakeSampleBy",
}


class MayaBodyBuildHost(MayaControlCurveMixin, MayaCharacterPoseMixin, MayaCharacterRegistryMixin, MayaBodyControlSpacesMixin, MayaBodySpineMixin, MayaBodyTorsoMixin, MayaFitJointHost):
    """Maya scene adapter for the first materialized Body skeleton stage."""

    def create_body_joint(self, spec: BodyJointSpec) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(
                f"同名节点已存在，拒绝创建构建关节：{spec.name}"
            )
        parent = None
        if spec.parent_path is not None:
            matches = self._cmds.ls(spec.parent_path, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError(
                    f"构建关节父级在执行前失效：{spec.parent_path}"
                )
            parent = matches[0]
        options = {
            "name": spec.name,
            "skipSelect": True,
        }
        if parent is not None:
            options["parent"] = parent
        joint = self._cmds.createNode("joint", **options)
        self._transaction_changed = True
        path = (self._cmds.ls(joint, long=True) or [joint])[0]
        self._cmds.xform(
            path,
            worldSpace=True,
            translation=spec.world_position,
        )
        self.set_joint_label(path, spec.label)
        self._cmds.setAttr(f"{path}.side", _MAYA_SIDE_FROM_CORE[spec.side])
        return path

    def scene_linear_unit(self) -> BodyFbxLinearUnit:
        value = str(self._cmds.currentUnit(query=True, linear=True))
        try:
            return BodyFbxLinearUnit(value)
        except ValueError as error:
            raise FitSkeletonValidationError(
                "FBX Profile 当前只支持 Maya centimeter 或 meter 场景单位"
            ) from error

    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"Body skeleton 根关节无效：{root_name}"
            )
        root = roots[0]
        paths = self._cmds.listRelatives(
            root,
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        paths.append(root)
        paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        paths = [path for path in paths if not (
            self._cmds.attributeQuery("advPyAuxiliaryInfluenceKind",
                                      node=path, exists=True)
            and self._cmds.getAttr(path + ".advPyAuxiliaryInfluenceKind")
                == "axial-part-v1")]
        states: list[BodyJointState] = []
        for path in paths:
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            position = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )
            side_code = int(self._cmds.getAttr(f"{path}.side"))
            try:
                side = _CORE_SIDE_FROM_MAYA[side_code]
            except KeyError as error:
                raise FitSkeletonValidationError(
                    f"构建关节侧向值无效：{path}.side={side_code}"
                ) from error
            joint_orient = self._cmds.getAttr(f"{path}.jointOrient")[0]
            rotation = self._cmds.getAttr(f"{path}.rotate")[0]
            matrix = self._cmds.xform(
                path,
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
                    f"{path}.jointOrient{axis.upper()}",
                    settable=True,
                )
            )
            states.append(
                BodyJointState(
                    path=path,
                    name=path.rsplit("|", 1)[-1].rsplit(":", 1)[-1],
                    parent_path=parents[0] if parents else None,
                    side=side,
                    world_position=tuple(float(value) for value in position),
                    label=self.read_joint_label(path),
                    joint_orient=tuple(float(value) for value in joint_orient),
                    rotation=tuple(float(value) for value in rotation),
                    world_axes=world_axes,
                    writable_joint_orient_axes=writable_axes,
                    world_scale=tuple(sum(float(v)*float(v) for v in matrix[i:i+3])**0.5 for i in (0,4,8)),
                )
            )
        return BodySkeletonSnapshot(
            root,
            tuple(states),
            self._capture_body_provenance(root),
        )

    def write_body_provenance(
        self,
        root: str,
        provenance: BodySkeletonProvenance,
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(root, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != root:
            raise FitSkeletonValidationError(
                f"Body provenance 根关节在执行前失效：{root}"
            )
        if any(
            self._cmds.attributeQuery(attribute, node=root, exists=True)
            for attribute in _BODY_PROVENANCE_ATTRIBUTES.values()
        ):
            raise FitSkeletonValidationError(
                "Body provenance 属性已存在，拒绝覆盖"
            )
        self._transaction_changed = True
        for field in ("owner", "artifact_kind", "source_container"):
            attribute = _BODY_PROVENANCE_ATTRIBUTES[field]
            self._cmds.addAttr(root, longName=attribute, dataType="string")
            self._cmds.setAttr(
                f"{root}.{attribute}",
                getattr(provenance, field),
                type="string",
            )
        for field in ("schema_version", "body_joint_count"):
            attribute = _BODY_PROVENANCE_ATTRIBUTES[field]
            self._cmds.addAttr(root, longName=attribute, attributeType="long")
            self._cmds.setAttr(
                f"{root}.{attribute}",
                getattr(provenance, field),
            )
        for attribute in _BODY_PROVENANCE_ATTRIBUTES.values():
            self._cmds.setAttr(f"{root}.{attribute}", lock=True)

    def capture_body_rebuild_state(
        self,
        root_name: str,
    ) -> BodyRebuildSceneState:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"Body ReBuild 根关节无效：{root_name}"
            )
        root = roots[0]
        descendants = self._cmds.listRelatives(
            root,
            allDescendents=True,
            fullPath=True,
        ) or []
        dag_paths = tuple(
            sorted(set(descendants + [root]), key=lambda path: (path.count("|"), path))
        )
        body_joints = set(
            self._cmds.listRelatives(
                root,
                allDescendents=True,
                type="joint",
                fullPath=True,
            )
            or []
        )
        body_joints.add(root)
        dependencies: set[BodyExternalDependency] = set()
        for joint in sorted(body_joints):
            pairs = self._cmds.listConnections(
                joint,
                source=True,
                destination=True,
                connections=True,
                plugs=True,
            ) or []
            for index in range(0, len(pairs) - 1, 2):
                first, second = pairs[index], pairs[index + 1]
                first_node = self._resolve_connected_node(first)
                second_node = self._resolve_connected_node(second)
                if first_node in body_joints:
                    body_plug, external_plug = first, second
                    external_node = second_node
                elif second_node in body_joints:
                    body_plug, external_plug = second, first
                    external_node = first_node
                else:
                    continue
                if external_node in body_joints:
                    continue
                dependencies.add(
                    BodyExternalDependency(
                        self._dependency_kind(external_node),
                        body_plug,
                        external_plug,
                    )
                )
        return BodyRebuildSceneState(
            root,
            dag_paths,
            tuple(
                sorted(
                    dependencies,
                    key=lambda item: (
                        item.kind.value,
                        item.body_plug,
                        item.external_plug,
                    ),
                )
            ),
        )

    def delete_owned_body(self, root: str) -> None:
        self._require_transaction()
        matches = self._cmds.ls(root, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != root:
            raise FitSkeletonValidationError(
                f"待替换 Body 根关节在执行前失效：{root}"
            )
        self._transaction_changed = True
        self._cmds.delete(matches[0])

    def create_body_control_root(self, name: str) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Body 控制根名称冲突：{name}")
        self._transaction_changed = True
        created = self._cmds.createNode(
            "transform",
            name=name,
            skipSelect=True,
        )
        return (self._cmds.ls(created, long=True) or [created])[0]

    def create_body_character_global(
        self,
        plan: BodyCharacterGlobalPlan,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []

        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            return values[0] if len(values) == 1 else None

        def values_close(left, right, tolerance=1e-4) -> bool:
            return len(left) == len(right) and all(
                abs(a - b) <= tolerance for a, b in zip(left, right)
            )

        try:
            if any(
                self.find_name_collisions(name)
                for name in plan.node_names
            ):
                raise FitSkeletonValidationError(
                    "角色总控名称在执行前发生冲突"
                )
            for path in plan.driven_roots:
                matches = self._cmds.ls(path, long=True) or []
                parent = self._cmds.listRelatives(
                    path,
                    parent=True,
                    fullPath=True,
                ) or []
                channels = tuple(
                    f"{path}.{kind}{axis}"
                    for kind in ("translate", "rotate", "scale")
                    for axis in "XYZ"
                )
                values = tuple(
                    float(self._cmds.getAttr(plug))
                    for plug in channels
                ) if len(matches) == 1 else ()
                if (
                    len(matches) != 1
                    or matches[0] != path
                    or self._cmds.nodeType(path) not in ("transform", "joint")
                    or parent
                    or any(source(plug) is not None for plug in channels)
                    or any(
                        not bool(self._cmds.getAttr(plug, settable=True))
                        for plug in channels
                    )
                    or not values_close(
                        values,
                        (0.0,) * 6 + (1.0,) * 3,
                    )
                ):
                    raise FitSkeletonValidationError(
                        f"角色总控根节点不可安全接线：{path}"
                    )
            for plug in plan.scale_destinations:
                if (
                    not self._cmds.objExists(plug)
                    or source(plug) is not None
                    or not bool(self._cmds.getAttr(plug, settable=True))
                    or abs(float(self._cmds.getAttr(plug)) - 1.0) > 1e-4
                ):
                    raise FitSkeletonValidationError(
                        f"角色总控比例补偿输入不可安全接线：{plug}"
                    )

            self._transaction_changed = True
            root = self._cmds.createNode(
                "transform",
                name=plan.root_name,
                skipSelect=True,
            )
            offset = self._cmds.createNode(
                "transform",
                name=plan.offset_name,
                parent=root,
                skipSelect=True,
            )
            control = self._cmds.circle(
                name=plan.control_name,
                normal=plan.circle_normal,
                radius=plan.radius,
                constructionHistory=False,
            )[0]
            control = self._cmds.parent(control, offset)[0]
            root = (self._cmds.ls(root, long=True) or [root])[0]
            offset = (self._cmds.ls(offset, long=True) or [offset])[0]
            control = (self._cmds.ls(control, long=True) or [control])[0]
            shapes = self._cmds.listRelatives(
                control,
                shapes=True,
                fullPath=True,
            ) or []
            if len(shapes) != 1:
                raise RuntimeError("角色总控曲线 shape 创建失败")
            shape = self._cmds.rename(shapes[0], plan.shape_name)
            if (
                root != plan.root_path
                or offset != plan.offset_path
                or control != plan.control_path
                or shape.rsplit("|", 1)[-1] != plan.shape_name
            ):
                raise RuntimeError("角色总控层级路径漂移")

            self._cmds.addAttr(
                control,
                longName=plan.scale_attribute,
                attributeType="double",
                minValue=plan.scale_minimum,
                defaultValue=plan.scale_default,
                keyable=True,
            )
            for axis in "XYZ":
                self._cmds.connectAttr(
                    plan.scale_source,
                    f"{control}.scale{axis}",
                )
                self._cmds.setAttr(
                    f"{control}.scale{axis}",
                    keyable=False,
                    channelBox=False,
                )
            for path in plan.driven_roots:
                for axis in "XYZ":
                    self._cmds.connectAttr(
                        f"{control}.translate{axis}",
                        f"{path}.translate{axis}",
                    )
                    self._cmds.connectAttr(
                        f"{control}.rotate{axis}",
                        f"{path}.rotate{axis}",
                    )
                    self._cmds.connectAttr(
                        plan.scale_source,
                        f"{path}.scale{axis}",
                    )
            for plug in plan.scale_destinations:
                self._cmds.connectAttr(plan.scale_source, plug)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_character_global(
        self,
        plan: BodyCharacterGlobalPlan,
    ) -> BodyCharacterGlobalSnapshot:
        def one_path(path: str, node_type: str) -> str:
            values = self._cmds.ls(path, long=True, type=node_type) or []
            if len(values) != 1 or values[0] != path:
                raise FitSkeletonValidationError(
                    f"角色总控节点无效：{path}"
                )
            return values[0]

        def parent(path: str) -> str | None:
            values = self._cmds.listRelatives(
                path,
                parent=True,
                fullPath=True,
            ) or []
            return values[0] if len(values) == 1 else None

        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        def vector(path: str, kind: str) -> tuple[float, float, float]:
            return tuple(
                float(self._cmds.getAttr(f"{path}.{kind}{axis}"))
                for axis in "XYZ"
            )

        root = one_path(plan.root_path, "transform")
        offset = one_path(plan.offset_path, "transform")
        control = one_path(plan.control_path, "transform")
        shapes = self._cmds.listRelatives(
            control,
            shapes=True,
            fullPath=True,
        ) or []
        shape_type = None
        if (
            len(shapes) == 1
            and shapes[0].rsplit("|", 1)[-1] == plan.shape_name
        ):
            shape_type = self._cmds.nodeType(shapes[0])
        scale_plug = plan.scale_source
        if not self._cmds.objExists(scale_plug):
            raise FitSkeletonValidationError("角色总控 uniform scale 属性缺失")
        minimum = self._cmds.attributeQuery(
            plan.scale_attribute,
            node=control,
            minimum=True,
        ) or []
        driven = []
        for path in plan.driven_roots:
            values = self._cmds.ls(path, long=True) or []
            if len(values) != 1 or values[0] != path:
                raise FitSkeletonValidationError(
                    f"角色总控被驱动根节点无效：{path}"
                )
            driven.append(BodyCharacterDrivenRootState(
                path=path,
                parent_path=parent(path),
                translation_sources=tuple(
                    source(f"{path}.translate{axis}") for axis in "XYZ"
                ),
                rotation_sources=tuple(
                    source(f"{path}.rotate{axis}") for axis in "XYZ"
                ),
                scale_sources=tuple(
                    source(f"{path}.scale{axis}") for axis in "XYZ"
                ),
            ))
        return BodyCharacterGlobalSnapshot(
            root_path=root,
            root_parent_path=parent(root),
            root_translation=vector(root, "translate"),
            root_rotation=vector(root, "rotate"),
            root_scale=vector(root, "scale"),
            offset_path=offset,
            offset_parent_path=parent(offset),
            offset_translation=vector(offset, "translate"),
            offset_rotation=vector(offset, "rotate"),
            offset_scale=vector(offset, "scale"),
            control_path=control,
            control_parent_path=parent(control),
            control_shape_type=shape_type,
            control_translation=vector(control, "translate"),
            control_rotation=vector(control, "rotate"),
            control_scale=vector(control, "scale"),
            scale_attribute_plug=scale_plug,
            scale_attribute_value=float(self._cmds.getAttr(scale_plug)),
            scale_attribute_minimum=(
                float(minimum[0]) if len(minimum) == 1 else None
            ),
            control_scale_sources=tuple(
                source(f"{control}.scale{axis}") for axis in "XYZ"
            ),
            driven_roots=tuple(driven),
            scale_destination_sources=tuple(
                (plug, source(plug))
                for plug in plan.scale_destinations
            ),
        )

    def create_body_root_motion(self, plan: BodyRootMotionPlan) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if any(self.find_name_collisions(name) for name in plan.node_names):
                raise FitSkeletonValidationError(
                    "Root Motion 名称在执行前发生冲突"
                )
            sources = self._cmds.ls(
                plan.source_root_path,
                long=True,
                type="joint",
            ) or []
            if len(sources) != 1 or sources[0] != plan.source_root_path:
                raise FitSkeletonValidationError(
                    "Root Motion 来源 Body root 在执行前失效"
                )

            self._transaction_changed = True
            output = self._cmds.createNode(
                "joint",
                name=plan.output_name,
                skipSelect=True,
            )
            output = (self._cmds.ls(output, long=True) or [output])[0]
            if output != plan.output_path:
                raise RuntimeError("Root Motion 输出路径漂移")
            self._cmds.pointConstraint(
                plan.source_root_path,
                output,
                maintainOffset=False,
                skip=plan.skipped_translation_axis,
                name=plan.point_constraint_name,
            )
            self._cmds.orientConstraint(
                plan.source_root_path,
                output,
                maintainOffset=False,
                skip=plan.skipped_rotation_axes,
                name=plan.orient_constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_root_motion(
        self,
        plan: BodyRootMotionPlan,
    ) -> BodyRootMotionSnapshot:
        outputs = self._cmds.ls(plan.output_path, long=True, type="joint") or []
        if len(outputs) != 1 or outputs[0] != plan.output_path:
            raise FitSkeletonValidationError("Root Motion 输出 joint 无效")
        output = outputs[0]
        parents = self._cmds.listRelatives(
            output,
            parent=True,
            fullPath=True,
        ) or []

        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            return values[0] if len(values) == 1 else None

        def vector(attribute: str) -> tuple[float, float, float]:
            return tuple(
                float(self._cmds.getAttr(f"{output}.{attribute}{axis}"))
                for axis in "XYZ"
            )

        def targets(name: str, command) -> tuple[str, ...]:
            constraints = self._cmds.ls(name) or []
            if len(constraints) != 1:
                return ()
            values = command(
                constraints[0],
                query=True,
                targetList=True,
            ) or []
            resolved = []
            for value in values:
                paths = self._cmds.ls(value, long=True) or []
                if len(paths) != 1:
                    return ()
                resolved.append(paths[0])
            return tuple(resolved)

        return BodyRootMotionSnapshot(
            output_path=output,
            output_parent_path=parents[0] if len(parents) == 1 else None,
            output_type=self._cmds.nodeType(output),
            translation=vector("translate"),
            rotation=vector("rotate"),
            scale=vector("scale"),
            joint_orient=tuple(
                float(value)
                for value in self._cmds.getAttr(f"{output}.jointOrient")[0]
            ),
            translation_sources=tuple(
                source(f"{output}.translate{axis}") for axis in "XYZ"
            ),
            rotation_sources=tuple(
                source(f"{output}.rotate{axis}") for axis in "XYZ"
            ),
            point_targets=targets(
                plan.point_constraint_name,
                self._cmds.pointConstraint,
            ),
            orient_targets=targets(
                plan.orient_constraint_name,
                self._cmds.orientConstraint,
            ),
        )

    def sample_body_root_motion(
        self,
        plan: BodyRootMotionBakePlan,
    ) -> tuple[BodyRootMotionSample, ...]:
        output = plan.root_motion.output_path
        if not self._cmds.objExists(output):
            raise FitSkeletonValidationError("Root Motion bake 输出 joint 缺失")
        original_time = float(self._cmds.currentTime(query=True))
        samples = []
        try:
            for frame in plan.frames:
                self._cmds.currentTime(frame, edit=True, update=True)
                translation = self._cmds.getAttr(f"{output}.translate")[0]
                rotation = self._cmds.getAttr(f"{output}.rotate")[0]
                samples.append(BodyRootMotionSample(
                    frame=frame,
                    translation=tuple(float(value) for value in translation),
                    rotation=tuple(float(value) for value in rotation),
                ))
        finally:
            self._cmds.currentTime(original_time, edit=True, update=True)
        return tuple(samples)

    def bake_body_root_motion(
        self,
        plan: BodyRootMotionBakePlan,
        samples: tuple[BodyRootMotionSample, ...],
    ) -> None:
        self._require_transaction()
        output = plan.root_motion.output_path
        point = self._cmds.ls(
            plan.root_motion.point_constraint_name,
            type="pointConstraint",
        ) or []
        orient = self._cmds.ls(
            plan.root_motion.orient_constraint_name,
            type="orientConstraint",
        ) or []
        if (
            len(point) != 1
            or len(orient) != 1
            or not self._cmds.objExists(output)
            or tuple(sample.frame for sample in samples) != plan.frames
        ):
            raise FitSkeletonValidationError(
                "Root Motion bake 输入在执行前失效"
            )

        translate_indices = {
            f"translate{axis.upper()}": "xyz".index(axis)
            for axis in plan.root_motion.translation_axes
        }
        rotate_attribute = f"rotate{plan.root_motion.rotation_axis.upper()}"
        self._transaction_changed = True
        self._cmds.delete(point + orient)
        for sample in samples:
            for attribute, index in translate_indices.items():
                self._cmds.setKeyframe(
                    output,
                    attribute=attribute,
                    time=sample.frame,
                    value=sample.translation[index],
                )
            self._cmds.setKeyframe(
                output,
                attribute=rotate_attribute,
                time=sample.frame,
                value=sample.rotation[
                    "xyz".index(plan.root_motion.rotation_axis)
                ],
            )
        for attribute in plan.channel_attributes:
            self._cmds.keyTangent(
                output,
                attribute=attribute,
                time=(plan.start_frame, plan.end_frame),
                inTangentType="linear",
                outTangentType="linear",
            )

    def capture_baked_body_root_motion(
        self,
        plan: BodyRootMotionBakePlan,
    ) -> BodyRootMotionBakedSnapshot:
        output = plan.root_motion.output_path
        outputs = self._cmds.ls(output, long=True, type="joint") or []
        if len(outputs) != 1 or outputs[0] != output:
            raise FitSkeletonValidationError("Root Motion bake 输出 joint 无效")
        channels = []
        for attribute in plan.channel_attributes:
            plug = f"{output}.{attribute}"
            sources = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
            ) or []
            source_kind = None
            if len(sources) == 1:
                node_type = self._cmds.nodeType(sources[0])
                source_kind = (
                    "animation_curve"
                    if node_type.startswith("animCurve")
                    else node_type
                )
            times = self._cmds.keyframe(
                plug,
                query=True,
                time=(plan.start_frame, plan.end_frame),
                timeChange=True,
            ) or []
            values = self._cmds.keyframe(
                plug,
                query=True,
                time=(plan.start_frame, plan.end_frame),
                valueChange=True,
            ) or []
            keys = []
            for time, value in zip(times, values):
                incoming = self._cmds.keyTangent(
                    plug,
                    query=True,
                    time=(time, time),
                    inTangentType=True,
                ) or []
                outgoing = self._cmds.keyTangent(
                    plug,
                    query=True,
                    time=(time, time),
                    outTangentType=True,
                ) or []
                keys.append(BodyRootMotionKeyState(
                    frame=int(round(float(time))),
                    value=float(value),
                    in_tangent=incoming[0] if len(incoming) == 1 else "",
                    out_tangent=outgoing[0] if len(outgoing) == 1 else "",
                ))
            channels.append(BodyRootMotionBakedChannelState(
                attribute=attribute,
                source_kind=source_kind,
                keys=tuple(keys),
            ))
        return BodyRootMotionBakedSnapshot(
            output_path=output,
            point_constraint_exists=bool(
                self._cmds.ls(
                    plan.root_motion.point_constraint_name,
                    type="pointConstraint",
                ) or []
            ),
            orient_constraint_exists=bool(
                self._cmds.ls(
                    plan.root_motion.orient_constraint_name,
                    type="orientConstraint",
                ) or []
            ),
            channels=tuple(channels),
        )

    def create_body_export_skeleton(
        self,
        plan: BodyExportSkeletonPlan,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if any(self.find_name_collisions(name) for name in plan.node_names):
                raise FitSkeletonValidationError(
                    "Export Skeleton 名称在执行前发生冲突"
                )
            root_motion = self._cmds.ls(
                plan.root_motion_path,
                long=True,
                type="joint",
            ) or []
            if len(root_motion) != 1 or root_motion[0] != plan.root_motion_path:
                raise FitSkeletonValidationError(
                    "Export Skeleton 的 Root Motion 父级失效"
                )

            self._transaction_changed = True
            for spec in plan.joints:
                sources = self._cmds.ls(
                    spec.source_path,
                    long=True,
                    type="joint",
                ) or []
                parents = self._cmds.ls(
                    spec.output_parent_path,
                    long=True,
                    type="joint",
                ) or []
                if (
                    len(sources) != 1
                    or sources[0] != spec.source_path
                    or len(parents) != 1
                    or parents[0] != spec.output_parent_path
                ):
                    raise FitSkeletonValidationError(
                        f"Export Skeleton joint 输入失效：{spec.source_path}"
                    )
                output = self._cmds.createNode(
                    "joint",
                    name=spec.output_name,
                    parent=spec.output_parent_path,
                    skipSelect=True,
                )
                output = (self._cmds.ls(output, long=True) or [output])[0]
                if output != spec.output_path:
                    raise RuntimeError(
                        f"Export Skeleton joint 路径漂移：{spec.output_name}"
                    )
                self._cmds.setAttr(
                    f"{output}.jointOrient",
                    *spec.joint_orient,
                    type="double3",
                )
                self._cmds.setAttr(
                    f"{output}.rotateOrder",
                    int(self._cmds.getAttr(f"{spec.source_path}.rotateOrder")),
                )
                self._cmds.setAttr(
                    f"{output}.segmentScaleCompensate",
                    bool(self._cmds.getAttr(
                        f"{spec.source_path}.segmentScaleCompensate"
                    )),
                )
                if spec.label is None:
                    self.clear_joint_label(output)
                else:
                    self.set_joint_label(output, spec.label)
                self._cmds.setAttr(
                    f"{output}.side",
                    _MAYA_SIDE_FROM_CORE[spec.side],
                )
                self._cmds.addAttr(
                    output,
                    longName=_BODY_EXPORT_SOURCE_ATTRIBUTE,
                    attributeType="message",
                )
                self._cmds.connectAttr(
                    f"{spec.source_path}.message",
                    f"{output}.{_BODY_EXPORT_SOURCE_ATTRIBUTE}",
                )
                for axis in "XYZ":
                    self._cmds.connectAttr(
                        f"{spec.source_path}.scale{axis}",
                        f"{output}.scale{axis}",
                    )
                if spec.is_root:
                    self._cmds.parentConstraint(
                        spec.source_path,
                        output,
                        maintainOffset=False,
                        name=spec.root_constraint_name,
                    )
                else:
                    for kind in ("translate", "rotate"):
                        for axis in "XYZ":
                            self._cmds.connectAttr(
                                f"{spec.source_path}.{kind}{axis}",
                                f"{output}.{kind}{axis}",
                            )

            root = plan.root.output_path
            values = {
                "owner": BODY_EXPORT_OWNER,
                "artifact_kind": BODY_EXPORT_KIND,
                "schema_version": BODY_EXPORT_SCHEMA_VERSION,
                "source_body_root": plan.source_body_root,
                "joint_count": len(plan.joints),
            }
            for field in ("owner", "artifact_kind", "source_body_root"):
                attribute = _BODY_EXPORT_PROVENANCE_ATTRIBUTES[field]
                self._cmds.addAttr(root, longName=attribute, dataType="string")
                self._cmds.setAttr(
                    f"{root}.{attribute}",
                    values[field],
                    type="string",
                )
            for field in ("schema_version", "joint_count"):
                attribute = _BODY_EXPORT_PROVENANCE_ATTRIBUTES[field]
                self._cmds.addAttr(
                    root,
                    longName=attribute,
                    attributeType="long",
                )
                self._cmds.setAttr(f"{root}.{attribute}", values[field])
            for attribute in _BODY_EXPORT_PROVENANCE_ATTRIBUTES.values():
                self._cmds.setAttr(f"{root}.{attribute}", lock=True)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_export_skeleton(
        self,
        plan: BodyExportSkeletonPlan,
    ) -> BodyExportSkeletonSnapshot:
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        states = []
        for spec in plan.joints:
            outputs = self._cmds.ls(
                spec.output_path,
                long=True,
                type="joint",
            ) or []
            if len(outputs) != 1 or outputs[0] != spec.output_path:
                raise FitSkeletonValidationError(
                    f"Export Skeleton joint 无效：{spec.output_path}"
                )
            output = outputs[0]
            parents = self._cmds.listRelatives(
                output,
                parent=True,
                fullPath=True,
            ) or []
            source_nodes = self._cmds.listConnections(
                f"{output}.{_BODY_EXPORT_SOURCE_ATTRIBUTE}",
                source=True,
                destination=False,
            ) or []
            source_path = None
            if len(source_nodes) == 1:
                source_paths = self._cmds.ls(source_nodes[0], long=True) or []
                if len(source_paths) == 1:
                    source_path = source_paths[0]
            position = self._cmds.xform(
                output,
                query=True,
                worldSpace=True,
                translation=True,
            )
            matrix = self._cmds.xform(
                output,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            side_code = int(self._cmds.getAttr(f"{output}.side"))
            states.append(BodyExportJointState(
                source_path=source_path,
                output_name=output.rsplit("|", 1)[-1],
                output_path=output,
                output_parent_path=parents[0] if len(parents) == 1 else None,
                side=_CORE_SIDE_FROM_MAYA[side_code],
                label=self.read_joint_label(output),
                joint_orient=tuple(
                    float(value)
                    for value in self._cmds.getAttr(
                        f"{output}.jointOrient"
                    )[0]
                ),
                world_position=tuple(float(value) for value in position),
                world_axes=tuple(
                    self._normalized_vector(
                        tuple(float(value) for value in matrix[index:index + 3])
                    )
                    for index in (0, 4, 8)
                ),
                translation_sources=tuple(
                    source(f"{output}.translate{axis}") for axis in "XYZ"
                ),
                rotation_sources=tuple(
                    source(f"{output}.rotate{axis}") for axis in "XYZ"
                ),
                scale_sources=tuple(
                    source(f"{output}.scale{axis}") for axis in "XYZ"
                ),
            ))

        root = plan.root.output_path
        def provenance(field: str):
            attribute = _BODY_EXPORT_PROVENANCE_ATTRIBUTES[field]
            plug = f"{root}.{attribute}"
            return self._cmds.getAttr(plug) if self._cmds.objExists(plug) else None

        return BodyExportSkeletonSnapshot(
            root_path=root,
            joints=tuple(states),
            owner=provenance("owner"),
            artifact_kind=provenance("artifact_kind"),
            schema_version=provenance("schema_version"),
            source_body_root=provenance("source_body_root"),
            joint_count=provenance("joint_count"),
        )

    def sample_body_export_skeleton(
        self,
        plan: BodyExportSkeletonBakePlan,
    ) -> tuple[BodyExportSkeletonSample, ...]:
        original_time = float(self._cmds.currentTime(query=True))

        def vector(path: str, kind: str) -> tuple[float, float, float]:
            return tuple(
                float(self._cmds.getAttr(f"{path}.{kind}{axis}"))
                for axis in "XYZ"
            )

        samples = []
        try:
            for frame in plan.frames:
                self._cmds.currentTime(frame, edit=True, update=True)
                root_motion = BodyRootMotionSample(
                    frame=frame,
                    translation=vector(
                        plan.root_motion.root_motion.output_path,
                        "translate",
                    ),
                    rotation=vector(
                        plan.root_motion.root_motion.output_path,
                        "rotate",
                    ),
                )
                joints = tuple(
                    BodyExportJointSample(
                        output_path=spec.output_path,
                        translation=vector(spec.output_path, "translate"),
                        rotation=vector(spec.output_path, "rotate"),
                        scale=vector(spec.output_path, "scale"),
                    )
                    for spec in plan.export_skeleton.joints
                )
                samples.append(BodyExportSkeletonSample(
                    frame=frame,
                    root_motion=root_motion,
                    joints=joints,
                ))
        finally:
            self._cmds.currentTime(original_time, edit=True, update=True)
        return tuple(samples)

    def bake_body_export_skeleton(
        self,
        plan: BodyExportSkeletonBakePlan,
        samples: tuple[BodyExportSkeletonSample, ...],
    ) -> None:
        self._require_transaction()
        if tuple(sample.frame for sample in samples) != plan.frames:
            raise FitSkeletonValidationError(
                "Export Skeleton bake 样本帧在执行前失效"
            )
        export_root = plan.export_skeleton.root.output_path
        if any(
            self._cmds.attributeQuery(attribute, node=export_root, exists=True)
            for attribute in _BODY_EXPORT_BAKE_ATTRIBUTES.values()
        ):
            raise FitSkeletonValidationError(
                "Export Skeleton bake 标记已存在，拒绝覆盖"
            )
        constraint_names = (
            plan.root_motion.root_motion.point_constraint_name,
            plan.root_motion.root_motion.orient_constraint_name,
            plan.export_skeleton.root.root_constraint_name,
        )
        constraints = []
        for name in constraint_names:
            values = self._cmds.ls(name) or []
            if len(values) != 1:
                raise FitSkeletonValidationError(
                    f"Export Skeleton bake 约束输入失效：{name}"
                )
            constraints.append(values[0])
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            self._cmds.delete(constraints)
            for spec in plan.export_skeleton.joints:
                output = spec.output_path
                for attribute in BODY_EXPORT_CHANNEL_ATTRIBUTES:
                    destination = f"{output}.{attribute}"
                    sources = self._cmds.listConnections(
                        destination,
                        source=True,
                        destination=False,
                        plugs=True,
                    ) or []
                    if len(sources) > 1:
                        raise RuntimeError(
                            f"Export Skeleton bake 通道来源不唯一：{destination}"
                        )
                    if sources:
                        self._cmds.disconnectAttr(sources[0], destination)
                source_attribute = f"{output}.{_BODY_EXPORT_SOURCE_ATTRIBUTE}"
                if not self._cmds.objExists(source_attribute):
                    raise RuntimeError(
                        f"Export Skeleton bake source message 缺失：{output}"
                    )
                self._cmds.deleteAttr(source_attribute)

            root_motion_output = plan.root_motion.root_motion.output_path
            root_translate_indices = {
                f"translate{axis.upper()}": "xyz".index(axis)
                for axis in plan.root_motion.root_motion.translation_axes
            }
            root_rotate_attribute = (
                f"rotate{plan.root_motion.root_motion.rotation_axis.upper()}"
            )
            joint_samples = {
                spec.output_path: tuple(
                    next(
                        joint
                        for joint in sample.joints
                        if joint.output_path == spec.output_path
                    )
                    for sample in samples
                )
                for spec in plan.export_skeleton.joints
            }
            for sample in samples:
                for attribute, index in root_translate_indices.items():
                    self._cmds.setKeyframe(
                        root_motion_output,
                        attribute=attribute,
                        time=sample.frame,
                        value=sample.root_motion.translation[index],
                    )
                self._cmds.setKeyframe(
                    root_motion_output,
                    attribute=root_rotate_attribute,
                    time=sample.frame,
                    value=sample.root_motion.rotation[
                        "xyz".index(
                            plan.root_motion.root_motion.rotation_axis
                        )
                    ],
                )
            for spec in plan.export_skeleton.joints:
                for sample, joint in zip(samples, joint_samples[spec.output_path]):
                    values = {
                        **{
                            f"translate{axis}": joint.translation[index]
                            for index, axis in enumerate("XYZ")
                        },
                        **{
                            f"rotate{axis}": joint.rotation[index]
                            for index, axis in enumerate("XYZ")
                        },
                        **{
                            f"scale{axis}": joint.scale[index]
                            for index, axis in enumerate("XYZ")
                        },
                    }
                    for attribute, value in values.items():
                        self._cmds.setKeyframe(
                            spec.output_path,
                            attribute=attribute,
                            time=sample.frame,
                            value=value,
                        )
            for attribute in plan.root_motion.channel_attributes:
                self._cmds.keyTangent(
                    root_motion_output,
                    attribute=attribute,
                    time=(
                        plan.root_motion.start_frame,
                        plan.root_motion.end_frame,
                    ),
                    inTangentType="linear",
                    outTangentType="linear",
                )
            for spec in plan.export_skeleton.joints:
                for attribute in BODY_EXPORT_CHANNEL_ATTRIBUTES:
                    self._cmds.keyTangent(
                        spec.output_path,
                        attribute=attribute,
                        time=(
                            plan.root_motion.start_frame,
                            plan.root_motion.end_frame,
                        ),
                        inTangentType="linear",
                        outTangentType="linear",
                    )

            metadata = {
                "bake_schema_version": BODY_EXPORT_BAKE_SCHEMA_VERSION,
                "start_frame": plan.root_motion.start_frame,
                "end_frame": plan.root_motion.end_frame,
                "sample_by": plan.root_motion.sample_by,
            }
            for field, attribute in _BODY_EXPORT_BAKE_ATTRIBUTES.items():
                self._cmds.addAttr(
                    export_root,
                    longName=attribute,
                    attributeType="long",
                )
                self._cmds.setAttr(f"{export_root}.{attribute}", metadata[field])
                self._cmds.setAttr(f"{export_root}.{attribute}", lock=True)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_baked_body_export_skeleton(
        self,
        plan: BodyExportSkeletonBakePlan,
    ) -> BodyExportSkeletonBakedSnapshot:
        def read_attribute(node: str, attribute: str):
            plug = f"{node}.{attribute}"
            return self._cmds.getAttr(plug) if self._cmds.objExists(plug) else None

        def channel(path: str, attribute: str) -> BodyRootMotionBakedChannelState:
            plug = f"{path}.{attribute}"
            sources = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
            ) or []
            source_kind = None
            if len(sources) == 1:
                node_type = self._cmds.nodeType(sources[0])
                source_kind = (
                    "animation_curve"
                    if node_type.startswith("animCurve")
                    else node_type
                )
            times = self._cmds.keyframe(
                plug,
                query=True,
                time=(
                    plan.root_motion.start_frame,
                    plan.root_motion.end_frame,
                ),
                timeChange=True,
            ) or []
            values = self._cmds.keyframe(
                plug,
                query=True,
                time=(
                    plan.root_motion.start_frame,
                    plan.root_motion.end_frame,
                ),
                valueChange=True,
            ) or []
            keys = []
            for frame, value in zip(times, values):
                incoming = self._cmds.keyTangent(
                    plug,
                    query=True,
                    time=(frame, frame),
                    inTangentType=True,
                ) or []
                outgoing = self._cmds.keyTangent(
                    plug,
                    query=True,
                    time=(frame, frame),
                    outTangentType=True,
                ) or []
                keys.append(BodyRootMotionKeyState(
                    frame=int(round(float(frame))),
                    value=float(value),
                    in_tangent=incoming[0] if len(incoming) == 1 else "",
                    out_tangent=outgoing[0] if len(outgoing) == 1 else "",
                ))
            return BodyRootMotionBakedChannelState(
                attribute=attribute,
                source_kind=source_kind,
                keys=tuple(keys),
            )

        export = plan.export_skeleton
        root = export.root.output_path
        joints = tuple(
            BodyExportBakedJointState(
                output_path=spec.output_path,
                source_message_exists=self._cmds.objExists(
                    f"{spec.output_path}.{_BODY_EXPORT_SOURCE_ATTRIBUTE}"
                ),
                channels=tuple(
                    channel(spec.output_path, attribute)
                    for attribute in BODY_EXPORT_CHANNEL_ATTRIBUTES
                ),
            )
            for spec in export.joints
        )
        return BodyExportSkeletonBakedSnapshot(
            root_path=root,
            owner=read_attribute(
                root,
                _BODY_EXPORT_PROVENANCE_ATTRIBUTES["owner"],
            ),
            artifact_kind=read_attribute(
                root,
                _BODY_EXPORT_PROVENANCE_ATTRIBUTES["artifact_kind"],
            ),
            schema_version=read_attribute(
                root,
                _BODY_EXPORT_PROVENANCE_ATTRIBUTES["schema_version"],
            ),
            source_body_root=read_attribute(
                root,
                _BODY_EXPORT_PROVENANCE_ATTRIBUTES["source_body_root"],
            ),
            joint_count=read_attribute(
                root,
                _BODY_EXPORT_PROVENANCE_ATTRIBUTES["joint_count"],
            ),
            bake_schema_version=read_attribute(
                root,
                _BODY_EXPORT_BAKE_ATTRIBUTES["bake_schema_version"],
            ),
            start_frame=read_attribute(
                root,
                _BODY_EXPORT_BAKE_ATTRIBUTES["start_frame"],
            ),
            end_frame=read_attribute(
                root,
                _BODY_EXPORT_BAKE_ATTRIBUTES["end_frame"],
            ),
            sample_by=read_attribute(
                root,
                _BODY_EXPORT_BAKE_ATTRIBUTES["sample_by"],
            ),
            root_constraint_exists=bool(
                self._cmds.ls(export.root.root_constraint_name) or []
            ),
            root_motion=self.capture_baked_body_root_motion(plan.root_motion),
            joints=joints,
        )

    def capture_body_export_dependency_plugs(
        self,
        body_root: str,
        export_paths: tuple[str, ...],
    ) -> tuple[str, ...]:
        body_roots = self._cmds.ls(body_root, long=True, type="joint") or []
        if len(body_roots) != 1:
            raise FitSkeletonValidationError("FBX 依赖审计的 Body root 无效")
        body_paths = {body_roots[0]}
        body_paths.update(self._cmds.listRelatives(
            body_roots[0],
            allDescendents=True,
            fullPath=True,
            type="joint",
        ) or [])
        dependencies: set[str] = set()
        for path in export_paths:
            matches = self._cmds.ls(path, long=True, type="joint") or []
            if len(matches) != 1 or matches[0] != path:
                raise FitSkeletonValidationError(
                    f"FBX 依赖审计的导出 joint 无效：{path}"
                )
            connections = self._cmds.listConnections(
                path,
                source=True,
                destination=True,
                connections=True,
                plugs=True,
            ) or []
            for index in range(0, len(connections) - 1, 2):
                left, right = connections[index:index + 2]
                endpoint_paths = {
                    long_path
                    for plug in (left, right)
                    for long_path in (self._cmds.ls(
                        plug.split(".", 1)[0], long=True
                    ) or [])
                }
                if endpoint_paths & body_paths:
                    dependencies.add(f"{left} -> {right}")
        return tuple(sorted(dependencies))

    def prepare_fbx_export_runtime(self) -> str:
        plugin = "fbxmaya"
        if not self._cmds.pluginInfo(plugin, query=True, loaded=True):
            self._cmds.loadPlugin(plugin, quiet=True)
        if not self._cmds.pluginInfo(plugin, query=True, loaded=True):
            raise RuntimeError("Maya FBX 插件加载失败")
        return str(self._cmds.pluginInfo(plugin, query=True, version=True))

    def capture_body_fbx_published_collisions(
        self,
        selection: BodyFbxExportSelection,
    ) -> tuple[str, ...]:
        scene_paths = set(selection.node_paths)
        collisions = {
            path
            for node in selection.published_nodes
            for path in (self._cmds.ls(node.published_path, long=True) or [])
            if path not in scene_paths
        }
        return tuple(sorted(collisions))

    def export_fbx_selection(
        self,
        destination: Path,
        selection: BodyFbxExportSelection,
        profile: BodyFbxExportProfile,
    ) -> BodyFbxAppliedProfile:
        from maya import mel

        class _PublishedNamesRestored(Exception):
            pass

        if destination.exists() or destination.is_symlink():
            raise FitSkeletonValidationError("FBX 临时导出目标已存在")
        for path in selection.node_paths:
            matches = self._cmds.ls(path, long=True, type="joint") or []
            if len(matches) != 1 or matches[0] != path:
                raise FitSkeletonValidationError(
                    f"FBX 明确选择集在执行前失效：{path}"
                )
        collisions = self.capture_body_fbx_published_collisions(selection)
        if collisions:
            raise FitSkeletonValidationError(
                "FBX 发布名称路径已存在：" + "、".join(collisions)
            )
        if not self._cmds.undoInfo(query=True, state=True):
            raise FitSkeletonValidationError(
                "FBX 临时发布名称需要启用 Maya Undo"
            )
        original_selection = self._cmds.ls(selection=True, long=True) or []
        original_time = float(self._cmds.currentTime(query=True))
        original_modified = bool(self._cmds.file(query=True, modified=True))
        original_undo_name = str(
            self._cmds.undoInfo(query=True, undoName=True) or ""
        )
        pushed = False
        applied_profile: BodyFbxAppliedProfile | None = None
        removed_linear_keys = 0
        max_matrix_error = 0.0
        euler_filtered_curves = 0
        try:
            mel.eval("FBXPushSettings;")
            pushed = True
            mel.eval("FBXResetExport;")
            mel.eval("FBXExportBakeComplexAnimation -v false;")
            mel.eval("FBXExportInputConnections -v false;")
            mel.eval("FBXExportConstraints -v false;")
            mel.eval("FBXExportCameras -v false;")
            mel.eval("FBXExportLights -v false;")
            mel.eval("FBXExportShapes -v false;")
            mel.eval("FBXExportSkins -v false;")
            mel.eval(f"FBXExportFileVersion -v {profile.file_version.value};")
            mel.eval(f"FBXExportUpAxis {profile.up_axis.value.lower()};")
            target_centimeters = float(mel.eval(
                f"FBXExportConvertUnitString {profile.linear_unit.value};"
            ))
            source_centimeters = float(mel.eval(
                f"FBXExportConvertUnitString {self.scene_linear_unit().value};"
            ))
            converted_scale = target_centimeters / source_centimeters
            mel.eval(f"FBXExportScaleFactor {converted_scale:.12g};")
            mel.eval(
                "FBXExportInAscii -v "
                + ("true;" if profile.encoding.value == "ascii" else "false;")
            )
            mel.eval("FBXExportGenerateLog -v false;")
            applied_profile = BodyFbxAppliedProfile(
                file_version=str(mel.eval("FBXExportFileVersion -q;")),
                up_axis=str(mel.eval("FBXExportUpAxis -q;")),
                scale_factor=float(mel.eval("FBXExportScaleFactor -q;")),
                encoding=(
                    "ascii"
                    if bool(mel.eval("FBXExportInAscii -q;"))
                    else "binary"
                ),
            )
            try:
                with self.transaction("临时规范化 FBX 发布名称"):
                    self._transaction_changed = True
                    export_root = selection.node_paths[1]
                    for attribute in (
                        *_BODY_EXPORT_PROVENANCE_ATTRIBUTES.values(),
                        *_BODY_EXPORT_BAKE_ATTRIBUTES.values(),
                    ):
                        plug = f"{export_root}.{attribute}"
                        if self._cmds.objExists(plug):
                            self._cmds.setAttr(plug, lock=False)
                            self._cmds.deleteAttr(plug)
                    for node in sorted(
                        selection.published_nodes,
                        key=lambda item: item.scene_path.count("|"),
                        reverse=True,
                    ):
                        self._cmds.rename(
                            node.scene_path,
                            node.published_name,
                            ignoreShape=True,
                        )
                    if any(
                        (self._cmds.ls(path, long=True, type="joint") or [])
                        != [path]
                        for path in selection.published_paths
                    ):
                        raise RuntimeError("FBX 发布名称临时映射复检失败")
                    def sample_matrices(times):
                        poses = []
                        for frame in times:
                            self._cmds.currentTime(frame, edit=True, update=True)
                            poses.append(tuple(tuple(float(value) for value in
                                self._cmds.xform(path, query=True, worldSpace=True,
                                                 matrix=True))
                                for path in selection.published_paths))
                        return tuple(poses)

                    verification_times = fbx_curve_verification_times(
                        selection.start_frame, selection.end_frame,
                        selection.sample_by)
                    original_matrices = (sample_matrices(verification_times)
                        if profile.curve_policy == BodyFbxCurvePolicy.BOUNDED_LINEAR
                        else ())
                    if profile.curve_policy in (BodyFbxCurvePolicy.LOSSLESS_LINEAR,
                                                BodyFbxCurvePolicy.BOUNDED_LINEAR):
                        root_attributes = (
                            ("translateX", "translateY", "rotateZ")
                            if self.scene_up_axis().value.lower() == "z"
                            else ("translateX", "translateZ", "rotateY")
                        )
                        for path in selection.published_paths:
                            attributes = (
                                root_attributes
                                if path == selection.published_root_path
                                else BODY_EXPORT_CHANNEL_ATTRIBUTES
                            )
                            for attribute in attributes:
                                plug = f"{path}.{attribute}"
                                frame_range = (selection.start_frame, selection.end_frame)
                                times = self._cmds.keyframe(
                                    plug, query=True, time=frame_range, timeChange=True
                                ) or []
                                values = self._cmds.keyframe(
                                    plug, query=True, time=frame_range, valueChange=True
                                ) or []
                                in_types = self._cmds.keyTangent(
                                    plug, query=True, time=frame_range,
                                    inTangentType=True) or []
                                out_types = self._cmds.keyTangent(
                                    plug, query=True, time=frame_range,
                                    outTangentType=True) or []
                                if (len(times)!=len(values)
                                        or len(times)!=len(in_types)
                                        or len(times)!=len(out_types)
                                        or any(before!='linear' or after!='linear'
                                               for before,after in zip(in_types,out_types))):
                                    raise FitSkeletonValidationError(
                                        'FBX 发布删键要求完整的线性烘焙曲线：'+plug)
                                keys = tuple(BodyRootMotionKeyState(
                                    frame=int(round(float(frame))), value=float(value),
                                    in_tangent=before, out_tangent=after,
                                ) for frame,value,before,after in zip(
                                    times,values,in_types,out_types))
                                value_tolerance = (profile.value_tolerance
                                    if profile.curve_policy == BodyFbxCurvePolicy.BOUNDED_LINEAR
                                    else 1e-9)
                                for frame in redundant_linear_key_frames(
                                        keys, tolerance=value_tolerance):
                                    self._cmds.cutKey(plug, time=(frame, frame), option="keys")
                                    removed_linear_keys += 1
                    if profile.euler_filter:
                        baked_frames = tuple(range(selection.start_frame,
                            selection.end_frame + 1, selection.sample_by))
                        before_filter = sample_matrices(baked_frames)
                        for path in selection.published_paths[1:]:
                            curves = []
                            for axis in "XYZ":
                                found = self._cmds.listConnections(
                                    f"{path}.rotate{axis}", source=True,
                                    destination=False, type="animCurve") or []
                                if len(found) != 1:
                                    raise FitSkeletonValidationError(
                                        "FBX Euler Filter 要求每个导出关节都有独立的旋转曲线："
                                        + path)
                                curves.append(found[0])
                            euler_filtered_curves += int(self._cmds.filterCurve(
                                *curves, filter="euler",
                                startTime=selection.start_frame,
                                endTime=selection.end_frame))
                        after_filter = sample_matrices(baked_frames)
                        filter_error = max(abs(a - b)
                            for before_frame, after_frame in zip(
                                before_filter, after_filter)
                            for before_joint, after_joint in zip(
                                before_frame, after_frame)
                            for a, b in zip(before_joint, after_joint))
                        if filter_error > 1e-5:
                            raise FitSkeletonValidationError(
                                "FBX Euler Filter 改变了烘焙帧世界姿态："
                                f"{filter_error:g}")
                    if original_matrices:
                        simplified_matrices = sample_matrices(verification_times)
                        max_matrix_error = max(abs(a - b)
                            for before_frame, after_frame in zip(
                                original_matrices, simplified_matrices)
                            for before_joint, after_joint in zip(
                                before_frame, after_frame)
                            for a, b in zip(before_joint, after_joint))
                        if max_matrix_error > profile.matrix_tolerance:
                            raise FitSkeletonValidationError(
                                "FBX 有界曲线简化超过世界矩阵误差上限："
                                f"{max_matrix_error:g} > {profile.matrix_tolerance:g}")
                    self._cmds.select(
                        selection.published_paths,
                        replace=True,
                        noExpand=True,
                    )
                    destination_literal = json.dumps(
                        destination.as_posix(), ensure_ascii=False
                    )
                    mel.eval(f"FBXExport -f {destination_literal} -s;")
                    if not destination.is_file():
                        raise RuntimeError("Maya FBX 导出未生成临时文件")
                    raise _PublishedNamesRestored()
            except _PublishedNamesRestored:
                pass
            if any(
                (self._cmds.ls(path, long=True, type="joint") or []) != [path]
                for path in selection.node_paths
            ):
                raise RuntimeError("FBX 导出后原始场景路径恢复失败")
        finally:
            try:
                if pushed:
                    mel.eval("FBXPopSettings;")
            finally:
                self._cmds.undoInfo(stateWithoutFlush=False)
                try:
                    self._cmds.currentTime(original_time, edit=True, update=True)
                    if original_selection:
                        self._cmds.select(original_selection, replace=True)
                    else:
                        self._cmds.select(clear=True)
                    self._cmds.file(modified=original_modified)
                finally:
                    self._cmds.undoInfo(stateWithoutFlush=True)
        if str(self._cmds.undoInfo(query=True, undoName=True) or "") != original_undo_name:
            raise RuntimeError("FBX 导出改变了 Maya 原有 Undo 队列顶部")
        if applied_profile is None:
            raise RuntimeError("FBX exporter Profile 未生成应用快照")
        return replace(
            applied_profile,
            curve_policy=profile.curve_policy.value,
            removed_linear_keys=removed_linear_keys,
            max_matrix_error=max_matrix_error,
            euler_filter=profile.euler_filter,
            euler_filtered_curves=euler_filtered_curves,
        )

    def create_body_arm_ik_root(self, name: str) -> str:
        return self.create_body_control_root(name)

    def create_body_leg_ik_root(self, name: str) -> str:
        return self.create_body_control_root(name)

    def create_body_arm_blend(self, plan: BodyArmBlendPlan) -> None:
        self._create_body_limb_blend(plan, "Arm")

    def create_body_leg_blend(self, plan: BodyLegBlendPlan) -> None:
        self._create_body_limb_blend(plan, "Leg")

    def _create_body_limb_blend(
        self,
        plan: BodyArmBlendPlan,
        limb_label: str,
    ) -> None:
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._create_body_limb_blend_nodes(plan, limb_label)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def _create_body_limb_blend_nodes(
        self,
        plan: BodyArmBlendPlan,
        limb_label: str,
    ) -> None:
        self._require_transaction()
        names = [plan.settings_name]
        for side in plan.sides:
            names.append(side.reverse_name)
            names.extend(joint.constraint_name for joint in side.joints)
            names.extend(joint.translation_constraint_name for joint in side.joints if joint.translation_constraint_name)
        if any(self.find_name_collisions(name) for name in names):
            raise FitSkeletonValidationError(
                f"{limb_label} IK/FK 输出名称冲突"
            )
        self._transaction_changed = True
        settings = self._cmds.createNode("transform", name=plan.settings_name, skipSelect=True)
        settings = (self._cmds.ls(settings, long=True) or [settings])[0]
        if settings != plan.settings_path:
            raise RuntimeError(f"{limb_label} IK/FK 设置节点路径漂移")
        for side in plan.sides:
            self._cmds.addAttr(settings, longName=side.attribute, attributeType="double", minValue=0.0, maxValue=1.0, defaultValue=0.0, keyable=True)
            plug = f"{settings}.{side.attribute}"
            reverse = self._cmds.createNode("reverse", name=side.reverse_name)
            self._cmds.connectAttr(plug, f"{reverse}.inputX")
            for joint in side.joints:
                if any(not self._cmds.objExists(path) for path in (joint.body_joint, joint.fk_driver, joint.ik_driver)):
                    raise FitSkeletonValidationError(
                        f"{limb_label} IK/FK 驱动或 Body joint 失效"
                    )
                constraint = self._cmds.orientConstraint(joint.fk_driver, joint.ik_driver, joint.body_joint, maintainOffset=False, name=joint.constraint_name)[0]
                aliases = self._cmds.orientConstraint(constraint, query=True, weightAliasList=True) or []
                if len(aliases) != 2:
                    raise RuntimeError(
                        f"{limb_label} IK/FK 双源权重别名无效"
                    )
                self._cmds.connectAttr(f"{reverse}.outputX", f"{constraint}.{aliases[0]}")
                self._cmds.connectAttr(plug, f"{constraint}.{aliases[1]}")
                if joint.translation_constraint_name:
                    point = self._cmds.pointConstraint(
                        joint.fk_driver,
                        joint.ik_driver,
                        joint.body_joint,
                        maintainOffset=False,
                        name=joint.translation_constraint_name,
                    )[0]
                    point_aliases = self._cmds.pointConstraint(point, query=True, weightAliasList=True) or []
                    if len(point_aliases) != 2:
                        raise RuntimeError(
                            f"{limb_label} FK/IK 位移双源权重别名无效"
                        )
                    self._cmds.connectAttr(f"{reverse}.outputX", f"{point}.{point_aliases[0]}")
                    self._cmds.connectAttr(plug, f"{point}.{point_aliases[1]}")

    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot:
        return self._capture_body_limb_blend(plan, "Arm")

    def capture_body_leg_blend(self, plan: BodyLegBlendPlan) -> BodyLegBlendSnapshot:
        return self._capture_body_limb_blend(plan, "Leg")

    def _capture_body_limb_blend(
        self,
        plan: BodyArmBlendPlan,
        limb_label: str,
    ) -> BodyArmBlendSnapshot:
        def normalized_plug(value: str | None) -> str | None:
            if value is None or "." not in value:
                return value
            node, attribute = value.split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings_nodes = self._cmds.ls(plan.settings_path, long=True, type="transform") or []
        if len(settings_nodes) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} IK/FK 设置节点无效"
            )
        settings = settings_nodes[0]
        side_states = []
        for side in plan.sides:
            plug = f"{settings}.{side.attribute}"
            reverse_nodes = self._cmds.ls(side.reverse_name, type="reverse") or []
            if len(reverse_nodes) != 1 or not self._cmds.objExists(plug):
                raise FitSkeletonValidationError(
                    f"{limb_label} IK/FK 属性或 reverse 无效"
                )
            reverse = reverse_nodes[0]
            reverse_sources = self._cmds.listConnections(f"{reverse}.inputX", source=True, destination=False, plugs=True) or []
            joint_states = []
            for spec in side.joints:
                constraints = self._cmds.ls(spec.constraint_name, type="orientConstraint") or []
                if len(constraints) != 1:
                    raise FitSkeletonValidationError(
                        f"{limb_label} IK/FK 约束无效"
                    )
                constraint = constraints[0]
                targets = self._cmds.orientConstraint(constraint, query=True, targetList=True) or []
                target_paths = tuple((self._cmds.ls(target, long=True) or [target])[0] for target in targets)
                aliases = self._cmds.orientConstraint(constraint, query=True, weightAliasList=True) or []
                weight_sources = [
                    normalized_plug((self._cmds.listConnections(f"{constraint}.{alias}", source=True, destination=False, plugs=True) or [None])[0])
                    for alias in aliases
                ]
                outputs = self._cmds.listConnections(f"{constraint}.constraintRotateX", source=False, destination=True, plugs=True) or []
                driven = self._resolve_connected_node(outputs[0]) if len(outputs) == 1 else None
                translation_name = None
                translation_targets = ()
                translation_weights = (None, None)
                translation_driven = None
                if spec.translation_constraint_name:
                    point_constraints = self._cmds.ls(spec.translation_constraint_name, type="pointConstraint") or []
                    if len(point_constraints) != 1:
                        raise FitSkeletonValidationError(
                            f"{limb_label} FK/IK 位移约束无效"
                        )
                    point = point_constraints[0]
                    point_targets = self._cmds.pointConstraint(point, query=True, targetList=True) or []
                    translation_targets = tuple((self._cmds.ls(target, long=True) or [target])[0] for target in point_targets)
                    point_aliases = self._cmds.pointConstraint(point, query=True, weightAliasList=True) or []
                    sources = tuple(
                        normalized_plug((self._cmds.listConnections(f"{point}.{alias}", source=True, destination=False, plugs=True) or [None])[0])
                        for alias in point_aliases
                    )
                    translation_weights = (
                        sources[0] if len(sources) > 0 else None,
                        sources[1] if len(sources) > 1 else None,
                    )
                    point_outputs = self._cmds.listConnections(f"{point}.constraintTranslateX", source=False, destination=True, plugs=True) or []
                    translation_driven = self._resolve_connected_node(point_outputs[0]) if len(point_outputs) == 1 else None
                    translation_name = point
                joint_states.append(BodyArmBlendJointState(
                    constraint,
                    driven,
                    target_paths,
                    weight_sources[0] if len(weight_sources) > 0 else None,
                    weight_sources[1] if len(weight_sources) > 1 else None,
                    translation_name,
                    translation_targets,
                    translation_weights[0],
                    translation_weights[1],
                    translation_driven,
                ))
            side_states.append(BodyArmBlendSideState(side.side, plug, float(self._cmds.getAttr(plug)), reverse, normalized_plug(reverse_sources[0]) if len(reverse_sources) == 1 else None, tuple(joint_states)))
        return BodyArmBlendSnapshot(settings, tuple(side_states))

    def create_body_arm_visibility(self, plan: BodyArmVisibilityPlan) -> None:
        self._create_body_limb_visibility(plan, "Arm")

    def create_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> None:
        self._create_body_limb_visibility(plan, "Leg")

    def _create_body_limb_visibility(self, plan, limb_label: str) -> None:
        self._require_transaction()
        targets = tuple(
            path
            for side in plan.sides
            for path in (side.fk_offset_path, *side.ik_offset_paths)
        )
        sources = tuple(
            plug
            for side in plan.sides
            for plug in (side.reverse_output_plug, side.blend_plug)
        )
        if any(not self._cmds.objExists(value) for value in (*targets, *sources)):
            raise FitSkeletonValidationError(f"{limb_label} 控制显隐节点或属性在执行前失效")
        self._transaction_changed = True
        for side in plan.sides:
            self._cmds.connectAttr(side.reverse_output_plug, f"{side.fk_offset_path}.visibility")
            for path in side.ik_offset_paths:
                self._cmds.connectAttr(side.blend_plug, f"{path}.visibility")

    def capture_body_arm_visibility(self, plan: BodyArmVisibilityPlan) -> BodyArmVisibilitySnapshot:
        return self._capture_body_limb_visibility(
            plan, BodyArmVisibilitySideState, BodyArmVisibilitySnapshot
        )

    def capture_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> BodyLegVisibilitySnapshot:
        return self._capture_body_limb_visibility(
            plan, BodyLegVisibilitySideState, BodyLegVisibilitySnapshot
        )

    def capture_body_leg_visibility_input(
        self, plan: BodyLegVisibilityPlan
    ) -> BodyLegVisibilityInputState:
        sources = tuple(
            plug
            for side in plan.sides
            for plug in (side.reverse_output_plug, side.blend_plug)
            if self._cmds.objExists(plug)
        )
        target_plugs = tuple(
            f"{path}.visibility"
            for side in plan.sides
            for path in (side.fk_offset_path, *side.ik_offset_paths)
        )
        writable = tuple(
            plug
            for plug in target_plugs
            if self._cmds.objExists(plug)
            and bool(self._cmds.getAttr(plug, settable=True))
        )
        return BodyLegVisibilityInputState(sources, writable)

    def _capture_body_limb_visibility(self, plan, side_state_type, snapshot_type):
        def source(path: str) -> str | None:
            values = self._cmds.listConnections(
                f"{path}.visibility",
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            value = values[0]
            if "." not in value:
                return value
            node, attribute = value.split(".", 1)
            nodes = self._cmds.ls(node, long=True) or [node]
            return f"{nodes[0]}.{attribute}"

        states = []
        for side in plan.sides:
            states.append(
                side_state_type(
                    side.side,
                    source(side.fk_offset_path),
                    tuple(source(path) for path in side.ik_offset_paths),
                )
            )
        return snapshot_type(tuple(states))

    def create_body_arm_stretch(self, plan: BodyArmStretchPlan) -> None:
        self._create_body_limb_stretch(plan)

    def create_body_leg_stretch(self, plan: BodyLegStretchPlan) -> None:
        self._create_body_limb_stretch(plan)

    def _create_body_limb_stretch(self, plan) -> None:
        self._require_transaction()
        label = plan.limb_label
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if not self._cmds.objExists(plan.settings_path):
                raise FitSkeletonValidationError(
                    f"{label} stretch 设置节点在执行前失效"
                )
            global_scale_plug = f"{plan.settings_path}.{plan.global_scale_attribute}"
            if self._cmds.objExists(global_scale_plug):
                raise FitSkeletonValidationError(
                    f"{label} stretch 全局比例属性已存在"
                )
            self._transaction_changed = True
            self._cmds.addAttr(
                plan.settings_path,
                longName=plan.global_scale_attribute,
                attributeType="double",
                minValue=0.0001,
                defaultValue=plan.global_scale_default,
                keyable=True,
            )
            for spec in plan.sides:
                names = (spec.start_name, spec.distance_name, spec.ratio_name, spec.rest_scale_name, spec.clamp_name, spec.blend_name, spec.segment_name)
                if any(self.find_name_collisions(name) for name in names):
                    raise FitSkeletonValidationError(
                        f"{label} stretch 输出名称冲突"
                    )
                if any(
                    not self._cmds.objExists(path)
                    for path in (spec.target_control_path, *spec.segment_joints)
                ):
                    raise FitSkeletonValidationError(
                        f"{label} stretch 控制或 IK mechanism 在执行前失效"
                    )
                plug = f"{plan.settings_path}.{spec.attribute}"
                if self._cmds.objExists(plug):
                    raise FitSkeletonValidationError(
                        f"{label} stretch 属性已存在"
                    )
                self._cmds.addAttr(plan.settings_path, longName=spec.attribute, attributeType="double", minValue=0.0, maxValue=1.0, defaultValue=1.0, keyable=True)
                start_parent = spec.start_path.rsplit("|", 1)[0]
                start = self._cmds.createNode("transform", name=spec.start_name, parent=start_parent, skipSelect=True)
                start = (self._cmds.ls(start, long=True) or [start])[0]
                self._cmds.xform(start, worldSpace=True, translation=spec.start_position)
                if start != spec.start_path:
                    raise RuntimeError(f"{label} stretch 起点路径漂移")
                distance = self._cmds.createNode("distanceBetween", name=spec.distance_name, skipSelect=True)
                ratio = self._cmds.createNode("multiplyDivide", name=spec.ratio_name, skipSelect=True)
                rest_scale = self._cmds.createNode("multiplyDivide", name=spec.rest_scale_name, skipSelect=True)
                clamp = self._cmds.createNode("clamp", name=spec.clamp_name, skipSelect=True)
                blend = self._cmds.createNode("blendColors", name=spec.blend_name, skipSelect=True)
                segments = self._cmds.createNode("multiplyDivide", name=spec.segment_name, skipSelect=True)
                self._cmds.connectAttr(f"{start}.worldMatrix[0]", f"{distance}.inMatrix1")
                self._cmds.connectAttr(f"{spec.target_control_path}.worldMatrix[0]", f"{distance}.inMatrix2")
                self._cmds.setAttr(f"{ratio}.operation", 2)
                self._cmds.connectAttr(f"{distance}.distance", f"{ratio}.input1X")
                self._cmds.setAttr(f"{rest_scale}.operation", 1)
                self._cmds.setAttr(f"{rest_scale}.input1X", spec.rest_length)
                self._cmds.connectAttr(global_scale_plug, f"{rest_scale}.input2X")
                self._cmds.connectAttr(f"{rest_scale}.outputX", f"{ratio}.input2X")
                self._cmds.setAttr(f"{clamp}.minR", 1.0)
                self._cmds.setAttr(f"{clamp}.maxR", 1000000.0)
                self._cmds.connectAttr(f"{ratio}.outputX", f"{clamp}.inputR")
                self._cmds.connectAttr(f"{clamp}.outputR", f"{blend}.color1R")
                self._cmds.setAttr(f"{blend}.color2R", 1.0)
                self._cmds.connectAttr(plug, f"{blend}.blender")
                self._cmds.setAttr(f"{segments}.operation", 1)
                self._cmds.setAttr(f"{segments}.input1X", spec.base_translations[0])
                self._cmds.setAttr(f"{segments}.input1Y", spec.base_translations[1])
                self._cmds.connectAttr(f"{blend}.outputR", f"{segments}.input2X")
                self._cmds.connectAttr(f"{blend}.outputR", f"{segments}.input2Y")
                self._cmds.connectAttr(
                    f"{segments}.outputX",
                    f"{spec.segment_joints[0]}.translate{spec.segment_channels[0]}",
                )
                self._cmds.connectAttr(
                    f"{segments}.outputY",
                    f"{spec.segment_joints[1]}.translate{spec.segment_channels[1]}",
                )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_stretch(self, plan: BodyArmStretchPlan) -> BodyArmStretchSnapshot:
        return self._capture_body_limb_stretch(plan)

    def capture_body_leg_stretch(self, plan: BodyLegStretchPlan) -> BodyLegStretchSnapshot:
        return self._capture_body_limb_stretch(plan)

    def _capture_body_limb_stretch(self, plan):
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
            if len(values) != 1:
                return None
            value = values[0]
            if "." not in value:
                return value
            node, attribute = value.split(".", 1)
            if attribute == "worldMatrix":
                attribute = "worldMatrix[0]"
            nodes = self._cmds.ls(node, long=True) or [node]
            return f"{nodes[0]}.{attribute}"

        settings = (self._cmds.ls(plan.settings_path, long=True, type="transform") or [None])[0]
        if settings is None:
            raise FitSkeletonValidationError(
                f"{plan.limb_label} stretch 设置节点无效"
            )
        global_scale_plug = f"{settings}.{plan.global_scale_attribute}"
        if not self._cmds.objExists(global_scale_plug):
            raise FitSkeletonValidationError(
                f"{plan.limb_label} stretch 全局比例输入无效"
            )
        states = []
        for spec in plan.sides:
            typed = (
                (spec.start_path, "transform"),
                (spec.distance_name, "distanceBetween"),
                (spec.ratio_name, "multiplyDivide"),
                (spec.rest_scale_name, "multiplyDivide"),
                (spec.clamp_name, "clamp"),
                (spec.blend_name, "blendColors"),
                (spec.segment_name, "multiplyDivide"),
            )
            if any(len(self._cmds.ls(name, type=node_type) or []) != 1 for name, node_type in typed):
                raise FitSkeletonValidationError(
                    f"{plan.limb_label} stretch 节点集合无效"
                )
            plug = f"{settings}.{spec.attribute}"
            states.append(BodyArmStretchSideState(
                spec.side,
                plug,
                float(self._cmds.getAttr(plug)),
                spec.start_path,
                tuple(float(value) for value in self._cmds.xform(spec.start_path, query=True, worldSpace=True, translation=True)),
                spec.distance_name,
                (source(f"{spec.distance_name}.inMatrix1"), source(f"{spec.distance_name}.inMatrix2")),
                spec.ratio_name,
                source(f"{spec.ratio_name}.input1X"),
                spec.rest_scale_name,
                float(self._cmds.getAttr(f"{spec.rest_scale_name}.input1X")),
                source(f"{spec.rest_scale_name}.input2X"),
                int(self._cmds.getAttr(f"{spec.rest_scale_name}.operation")),
                source(f"{spec.ratio_name}.input2X"),
                int(self._cmds.getAttr(f"{spec.ratio_name}.operation")),
                spec.clamp_name,
                source(f"{spec.clamp_name}.inputR"),
                float(self._cmds.getAttr(f"{spec.clamp_name}.minR")),
                float(self._cmds.getAttr(f"{spec.clamp_name}.maxR")),
                spec.blend_name,
                source(f"{spec.blend_name}.color1R"),
                source(f"{spec.blend_name}.blender"),
                float(self._cmds.getAttr(f"{spec.blend_name}.color2R")),
                spec.segment_name,
                (float(self._cmds.getAttr(f"{spec.segment_name}.input1X")), float(self._cmds.getAttr(f"{spec.segment_name}.input1Y"))),
                (source(f"{spec.segment_name}.input2X"), source(f"{spec.segment_name}.input2Y")),
                (
                    source(
                        f"{spec.segment_joints[0]}.translate{spec.segment_channels[0]}"
                    ),
                    source(
                        f"{spec.segment_joints[1]}.translate{spec.segment_channels[1]}"
                    ),
                ),
                int(self._cmds.getAttr(f"{spec.segment_name}.operation")),
            ))
        return BodyArmStretchSnapshot(
            settings,
            global_scale_plug,
            float(self._cmds.getAttr(global_scale_plug)),
            tuple(states),
        )

    def create_body_leg_stretch_bias(
        self,
        plan: BodyLegStretchBiasPlan,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []

        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            return values[0] if len(values) == 1 else None

        try:
            settings = self._cmds.ls(
                plan.settings_path,
                long=True,
                type="transform",
            ) or []
            if len(settings) != 1 or settings[0] != plan.settings_path:
                raise FitSkeletonValidationError(
                    "Leg stretch bias 设置节点在执行前失效"
                )
            for spec in plan.sides:
                plug = f"{plan.settings_path}.{spec.attribute}"
                names = (
                    spec.delta_name,
                    spec.candidates_name,
                    spec.weights_name,
                    spec.factors_name,
                )
                segments = self._cmds.ls(
                    spec.segment_name,
                    type="multiplyDivide",
                ) or []
                if (
                    self._cmds.objExists(plug)
                    or any(self.find_name_collisions(name) for name in names)
                    or len(segments) != 1
                    or not self._cmds.objExists(spec.ratio_source)
                    or any(
                        source(destination) != spec.original_factor_source
                        for destination in spec.factor_destinations
                    )
                ):
                    raise FitSkeletonValidationError(
                        "Leg stretch bias 输入、名称或原始段长连接失效"
                    )

            self._transaction_changed = True
            for spec in plan.sides:
                plug = f"{plan.settings_path}.{spec.attribute}"
                self._cmds.addAttr(
                    plan.settings_path,
                    longName=spec.attribute,
                    attributeType="double",
                    minValue=0.0,
                    maxValue=1.0,
                    defaultValue=spec.default_value,
                    keyable=True,
                )
                delta = self._cmds.createNode(
                    "plusMinusAverage",
                    name=spec.delta_name,
                    skipSelect=True,
                )
                candidates = self._cmds.createNode(
                    "multiplyDivide",
                    name=spec.candidates_name,
                    skipSelect=True,
                )
                weights = self._cmds.createNode(
                    "blendColors",
                    name=spec.weights_name,
                    skipSelect=True,
                )
                factors = self._cmds.createNode(
                    "plusMinusAverage",
                    name=spec.factors_name,
                    skipSelect=True,
                )

                self._cmds.setAttr(f"{delta}.operation", 2)
                self._cmds.connectAttr(
                    spec.ratio_source,
                    f"{delta}.input1D[0]",
                )
                self._cmds.setAttr(f"{delta}.input1D[1]", 1.0)

                self._cmds.setAttr(f"{candidates}.operation", 1)
                self._cmds.connectAttr(
                    f"{delta}.output1D",
                    f"{candidates}.input1X",
                )
                self._cmds.connectAttr(
                    f"{delta}.output1D",
                    f"{candidates}.input1Y",
                )
                self._cmds.setAttr(
                    f"{candidates}.input2X",
                    spec.candidate_multipliers[0],
                )
                self._cmds.setAttr(
                    f"{candidates}.input2Y",
                    spec.candidate_multipliers[1],
                )

                self._cmds.connectAttr(
                    f"{candidates}.outputX",
                    f"{weights}.color1R",
                )
                self._cmds.setAttr(f"{weights}.color2R", 0.0)
                self._cmds.setAttr(f"{weights}.color1G", 0.0)
                self._cmds.connectAttr(
                    f"{candidates}.outputY",
                    f"{weights}.color2G",
                )
                self._cmds.connectAttr(plug, f"{weights}.blender")

                self._cmds.setAttr(f"{factors}.operation", 1)
                self._cmds.setAttr(
                    f"{factors}.input2D[0].input2Dx",
                    1.0,
                )
                self._cmds.setAttr(
                    f"{factors}.input2D[0].input2Dy",
                    1.0,
                )
                self._cmds.connectAttr(
                    f"{weights}.outputR",
                    f"{factors}.input2D[1].input2Dx",
                )
                self._cmds.connectAttr(
                    f"{weights}.outputG",
                    f"{factors}.input2D[1].input2Dy",
                )

                for old_source, destination, new_source in zip(
                    (spec.original_factor_source,) * 2,
                    spec.factor_destinations,
                    spec.factor_sources,
                ):
                    self._cmds.disconnectAttr(old_source, destination)
                    self._cmds.connectAttr(new_source, destination)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_leg_stretch_bias(
        self,
        plan: BodyLegStretchBiasPlan,
    ) -> BodyLegStretchBiasSnapshot:
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings = self._cmds.ls(
            plan.settings_path,
            long=True,
            type="transform",
        ) or []
        if len(settings) != 1:
            raise FitSkeletonValidationError(
                "Leg stretch bias 设置节点无效"
            )
        states = []
        for spec in plan.sides:
            typed = (
                (spec.delta_name, "plusMinusAverage"),
                (spec.candidates_name, "multiplyDivide"),
                (spec.weights_name, "blendColors"),
                (spec.factors_name, "plusMinusAverage"),
                (spec.segment_name, "multiplyDivide"),
            )
            plug = f"{plan.settings_path}.{spec.attribute}"
            if (
                not self._cmds.objExists(plug)
                or any(
                    len(self._cmds.ls(name, type=node_type) or []) != 1
                    for name, node_type in typed
                )
            ):
                raise FitSkeletonValidationError(
                    "Leg stretch bias 节点集合无效"
                )
            states.append(BodyLegStretchBiasSideState(
                side=spec.side,
                attribute_plug=plug,
                attribute_value=float(self._cmds.getAttr(plug)),
                delta_name=spec.delta_name,
                delta_ratio_source=source(f"{spec.delta_name}.input1D[0]"),
                delta_base_value=float(self._cmds.getAttr(
                    f"{spec.delta_name}.input1D[1]"
                )),
                delta_operation=int(self._cmds.getAttr(
                    f"{spec.delta_name}.operation"
                )),
                candidates_name=spec.candidates_name,
                candidate_sources=(
                    source(f"{spec.candidates_name}.input1X"),
                    source(f"{spec.candidates_name}.input1Y"),
                ),
                candidate_multipliers=(
                    float(self._cmds.getAttr(
                        f"{spec.candidates_name}.input2X"
                    )),
                    float(self._cmds.getAttr(
                        f"{spec.candidates_name}.input2Y"
                    )),
                ),
                candidate_operation=int(self._cmds.getAttr(
                    f"{spec.candidates_name}.operation"
                )),
                weights_name=spec.weights_name,
                upper_candidate_source=source(
                    f"{spec.weights_name}.color1R"
                ),
                upper_zero=float(self._cmds.getAttr(
                    f"{spec.weights_name}.color2R"
                )),
                lower_zero=float(self._cmds.getAttr(
                    f"{spec.weights_name}.color1G"
                )),
                lower_candidate_source=source(
                    f"{spec.weights_name}.color2G"
                ),
                bias_source=source(f"{spec.weights_name}.blender"),
                factors_name=spec.factors_name,
                base_factors=(
                    float(self._cmds.getAttr(
                        f"{spec.factors_name}.input2D[0].input2Dx"
                    )),
                    float(self._cmds.getAttr(
                        f"{spec.factors_name}.input2D[0].input2Dy"
                    )),
                ),
                weighted_sources=(
                    source(f"{spec.factors_name}.input2D[1].input2Dx"),
                    source(f"{spec.factors_name}.input2D[1].input2Dy"),
                ),
                factor_operation=int(self._cmds.getAttr(
                    f"{spec.factors_name}.operation"
                )),
                factor_destinations=spec.factor_destinations,
                factor_destination_sources=tuple(
                    source(destination)
                    for destination in spec.factor_destinations
                ),
            ))
        return BodyLegStretchBiasSnapshot(settings[0], tuple(states))

    def create_body_leg_knee_pin(
        self,
        plan: BodyLegKneePinPlan,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []

        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            return values[0] if len(values) == 1 else None

        try:
            settings = self._cmds.ls(
                plan.settings_path,
                long=True,
                type="transform",
            ) or []
            if len(settings) != 1 or settings[0] != plan.settings_path:
                raise FitSkeletonValidationError(
                    "Leg knee pin 设置节点在执行前失效"
                )
            for spec in plan.sides:
                plug = f"{plan.settings_path}.{spec.attribute}"
                required = (
                    spec.start_matrix_source,
                    spec.pole_matrix_source,
                    spec.ankle_matrix_source,
                    spec.global_scale_source,
                    *spec.normal_factor_sources,
                    *spec.factor_destinations,
                )
                if (
                    self._cmds.objExists(plug)
                    or any(
                        self.find_name_collisions(name)
                        for name in spec.node_names
                    )
                    or any(not self._cmds.objExists(value) for value in required)
                    or any(
                        source(destination) != normal_source
                        for destination, normal_source in zip(
                            spec.factor_destinations,
                            spec.normal_factor_sources,
                        )
                    )
                ):
                    raise FitSkeletonValidationError(
                        "Leg knee pin 输入、名称或原始段长连接失效"
                    )

            self._transaction_changed = True
            for spec in plan.sides:
                plug = f"{plan.settings_path}.{spec.attribute}"
                self._cmds.addAttr(
                    plan.settings_path,
                    longName=spec.attribute,
                    attributeType="double",
                    minValue=0.0,
                    maxValue=1.0,
                    defaultValue=spec.default_value,
                    keyable=True,
                )
                upper_distance = self._cmds.createNode(
                    "distanceBetween",
                    name=spec.upper_distance_name,
                    skipSelect=True,
                )
                lower_distance = self._cmds.createNode(
                    "distanceBetween",
                    name=spec.lower_distance_name,
                    skipSelect=True,
                )
                local_lengths = self._cmds.createNode(
                    "multiplyDivide",
                    name=spec.local_lengths_name,
                    skipSelect=True,
                )
                clamp = self._cmds.createNode(
                    "clamp",
                    name=spec.clamp_name,
                    skipSelect=True,
                )
                pin_factors = self._cmds.createNode(
                    "multiplyDivide",
                    name=spec.pin_factors_name,
                    skipSelect=True,
                )
                factors = self._cmds.createNode(
                    "blendColors",
                    name=spec.factors_name,
                    skipSelect=True,
                )
                ratio_terms = self._cmds.createNode(
                    "multiplyDivide",
                    name=spec.ratio_terms_name,
                    skipSelect=True,
                )
                total_ratio = self._cmds.createNode(
                    "plusMinusAverage",
                    name=spec.total_ratio_name,
                    skipSelect=True,
                )

                self._cmds.connectAttr(
                    spec.start_matrix_source,
                    f"{upper_distance}.inMatrix1",
                )
                self._cmds.connectAttr(
                    spec.pole_matrix_source,
                    f"{upper_distance}.inMatrix2",
                )
                self._cmds.connectAttr(
                    spec.pole_matrix_source,
                    f"{lower_distance}.inMatrix1",
                )
                self._cmds.connectAttr(
                    spec.ankle_matrix_source,
                    f"{lower_distance}.inMatrix2",
                )

                self._cmds.setAttr(f"{local_lengths}.operation", 2)
                self._cmds.connectAttr(
                    f"{upper_distance}.distance",
                    f"{local_lengths}.input1X",
                )
                self._cmds.connectAttr(
                    f"{lower_distance}.distance",
                    f"{local_lengths}.input1Y",
                )
                self._cmds.connectAttr(
                    spec.global_scale_source,
                    f"{local_lengths}.input2X",
                )
                self._cmds.connectAttr(
                    spec.global_scale_source,
                    f"{local_lengths}.input2Y",
                )

                self._cmds.connectAttr(
                    f"{local_lengths}.outputX",
                    f"{clamp}.inputR",
                )
                self._cmds.connectAttr(
                    f"{local_lengths}.outputY",
                    f"{clamp}.inputG",
                )
                self._cmds.setAttr(f"{clamp}.minR", spec.minimum_length)
                self._cmds.setAttr(f"{clamp}.minG", spec.minimum_length)
                self._cmds.setAttr(f"{clamp}.maxR", 1000000.0)
                self._cmds.setAttr(f"{clamp}.maxG", 1000000.0)

                self._cmds.setAttr(f"{pin_factors}.operation", 2)
                self._cmds.connectAttr(
                    f"{clamp}.outputR",
                    f"{pin_factors}.input1X",
                )
                self._cmds.connectAttr(
                    f"{clamp}.outputG",
                    f"{pin_factors}.input1Y",
                )
                self._cmds.setAttr(
                    f"{pin_factors}.input2X",
                    spec.base_lengths[0],
                )
                self._cmds.setAttr(
                    f"{pin_factors}.input2Y",
                    spec.base_lengths[1],
                )

                self._cmds.connectAttr(
                    f"{pin_factors}.outputX",
                    f"{factors}.color1R",
                )
                self._cmds.connectAttr(
                    f"{pin_factors}.outputY",
                    f"{factors}.color1G",
                )
                self._cmds.connectAttr(
                    spec.normal_factor_sources[0],
                    f"{factors}.color2R",
                )
                self._cmds.connectAttr(
                    spec.normal_factor_sources[1],
                    f"{factors}.color2G",
                )
                self._cmds.connectAttr(plug, f"{factors}.blender")

                self._cmds.setAttr(f"{ratio_terms}.operation", 1)
                self._cmds.connectAttr(
                    f"{factors}.outputR",
                    f"{ratio_terms}.input1X",
                )
                self._cmds.connectAttr(
                    f"{factors}.outputG",
                    f"{ratio_terms}.input1Y",
                )
                self._cmds.setAttr(
                    f"{ratio_terms}.input2X",
                    spec.base_lengths[0] / spec.rest_length,
                )
                self._cmds.setAttr(
                    f"{ratio_terms}.input2Y",
                    spec.base_lengths[1] / spec.rest_length,
                )
                self._cmds.setAttr(f"{total_ratio}.operation", 1)
                self._cmds.connectAttr(
                    f"{ratio_terms}.outputX",
                    f"{total_ratio}.input1D[0]",
                )
                self._cmds.connectAttr(
                    f"{ratio_terms}.outputY",
                    f"{total_ratio}.input1D[1]",
                )

                for old_source, destination, new_source in zip(
                    spec.normal_factor_sources,
                    spec.factor_destinations,
                    spec.factor_sources,
                ):
                    self._cmds.disconnectAttr(old_source, destination)
                    self._cmds.connectAttr(new_source, destination)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_leg_knee_pin(
        self,
        plan: BodyLegKneePinPlan,
    ) -> BodyLegKneePinSnapshot:
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            if attribute == "worldMatrix":
                attribute = "worldMatrix[0]"
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings = self._cmds.ls(
            plan.settings_path,
            long=True,
            type="transform",
        ) or []
        if len(settings) != 1:
            raise FitSkeletonValidationError("Leg knee pin 设置节点无效")
        states = []
        for spec in plan.sides:
            typed = (
                (spec.upper_distance_name, "distanceBetween"),
                (spec.lower_distance_name, "distanceBetween"),
                (spec.local_lengths_name, "multiplyDivide"),
                (spec.clamp_name, "clamp"),
                (spec.pin_factors_name, "multiplyDivide"),
                (spec.factors_name, "blendColors"),
                (spec.ratio_terms_name, "multiplyDivide"),
                (spec.total_ratio_name, "plusMinusAverage"),
            )
            plug = f"{plan.settings_path}.{spec.attribute}"
            if (
                not self._cmds.objExists(plug)
                or any(
                    len(self._cmds.ls(name, type=node_type) or []) != 1
                    for name, node_type in typed
                )
            ):
                raise FitSkeletonValidationError(
                    "Leg knee pin 节点集合无效"
                )
            states.append(BodyLegKneePinSideState(
                side=spec.side,
                attribute_plug=plug,
                attribute_value=float(self._cmds.getAttr(plug)),
                upper_distance_name=spec.upper_distance_name,
                upper_matrix_sources=(
                    source(f"{spec.upper_distance_name}.inMatrix1"),
                    source(f"{spec.upper_distance_name}.inMatrix2"),
                ),
                lower_distance_name=spec.lower_distance_name,
                lower_matrix_sources=(
                    source(f"{spec.lower_distance_name}.inMatrix1"),
                    source(f"{spec.lower_distance_name}.inMatrix2"),
                ),
                local_lengths_name=spec.local_lengths_name,
                local_distance_sources=(
                    source(f"{spec.local_lengths_name}.input1X"),
                    source(f"{spec.local_lengths_name}.input1Y"),
                ),
                global_scale_sources=(
                    source(f"{spec.local_lengths_name}.input2X"),
                    source(f"{spec.local_lengths_name}.input2Y"),
                ),
                local_operation=int(self._cmds.getAttr(
                    f"{spec.local_lengths_name}.operation"
                )),
                clamp_name=spec.clamp_name,
                clamp_sources=(
                    source(f"{spec.clamp_name}.inputR"),
                    source(f"{spec.clamp_name}.inputG"),
                ),
                minimum_lengths=(
                    float(self._cmds.getAttr(f"{spec.clamp_name}.minR")),
                    float(self._cmds.getAttr(f"{spec.clamp_name}.minG")),
                ),
                maximum_lengths=(
                    float(self._cmds.getAttr(f"{spec.clamp_name}.maxR")),
                    float(self._cmds.getAttr(f"{spec.clamp_name}.maxG")),
                ),
                pin_factors_name=spec.pin_factors_name,
                pin_length_sources=(
                    source(f"{spec.pin_factors_name}.input1X"),
                    source(f"{spec.pin_factors_name}.input1Y"),
                ),
                base_divisors=(
                    float(self._cmds.getAttr(
                        f"{spec.pin_factors_name}.input2X"
                    )),
                    float(self._cmds.getAttr(
                        f"{spec.pin_factors_name}.input2Y"
                    )),
                ),
                pin_operation=int(self._cmds.getAttr(
                    f"{spec.pin_factors_name}.operation"
                )),
                factors_name=spec.factors_name,
                pin_factor_sources=(
                    source(f"{spec.factors_name}.color1R"),
                    source(f"{spec.factors_name}.color1G"),
                ),
                normal_factor_sources=(
                    source(f"{spec.factors_name}.color2R"),
                    source(f"{spec.factors_name}.color2G"),
                ),
                weight_source=source(f"{spec.factors_name}.blender"),
                ratio_terms_name=spec.ratio_terms_name,
                ratio_factor_sources=(
                    source(f"{spec.ratio_terms_name}.input1X"),
                    source(f"{spec.ratio_terms_name}.input1Y"),
                ),
                ratio_weights=(
                    float(self._cmds.getAttr(
                        f"{spec.ratio_terms_name}.input2X"
                    )),
                    float(self._cmds.getAttr(
                        f"{spec.ratio_terms_name}.input2Y"
                    )),
                ),
                ratio_operation=int(self._cmds.getAttr(
                    f"{spec.ratio_terms_name}.operation"
                )),
                total_ratio_name=spec.total_ratio_name,
                ratio_term_sources=(
                    source(f"{spec.total_ratio_name}.input1D[0]"),
                    source(f"{spec.total_ratio_name}.input1D[1]"),
                ),
                total_operation=int(self._cmds.getAttr(
                    f"{spec.total_ratio_name}.operation"
                )),
                factor_destinations=spec.factor_destinations,
                factor_destination_sources=tuple(
                    source(destination)
                    for destination in spec.factor_destinations
                ),
            ))
        return BodyLegKneePinSnapshot(settings[0], tuple(states))

    def prepare_body_arm_twist_runtime(self) -> None:
        self._prepare_body_limb_twist_runtime("Arm")

    def prepare_body_leg_twist_runtime(self) -> None:
        self._prepare_body_limb_twist_runtime("Leg")

    def _prepare_body_limb_twist_runtime(self, limb_label: str) -> None:
        try:
            if not self._cmds.pluginInfo("quatNodes", query=True, loaded=True):
                self._cmds.loadPlugin("quatNodes", quiet=True)
        except Exception as exc:
            raise FitSkeletonValidationError(
                f"{limb_label} twist 需要 Maya 自带 quatNodes 插件"
            ) from exc
        if "quatToEuler" not in (self._cmds.allNodeTypes() or []):
            raise FitSkeletonValidationError(
                f"{limb_label} twist 缺少 quatToEuler 节点"
            )

    def create_body_arm_twist_root(self, name: str) -> str:
        return self._create_body_limb_twist_root("Arm", name)

    def create_body_leg_twist_root(self, name: str) -> str:
        return self._create_body_limb_twist_root("Leg", name)

    def _create_body_limb_twist_root(
        self,
        limb_label: str,
        name: str,
    ) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(
                f"{limb_label} twist 根名称冲突：{name}"
            )
        if "quatToEuler" not in (self._cmds.allNodeTypes() or []):
            raise FitSkeletonValidationError(
                f"{limb_label} twist 运行依赖在执行前失效"
            )
        self._transaction_changed = True
        root = self._cmds.createNode("transform", name=name, skipSelect=True)
        return (self._cmds.ls(root, long=True) or [root])[0]

    def create_body_arm_twist_segment(self, spec: BodyArmTwistSegmentSpec) -> None:
        self._create_body_limb_twist_segment("Arm", spec)

    def create_body_leg_twist_segment(self, spec: BodyLegTwistSegmentSpec) -> None:
        self._create_body_limb_twist_segment("Leg", spec)

    def _create_body_limb_twist_segment(
        self,
        limb_label: str,
        spec: BodyLimbTwistSegmentSpec,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        names = (
            spec.name,
            spec.constraint_name,
            spec.compose_name,
            spec.decompose_name,
            spec.quaternion_name,
        )
        try:
            if any(self.find_name_collisions(name) for name in names):
                raise FitSkeletonValidationError(
                    f"{limb_label} twist 段驱动名称冲突"
                )
            if any(
                not self._cmds.objExists(path)
                for path in (spec.parent_path, spec.start_joint, spec.end_joint)
            ):
                raise FitSkeletonValidationError(
                    f"{limb_label} twist 段父级或 Body 端点失效"
                )
            end_parents = self._cmds.listRelatives(
                spec.end_joint,
                parent=True,
                fullPath=True,
            ) or []
            if end_parents != [spec.start_joint]:
                raise FitSkeletonValidationError(
                    f"{limb_label} twist 端点不再是直接父子链"
                )
            self._transaction_changed = True
            base = self._cmds.createNode(
                "transform",
                name=spec.name,
                parent=spec.parent_path,
                skipSelect=True,
            )
            base = (self._cmds.ls(base, long=True) or [base])[0]
            self._cmds.xform(
                base,
                worldSpace=True,
                matrix=self._cmds.xform(
                    spec.start_joint,
                    query=True,
                    worldSpace=True,
                    matrix=True,
                ),
            )
            if base != spec.path:
                raise RuntimeError(f"{limb_label} twist 段基座路径漂移")
            self._cmds.parentConstraint(
                spec.start_joint,
                base,
                maintainOffset=False,
                name=spec.constraint_name,
            )
            compose = self._cmds.createNode("composeMatrix", name=spec.compose_name)
            decompose = self._cmds.createNode("decomposeMatrix", name=spec.decompose_name)
            quaternion = self._cmds.createNode("quatToEuler", name=spec.quaternion_name)
            self._cmds.connectAttr(f"{spec.end_joint}.rotate", f"{compose}.inputRotate")
            self._cmds.connectAttr(
                f"{spec.end_joint}.rotateOrder",
                f"{compose}.inputRotateOrder",
            )
            self._cmds.connectAttr(f"{compose}.outputMatrix", f"{decompose}.inputMatrix")
            self._cmds.connectAttr(
                f"{decompose}.outputQuat{spec.axis}",
                f"{quaternion}.inputQuat{spec.axis}",
            )
            self._cmds.connectAttr(
                f"{decompose}.outputQuatW",
                f"{quaternion}.inputQuatW",
            )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def create_body_arm_twist_joint(self, spec: BodyArmTwistJointSpec) -> None:
        self._create_body_limb_twist_joint("Arm", spec)

    def create_body_leg_twist_joint(self, spec: BodyLegTwistJointSpec) -> None:
        self._create_body_limb_twist_joint("Leg", spec)

    def _create_body_limb_twist_joint(
        self,
        limb_label: str,
        spec: BodyLimbTwistJointSpec,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if any(
                self.find_name_collisions(name)
                for name in (spec.name, spec.constraint_name, spec.multiplier_name)
            ):
                raise FitSkeletonValidationError(
                    f"{limb_label} twist joint、约束或角度节点名称冲突"
                )
            if any(not self._cmds.objExists(path) for path in (spec.parent_path, spec.start_joint, spec.end_joint)):
                raise FitSkeletonValidationError(
                    f"{limb_label} twist 父级或 Body 端点在执行前失效"
                )
            self._transaction_changed = True
            joint = self._cmds.createNode("joint", name=spec.name, parent=spec.parent_path, skipSelect=True)
            joint = (self._cmds.ls(joint, long=True) or [joint])[0]
            self._cmds.xform(joint, worldSpace=True, translation=spec.world_position)
            self._cmds.setAttr(f"{joint}.side", _MAYA_SIDE_FROM_CORE[spec.side])
            if joint != spec.path:
                raise RuntimeError(f"{limb_label} twist joint 路径漂移")
            constraint = self._cmds.pointConstraint(
                spec.start_joint,
                spec.end_joint,
                joint,
                maintainOffset=False,
                name=spec.constraint_name,
            )[0]
            aliases = self._cmds.pointConstraint(constraint, query=True, weightAliasList=True) or []
            if len(aliases) != 2:
                raise RuntimeError(f"{limb_label} twist 双端权重别名无效")
            self._cmds.setAttr(f"{constraint}.{aliases[0]}", 1.0 - spec.fraction)
            self._cmds.setAttr(f"{constraint}.{aliases[1]}", spec.fraction)
            multiplier = self._cmds.createNode(
                "unitConversion",
                name=spec.multiplier_name,
            )
            self._cmds.setAttr(f"{multiplier}.conversionFactor", spec.fraction)
            self._cmds.connectAttr(
                f"{spec.quaternion_name}.outputRotate{spec.axis}",
                f"{multiplier}.input",
            )
            self._cmds.connectAttr(
                f"{multiplier}.output",
                f"{joint}.rotate{spec.axis}",
            )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_twist(self, plan: BodyArmTwistPlan) -> BodyArmTwistSnapshot:
        return self._capture_body_limb_twist("Arm", plan)

    def capture_body_leg_twist(self, plan: BodyLegTwistPlan) -> BodyLegTwistSnapshot:
        return self._capture_body_limb_twist("Leg", plan)

    def _capture_body_limb_twist(
        self,
        limb_label: str,
        plan: BodyLimbTwistPlan,
    ) -> BodyLimbTwistSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(f"{limb_label} twist 根节点无效")
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        segment_states = []
        for spec in plan.segments:
            bases = self._cmds.ls(spec.path, long=True, type="transform") or []
            constraints = self._cmds.ls(spec.constraint_name, type="parentConstraint") or []
            typed_nodes = (
                (spec.compose_name, "composeMatrix"),
                (spec.decompose_name, "decomposeMatrix"),
                (spec.quaternion_name, "quatToEuler"),
            )
            if (
                len(bases) != 1
                or len(constraints) != 1
                or any(len(self._cmds.ls(name, type=node_type) or []) != 1 for name, node_type in typed_nodes)
            ):
                raise FitSkeletonValidationError(
                    f"{limb_label} twist 段驱动节点无效"
                )
            base, constraint = bases[0], constraints[0]
            parents = self._cmds.listRelatives(base, parent=True, fullPath=True) or []
            targets = self._cmds.parentConstraint(
                constraint,
                query=True,
                targetList=True,
            ) or []
            target_paths = tuple(
                (self._cmds.ls(target, long=True) or [target])[0]
                for target in targets
            )
            outputs = self._cmds.listConnections(
                f"{constraint}.constraintTranslateX",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            segment_states.append(
                BodyLimbTwistSegmentState(
                    side=spec.side,
                    segment=spec.segment,
                    path=base,
                    parent_path=parents[0] if parents else None,
                    constraint_name=constraint,
                    targets=target_paths,
                    driven_path=self._resolve_connected_node(outputs[0]) if len(outputs) == 1 else None,
                    compose_name=spec.compose_name,
                    rotate_source=source(f"{spec.compose_name}.inputRotate"),
                    rotate_order_source=source(f"{spec.compose_name}.inputRotateOrder"),
                    decompose_name=spec.decompose_name,
                    decompose_source=source(f"{spec.decompose_name}.inputMatrix"),
                    quaternion_name=spec.quaternion_name,
                    quaternion_axis_source=source(
                        f"{spec.quaternion_name}.inputQuat{spec.axis}"
                    ),
                    quaternion_w_source=source(f"{spec.quaternion_name}.inputQuatW"),
                    axis=spec.axis,
                )
            )

        states = []
        for spec in plan.joints:
            joints = self._cmds.ls(spec.path, long=True, type="joint") or []
            constraints = self._cmds.ls(spec.constraint_name, type="pointConstraint") or []
            multipliers = self._cmds.ls(spec.multiplier_name, type="unitConversion") or []
            if len(joints) != 1 or len(constraints) != 1 or len(multipliers) != 1:
                raise FitSkeletonValidationError(
                    f"{limb_label} twist joint、位置约束或角度节点无效"
                )
            joint, constraint = joints[0], constraints[0]
            parents = self._cmds.listRelatives(joint, parent=True, fullPath=True) or []
            targets = self._cmds.pointConstraint(constraint, query=True, targetList=True) or []
            target_paths = tuple((self._cmds.ls(target, long=True) or [target])[0] for target in targets)
            aliases = self._cmds.pointConstraint(constraint, query=True, weightAliasList=True) or []
            weights = tuple(float(self._cmds.getAttr(f"{constraint}.{alias}")) for alias in aliases)
            outputs = self._cmds.listConnections(f"{constraint}.constraintTranslateX", source=False, destination=True, plugs=True) or []
            driven = self._resolve_connected_node(outputs[0]) if len(outputs) == 1 else None
            orthogonal_axes = tuple(axis for axis in "XYZ" if axis != spec.axis)
            states.append(BodyLimbTwistJointState(
                side=spec.side,
                segment=spec.segment,
                path=joint,
                parent_path=parents[0] if parents else None,
                world_position=tuple(float(value) for value in self._cmds.xform(joint, query=True, worldSpace=True, translation=True)),
                constraint_name=constraint,
                targets=target_paths,
                weights=weights,
                driven_joint=driven,
                multiplier_name=spec.multiplier_name,
                twist_source=source(f"{spec.multiplier_name}.input"),
                multiplier_scale=float(self._cmds.getAttr(f"{spec.multiplier_name}.conversionFactor")),
                rotate_axis_source=source(f"{joint}.rotate{spec.axis}"),
                orthogonal_rotations=tuple(
                    float(self._cmds.getAttr(f"{joint}.rotate{axis}"))
                    for axis in orthogonal_axes
                ),
                axis=spec.axis,
            ))
        return BodyLimbTwistSnapshot(
            roots[0],
            tuple(segment_states),
            tuple(states),
        )

    def create_body_arm_volume(self, plan: BodyArmVolumePlan) -> None:
        self._create_body_limb_volume("Arm", plan)

    def create_body_leg_volume(self, plan: BodyLegVolumePlan) -> None:
        self._create_body_limb_volume("Leg", plan)

    def _create_body_limb_volume(
        self,
        limb_label: str,
        plan: BodyLimbVolumePlan,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            settings = self._cmds.ls(
                plan.settings_path,
                long=True,
                type="transform",
            ) or []
            if len(settings) != 1 or settings[0] != plan.settings_path:
                raise FitSkeletonValidationError(
                    f"{limb_label} 体积设置节点失效"
                )
            for spec in plan.sides:
                plug = f"{plan.settings_path}.{spec.attribute}"
                if (
                    self._cmds.attributeQuery(
                        spec.attribute,
                        node=plan.settings_path,
                        exists=True,
                    )
                    or any(
                        self.find_name_collisions(name)
                        for name in (
                            spec.mode_blend_name,
                            spec.power_name,
                            spec.blend_name,
                        )
                    )
                    or len(spec.helper_scale_axes) != len(spec.helper_joints)
                    or any(
                        not self._cmds.objExists(path)
                        for path in spec.helper_joints
                    )
                    or not self._cmds.objExists(spec.stretch_ratio_source)
                    or not self._cmds.objExists(
                        f"{plan.settings_path}.{spec.mode_attribute}"
                    )
                ):
                    raise FitSkeletonValidationError(
                        f"{limb_label} 体积输入或名称在执行前失效"
                    )
                self._transaction_changed = True
                self._cmds.addAttr(
                    plan.settings_path,
                    longName=spec.attribute,
                    attributeType="double",
                    minValue=0.0,
                    maxValue=1.0,
                    defaultValue=1.0,
                    keyable=True,
                )
                mode_blend = self._cmds.createNode(
                    "blendColors",
                    name=spec.mode_blend_name,
                )
                self._cmds.connectAttr(
                    spec.stretch_ratio_source,
                    f"{mode_blend}.color1R",
                )
                self._cmds.setAttr(f"{mode_blend}.color2R", 1.0)
                self._cmds.connectAttr(
                    f"{plan.settings_path}.{spec.mode_attribute}",
                    f"{mode_blend}.blender",
                )
                power = self._cmds.createNode(
                    "multiplyDivide",
                    name=spec.power_name,
                )
                self._cmds.setAttr(f"{power}.operation", 3)
                self._cmds.setAttr(f"{power}.input2X", spec.exponent)
                self._cmds.connectAttr(f"{mode_blend}.outputR", f"{power}.input1X")
                blend = self._cmds.createNode(
                    "blendColors",
                    name=spec.blend_name,
                )
                self._cmds.connectAttr(f"{power}.outputX", f"{blend}.color1R")
                self._cmds.setAttr(f"{blend}.color2R", 1.0)
                self._cmds.connectAttr(plug, f"{blend}.blender")
                for helper, axes in zip(
                    spec.helper_joints,
                    spec.helper_scale_axes,
                ):
                    for axis in axes:
                        self._cmds.connectAttr(
                            f"{blend}.outputR",
                            f"{helper}.scale{axis}",
                        )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_volume(
        self,
        plan: BodyArmVolumePlan,
    ) -> BodyArmVolumeSnapshot:
        return self._capture_body_limb_volume("Arm", plan)

    def capture_body_leg_volume(
        self,
        plan: BodyLegVolumePlan,
    ) -> BodyLegVolumeSnapshot:
        return self._capture_body_limb_volume("Leg", plan)

    def _capture_body_limb_volume(
        self,
        limb_label: str,
        plan: BodyLimbVolumePlan,
    ) -> BodyLimbVolumeSnapshot:
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings = self._cmds.ls(
            plan.settings_path,
            long=True,
            type="transform",
        ) or []
        if len(settings) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} 体积设置节点无效"
            )
        states = []
        for spec in plan.sides:
            plug = f"{plan.settings_path}.{spec.attribute}"
            mode_blend = self._cmds.ls(spec.mode_blend_name, type="blendColors") or []
            power = self._cmds.ls(spec.power_name, type="multiplyDivide") or []
            blend = self._cmds.ls(spec.blend_name, type="blendColors") or []
            helpers = tuple(
                self._cmds.ls(path, long=True, type="joint") or []
                for path in spec.helper_joints
            )
            if (
                not self._cmds.objExists(plug)
                or len(mode_blend) != 1
                or len(power) != 1
                or len(blend) != 1
                or len(spec.helper_scale_axes) != len(spec.helper_joints)
                or any(len(values) != 1 for values in helpers)
            ):
                raise FitSkeletonValidationError(
                    f"{limb_label} 体积节点集合无效"
                )
            states.append(
                BodyLimbVolumeSideState(
                    side=spec.side,
                    attribute_plug=plug,
                    attribute_value=float(self._cmds.getAttr(plug)),
                    mode_blend_name=spec.mode_blend_name,
                    stretch_ratio_source=source(
                        f"{spec.mode_blend_name}.color1R"
                    ),
                    mode_weight_source=source(
                        f"{spec.mode_blend_name}.blender"
                    ),
                    mode_base_ratio=float(self._cmds.getAttr(
                        f"{spec.mode_blend_name}.color2R"
                    )),
                    power_name=spec.power_name,
                    ratio_source=source(f"{spec.power_name}.input1X"),
                    exponent=float(self._cmds.getAttr(
                        f"{spec.power_name}.input2X"
                    )),
                    power_operation=int(self._cmds.getAttr(
                        f"{spec.power_name}.operation"
                    )),
                    blend_name=spec.blend_name,
                    power_source=source(f"{spec.blend_name}.color1R"),
                    volume_source=source(f"{spec.blend_name}.blender"),
                    base_scale=float(self._cmds.getAttr(
                        f"{spec.blend_name}.color2R"
                    )),
                    helper_scale_sources=tuple(
                        (
                            path,
                            source(f"{path}.scale{axes[0]}"),
                            source(f"{path}.scale{axes[1]}"),
                        )
                        for path, axes in zip(
                            spec.helper_joints,
                            spec.helper_scale_axes,
                        )
                    ),
                    helper_scale_axes=spec.helper_scale_axes,
                )
            )
        return BodyLimbVolumeSnapshot(settings[0], tuple(states))

    def capture_skin_bind_input(self, plan: SkinBindPlan) -> SkinBindInputState:
        meshes = self._cmds.ls(plan.mesh_path, long=True, type="transform") or []
        mesh = meshes[0] if len(meshes) == 1 else None
        shapes = tuple(
            self._cmds.listRelatives(
                mesh,
                shapes=True,
                noIntermediate=True,
                fullPath=True,
                type="mesh",
            ) or []
        ) if mesh else ()
        vertex_count = (
            int(self._cmds.polyEvaluate(mesh, vertex=True))
            if mesh and len(shapes) == 1
            else 0
        )
        available = []
        for path in plan.influence_paths:
            matches = self._cmds.ls(path, long=True, type="joint") or []
            if len(matches) == 1 and matches[0] == path:
                available.append(path)
        history = (
            self._cmds.listHistory(shapes[0], pruneDagObjects=True) or []
            if len(shapes) == 1
            else []
        )
        skin_clusters = tuple(
            sorted(
                node
                for node in history
                if self._cmds.nodeType(node) == "skinCluster"
            )
        )
        return SkinBindInputState(
            mesh,
            shapes,
            vertex_count,
            tuple(available),
            skin_clusters,
        )

    def create_skin_bind(self, plan: SkinBindPlan) -> None:
        self._require_transaction()
        if self.find_name_collisions(plan.skin_name):
            raise FitSkeletonValidationError(f"Skin Bind 节点名称冲突：{plan.skin_name}")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            created = self._cmds.skinCluster(
                list(plan.influence_paths),
                plan.mesh_path,
                toSelectedBones=True,
                bindMethod=0,
                normalizeWeights=1,
                maximumInfluences=plan.maximum_influences,
                obeyMaxInfluences=plan.maintain_maximum_influences,
                name=plan.skin_name,
            )
            if not created or created[0] != plan.skin_name:
                raise RuntimeError("Maya 未按计划创建 skinCluster")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_skin_bind(self, plan: SkinBindPlan) -> SkinBindSnapshot:
        clusters = self._cmds.ls(plan.skin_name, type="skinCluster") or []
        if len(clusters) != 1:
            raise FitSkeletonValidationError("Skin Bind 结果节点无效")
        skin = clusters[0]
        geometry = []
        for shape in self._cmds.skinCluster(skin, query=True, geometry=True) or []:
            shape_paths = self._cmds.ls(shape, long=True, type="mesh") or []
            parents = (
                self._cmds.listRelatives(
                    shape_paths[0],
                    parent=True,
                    fullPath=True,
                ) or []
                if len(shape_paths) == 1
                else []
            )
            if len(parents) == 1:
                geometry.append(parents[0])
        influences = []
        for joint in self._cmds.skinCluster(skin, query=True, influence=True) or []:
            matches = self._cmds.ls(joint, long=True, type="joint") or []
            if len(matches) == 1:
                influences.append(matches[0])
        bind_method = {0: SkinBindMethod.CLOSEST_DISTANCE}.get(
            int(self._cmds.getAttr(f"{skin}.bindMethod"))
        )
        normalization = {1: SkinWeightNormalization.INTERACTIVE}.get(
            int(self._cmds.getAttr(f"{skin}.normalizeWeights"))
        )
        return SkinBindSnapshot(
            skin,
            tuple(geometry),
            tuple(influences),
            int(self._cmds.getAttr(f"{skin}.maxInfluences")),
            bool(self._cmds.getAttr(f"{skin}.maintainMaxInfluences")),
            bind_method,
            normalization,
        )

    def capture_skin_weight_input(
        self,
        request: SkinWeightEditRequest,
    ) -> SkinWeightInputState:
        return self._capture_skin_weight_state(
            request.skin_name,
            tuple(vertex.vertex_index for vertex in request.vertices),
        )

    def capture_all_skin_weights(
        self,
        skin_name: str,
        mesh_path: str,
    ) -> SkinWeightInputState:
        del mesh_path
        return self._capture_skin_weight_state(skin_name, None)

    def capture_skin_vertices(
        self,
        skin_name: str,
        mesh_path: str,
        vertex_indices: tuple[int, ...],
    ) -> SkinWeightInputState:
        del mesh_path
        return self._capture_skin_weight_state(skin_name, vertex_indices)

    def capture_mesh_vertex_positions(self, mesh_path: str) -> SkinMeshGeometryState:
        matches = self._cmds.ls(mesh_path, long=True, type="transform") or []
        if len(matches) != 1 or matches[0] != mesh_path:
            return SkinMeshGeometryState(None, 0, ())
        shapes = self._cmds.listRelatives(
            mesh_path,
            shapes=True,
            noIntermediate=True,
            fullPath=True,
            type="mesh",
        ) or []
        if len(shapes) != 1:
            return SkinMeshGeometryState(None, 0, ())
        vertex_count = int(self._cmds.polyEvaluate(mesh_path, vertex=True))
        vertices = tuple(
            SkinMeshVertexPosition(
                index,
                tuple(
                    float(value)
                    for value in self._cmds.pointPosition(
                        f"{mesh_path}.vtx[{index}]",
                        world=True,
                    )
                ),
            )
            for index in range(vertex_count)
        )
        return SkinMeshGeometryState(mesh_path, vertex_count, vertices)

    def _capture_skin_weight_state(
        self,
        skin_name: str,
        vertex_indices: tuple[int, ...] | None,
    ) -> SkinWeightInputState:
        clusters = self._cmds.ls(skin_name, type="skinCluster") or []
        if len(clusters) != 1:
            return SkinWeightInputState(None, None, 0, (), (), 0, False, ())
        skin = clusters[0]
        geometry = []
        bound_shapes = []
        for shape in self._cmds.skinCluster(skin, query=True, geometry=True) or []:
            shape_paths = self._cmds.ls(shape, long=True, type="mesh") or []
            parents = (
                self._cmds.listRelatives(
                    shape_paths[0],
                    parent=True,
                    fullPath=True,
                ) or []
                if len(shape_paths) == 1
                else []
            )
            if len(parents) == 1:
                geometry.append(parents[0])
                bound_shapes.append(shape_paths[0])
        mesh = geometry[0] if len(geometry) == 1 else None
        bound_shape = bound_shapes[0] if mesh else None
        vertex_count = int(self._cmds.polyEvaluate(mesh, vertex=True)) if mesh else 0
        influences = []
        locked = []
        for joint in self._cmds.skinCluster(skin, query=True, influence=True) or []:
            matches = self._cmds.ls(joint, long=True, type="joint") or []
            if len(matches) != 1:
                continue
            path = matches[0]
            influences.append(path)
            if self._cmds.attributeQuery(
                "lockInfluenceWeights",
                node=path,
                exists=True,
            ) and self._cmds.getAttr(f"{path}.lockInfluenceWeights"):
                locked.append(path)
        vertices = []
        if mesh:
            vertices = list(self._capture_skin_vertices_api(
                skin, bound_shape, vertex_count, tuple(influences), vertex_indices))
        return SkinWeightInputState(
            skin,
            mesh,
            vertex_count,
            tuple(influences),
            tuple(locked),
            int(self._cmds.getAttr(f"{skin}.maxInfluences")),
            bool(self._cmds.getAttr(f"{skin}.maintainMaxInfluences")),
            tuple(vertices),
        )

    def _capture_skin_vertices_api(
        self, skin: str, shape: str, vertex_count: int,
        influences: tuple[str, ...],
        vertex_indices: tuple[int, ...] | None,
    ) -> tuple[SkinVertexWeights, ...]:
        from maya.api import OpenMaya as om
        from maya.api import OpenMayaAnim as oma

        selection = om.MSelectionList()
        selection.add(self.scene_address(skin))
        skin_fn = oma.MFnSkinCluster(selection.getDependNode(0))
        selection = om.MSelectionList()
        selection.add(self.scene_address(shape))
        dag = selection.getDagPath(0)
        influence_order = {path.fullPathName(): index
                           for index, path in enumerate(skin_fn.influenceObjects())}
        if any(self.scene_address(path) not in influence_order for path in influences):
            raise RuntimeError("skinCluster API 影响关节集合与场景查询不一致")
        requested = (tuple(range(vertex_count)) if vertex_indices is None
                     else tuple(index for index in vertex_indices if index < vertex_count))
        unique = requested if vertex_indices is None else tuple(sorted(set(requested)))
        rows = []
        for start in range(0, len(unique), 4096):
            indices = unique[start:start + 4096]
            component_fn = om.MFnSingleIndexedComponent()
            component = component_fn.create(om.MFn.kMeshVertComponent)
            component_fn.addElements(indices)
            component_indices = tuple(int(index) for index in component_fn.getElements())
            values, influence_count = skin_fn.getWeights(dag, component)
            if (influence_count != len(influence_order)
                    or len(values) != len(component_indices) * influence_count
                    or set(component_indices) != set(indices)):
                raise RuntimeError("skinCluster API 返回的权重矩阵维度无效")
            for offset, vertex_index in enumerate(component_indices):
                weights = []
                for path in influences:
                    value = float(values[offset * influence_count
                        + influence_order[self.scene_address(path)]])
                    if value > SKIN_WEIGHT_VISIBLE_THRESHOLD:
                        weights.append(SkinInfluenceWeight(path, value))
                rows.append(SkinVertexWeights(vertex_index, tuple(weights)))
        if vertex_indices is None:
            return tuple(rows)
        by_index = {row.vertex_index: row for row in rows}
        return tuple(by_index[index] for index in requested)

    def apply_skin_weight_changes(
        self,
        request: SkinWeightEditRequest,
        changes: tuple[SkinWeightChange, ...],
    ) -> None:
        self._require_transaction()
        if not changes:
            return
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            for change in changes:
                self._cmds.skinPercent(
                    request.skin_name,
                    f"{request.mesh_path}.vtx[{change.vertex_index}]",
                    transformValue=[
                        (entry.influence_path, entry.weight)
                        for entry in change.after
                    ],
                    normalize=False,
                    zeroRemainingInfluences=True,
                )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_fk_to_ik_state(self, plan: BodyArmFkToIkPlan) -> BodyArmFkToIkSceneState:
        existing = tuple(path for path in plan.required_paths if self._cmds.objExists(path))
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug) and self._cmds.getAttr(plug, settable=True)
        )
        value = float(self._cmds.getAttr(plan.blend_plug)) if self._cmds.objExists(plan.blend_plug) else float("nan")
        return BodyArmFkToIkSceneState(existing, writable, value)

    def apply_body_arm_fk_to_ik(self, plan: BodyArmFkToIkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_arm_fk_to_ik_state(plan)
        if set(state.existing_paths) != set(plan.required_paths) or set(state.writable_plugs) != set(plan.required_writable_plugs) or abs(state.blend_value) > 1e-6:
            raise FitSkeletonValidationError("Arm FK→IK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            from .maya_limb_shape import begin_optional_match, finish_match
            shape_state=begin_optional_match(self,"arm",plan.side.value,"ik")
            from .maya_limb_orientation import begin_orientation_match, finish_orientation_match
            orientation_state=begin_orientation_match(self,"arm",plan.side.value)
            self._cmds.xform(plan.pole_control_path, worldSpace=True, translation=plan.pole_position)
            x_axis, y_axis, z_axis = plan.wrist_axes
            matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *plan.wrist_position, 1.0)
            self._cmds.xform(plan.wrist_control_path, worldSpace=True, translation=plan.wrist_position)
            self._spine_set_world_rotation(plan.wrist_control_path,matrix)
            self._cmds.setAttr(plan.blend_plug, 1.0)
            finish_orientation_match(self,"arm",plan.side.value,orientation_state)
            finish_match(self,shape_state)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_leg_fk_to_ik_state(
        self, plan: BodyLegFkToIkPlan
    ) -> BodyLegFkToIkSceneState:
        existing = tuple(
            path for path in plan.required_paths if self._cmds.objExists(path)
        )
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug)
            and self._cmds.getAttr(plug, settable=True)
        )
        value = (
            float(self._cmds.getAttr(plan.blend_plug))
            if self._cmds.objExists(plan.blend_plug)
            else float("nan")
        )
        positions = []
        for path in plan.body_joint_paths:
            if not self._cmds.objExists(path):
                break
            positions.append(tuple(float(item) for item in self._cmds.xform(
                path, query=True, worldSpace=True, translation=True
            )))
        ankle_axes = ()
        ankle_path = plan.body_joint_paths[2]
        if self._cmds.objExists(ankle_path):
            matrix = self._cmds.xform(
                ankle_path, query=True, worldSpace=True, matrix=True
            )
            ankle_axes = tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index:index + 3])
                )
                for index in (0, 4, 8)
            )
        toe_body_axes = ()
        if self._cmds.objExists(plan.toe_body_path):
            matrix = self._cmds.xform(
                plan.toe_body_path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            toe_body_axes = tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index:index + 3])
                )
                for index in (0, 4, 8)
            )
        foot_values = tuple(
            (plug, float(self._cmds.getAttr(plug)))
            for plug in plan.foot_attribute_plugs
            if self._cmds.objExists(plug)
        )
        return BodyLegFkToIkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            ankle_axes,
            toe_body_axes,
            foot_values,
        )

    def apply_body_leg_fk_to_ik(self, plan: BodyLegFkToIkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_leg_fk_to_ik_state(plan)
        if audit_body_leg_fk_to_ik_preflight(plan, state):
            raise FitSkeletonValidationError("Leg FK→IK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            from .maya_limb_shape import begin_optional_match, finish_match
            shape_state=begin_optional_match(self,"leg",plan.side.value,"ik")
            from .maya_limb_orientation import begin_orientation_match, finish_orientation_match
            orientation_state=begin_orientation_match(self,"leg",plan.side.value)
            for plug in plan.foot_attribute_plugs:
                self._cmds.setAttr(plug, 0.0)
            self._cmds.xform(
                plan.pole_control_path,
                worldSpace=True,
                translation=plan.pole_position,
            )
            x_axis, y_axis, z_axis = plan.ankle_axes
            matrix = (
                *x_axis, 0.0,
                *y_axis, 0.0,
                *z_axis, 0.0,
                *plan.ankle_position, 1.0,
            )
            self._cmds.xform(plan.ankle_control_path, worldSpace=True, translation=plan.ankle_position)
            self._spine_set_world_rotation(plan.ankle_control_path,matrix)
            toe_position = tuple(float(value) for value in self._cmds.xform(
                plan.toe_control_path,
                query=True,
                worldSpace=True,
                translation=True,
            ))
            toe_x, toe_y, toe_z = plan.toe_body_axes
            toe_matrix = (
                *toe_x, 0.0,
                *toe_y, 0.0,
                *toe_z, 0.0,
                *toe_position, 1.0,
            )
            self._spine_set_world_rotation(plan.toe_control_path,toe_matrix)
            self._cmds.setAttr(plan.blend_plug, 1.0)
            finish_orientation_match(self,"leg",plan.side.value,orientation_state)
            finish_match(self,shape_state)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_leg_ik_to_fk_state(
        self, plan: BodyLegIkToFkPlan
    ) -> BodyLegIkToFkSceneState:
        existing = tuple(
            path for path in plan.required_paths if self._cmds.objExists(path)
        )
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug)
            and self._cmds.getAttr(plug, settable=True)
        )
        value = (
            float(self._cmds.getAttr(plan.blend_plug))
            if self._cmds.objExists(plan.blend_plug)
            else float("nan")
        )
        positions = []
        axes = []
        for path in plan.body_joint_paths:
            if not self._cmds.objExists(path):
                break
            positions.append(tuple(float(item) for item in self._cmds.xform(
                path, query=True, worldSpace=True, translation=True
            )))
            matrix = self._cmds.xform(
                path, query=True, worldSpace=True, matrix=True
            )
            axes.append(tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index:index + 3])
                )
                for index in (0, 4, 8)
            ))
        segment_translations = tuple(
            float(self._cmds.getAttr(plug))
            for plug in plan.fk_segment_plugs
            if self._cmds.objExists(plug)
        )
        return BodyLegIkToFkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            tuple(axes),
            segment_translations,
        )

    def apply_body_leg_ik_to_fk(self, plan: BodyLegIkToFkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_leg_ik_to_fk_state(plan)
        if audit_body_leg_ik_to_fk_preflight(plan, state):
            raise FitSkeletonValidationError("Leg IK→FK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            from .maya_limb_shape import begin_optional_match, finish_match
            shape_state=begin_optional_match(self,"leg",plan.side.value,"fk")
            for path, target_axes in zip(
                plan.fk_control_paths, plan.fk_control_axes
            ):
                position = self._cmds.xform(
                    path, query=True, worldSpace=True, translation=True
                )
                x_axis, y_axis, z_axis = target_axes
                matrix = (
                    *x_axis, 0.0,
                    *y_axis, 0.0,
                    *z_axis, 0.0,
                    *position, 1.0,
                )
                self._spine_set_world_rotation(path,matrix)
            for plug, value in zip(
                plan.fk_segment_plugs,
                plan.fk_segment_translations,
            ):
                self._cmds.setAttr(plug, value)
            self._cmds.setAttr(plan.blend_plug, 0.0)
            finish_match(self,shape_state)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_ik_to_fk_state(self, plan: BodyArmIkToFkPlan) -> BodyArmIkToFkSceneState:
        existing = tuple(path for path in plan.required_paths if self._cmds.objExists(path))
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug) and self._cmds.getAttr(plug, settable=True)
        )
        value = float(self._cmds.getAttr(plan.blend_plug)) if self._cmds.objExists(plan.blend_plug) else float("nan")
        positions = []
        axes = []
        for path in plan.body_joint_paths:
            if not self._cmds.objExists(path):
                break
            positions.append(tuple(float(item) for item in self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )))
            matrix = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            axes.append(tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            ))
        segment_translations = tuple(
            float(self._cmds.getAttr(plug))
            for plug in plan.fk_segment_plugs
            if self._cmds.objExists(plug)
        )
        return BodyArmIkToFkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            tuple(axes),
            segment_translations,
        )

    def apply_body_arm_ik_to_fk(self, plan: BodyArmIkToFkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_arm_ik_to_fk_state(plan)
        if set(state.existing_paths) != set(plan.required_paths) or set(state.writable_plugs) != set(plan.required_writable_plugs) or abs(state.blend_value - 1.0) > 1e-6:
            raise FitSkeletonValidationError("Arm IK→FK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            from .maya_limb_shape import begin_optional_match, finish_match
            shape_state=begin_optional_match(self,"arm",plan.side.value,"fk")
            for path, target_axes in zip(plan.fk_control_paths, plan.fk_control_axes):
                position = self._cmds.xform(path, query=True, worldSpace=True, translation=True)
                x_axis, y_axis, z_axis = target_axes
                matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *position, 1.0)
                self._spine_set_world_rotation(path,matrix)
            for plug, value in zip(
                plan.fk_segment_plugs,
                plan.fk_segment_translations,
            ):
                self._cmds.setAttr(plug, value)
            self._cmds.setAttr(plan.blend_plug, 0.0)
            finish_match(self,shape_state)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def create_body_arm_ik(self, spec: BodyArmIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            for name in (spec.wrist_offset_name, spec.wrist_control_name, spec.pole_offset_name, spec.pole_control_name, spec.handle_name, spec.pole_constraint_name, spec.wrist_constraint_name):
                if self.find_name_collisions(name):
                    raise FitSkeletonValidationError(f"Arm IK 名称冲突：{name}")
            if any(not self._cmds.objExists(path) for path in spec.chain):
                raise FitSkeletonValidationError("Arm IK mechanism chain 在执行前失效")
            self._transaction_changed = True
            wrist_offset = self._cmds.createNode("transform", name=spec.wrist_offset_name, parent=spec.root_path, skipSelect=True)
            wrist_offset = (self._cmds.ls(wrist_offset, long=True) or [wrist_offset])[0]
            x_axis, y_axis, z_axis = spec.wrist_axes
            matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *spec.wrist_position, 1.0)
            self._cmds.xform(wrist_offset, worldSpace=True, matrix=matrix)
            wrist = self._cmds.circle(name=spec.wrist_control_name, normal=(1, 0, 0), radius=spec.radius, degree=3, sections=12, constructionHistory=False)[0]
            wrist = self._cmds.parent(wrist, wrist_offset, relative=True)[0]
            wrist = (self._cmds.ls(wrist, long=True) or [wrist])[0]
            pole_offset = self._cmds.createNode("transform", name=spec.pole_offset_name, parent=spec.root_path, skipSelect=True)
            pole_offset = (self._cmds.ls(pole_offset, long=True) or [pole_offset])[0]
            self._cmds.xform(pole_offset, worldSpace=True, translation=spec.pole_position)
            pole = self._cmds.circle(name=spec.pole_control_name, normal=(0, 0, 1), radius=spec.radius * 0.65, degree=3, sections=8, constructionHistory=False)[0]
            pole = self._cmds.parent(pole, pole_offset, relative=True)[0]
            pole = (self._cmds.ls(pole, long=True) or [pole])[0]
            if wrist != spec.wrist_control_path or pole != spec.pole_control_path:
                raise RuntimeError("Arm IK 控制路径漂移")
            handle, _ = self._cmds.ikHandle(name=spec.handle_name, startJoint=spec.chain[0], endEffector=spec.chain[2], solver="ikRPsolver")
            self._cmds.parent(handle, wrist, absolute=True)
            self._cmds.poleVectorConstraint(pole, handle, name=spec.pole_constraint_name)
            self._cmds.orientConstraint(
                wrist,
                spec.chain[2],
                maintainOffset=False,
                name=spec.wrist_constraint_name,
            )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_ik(self, plan: BodyArmIkPlan) -> BodyArmIkSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1: raise FitSkeletonValidationError("Arm IK 控制根节点无效")
        states = []
        for spec in plan.limbs:
            wrist = (self._cmds.ls(spec.wrist_control_path, long=True, type="transform") or [None])[0]
            pole = (self._cmds.ls(spec.pole_control_path, long=True, type="transform") or [None])[0]
            handles = self._cmds.ls(spec.handle_name, long=True, type="ikHandle") or []
            constraints = self._cmds.ls(spec.pole_constraint_name, type="poleVectorConstraint") or []
            wrist_constraints = self._cmds.ls(spec.wrist_constraint_name, type="orientConstraint") or []
            if wrist is None or pole is None or len(handles) != 1 or len(constraints) != 1 or len(wrist_constraints) != 1:
                raise FitSkeletonValidationError("Arm IK 节点集合无效")
            handle = handles[0]
            wp = self._cmds.listRelatives(wrist, parent=True, fullPath=True) or []
            pp = self._cmds.listRelatives(pole, parent=True, fullPath=True) or []
            hp = self._cmds.listRelatives(handle, parent=True, fullPath=True) or []
            joint_list = tuple((self._cmds.ls(value, long=True) or [value])[0] for value in (self._cmds.ikHandle(handle, query=True, jointList=True) or []))
            targets = self._cmds.poleVectorConstraint(constraints[0], query=True, targetList=True) or []
            pole_source = (self._cmds.ls(targets[0], long=True) or [targets[0]])[0] if len(targets) == 1 else None
            wrist_targets = self._cmds.orientConstraint(wrist_constraints[0], query=True, targetList=True) or []
            wrist_source = (self._cmds.ls(wrist_targets[0], long=True) or [wrist_targets[0]])[0] if len(wrist_targets) == 1 else None
            wrist_outputs = self._cmds.listConnections(f"{wrist_constraints[0]}.constraintRotateX", source=False, destination=True, plugs=True) or []
            wrist_driven = self._resolve_connected_node(wrist_outputs[0]) if len(wrist_outputs) == 1 else None
            def shape_type(node):
                shapes = self._cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or []
                return self._cmds.nodeType(shapes[0]) if len(shapes) == 1 else None
            def vector(node, attr): return tuple(float(v) for v in self._cmds.getAttr(f"{node}.{attr}")[0])
            states.append(BodyArmIkState(
                spec.side, wrist, wp[0] if wp else None, pole, pp[0] if pp else None,
                spec.handle_name, constraints[0], hp[0] if hp else None, joint_list, pole_source,
                tuple(float(v) for v in self._cmds.xform(wrist, query=True, worldSpace=True, translation=True)),
                tuple(float(v) for v in self._cmds.xform(pole, query=True, worldSpace=True, translation=True)),
                shape_type(wrist), shape_type(pole), vector(wrist, "translate"), vector(wrist, "rotate"), vector(pole, "translate"), vector(pole, "rotate"),
                wrist_constraints[0], wrist_source, wrist_driven,
            ))
        return BodyArmIkSnapshot(roots[0], tuple(states))

    def create_body_leg_ik(self, spec: BodyLegIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            names = (
                spec.ankle_offset_name,
                spec.ankle_control_name,
                spec.pole_offset_name,
                spec.pole_control_name,
                spec.handle_name,
                spec.pole_constraint_name,
                spec.ankle_constraint_name,
            )
            if any(self.find_name_collisions(name) for name in names):
                raise FitSkeletonValidationError("Leg IK 名称冲突")
            if any(not self._cmds.objExists(path) for path in spec.chain):
                raise FitSkeletonValidationError(
                    "Leg IK mechanism chain 在执行前失效"
                )
            self._transaction_changed = True
            ankle_offset = self._cmds.createNode(
                "transform",
                name=spec.ankle_offset_name,
                parent=spec.root_path,
                skipSelect=True,
            )
            ankle_offset = (
                self._cmds.ls(ankle_offset, long=True) or [ankle_offset]
            )[0]
            x_axis, y_axis, z_axis = spec.ankle_axes
            matrix = (
                *x_axis,
                0.0,
                *y_axis,
                0.0,
                *z_axis,
                0.0,
                *spec.ankle_position,
                1.0,
            )
            self._cmds.xform(ankle_offset, worldSpace=True, matrix=matrix)
            ankle = self._cmds.circle(
                name=spec.ankle_control_name,
                normal=(1.0, 0.0, 0.0),
                radius=spec.radius,
                degree=3,
                sections=12,
                constructionHistory=False,
            )[0]
            ankle = self._cmds.parent(ankle, ankle_offset, relative=True)[0]
            ankle = (self._cmds.ls(ankle, long=True) or [ankle])[0]
            pole_offset = self._cmds.createNode(
                "transform",
                name=spec.pole_offset_name,
                parent=spec.root_path,
                skipSelect=True,
            )
            pole_offset = (
                self._cmds.ls(pole_offset, long=True) or [pole_offset]
            )[0]
            self._cmds.xform(
                pole_offset,
                worldSpace=True,
                translation=spec.pole_position,
            )
            pole = self._cmds.circle(
                name=spec.pole_control_name,
                normal=(0.0, 0.0, 1.0),
                radius=spec.radius * 0.65,
                degree=3,
                sections=8,
                constructionHistory=False,
            )[0]
            pole = self._cmds.parent(pole, pole_offset, relative=True)[0]
            pole = (self._cmds.ls(pole, long=True) or [pole])[0]
            if (
                ankle != spec.ankle_control_path
                or pole != spec.pole_control_path
            ):
                raise RuntimeError("Leg IK 控制路径漂移")
            handle, _ = self._cmds.ikHandle(
                name=spec.handle_name,
                startJoint=spec.chain[0],
                endEffector=spec.chain[2],
                solver="ikRPsolver",
            )
            self._cmds.parent(handle, ankle, absolute=True)
            self._cmds.poleVectorConstraint(
                pole,
                handle,
                name=spec.pole_constraint_name,
            )
            self._cmds.orientConstraint(
                ankle,
                spec.chain[2],
                maintainOffset=False,
                name=spec.ankle_constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_leg_ik(self, plan: BodyLegIkPlan) -> BodyLegIkSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("Leg IK 控制根节点无效")
        states = []
        for spec in plan.limbs:
            ankle = (
                self._cmds.ls(
                    spec.ankle_control_path,
                    long=True,
                    type="transform",
                )
                or [None]
            )[0]
            pole = (
                self._cmds.ls(
                    spec.pole_control_path,
                    long=True,
                    type="transform",
                )
                or [None]
            )[0]
            handles = self._cmds.ls(
                spec.handle_name,
                long=True,
                type="ikHandle",
            ) or []
            pole_constraints = self._cmds.ls(
                spec.pole_constraint_name,
                type="poleVectorConstraint",
            ) or []
            ankle_constraints = self._cmds.ls(
                spec.ankle_constraint_name,
                type="orientConstraint",
            ) or []
            if (
                ankle is None
                or pole is None
                or len(handles) != 1
                or len(pole_constraints) != 1
                or len(ankle_constraints) != 1
            ):
                raise FitSkeletonValidationError("Leg IK 节点集合无效")
            handle = handles[0]
            ankle_parent = self._cmds.listRelatives(
                ankle, parent=True, fullPath=True
            ) or []
            pole_parent = self._cmds.listRelatives(
                pole, parent=True, fullPath=True
            ) or []
            handle_parent = self._cmds.listRelatives(
                handle, parent=True, fullPath=True
            ) or []
            joint_list = tuple(
                (self._cmds.ls(value, long=True) or [value])[0]
                for value in (
                    self._cmds.ikHandle(handle, query=True, jointList=True) or []
                )
            )
            pole_targets = self._cmds.poleVectorConstraint(
                pole_constraints[0],
                query=True,
                targetList=True,
            ) or []
            pole_source = (
                (self._cmds.ls(pole_targets[0], long=True) or [pole_targets[0]])[0]
                if len(pole_targets) == 1
                else None
            )
            ankle_targets = self._cmds.orientConstraint(
                ankle_constraints[0],
                query=True,
                targetList=True,
            ) or []
            ankle_source = (
                (self._cmds.ls(ankle_targets[0], long=True) or [ankle_targets[0]])[0]
                if len(ankle_targets) == 1
                else None
            )
            outputs = self._cmds.listConnections(
                f"{ankle_constraints[0]}.constraintRotateX",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            ankle_driven = (
                self._resolve_connected_node(outputs[0])
                if len(outputs) == 1
                else None
            )

            def shape_type(node):
                shapes = self._cmds.listRelatives(
                    node,
                    shapes=True,
                    noIntermediate=True,
                    fullPath=True,
                ) or []
                return (
                    self._cmds.nodeType(shapes[0])
                    if len(shapes) == 1
                    else None
                )

            def vector(node, attribute):
                return tuple(
                    float(value)
                    for value in self._cmds.getAttr(
                        f"{node}.{attribute}"
                    )[0]
                )

            states.append(BodyLegIkState(
                side=spec.side,
                ankle_control_path=ankle,
                ankle_parent_path=(ankle_parent[0] if ankle_parent else None),
                pole_control_path=pole,
                pole_parent_path=(pole_parent[0] if pole_parent else None),
                handle_name=spec.handle_name,
                pole_constraint_name=pole_constraints[0],
                handle_parent_path=(handle_parent[0] if handle_parent else None),
                joint_list=joint_list,
                pole_source=pole_source,
                ankle_position=tuple(
                    float(value)
                    for value in self._cmds.xform(
                        ankle,
                        query=True,
                        worldSpace=True,
                        translation=True,
                    )
                ),
                pole_position=tuple(
                    float(value)
                    for value in self._cmds.xform(
                        pole,
                        query=True,
                        worldSpace=True,
                        translation=True,
                    )
                ),
                ankle_shape=shape_type(ankle),
                pole_shape=shape_type(pole),
                ankle_translation=vector(ankle, "translate"),
                ankle_rotation=vector(ankle, "rotate"),
                pole_translation=vector(pole, "translate"),
                pole_rotation=vector(pole, "rotate"),
                ankle_constraint_name=ankle_constraints[0],
                ankle_source=ankle_source,
                ankle_driven_joint=ankle_driven,
            ))
        return BodyLegIkSnapshot(roots[0], tuple(states))

    def capture_body_leg_foot_input(
        self,
        plan: BodyLegFootPlan,
    ) -> BodyLegFootInputState:
        required = []
        collisions = []
        non_writable = []
        existing_attributes = []
        occupied_rotations = []
        invalid_ankle_constraints = []
        for side in plan.sides:
            handles = self._cmds.ls(side.handle_name, long=True, type="ikHandle") or []
            required.extend((
                side.ankle_control_path,
                side.ankle_driver_path,
                side.toe_driver_path,
                side.ankle_constraint_name,
            ))
            if len(handles) == 1:
                required.append(handles[0])
            else:
                required.append(side.handle_name)
            names = [pivot.name for pivot in side.pivots]
            names.extend(
                pivot.multiplier_name
                for pivot in side.pivots
                if pivot.multiplier_name
            )
            names.append(side.toe_constraint_name)
            names.extend((side.toe_offset_name, side.toe_control_name))
            names.extend(node.name for node in side.roll.nodes)
            collisions.extend(
                name for name in names if self.find_name_collisions(name)
            )
            for path in (
                side.ankle_control_path,
                side.ankle_driver_path,
                side.toe_driver_path,
                side.ankle_constraint_name,
                *handles,
            ):
                if not self._cmds.objExists(path):
                    continue
                locked = bool((self._cmds.lockNode(path, query=True, lock=True) or [False])[0])
                referenced = bool(self._cmds.referenceQuery(path, isNodeReferenced=True))
                if locked or referenced:
                    non_writable.append(path)
            existing_attributes.extend(
                f"{side.ankle_control_path}.{attribute}"
                for attribute in side.attributes
                if self._cmds.attributeQuery(
                    attribute, node=side.ankle_control_path, exists=True
                )
            )
            ankle_constraints = self._cmds.ls(
                side.ankle_constraint_name,
                type="orientConstraint",
            ) or []
            if len(ankle_constraints) == 1:
                targets = self._cmds.orientConstraint(
                    ankle_constraints[0], query=True, targetList=True
                ) or []
                target = (
                    (self._cmds.ls(targets[0], long=True) or [targets[0]])[0]
                    if len(targets) == 1 else None
                )
                outputs = self._cmds.listConnections(
                    f"{ankle_constraints[0]}.constraintRotateX",
                    source=False,
                    destination=True,
                    plugs=True,
                ) or []
                driven = (
                    self._resolve_connected_node(outputs[0])
                    if len(outputs) == 1 else None
                )
                if (
                    target != side.ankle_control_path
                    or driven != side.ankle_driver_path
                ):
                    invalid_ankle_constraints.append(side.ankle_constraint_name)
            elif self._cmds.objExists(side.ankle_constraint_name):
                invalid_ankle_constraints.append(side.ankle_constraint_name)
            for axis in "XYZ":
                plug = f"{side.toe_driver_path}.rotate{axis}"
                sources = self._cmds.listConnections(
                    plug,
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                if sources:
                    occupied_rotations.append(plug)
        missing = tuple(path for path in required if not self._cmds.objExists(path))
        return BodyLegFootInputState(
            missing_required_paths=missing,
            name_collisions=tuple(collisions),
            non_writable_paths=tuple(non_writable),
            existing_attribute_plugs=tuple(existing_attributes),
            occupied_rotation_plugs=tuple(occupied_rotations),
            invalid_ankle_constraints=tuple(invalid_ankle_constraints),
        )

    def create_body_leg_foot_side(self, spec: BodyLegFootSideSpec) -> None:
        self._require_transaction()
        state = self.capture_body_leg_foot_input(BodyLegFootPlan((spec,)))
        if any((
            state.missing_required_paths,
            state.name_collisions,
            state.non_writable_paths,
            state.existing_attribute_plugs,
            state.occupied_rotation_plugs,
            state.invalid_ankle_constraints,
        )):
            raise FitSkeletonValidationError("Foot pivot 输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            for attribute in spec.attributes:
                options = {}
                if attribute == spec.roll.master_attribute:
                    options = {
                        "minValue": spec.roll.minimum,
                        "maxValue": spec.roll.maximum,
                    }
                self._cmds.addAttr(
                    spec.ankle_control_path,
                    longName=attribute,
                    attributeType="double",
                    defaultValue=0.0,
                    keyable=True,
                    **options,
                )
            for node in spec.roll.nodes:
                created = self._cmds.createNode(
                    node.node_type, name=node.name, skipSelect=True
                )
                if created != node.name:
                    raise RuntimeError("自动 footRoll 节点名称漂移")
                for plug, value in node.numeric_values:
                    self._cmds.setAttr(plug, value)
                for source, target in node.input_connections:
                    self._cmds.connectAttr(source, target)
            for pivot in spec.pivots:
                created = self._cmds.createNode(
                    "transform",
                    name=pivot.name,
                    parent=pivot.parent_path,
                    skipSelect=True,
                )
                created = (self._cmds.ls(created, long=True) or [created])[0]
                if created != pivot.path:
                    raise RuntimeError("Foot pivot 路径漂移")
                self._cmds.xform(
                    created,
                    worldSpace=True,
                    translation=pivot.world_position,
                )
                attribute_plug = f"{spec.ankle_control_path}.{pivot.attribute}"
                if pivot.multiplier_name:
                    multiplier = self._cmds.createNode(
                        "multDoubleLinear",
                        name=pivot.multiplier_name,
                        skipSelect=True,
                    )
                    self._cmds.connectAttr(attribute_plug, f"{multiplier}.input1")
                    self._cmds.setAttr(f"{multiplier}.input2", pivot.multiplier)
                    self._cmds.connectAttr(f"{multiplier}.output", pivot.target_plug)
                else:
                    self._cmds.connectAttr(pivot.source_plug, pivot.target_plug)
            toe_pivot = next(
                pivot.path for pivot in spec.pivots
                if pivot.role is BodyLegFootPivotRole.TOE
            )
            toe_offset = self._cmds.createNode(
                "transform",
                name=spec.toe_offset_name,
                parent=toe_pivot,
                skipSelect=True,
            )
            toe_offset = (
                self._cmds.ls(toe_offset, long=True) or [toe_offset]
            )[0]
            toe_x, toe_y, toe_z = spec.toe_control_axes
            toe_matrix = (
                *toe_x, 0.0,
                *toe_y, 0.0,
                *toe_z, 0.0,
                *spec.toe_control_position, 1.0,
            )
            self._cmds.xform(
                toe_offset, worldSpace=True, matrix=toe_matrix
            )
            toe_control = self._cmds.circle(
                name=spec.toe_control_name,
                normal=(0.0, 1.0, 0.0),
                radius=spec.toe_control_radius,
                degree=3,
                sections=8,
                constructionHistory=False,
            )[0]
            toe_control = self._cmds.parent(
                toe_control, toe_offset, relative=True
            )[0]
            toe_control = (
                self._cmds.ls(toe_control, long=True) or [toe_control]
            )[0]
            if (
                toe_offset != spec.toe_offset_path
                or toe_control != spec.toe_control_path
            ):
                raise RuntimeError("Toe IK 控制路径漂移")
            handles = self._cmds.ls(spec.handle_name, long=True, type="ikHandle") or []
            if len(handles) != 1:
                raise FitSkeletonValidationError("Leg IK Handle 在执行前失效")
            self._cmds.parent(handles[0], spec.final_handle_parent_path, absolute=True)
            ankle_constraints = self._cmds.ls(
                spec.ankle_constraint_name,
                type="orientConstraint",
            ) or []
            if len(ankle_constraints) != 1:
                raise FitSkeletonValidationError("Ankle IK 朝向约束在执行前失效")
            self._cmds.delete(ankle_constraints[0])
            self._cmds.orientConstraint(
                spec.ankle_orientation_source_path,
                spec.ankle_driver_path,
                maintainOffset=False,
                name=spec.ankle_constraint_name,
            )
            self._cmds.orientConstraint(
                spec.toe_orientation_source_path,
                spec.toe_driver_path,
                maintainOffset=False,
                name=spec.toe_constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_leg_foot(
        self,
        plan: BodyLegFootPlan,
    ) -> BodyLegFootSnapshot:
        sides = []
        for spec in plan.sides:
            values = tuple(
                (
                    f"{spec.ankle_control_path}.{attribute}",
                    float(self._cmds.getAttr(
                        f"{spec.ankle_control_path}.{attribute}"
                    )),
                )
                for attribute in spec.attributes
            )
            pivots = []
            for pivot in spec.pivots:
                nodes = self._cmds.ls(pivot.path, long=True, type="transform") or []
                if len(nodes) != 1:
                    raise FitSkeletonValidationError("Foot pivot 节点集合无效")
                node = nodes[0]
                parents = self._cmds.listRelatives(
                    node, parent=True, fullPath=True
                ) or []
                sources = self._cmds.listConnections(
                    pivot.target_plug,
                    source=True,
                    destination=False,
                    plugs=True,
                    skipConversionNodes=True,
                ) or []
                source = self._canonical_plug(sources[0]) if len(sources) == 1 else None
                multiplier_input = None
                multiplier_value = None
                if pivot.multiplier_name:
                    inputs = self._cmds.listConnections(
                        f"{pivot.multiplier_name}.input1",
                        source=True,
                        destination=False,
                        plugs=True,
                    ) or []
                    multiplier_input = (
                        self._canonical_plug(inputs[0]) if len(inputs) == 1 else None
                    )
                    multiplier_value = float(
                        self._cmds.getAttr(f"{pivot.multiplier_name}.input2")
                    )
                pivots.append(BodyLegFootPivotState(
                    role=pivot.role,
                    path=node,
                    parent_path=parents[0] if parents else None,
                    world_position=tuple(
                        float(value) for value in self._cmds.xform(
                            node,
                            query=True,
                            worldSpace=True,
                            translation=True,
                        )
                    ),
                    rotation_source=source,
                    multiplier_input_source=multiplier_input,
                    multiplier_value=multiplier_value,
                ))
            handles = self._cmds.ls(spec.handle_name, long=True, type="ikHandle") or []
            if len(handles) != 1:
                raise FitSkeletonValidationError("Foot IK Handle 节点集合无效")
            parents = self._cmds.listRelatives(
                handles[0], parent=True, fullPath=True
            ) or []

            def orientation_state(name):
                constraints = self._cmds.ls(name, type="orientConstraint") or []
                if len(constraints) != 1:
                    return (None, None, None)
                constraint = constraints[0]
                targets = self._cmds.orientConstraint(
                    constraint, query=True, targetList=True
                ) or []
                source = (
                    (self._cmds.ls(targets[0], long=True) or [targets[0]])[0]
                    if len(targets) == 1 else None
                )
                outputs = self._cmds.listConnections(
                    f"{constraint}.constraintRotateX",
                    source=False,
                    destination=True,
                    plugs=True,
                ) or []
                driven = (
                    self._resolve_connected_node(outputs[0])
                    if len(outputs) == 1 else None
                )
                return (constraint, source, driven)

            ankle_orientation = orientation_state(spec.ankle_constraint_name)
            toe_orientation = orientation_state(spec.toe_constraint_name)
            toe_offsets = self._cmds.ls(
                spec.toe_offset_path, long=True, type="transform"
            ) or []
            toe_controls = self._cmds.ls(
                spec.toe_control_path, long=True, type="transform"
            ) or []
            if len(toe_offsets) != 1 or len(toe_controls) != 1:
                raise FitSkeletonValidationError("Toe IK 控制节点集合无效")
            toe_offset_parent = self._cmds.listRelatives(
                toe_offsets[0], parent=True, fullPath=True
            ) or []
            toe_control_parent = self._cmds.listRelatives(
                toe_controls[0], parent=True, fullPath=True
            ) or []
            toe_control_matrix = self._cmds.xform(
                toe_controls[0], query=True, worldSpace=True, matrix=True
            )
            toe_shapes = self._cmds.listRelatives(
                toe_controls[0],
                shapes=True,
                noIntermediate=True,
                fullPath=True,
            ) or []

            def control_vector(attribute):
                return tuple(
                    float(value) for value in self._cmds.getAttr(
                        f"{toe_controls[0]}.{attribute}"
                    )[0]
                )

            roll_nodes = []
            for node_spec in spec.roll.nodes:
                nodes = self._cmds.ls(node_spec.name) or []
                node_type = (
                    self._cmds.nodeType(nodes[0]) if len(nodes) == 1 else None
                )
                connections = []
                for _, target in node_spec.input_connections:
                    sources = self._cmds.listConnections(
                        target,
                        source=True,
                        destination=False,
                        plugs=True,
                        skipConversionNodes=True,
                    ) or []
                    connections.append((
                        target,
                        self._canonical_plug(sources[0])
                        if len(sources) == 1 else None,
                    ))
                numeric_values = tuple(
                    (
                        plug,
                        float(self._cmds.getAttr(plug))
                        if self._cmds.objExists(plug) else None,
                    )
                    for plug, _ in node_spec.numeric_values
                )
                roll_nodes.append(BodyLegFootRollNodeState(
                    node_spec.name,
                    node_type,
                    tuple(connections),
                    numeric_values,
                ))
            roll_state = BodyLegFootRollState(
                spec.roll.master_plug,
                float(self._cmds.getAttr(spec.roll.master_plug)),
                tuple(roll_nodes),
            )

            sides.append(BodyLegFootSideState(
                spec.side,
                values,
                tuple(pivots),
                parents[0] if parents else None,
                *ankle_orientation,
                *toe_orientation,
                toe_offsets[0],
                toe_offset_parent[0] if toe_offset_parent else None,
                toe_controls[0],
                toe_control_parent[0] if toe_control_parent else None,
                tuple(float(value) for value in self._cmds.xform(
                    toe_controls[0],
                    query=True,
                    worldSpace=True,
                    translation=True,
                )),
                tuple(
                    self._normalized_vector(tuple(
                        float(value)
                        for value in toe_control_matrix[index:index + 3]
                    ))
                    for index in (0, 4, 8)
                ),
                control_vector("translate"),
                control_vector("rotate"),
                (
                    self._cmds.nodeType(toe_shapes[0])
                    if len(toe_shapes) == 1 else None
                ),
                roll_state,
            ))
        return BodyLegFootSnapshot(tuple(sides))

    def _canonical_plug(self, plug: str) -> str:
        node, attribute = plug.split(".", 1)
        paths = self._cmds.ls(node, long=True) or [node]
        return f"{paths[0]}.{attribute}"

    def create_body_arm_mechanism_root(self, name: str) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Arm 机制链根名称冲突：{name}")
        self._transaction_changed = True
        created = self._cmds.createNode(
            "transform",
            name=name,
            skipSelect=True,
        )
        return (self._cmds.ls(created, long=True) or [created])[0]

    def create_body_arm_mechanism_joint(
        self,
        spec: BodyArmMechanismJointSpec,
    ) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(f"Arm 机制关节名称冲突：{spec.name}")
        parents = self._cmds.ls(spec.parent_path, long=True) or []
        sources = self._cmds.ls(spec.source_joint, long=True, type="joint") or []
        if (
            len(parents) != 1
            or self._cmds.nodeType(parents[0]) not in {"transform", "joint"}
            or len(sources) != 1
            or sources[0] != spec.source_joint
        ):
            raise FitSkeletonValidationError(
                f"Arm 机制关节父级或来源失效：{spec.name}"
            )
        self._transaction_changed = True
        joint = self._cmds.createNode(
            "joint",
            name=spec.name,
            parent=parents[0],
            skipSelect=True,
        )
        joint = (self._cmds.ls(joint, long=True) or [joint])[0]
        self._cmds.xform(
            joint,
            worldSpace=True,
            translation=spec.world_position,
        )
        self._set_joint_world_axes(joint, spec.world_axes)
        self._cmds.setAttr(f"{joint}.side", _MAYA_SIDE_FROM_CORE[spec.side])
        self._cmds.addAttr(joint, longName="advPySourceJoint", attributeType="message")
        self._cmds.connectAttr(
            f"{sources[0]}.message",
            f"{joint}.advPySourceJoint",
        )
        return joint

    def capture_body_arm_mechanisms(
        self,
        plan: BodyArmMechanismPlan,
    ) -> BodyArmMechanismSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("Arm 机制链根节点无效")
        paths = self._cmds.listRelatives(
            roots[0],
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        states: list[BodyArmMechanismJointState] = []
        for path in sorted(set(paths), key=lambda value: (value.count("|"), value)):
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            position = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )
            matrix = self._cmds.xform(
                path,
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
            source_nodes = []
            if self._cmds.attributeQuery(
                "advPySourceJoint",
                node=path,
                exists=True,
            ):
                source_nodes = self._cmds.listConnections(
                    f"{path}.advPySourceJoint",
                    source=True,
                    destination=False,
                    type="joint",
                ) or []
            source = None
            if len(source_nodes) == 1:
                source = (
                    self._cmds.ls(source_nodes[0], long=True) or [source_nodes[0]]
                )[0]
            side_code = int(self._cmds.getAttr(f"{path}.side"))
            side = _CORE_SIDE_FROM_MAYA.get(side_code)
            if side is None:
                raise FitSkeletonValidationError(
                    f"Arm 机制关节侧向值无效：{path}.side={side_code}"
                )
            rotation = self._cmds.getAttr(f"{path}.rotate")[0]
            states.append(
                BodyArmMechanismJointState(
                    path=path,
                    parent_path=parents[0] if parents else None,
                    side=side,
                    source_joint=source,
                    world_position=tuple(float(value) for value in position),
                    world_axes=world_axes,
                    rotation=tuple(float(value) for value in rotation),
                )
            )
        return BodyArmMechanismSnapshot(roots[0], tuple(states))

    def create_body_leg_mechanism_root(self, name: str) -> str:
        return self.create_body_arm_mechanism_root(name)

    def create_body_leg_mechanism_joint(
        self,
        spec: BodyLegMechanismJointSpec,
    ) -> str:
        return self.create_body_arm_mechanism_joint(spec)

    def capture_body_leg_mechanisms(
        self,
        plan: BodyLegMechanismPlan,
    ) -> BodyLegMechanismSnapshot:
        return self.capture_body_arm_mechanisms(plan)

    def create_body_arm_fk_control(self, spec: BodyArmFkControlSpec) -> None:
        self._create_body_limb_fk_control(spec, "Arm")

    def create_body_leg_fk_control(self, spec: BodyLegFkControlSpec) -> None:
        self._create_body_limb_fk_control(spec, "Leg")

    def capture_body_hand_fk_input(
        self,
        plan: BodyHandFkControlPlan,
    ) -> BodyHandFkInputSnapshot:
        states = []
        for path in dict.fromkeys(
            control.driven_joint for control in plan.controls
        ):
            matches = self._cmds.ls(path, long=True, type="joint") or []
            if len(matches) != 1 or matches[0] != path:
                raise FitSkeletonValidationError(
                    f"Hand FK 输入关节无效：{path}"
                )
            sources = []
            writable = set()
            for axis in "XYZ":
                plug = f"{path}.rotate{axis}"
                values = self._cmds.listConnections(
                    plug,
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                source = None
                if len(values) == 1:
                    node, attribute = values[0].split(".", 1)
                    source = f"{self._resolve_connected_node(node)}.{attribute}"
                elif len(values) > 1:
                    source = "<multiple>"
                sources.append(source)
                if self._cmds.getAttr(plug, settable=True):
                    writable.add(axis.lower())
            states.append(BodyHandFkJointInputState(
                joint=path,
                writable_rotation_axes=frozenset(writable),
                rotation_sources=tuple(sources),
            ))
        return BodyHandFkInputSnapshot(tuple(states))

    def create_body_hand_fk_root(self, spec: BodyHandFkRootSpec) -> str:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if self.find_name_collisions(spec.name):
                raise FitSkeletonValidationError(
                    f"Hand FK 根节点名称冲突：{spec.name}"
                )
            parents = self._cmds.ls(
                spec.parent_path,
                long=True,
                type="joint",
            ) or []
            if len(parents) != 1 or parents[0] != spec.parent_path:
                raise FitSkeletonValidationError(
                    f"Hand FK Wrist 父级失效：{spec.parent_path}"
                )
            self._transaction_changed = True
            root = self._cmds.createNode(
                "transform",
                name=spec.name,
                parent=parents[0],
                skipSelect=True,
            )
            root = (self._cmds.ls(root, long=True) or [root])[0]
            if root != spec.path:
                raise RuntimeError(f"Hand FK 根节点路径漂移：{spec.name}")
            return root
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def create_body_hand_fk_control(
        self,
        spec: BodyHandFkControlSpec,
    ) -> None:
        self._create_body_limb_fk_control(spec, "Hand")

    def create_body_hand_pose(self, plan: BodyHandPosePlan) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if any(
                self.find_name_collisions(name) for name in plan.node_names
            ):
                raise FitSkeletonValidationError(
                    "Hand 聚合姿态节点名称发生冲突"
                )
            for spec in plan.attributes:
                roots = self._cmds.ls(
                    spec.root_path,
                    long=True,
                    type="transform",
                ) or []
                if len(roots) != 1 or roots[0] != spec.root_path:
                    raise FitSkeletonValidationError(
                        f"Hand 聚合姿态根节点失效：{spec.root_path}"
                    )
                if self._cmds.attributeQuery(
                    spec.name,
                    node=spec.root_path,
                    exists=True,
                ):
                    raise FitSkeletonValidationError(
                        f"Hand 聚合姿态属性已存在：{spec.plug}"
                    )
            for destination in (
                *(spec.destination_plug for spec in plan.curls),
                *(spec.destination_plug for spec in plan.spreads),
            ):
                sources = self._cmds.listConnections(
                    destination,
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                if (
                    not self._cmds.objExists(destination)
                    or not self._cmds.getAttr(destination, settable=True)
                    or sources
                ):
                    raise FitSkeletonValidationError(
                        f"Hand 聚合姿态目标通道不可写：{destination}"
                    )

            self._transaction_changed = True
            for spec in plan.attributes:
                self._cmds.addAttr(
                    spec.root_path,
                    longName=spec.name,
                    attributeType="double",
                    minValue=spec.minimum,
                    maxValue=spec.maximum,
                    defaultValue=spec.default,
                    keyable=True,
                )
            for spec in plan.curls:
                node = self._cmds.createNode(
                    "blendWeighted",
                    name=spec.node_name,
                )
                self._cmds.connectAttr(spec.source_plugs[0], f"{node}.input[0]")
                self._cmds.connectAttr(spec.source_plugs[1], f"{node}.input[1]")
                self._cmds.setAttr(f"{node}.weight[0]", spec.weights[0])
                self._cmds.setAttr(f"{node}.weight[1]", spec.weights[1])
                self._cmds.connectAttr(
                    f"{node}.output",
                    spec.destination_plug,
                )
            for spec in plan.spreads:
                node = self._cmds.createNode(
                    "multDoubleLinear",
                    name=spec.node_name,
                )
                self._cmds.connectAttr(spec.source_plug, f"{node}.input1")
                self._cmds.setAttr(f"{node}.input2", spec.factor)
                self._cmds.connectAttr(
                    f"{node}.output",
                    spec.destination_plug,
                )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_hand_pose(
        self,
        plan: BodyHandPosePlan,
    ) -> BodyHandPoseSnapshot:
        def source(plug: str, *, skip_conversion=False) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
                skipConversionNodes=skip_conversion,
            ) or []
            if len(values) == 1:
                return self._canonical_plug(values[0])
            return "<multiple>" if values else None

        layers = []
        for spec in plan.layers:
            nodes = self._cmds.ls(
                spec.path,
                long=True,
                type="transform",
            ) or []
            if len(nodes) != 1 or nodes[0] != spec.path:
                raise FitSkeletonValidationError(
                    f"Hand Pose 层缺失：{spec.path}"
                )
            node = nodes[0]
            parent = self._cmds.listRelatives(
                node,
                parent=True,
                fullPath=True,
            ) or []
            layers.append(BodyHandPoseLayerState(
                path=node,
                parent_path=parent[0] if len(parent) == 1 else None,
                local_translation=tuple(
                    float(value)
                    for value in self._cmds.getAttr(f"{node}.translate")[0]
                ),
                local_rotation=tuple(
                    float(value)
                    for value in self._cmds.getAttr(f"{node}.rotate")[0]
                ),
                local_scale=tuple(
                    float(value)
                    for value in self._cmds.getAttr(f"{node}.scale")[0]
                ),
            ))

        attributes = []
        for spec in plan.attributes:
            if not self._cmds.objExists(spec.plug):
                raise FitSkeletonValidationError(
                    f"Hand 聚合姿态属性缺失：{spec.plug}"
                )
            minimum = self._cmds.attributeQuery(
                spec.name,
                node=spec.root_path,
                minimum=True,
            ) or []
            maximum = self._cmds.attributeQuery(
                spec.name,
                node=spec.root_path,
                maximum=True,
            ) or []
            attributes.append(BodyHandPoseAttributeState(
                plug=spec.plug,
                value=float(self._cmds.getAttr(spec.plug)),
                minimum=float(minimum[0]) if len(minimum) == 1 else None,
                maximum=float(maximum[0]) if len(maximum) == 1 else None,
                keyable=bool(self._cmds.getAttr(spec.plug, keyable=True)),
            ))

        curls = []
        for spec in plan.curls:
            nodes = self._cmds.ls(spec.node_name, type="blendWeighted") or []
            if len(nodes) != 1:
                raise FitSkeletonValidationError(
                    f"Hand curl 节点缺失：{spec.node_name}"
                )
            node = nodes[0]
            curls.append(BodyHandCurlState(
                node_name=node,
                node_type=self._cmds.nodeType(node),
                source_plugs=(
                    source(f"{node}.input[0]"),
                    source(f"{node}.input[1]"),
                ),
                weights=(
                    float(self._cmds.getAttr(f"{node}.weight[0]")),
                    float(self._cmds.getAttr(f"{node}.weight[1]")),
                ),
                destination_plug=spec.destination_plug,
                destination_source=source(
                    spec.destination_plug,
                    skip_conversion=True,
                ),
            ))

        spreads = []
        for spec in plan.spreads:
            nodes = self._cmds.ls(
                spec.node_name,
                type="multDoubleLinear",
            ) or []
            if len(nodes) != 1:
                raise FitSkeletonValidationError(
                    f"Hand spread 节点缺失：{spec.node_name}"
                )
            node = nodes[0]
            spreads.append(BodyHandSpreadState(
                node_name=node,
                node_type=self._cmds.nodeType(node),
                source_plug=source(f"{node}.input1"),
                factor=float(self._cmds.getAttr(f"{node}.input2")),
                destination_plug=spec.destination_plug,
                destination_source=source(
                    spec.destination_plug,
                    skip_conversion=True,
                ),
            ))
        return BodyHandPoseSnapshot(
            tuple(layers),
            tuple(attributes),
            tuple(curls),
            tuple(spreads),
        )

    def capture_body_hand_pose_channels(
        self,
        hand: BodyHandFkControlPlan,
        pose: BodyHandPosePlan,
    ) -> BodyHandPoseChannelSnapshot:
        def source_info(plug: str) -> tuple[str | None, str | None]:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) == 1:
                node = values[0].split(".", 1)[0]
                return self._canonical_plug(values[0]), self._cmds.nodeType(node)
            if values:
                return "<multiple>", "<multiple>"
            return None, None

        def keyframe_writable(plug: str, source_type: str | None) -> bool:
            return (
                not self._cmds.getAttr(plug, lock=True)
                and bool(self._cmds.getAttr(plug, keyable=True))
                and (
                    source_type is None
                    or source_type.startswith("animCurve")
                )
            )

        aggregates = []
        for spec in pose.attributes:
            if not self._cmds.objExists(spec.plug):
                raise FitSkeletonValidationError(
                    f"Hand Pose 聚合通道缺失：{spec.plug}"
                )
            minimum = self._cmds.attributeQuery(
                spec.name,
                node=spec.root_path,
                minimum=True,
            ) or []
            maximum = self._cmds.attributeQuery(
                spec.name,
                node=spec.root_path,
                maximum=True,
            ) or []
            incoming_source, incoming_source_type = source_info(spec.plug)
            aggregates.append(BodyHandAggregatePoseChannelState(
                side=spec.side,
                name=spec.name,
                plug=spec.plug,
                value=float(self._cmds.getAttr(spec.plug)),
                minimum=float(minimum[0]) if len(minimum) == 1 else None,
                maximum=float(maximum[0]) if len(maximum) == 1 else None,
                writable=bool(self._cmds.getAttr(spec.plug, settable=True)),
                incoming_source=incoming_source,
                incoming_source_type=incoming_source_type,
                keyframe_writable=keyframe_writable(
                    spec.plug,
                    incoming_source_type,
                ),
            ))

        by_name = {
            spec.control_name.rsplit(":", 1)[-1]: spec
            for spec in hand.controls
        }
        controls = []
        for side in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
            for digit in BODY_HAND_DIGITS:
                for segment in BODY_HAND_POSE_FK_SEGMENTS:
                    name = f"AdvPy_{digit.value}{segment}FK_{side.value}"
                    spec = by_name.get(name)
                    if spec is None or spec.side is not side:
                        raise FitSkeletonValidationError(
                            f"Hand Pose FK 语义控制缺失：{name}"
                        )
                    nodes = self._cmds.ls(
                        spec.control_path,
                        long=True,
                        type="transform",
                    ) or []
                    if len(nodes) != 1 or nodes[0] != spec.control_path:
                        raise FitSkeletonValidationError(
                            f"Hand Pose FK 控制缺失：{spec.control_path}"
                        )
                    path = nodes[0]
                    source_infos = tuple(
                        source_info(f"{path}.rotate{axis}")
                        for axis in ("X", "Y", "Z")
                    )
                    controls.append(BodyHandFkPoseChannelState(
                        side=side,
                        digit=digit,
                        segment=segment,
                        control_path=path,
                        rotation=tuple(
                            float(value)
                            for value in self._cmds.getAttr(f"{path}.rotate")[0]
                        ),
                        writable_rotation_axes=frozenset(
                            axis.lower()
                            for axis in ("X", "Y", "Z")
                            if self._cmds.getAttr(
                                f"{path}.rotate{axis}",
                                settable=True,
                            )
                        ),
                        rotation_sources=tuple(
                            info[0] for info in source_infos
                        ),
                        rotation_source_types=tuple(
                            info[1] for info in source_infos
                        ),
                        keyframe_writable_rotation_axes=frozenset(
                            axis.lower()
                            for axis, info in zip(
                                ("X", "Y", "Z"),
                                source_infos,
                            )
                            if keyframe_writable(
                                f"{path}.rotate{axis}",
                                info[1],
                            )
                        ),
                    ))
        return BodyHandPoseChannelSnapshot(tuple(aggregates), tuple(controls))

    def apply_body_hand_pose_changes(
        self,
        changes: BodyHandPoseChangeSet,
        *,
        keyframe: bool = False,
    ) -> None:
        self._require_transaction()
        if not isinstance(keyframe, bool):
            raise FitSkeletonValidationError(
                "Hand Pose keyframe 选项必须是布尔值"
            )
        for change in changes.aggregates:
            if (
                not self._cmds.objExists(change.plug)
                or (
                    not self._body_hand_pose_keyframe_writable(change.plug)
                    if keyframe
                    else not self._cmds.getAttr(change.plug, settable=True)
                )
                or abs(float(self._cmds.getAttr(change.plug)) - change.before)
                > 1e-6
            ):
                raise FitSkeletonValidationError(
                    f"Hand Pose 聚合通道执行前失效：{change.plug}"
                )
        for change in changes.controls:
            nodes = self._cmds.ls(
                change.control_path,
                long=True,
                type="transform",
            ) or []
            if len(nodes) != 1 or nodes[0] != change.control_path:
                raise FitSkeletonValidationError(
                    f"Hand Pose FK 控制执行前失效：{change.control_path}"
                )
            current = tuple(
                float(value)
                for value in self._cmds.getAttr(f"{change.control_path}.rotate")[0]
            )
            if any(abs(a - b) > 1e-6 for a, b in zip(current, change.before)):
                raise FitSkeletonValidationError(
                    f"Hand Pose FK rotate 执行前变化：{change.control_path}"
                )
            if any((
                not self._body_hand_pose_keyframe_writable(
                    f"{change.control_path}.rotate{axis}"
                )
                if keyframe
                else not self._cmds.getAttr(
                    f"{change.control_path}.rotate{axis}",
                    settable=True,
                )
            ) for axis in ("X", "Y", "Z")):
                raise FitSkeletonValidationError(
                    f"Hand Pose FK rotate 执行前不可写：{change.control_path}"
                )
        if not changes.changed_channel_count:
            return
        self._transaction_changed = True
        current_time = float(self._cmds.currentTime(query=True))
        for change in changes.aggregates:
            if keyframe:
                self._cmds.setKeyframe(
                    change.plug,
                    time=(current_time,),
                    value=change.after,
                )
            else:
                self._cmds.setAttr(change.plug, change.after)
        for change in changes.controls:
            for axis, value in zip(("X", "Y", "Z"), change.after):
                plug = f"{change.control_path}.rotate{axis}"
                if keyframe:
                    self._cmds.setKeyframe(
                        plug,
                        time=(current_time,),
                        value=value,
                    )
                else:
                    self._cmds.setAttr(plug, value)
        if keyframe:
            # Maya does not immediately expose a setKeyframe(value=...) result
            # at an unchanged current time. Re-evaluate once before postcheck.
            self._cmds.currentTime(
                current_time,
                edit=True,
                update=True,
            )

    def _body_hand_pose_keyframe_writable(self, plug: str) -> bool:
        if (
            not self._cmds.objExists(plug)
            or self._cmds.getAttr(plug, lock=True)
            or not self._cmds.getAttr(plug, keyable=True)
        ):
            return False
        sources = self._cmds.listConnections(
            plug,
            source=True,
            destination=False,
            plugs=True,
        ) or []
        if not sources:
            return True
        if len(sources) != 1:
            return False
        node = sources[0].split(".", 1)[0]
        return self._cmds.nodeType(node).startswith("animCurve")

    def _create_body_limb_fk_control(
        self,
        spec: BodyArmFkControlSpec,
        limb_label: str,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        pose_name = (
            spec.control_parent_path.rsplit("|", 1)[-1]
            if spec.control_parent_path is not None
            and spec.control_parent_path != spec.offset_path
            else None
        )
        for name in (
            spec.offset_name,
            *((pose_name,) if pose_name is not None else ()),
            spec.control_name,
            spec.constraint_name,
        ):
            if self.find_name_collisions(name):
                raise FitSkeletonValidationError(
                    f"{limb_label} FK 控制名称冲突：{name}"
                )
        parent = self._cmds.ls(spec.parent_path, long=True, type="transform") or []
        driven = self._cmds.ls(spec.driven_joint, long=True, type="joint") or []
        if len(parent) != 1 or len(driven) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} FK 控制父级或驱动关节失效：{spec.control_name}"
            )
        self._transaction_changed = True
        try:
            offset = self._cmds.createNode(
                "transform",
                name=spec.offset_name,
                parent=parent[0],
                skipSelect=True,
            )
            offset = (self._cmds.ls(offset, long=True) or [offset])[0]
            x_axis, y_axis, z_axis = spec.world_axes
            matrix = (
                *x_axis,
                0.0,
                *y_axis,
                0.0,
                *z_axis,
                0.0,
                *spec.world_position,
                1.0,
            )
            self._cmds.xform(offset, worldSpace=True, matrix=matrix)
            control_parent = offset
            if pose_name is not None:
                control_parent = self._cmds.createNode(
                    "transform",
                    name=pose_name,
                    parent=offset,
                    skipSelect=True,
                )
                control_parent = (
                    self._cmds.ls(control_parent, long=True)
                    or [control_parent]
                )[0]
                if control_parent != spec.control_parent_path:
                    raise RuntimeError(
                        f"{limb_label} FK Pose 层路径漂移：{pose_name}"
                    )
            control = self._cmds.circle(
                name=spec.control_name,
                normal=(1.0, 0.0, 0.0),
                radius=spec.radius,
                degree=3,
                sections=12,
                constructionHistory=False,
            )[0]
            control = self._cmds.parent(
                control,
                control_parent,
                relative=True,
            )[0]
            control = (self._cmds.ls(control, long=True) or [control])[0]
            if offset != spec.offset_path or control != spec.control_path:
                raise RuntimeError(
                    f"{limb_label} FK 控制路径漂移：{spec.control_name}"
                )
            self._cmds.orientConstraint(
                control,
                driven[0],
                maintainOffset=False,
                name=spec.constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_arm_fk_controls(
        self,
        plan: BodyArmFkControlPlan,
    ) -> BodyArmFkControlSnapshot:
        return self._capture_body_limb_fk_controls(plan, "Arm")

    def capture_body_leg_fk_controls(
        self,
        plan: BodyLegFkControlPlan,
    ) -> BodyLegFkControlSnapshot:
        return self._capture_body_limb_fk_controls(plan, "Leg")

    def capture_body_hand_fk_controls(
        self,
        plan: BodyHandFkControlPlan,
    ) -> BodyHandFkControlSnapshot:
        roots = []
        for spec in plan.roots:
            matches = self._cmds.ls(
                spec.path,
                long=True,
                type="transform",
            ) or []
            if len(matches) != 1 or matches[0] != spec.path:
                raise FitSkeletonValidationError(
                    f"Hand FK 根节点无效：{spec.path}"
                )
            path = matches[0]
            parent = self._cmds.listRelatives(
                path,
                parent=True,
                fullPath=True,
            ) or []
            matrix = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            roots.append(BodyHandFkRootState(
                path=path,
                parent_path=parent[0] if len(parent) == 1 else None,
                world_position=tuple(float(value) for value in matrix[12:15]),
                world_axes=tuple(
                    self._normalized_vector(
                        tuple(float(value) for value in matrix[index:index + 3])
                    )
                    for index in (0, 4, 8)
                ),
                local_translation=tuple(
                    float(value)
                    for value in self._cmds.getAttr(f"{path}.translate")[0]
                ),
                local_rotation=tuple(
                    float(value)
                    for value in self._cmds.getAttr(f"{path}.rotate")[0]
                ),
                local_scale=tuple(
                    float(value)
                    for value in self._cmds.getAttr(f"{path}.scale")[0]
                ),
            ))
        controls = self._capture_body_limb_fk_control_states(
            plan.controls,
            "Hand",
        )
        return BodyHandFkControlSnapshot(tuple(roots), controls)

    def _capture_body_limb_fk_controls(
        self,
        plan: BodyArmFkControlPlan,
        limb_label: str,
    ) -> BodyArmFkControlSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} FK 控制根节点无效"
            )
        states = self._capture_body_limb_fk_control_states(
            plan.controls,
            limb_label,
        )
        return BodyArmFkControlSnapshot(roots[0], states)

    def _capture_body_limb_fk_control_states(
        self,
        specs: tuple[BodyArmFkControlSpec, ...],
        limb_label: str,
    ) -> tuple[BodyArmFkControlState, ...]:
        states: list[BodyArmFkControlState] = []
        for spec in specs:
            offsets = self._cmds.ls(spec.offset_path, long=True, type="transform") or []
            control_nodes = self._cmds.ls(
                spec.control_path,
                long=True,
                type="transform",
            ) or []
            constraints = self._cmds.ls(spec.constraint_name, type="orientConstraint") or []
            if (
                len(offsets) != 1
                or len(control_nodes) != 1
                or len(constraints) != 1
            ):
                raise FitSkeletonValidationError(
                    f"{limb_label} FK 控制或约束无效：{spec.control_name}"
                )
            offset = offsets[0]
            control = control_nodes[0]
            constraint = constraints[0]
            offset_parent = self._cmds.listRelatives(
                offset, parent=True, fullPath=True
            ) or []
            control_parent = self._cmds.listRelatives(
                control, parent=True, fullPath=True
            ) or []
            position = self._cmds.xform(
                control, query=True, worldSpace=True, translation=True
            )
            matrix = self._cmds.xform(
                control, query=True, worldSpace=True, matrix=True
            )
            world_axes = tuple(
                self._normalized_vector(
                    tuple(float(value) for value in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            )
            local_translation = self._cmds.getAttr(f"{control}.translate")[0]
            local_rotation = self._cmds.getAttr(f"{control}.rotate")[0]
            shapes = self._cmds.listRelatives(
                control,
                shapes=True,
                noIntermediate=True,
                fullPath=True,
            ) or []
            targets = self._cmds.orientConstraint(
                constraint,
                query=True,
                targetList=True,
            ) or []
            source = None
            if len(targets) == 1:
                source = (self._cmds.ls(targets[0], long=True) or [targets[0]])[0]
            outputs = self._cmds.listConnections(
                f"{constraint}.constraintRotateX",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            driven_joint = None
            if len(outputs) == 1:
                driven_joint = self._resolve_connected_node(outputs[0])
            states.append(
                BodyArmFkControlState(
                    offset_path=offset,
                    offset_parent_path=offset_parent[0] if offset_parent else None,
                    control_path=control,
                    control_parent_path=control_parent[0] if control_parent else None,
                    constraint_name=constraint,
                    source_control=source,
                    driven_joint=driven_joint,
                    world_position=tuple(float(value) for value in position),
                    world_axes=world_axes,
                    local_translation=tuple(float(value) for value in local_translation),
                    local_rotation=tuple(float(value) for value in local_rotation),
                    shape_type=(self._cmds.nodeType(shapes[0]) if len(shapes) == 1 else None),
                )
            )
        return tuple(states)

    def set_body_joint_world_axes(
        self,
        change: BodyJointOrientationChange,
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(change.joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != change.joint:
            raise FitSkeletonValidationError(
                f"Body joint 在执行前失效：{change.joint}"
            )
        for axis in ("X", "Y", "Z"):
            attribute = f"{matches[0]}.jointOrient{axis}"
            if not self._cmds.getAttr(attribute, settable=True):
                raise FitSkeletonValidationError(
                    f"Body joint 朝向轴在执行前变为不可写：{attribute}"
                )
        self._transaction_changed = True
        self._set_joint_world_axes(matches[0], change.desired_world_axes)

    def set_body_joint_world_position(
        self,
        joint: str,
        position: tuple[float, float, float],
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != joint:
            raise FitSkeletonValidationError(
                f"Body joint 在位置恢复前失效：{joint}"
            )
        for axis in ("x", "y", "z"):
            attribute = f"{matches[0]}.t{axis}"
            if not self._cmds.getAttr(attribute, settable=True):
                raise FitSkeletonValidationError(
                    f"Body joint 位置轴在执行前变为不可写：{attribute}"
                )
        self._transaction_changed = True
        self._cmds.xform(
            matches[0],
            worldSpace=True,
            translation=position,
        )

    def _capture_body_provenance(
        self,
        root: str,
    ) -> BodySkeletonProvenanceState | None:
        exists = {
            field: bool(
                self._cmds.attributeQuery(attribute, node=root, exists=True)
            )
            for field, attribute in _BODY_PROVENANCE_ATTRIBUTES.items()
        }
        if not any(exists.values()):
            return None

        def value(field: str):
            if not exists[field]:
                return None
            return self._cmds.getAttr(
                f"{root}.{_BODY_PROVENANCE_ATTRIBUTES[field]}"
            )

        return BodySkeletonProvenanceState(
            owner=value("owner"),
            artifact_kind=value("artifact_kind"),
            schema_version=value("schema_version"),
            source_container=value("source_container"),
            body_joint_count=value("body_joint_count"),
        )

    def _resolve_connected_node(self, plug: str) -> str:
        node = plug.split(".", 1)[0]
        matches = self._cmds.ls(node, long=True) or [node]
        return matches[0]

    def _dependency_kind(self, node: str) -> BodyExternalDependencyKind:
        node_type = self._cmds.nodeType(node)
        inherited = set(self._cmds.nodeType(node, inherited=True) or [])
        if node_type == "skinCluster":
            return BodyExternalDependencyKind.SKIN_CLUSTER
        if "constraint" in inherited:
            return BodyExternalDependencyKind.CONSTRAINT
        if node_type.startswith("animCurve"):
            return BodyExternalDependencyKind.ANIMATION
        return BodyExternalDependencyKind.CONNECTION
