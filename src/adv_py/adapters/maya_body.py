from __future__ import annotations

from .maya_character_pose import MayaCharacterPoseMixin
from .maya_character_registry import MayaCharacterRegistryMixin
from .maya_fit_tweaker import MayaFitTweakerMixin
from .maya_body_fk_scale_compensation import (
    MayaBodyFkScaleCompensationMixin,
)
from .maya_torso import MayaBodyTorsoMixin
from .maya_spine import MayaBodySpineMixin
from .maya_control_spaces import MayaBodyControlSpacesMixin
from .maya_body_pole_aim import MayaBodyPoleAimMixin
from .maya_body_fit_aim import MayaBodyFitAimMixin

import json
from dataclasses import replace
from pathlib import Path

from adv_py.core.body_arm_mechanisms import (
    BodyArmMechanismJointSpec,
    BodyArmMechanismJointState,
    BodyArmMechanismPlan,
    BodyArmMechanismSnapshot,
)
from adv_py.core.body_system_hierarchy import (
    BODY_SYSTEM_RESERVED_NAMES, expected_body_system_hierarchy,
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
    audit_body_arm_fk_to_ik_preflight,
    audit_body_arm_ik_to_fk_preflight,
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
    fit_character_height,
)
from adv_py.core.body_fk_global import (
    BodyFkGlobalSpec, BodyFkGlobalState, GLOBAL_FOLLOW,
    body_fk_global_sources,
)
from adv_py.core.body_fk_channel_locks import (
    BodyFkChannelLockSpec, FK_LOCK_ATTRIBUTES,
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
    BodyExportSourceJoint,
    BodyExportJointState,
    BodyExportSkeletonBakePlan,
    BodyExportSkeletonBakedSnapshot,
    BodyExportSkeletonPlan,
    BodyExportSkeletonSample,
    BodyExportSkeletonSnapshot,
)
from adv_py.core.body_controller_layers import (
    BodyExtraControllerState, BodySubControllerState,
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
    BodyLegFootManualPivotState,
    BodyLegFootHighHeelState,
    BodyLegFootHybridState,
    BodyLegFootAlignState,
    BodyLegFootRockPivotState,
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
    SkinningMethod,
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
    FitDeformProfile,
    BodySkeletonProvenance,
    BodySkeletonProvenanceState,
    BodySkeletonSnapshot,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .maya_fit import MayaFitJointHost
from .maya_control_curves import MayaControlCurveMixin
from .maya_adv_icons import create_adv_icon, original_fit_icon_axis_offset
from adv_py.core.body_controller_appearance import body_controller_icon_template
from .maya_fit_part import MayaFitPartMixin
from .maya_fit_bendy import MayaFitBendyMixin
from .maya_body_selection_sets import MayaBodySelectionSetsMixin
from .maya_body_build_pose import MayaBodyBuildPoseMixin
from .maya_fit_inbetween import MayaFitInbetweenMixin
from .maya_fit_inbetween_spline_ik import MayaInbetweenSplineIkMixin
from .maya_fit_inbetween_hip_swing import MayaHipSwingReverseMixin
from .maya_fit_hip_swing_no_parts import MayaHipSwingNoPartsMixin
from .maya_body_parent_constraint import MayaBodyParentConstraintMixin
from .maya_body_fit_advanced_constraint import MayaBodyFitAdvancedConstraintMixin
from .maya_body_fit_follow import MayaBodyFitFollowMixin
from .maya_body_fit_named_follow import MayaBodyFitNamedFollowMixin
from .maya_body_fit_follow_spaces import MayaBodyFitFollowSpacesMixin
from .maya_body_fit_aim_at import MayaBodyFitAimAtMixin
from .maya_body_fit_geo_attach import MayaBodyFitGeoAttachMixin
from .maya_body_fit_proximity_pin import MayaBodyFitProximityPinMixin
from .maya_body_fit_curve_guide import MayaBodyFitCurveGuideMixin
from .maya_body_fit_wheel import MayaBodyFitWheelMixin
from .maya_body_center_between_feet import MayaBodyCenterBetweenFeetMixin
from .maya_body_game_root_motion import MayaBodyGameRootMotionMixin
from .maya_body_game_scaling import MayaBodyGameScalingMixin
from .maya_body_driving_fit import MayaBodyDrivingFitMixin
from .maya_fit_non_symmetry import MayaFitNonSymmetryMixin
from .maya_body_delete import MayaBodyDeleteMixin


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


class MayaBodyBuildHost(MayaBodyDrivingFitMixin, MayaFitNonSymmetryMixin, MayaBodyDeleteMixin, MayaBodyFitCurveGuideMixin, MayaBodyFitWheelMixin, MayaBodyBuildPoseMixin, MayaBodySelectionSetsMixin, MayaBodyFkScaleCompensationMixin, MayaBodyFitFollowMixin, MayaBodyFitNamedFollowMixin, MayaBodyFitFollowSpacesMixin, MayaBodyFitAimAtMixin, MayaBodyFitGeoAttachMixin, MayaBodyFitProximityPinMixin, MayaBodyCenterBetweenFeetMixin, MayaBodyFitAdvancedConstraintMixin, MayaBodyParentConstraintMixin, MayaBodyGameRootMotionMixin, MayaBodyGameScalingMixin, MayaHipSwingNoPartsMixin, MayaHipSwingReverseMixin, MayaInbetweenSplineIkMixin, MayaFitInbetweenMixin, MayaFitBendyMixin, MayaFitPartMixin, MayaControlCurveMixin, MayaCharacterPoseMixin, MayaCharacterRegistryMixin, MayaBodyFitAimMixin, MayaBodyPoleAimMixin, MayaBodyControlSpacesMixin, MayaBodySpineMixin, MayaBodyTorsoMixin, MayaFitJointHost):
    """Maya scene adapter for the first materialized Body skeleton stage."""

    def copy_external_mesh_for_character(self, mesh_path: str) -> str:
        """Keep a source mesh intact when building a separate character."""
        self._require_transaction()
        c = self._cmds.raw
        identity = self._cmds.identity
        matches = c.ls(mesh_path, long=True, type="transform") or []
        if len(matches) != 1:
            raise FitSkeletonValidationError(
                "网格路径不存在或不唯一：" + mesh_path)
        path = matches[0]
        local = identity.to_local(path)
        self.preflight_body_mesh(local)
        if identity.owns(path):
            return local
        copy = c.duplicate(path, returnRootsOnly=True,
                           renameChildren=True)[0]
        self._transaction_changed = True
        leaf = path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        target = (":" + identity.namespace + ":" + leaf
                  if identity.namespace else ":" + leaf)
        copy = c.rename(copy, target)
        if c.listRelatives(copy, parent=True):
            copy = c.parent(copy, world=True)[0]
        c.delete(copy, constructionHistory=True)
        return identity.to_local((c.ls(copy, long=True) or [copy])[0])

    def preflight_body_mesh(self, mesh_path: str) -> int:
        c = self._cmds
        matches = c.ls(mesh_path, long=True, type="transform") or []
        if len(matches) != 1 or matches[0] != mesh_path:
            raise FitSkeletonValidationError("网格路径不存在或不唯一：" + mesh_path)
        shapes = c.listRelatives(mesh_path, shapes=True,
            noIntermediate=True, fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("网格必须恰好有一个可见多边形 Shape")
        history = c.listHistory(shapes[0], pruneDagObjects=True) or []
        if any(c.nodeType(node) == "skinCluster" for node in history):
            raise FitSkeletonValidationError("网格已有 Skin，不能重复绑定：" + mesh_path)
        vertices = int(c.polyEvaluate(mesh_path, vertex=True))
        if vertices < 1:
            raise FitSkeletonValidationError("网格没有顶点：" + mesh_path)
        return vertices

    def read_fit_deform_profile(self, joint: str) -> FitDeformProfile:
        c = self._cmds
        matches = c.ls(joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != joint:
            raise FitSkeletonValidationError("Fit 体积来源关节无效：" + joint)

        def read(*names: str) -> float:
            for name in names:
                if c.attributeQuery(name, node=joint, exists=True):
                    return float(c.getAttr(f"{joint}.{name}"))
            return 1.0

        return FitDeformProfile(
            read("fat"), read("fatFront", "fatY"),
            read("fatWidth", "fatZ"))

    def read_fit_deform_profile_presence(self, joint: str) -> bool:
        c = self._cmds
        matches = c.ls(joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != joint:
            raise FitSkeletonValidationError("Fit 体积属性来源关节无效：" + joint)
        return all(c.attributeQuery(name, node=joint, exists=True)
                   for name in ("fat", "fatFront", "fatWidth"))

    def read_fit_skin_enabled(self, joint: str) -> bool:
        c = self._cmds
        current = c.ls(joint, long=True, type="joint") or []
        if len(current) != 1 or current[0] != joint:
            raise FitSkeletonValidationError("Fit Skin 来源关节无效：" + joint)
        node = current[0]
        while node:
            if (c.attributeQuery("noSkin", node=node, exists=True)
                    and bool(c.getAttr(node + ".noSkin"))):
                return False
            parents = c.listRelatives(node, parent=True, fullPath=True) or []
            node = parents[0] if parents else ""
        return True

    def read_fit_rotation_order(self, joint: str) -> int:
        matches = self._cmds.ls(joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != joint:
            raise FitSkeletonValidationError("Fit 旋转顺序来源关节无效：" + joint)
        return int(self._cmds.getAttr(joint + ".rotateOrder"))

    def read_skin_influence_enabled(self, joint: str) -> bool:
        c = self._cmds
        matches = c.ls(joint, long=True, type="joint") or []
        if len(matches) != 1:
            raise FitSkeletonValidationError("Skin 影响关节无效：" + joint)
        node = matches[0]
        while node:
            if (c.attributeQuery("advPySkinEnabled", node=node, exists=True)
                    and not bool(c.getAttr(node + ".advPySkinEnabled"))):
                return False
            parents = c.listRelatives(node, parent=True, fullPath=True) or []
            node = parents[0] if parents else ""
        return True

    def create_body_joint(self, spec: BodyJointSpec) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(
                f"同名节点已存在，拒绝创建构建关节：{spec.name}"
            )
        parent = None
        if spec.parent_path is not None:
            matches = self._cmds.ls(spec.parent_path, long=True) or []
            if len(matches) != 1:
                raise FitSkeletonValidationError(
                    f"构建关节父级在执行前失效：{spec.parent_path}"
                )
            if self._cmds.nodeType(matches[0]) not in ("joint", "transform"):
                raise FitSkeletonValidationError(
                    f"构建关节父级类型无效：{spec.parent_path}"
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
        self._cmds.setAttr(f"{path}.rotateOrder", spec.rotation_order)
        self._cmds.setAttr(f"{path}.segmentScaleCompensate",
                           spec.segment_scale_compensate)
        for name, value in (
            ("fat", spec.deform_profile.fat),
            ("fatFront", spec.deform_profile.fat_front),
            ("fatWidth", spec.deform_profile.fat_width),
        ):
            self._cmds.addAttr(path, longName=name, attributeType="double",
                               minValue=0.0, defaultValue=value, keyable=False)
        self._cmds.addAttr(path, longName="advPySkinEnabled",
                           attributeType="bool", defaultValue=spec.skin_enabled)
        self._cmds.addAttr(path, longName="advPyFitHasDeformProfile",
                           attributeType="bool",
                           defaultValue=spec.fit_has_deform_profile)
        return path

    def has_body_dynamic_system(self) -> bool:
        path = "|Group|MotionSystem|DynamicSystem"
        return (self._cmds.ls(path, long=True, type="transform") or []) == [path]

    def set_scene_up_axis(self, axis: str) -> None:
        """Set Maya's scene axis inside the character build undo chunk."""
        self._require_transaction()
        if axis not in ("y", "z"):
            raise ValueError("场景上方向只能是 Y 或 Z")
        if self._cmds.upAxis(query=True, axis=True) != axis:
            self._transaction_changed = True
            self._cmds.upAxis(axis=axis)

    def flip_character_scene_up_axis(self, transform: str, axis: str) -> None:
        """Port asSceneUpAxisFlip's rotate-channel and up-axis sequence."""
        self._require_transaction()
        matches = self._cmds.ls(transform, long=True, type="transform") or []
        if len(matches) != 1:
            raise FitSkeletonValidationError(
                "场景上方向转换目标不存在或不唯一：" + transform)
        transform = matches[0]
        if axis not in ("y", "z"):
            raise ValueError("场景上方向只能是 Y 或 Z")
        channels = tuple(transform + ".r" + suffix
                         for suffix in ("x", "y", "z", ""))
        locked = tuple(bool(self._cmds.getAttr(plug, lock=True))
                       for plug in channels)
        self._transaction_changed = True
        try:
            for plug, was_locked in zip(channels, locked):
                if was_locked:
                    self._cmds.setAttr(plug, lock=False)
            self._cmds.setAttr(transform + ".r", 90 if axis == "z" else 0,
                               0, 0, type="float3")
        finally:
            for plug, was_locked in zip(channels, locked):
                if was_locked:
                    self._cmds.setAttr(plug, lock=True)
        self.set_scene_up_axis(axis)

    def create_body_system_hierarchy(
        self, *, include_dynamic: bool = True,
    ) -> str:
        """Reserve the original rig's Group and DeformationSystem before Body."""
        self._require_transaction()
        if any(self.find_name_collisions(name)
               for name in BODY_SYSTEM_RESERVED_NAMES):
            raise FitSkeletonValidationError(
                "角色系统层级名称已被占用")
        group = self._cmds.createNode(
            "transform", name="Group", skipSelect=True)
        deformation = self._cmds.createNode(
            "transform", name="DeformationSystem", parent=group,
            skipSelect=True)
        geometry = self._cmds.createNode(
            "transform", name="Geometry", parent=group,
            skipSelect=True)
        motion = self._cmds.createNode(
            "transform", name="MotionSystem", parent=group,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="FKSystem", parent=motion,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="IKSystem", parent=motion,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="FKIKSystem", parent=motion,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="TwistSystem", parent=motion,
            skipSelect=True)
        bend = self._cmds.createNode(
            "transform", name="BendSystem", parent=motion,
            skipSelect=True)
        self._cmds.setAttr(f"{bend}.inheritsTransform", False)
        self._cmds.setAttr(f"{bend}.inheritsTransform", lock=True)
        root_system = self._cmds.createNode(
            "transform", name="RootSystem", parent=motion,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="RootFollowMain", parent=root_system,
            skipSelect=True)
        global_system = self._cmds.createNode(
            "transform", name="GlobalSystem", parent=motion,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="GlobalFollowMain", parent=global_system,
            skipSelect=True)
        self._cmds.createNode(
            "transform", name="AimSystem", parent=motion,
            skipSelect=True)
        constraint_system = self._cmds.createNode(
            "transform", name="ConstraintSystem", parent=motion,
            skipSelect=True)
        self._cmds.setAttr(constraint_system + ".visibility", False)
        self._cmds.setAttr(constraint_system + ".visibility", lock=True)
        if include_dynamic:
            self._cmds.createNode(
                "transform", name="DynamicSystem", parent=motion,
                skipSelect=True)
        self._cmds.createNode(
            "transform", name="DrivingSystem", parent=motion,
            skipSelect=True)
        for kind in ("translate", "rotate", "scale"):
            for axis in "XYZ":
                self._cmds.setAttr(
                    f"{group}.{kind}{axis}", lock=True, keyable=False)
        self._cmds.setAttr(group + ".visibility", lock=False, keyable=True)
        self._cmds.setAttr(geometry + ".inheritsTransform", False)
        self._cmds.setAttr(geometry + ".inheritsTransform", lock=True)
        self._transaction_changed = True
        group_path = (self._cmds.ls(group, long=True) or [group])[0]
        deformation_path = (self._cmds.ls(deformation, long=True)
                            or [deformation])[0]
        if group_path != "|Group" or deformation_path != "|Group|DeformationSystem":
            raise RuntimeError("Body 系统层级路径漂移")
        return deformation_path

    def parent_body_mesh_under_geometry(self, mesh_path: str) -> str:
        self._require_transaction()
        self.preflight_body_mesh(mesh_path)
        geometry = "|Group|Geometry"
        if (self._cmds.ls(geometry, long=True, type="transform") or []) != [geometry]:
            raise FitSkeletonValidationError("角色 Geometry 层级不存在")
        parents = self._cmds.listRelatives(
            mesh_path, parent=True, fullPath=True) or []
        if parents == [geometry]:
            return mesh_path
        self._transaction_changed = True
        moved = self._cmds.parent(mesh_path, geometry)[0]
        path = (self._cmds.ls(moved, long=True) or [moved])[0]
        if path != geometry + "|" + mesh_path.rsplit("|", 1)[-1]:
            raise RuntimeError("Skin 网格移入 Geometry 后路径漂移")
        self.preflight_body_mesh(path)
        return path

    def parent_fit_skeleton_under_group(self, container_name: str) -> str:
        self._require_transaction()
        matches = self._cmds.ls(
            container_name, long=True, type="transform") or []
        if len(matches) != 1:
            raise FitSkeletonValidationError("FitSkeleton 容器不存在或不唯一")
        fit_path = matches[0]
        leaf = fit_path.rsplit("|", 1)[-1]
        parents = self._cmds.listRelatives(
            fit_path, parent=True, fullPath=True) or []
        if parents:
            raise FitSkeletonValidationError(
                "FitSkeleton 必须从场景根层移入 Group")
        self._transaction_changed = True
        moved = self._cmds.parent(fit_path, "|Group")[0]
        path = (self._cmds.ls(moved, long=True) or [moved])[0]
        if path != "|Group|" + leaf:
            raise RuntimeError("FitSkeleton 移入 Group 后路径漂移")
        return path

    def finalize_fit_skeleton_visibility(self, container_path: str) -> None:
        self._require_transaction()
        matches = self._cmds.ls(
            container_path, long=True, type="transform") or []
        if matches != [container_path] or not container_path.startswith(
                "|Group|") or container_path.count("|") != 2:
            raise FitSkeletonValidationError("待隐藏 Fit 容器层级无效")
        plug = container_path + ".visibility"
        self._transaction_changed = True
        self._cmds.setAttr(plug, lock=False)
        self._cmds.setAttr(plug, False)
        self._cmds.setAttr(plug, lock=True)

    def toggle_fit_advanced_visibility(self) -> bool:
        """Switch an existing Body between Fit and generated rig display."""
        c = self._cmds
        names = ("FitSkeleton", "MotionSystem", "DeformationSystem")
        found = {name: c.ls(name, long=True, type="transform") or ()
                 for name in names}
        if any(len(paths) != 1 for paths in found.values()):
            raise FitSkeletonValidationError(
                "Toggle Fit/Adv 需要完整且唯一的 Body 系统层级")
        fit, motion, deformation = (found[name][0] for name in names)
        was_visible = bool(c.getAttr(fit + ".visibility"))
        driving_plan = (self.plan_body_driving_fit_sync(fit)
                        if not was_visible else None)
        for path in (fit, motion, deformation):
            if c.referenceQuery(path, isNodeReferenced=True):
                raise FitSkeletonValidationError(
                    "不能切换引用中的 Body 系统可见性")
        with self.transaction("切换 Body Fit／Advanced 显示"):
            self._transaction_changed = True
            fit_plug = fit + ".visibility"
            if c.getAttr(fit_plug, lock=True):
                c.setAttr(fit_plug, lock=False)
            c.setAttr(fit_plug, not was_visible)
            c.setAttr(fit_plug, lock=True)
            c.setAttr(motion + ".visibility", was_visible)
            c.setAttr(deformation + ".visibility", was_visible)
            if driving_plan is not None:
                self.apply_body_driving_fit_sync(driving_plan)
            if (bool(c.getAttr(fit_plug)) == was_visible
                    or bool(c.getAttr(motion + ".visibility")) != was_visible
                    or bool(c.getAttr(deformation + ".visibility"))
                        != was_visible):
                raise RuntimeError("Body Fit／Advanced 显示切换未生效")
        return not was_visible

    def capture_body_system_hierarchy(
        self, body_root_path: str,
        fit_container_path: str = "|Group|FitSkeleton",
        *, include_dynamic: bool = True,
    ) -> tuple[tuple[str, str | None, str], ...]:
        if bool(self._cmds.getAttr("|Group|Geometry.inheritsTransform")):
            raise FitSkeletonValidationError(
                "角色 Geometry 不得继承 Group 变换")
        if (bool(self._cmds.getAttr(
                "|Group|MotionSystem|BendSystem.inheritsTransform"))
                or not bool(self._cmds.getAttr(
                    "|Group|MotionSystem|BendSystem.inheritsTransform",
                    lock=True))):
            raise FitSkeletonValidationError(
                "角色 BendSystem 不得继承 MotionSystem 变换")
        constraint_visibility = (
            "|Group|MotionSystem|ConstraintSystem.visibility")
        if (bool(self._cmds.getAttr(constraint_visibility))
                or not bool(self._cmds.getAttr(
                    constraint_visibility, lock=True))):
            raise FitSkeletonValidationError(
                "角色 ConstraintSystem 必须隐藏并锁定可见性")
        if any(
            not bool(self._cmds.getAttr(
                f"|Group.{kind}{axis}", lock=True))
            or bool(self._cmds.getAttr(
                f"|Group.{kind}{axis}", keyable=True))
            for kind in ("translate", "rotate", "scale")
            for axis in "XYZ"
        ):
            raise FitSkeletonValidationError(
                "角色 Group 变换通道必须锁定并隐藏")
        fit_visibility = fit_container_path + ".visibility"
        if (bool(self._cmds.getAttr(fit_visibility))
                or not bool(self._cmds.getAttr(fit_visibility, lock=True))):
            raise FitSkeletonValidationError(
                "构建完成的 Fit 容器可见性必须关闭并锁定")
        paths = tuple(path for path, _, _ in expected_body_system_hierarchy(
            body_root_path, fit_container_path,
            include_dynamic=include_dynamic))
        rows = []
        for path in paths:
            matches = self._cmds.ls(path, long=True) or []
            if matches != [path]:
                raise FitSkeletonValidationError(
                    "Body 系统层级节点缺失或路径不唯一：" + path)
            parents = self._cmds.listRelatives(
                path, parent=True, fullPath=True) or []
            rows.append((path, parents[0] if parents else None,
                         self._cmds.nodeType(path)))
        return tuple(rows)

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
                in {"axial-part-v1", "finger-mid-v1", "limb-part-v1",
                    "fit-part-v1", "fit-inbetween-v1",
                    "root-volume-v1", "chest-volume-v1", "sdk-volume-v1",
                    "volume-half-parent-v1", "original-local-angle-v1",
                    "face-eye-v1", "custom-skin-v1",
                    "custom-partial-parent-v1"})]
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
                    deform_profile=FitDeformProfile(*(
                        float(self._cmds.getAttr(f"{path}.{name}"))
                        if self._cmds.attributeQuery(name, node=path, exists=True)
                        else 1.0
                        for name in ("fat", "fatFront", "fatWidth")
                    )),
                    skin_enabled=(
                        bool(self._cmds.getAttr(path + ".advPySkinEnabled"))
                        if self._cmds.attributeQuery(
                            "advPySkinEnabled", node=path, exists=True)
                        else True),
                    rotation_order=int(self._cmds.getAttr(
                        path + ".rotateOrder")),
                    segment_scale_compensate=bool(self._cmds.getAttr(
                        path + ".segmentScaleCompensate")),
                    fit_has_deform_profile=(
                        bool(self._cmds.getAttr(
                            path + ".advPyFitHasDeformProfile"))
                        if self._cmds.attributeQuery(
                            "advPyFitHasDeformProfile", node=path,
                            exists=True) else False),
                )
            )
        provenance = self._capture_body_provenance(root)
        fit_height = None
        if provenance is not None and provenance.source_container:
            containers = self._cmds.ls(provenance.source_container,
                                       long=True, type="transform") or []
            if len(containers) == 1:
                fit_joints = self._cmds.listRelatives(
                    containers[0], allDescendents=True,
                    fullPath=True, type="joint") or []
                if fit_joints:
                    fit_height = fit_character_height(tuple(
                        tuple(float(value) for value in self._cmds.xform(
                            joint, query=True, worldSpace=True,
                            translation=True)) for joint in fit_joints))
        return BodySkeletonSnapshot(
            root, tuple(states), provenance, fit_height,
        )

    def capture_body_rebuild_segment_mode(self, root_name: str) -> str:
        """Select the same segment construction used by the existing rig."""
        c = self._cmds
        roots = c.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                "重建分段检查需要唯一 Body 根关节：" + root_name)
        descendants = c.listRelatives(roots[0], allDescendents=True,
                                      fullPath=True, type="joint") or []
        kinds = {
            c.getAttr(path + ".advPyAuxiliaryInfluenceKind")
            for path in descendants
            if c.attributeQuery("advPyAuxiliaryInfluenceKind",
                                node=path, exists=True)
        }
        if kinds & {"fit-part-v1", "fit-inbetween-v1"}:
            return "fit_part"
        if kinds & {"axial-part-v1", "finger-mid-v1", "limb-part-v1"}:
            return "legacy_segments"
        return "fit_part"

    def capture_body_export_source_joints(
        self, root_name: str,
    ) -> tuple[BodyExportSourceJoint, ...]:
        """Read the actual deformation hierarchy, including inserted Part joints."""
        body = self.capture_body_skeleton(root_name)
        c = self._cmds
        paths = c.listRelatives(body.root, allDescendents=True,
                                type="joint", fullPath=True) or []
        paths.append(body.root)
        result = []
        for path in sorted(set(paths), key=lambda value: (value.count("|"), value)):
            parents = c.listRelatives(path, parent=True, fullPath=True) or []
            matrix = c.xform(path, query=True, worldSpace=True, matrix=True)
            name = path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            side_code = int(c.getAttr(path + ".side"))
            side = _CORE_SIDE_FROM_MAYA.get(side_code)
            if side is None:
                raise FitSkeletonValidationError(
                    f"导出关节侧向值无效：{path}.side={side_code}")
            if (side is FitBuildSide.MIDDLE
                    and c.attributeQuery("advPyAuxiliaryInfluenceKind",
                                         node=path, exists=True)
                    and c.getAttr(path + ".advPyAuxiliaryInfluenceKind")
                        in ("fit-part-v1", "fit-inbetween-v1")):
                # Older Part builds left Maya's side at its default value.
                if name.endswith("_L"):
                    side = FitBuildSide.LEFT
                elif name.endswith("_R"):
                    side = FitBuildSide.RIGHT
            result.append(BodyExportSourceJoint(
                path=path,
                name=name,
                parent_path=parents[0] if parents else None,
                side=side,
                label=self.read_joint_label(path),
                joint_orient=tuple(float(value) for value in
                                   c.getAttr(path + ".jointOrient")[0]),
                world_position=tuple(float(value) for value in
                                     c.xform(path, query=True,
                                             worldSpace=True, translation=True)),
                world_axes=tuple(self._normalized_vector(tuple(float(value)
                    for value in matrix[index:index + 3]))
                    for index in (0, 4, 8)),
            ))
        return tuple(result)

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

    def create_body_control_root(self, name: str, *,
                                 parent_path: str | None = None) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Body 控制根名称冲突：{name}")
        self._transaction_changed = True
        parent = parent_path or ("|Group|MotionSystem|FKSystem"
                  if name in ("AdvPy_ArmFKControls", "AdvPy_LegFKControls")
                  and self._cmds.objExists("|Group|MotionSystem|FKSystem")
                  else None)
        if (parent_path is None
                and name in ("AdvPy_ArmIKControls", "AdvPy_LegIKControls")
                and self._cmds.objExists("|Group|MotionSystem|IKSystem")):
            parent = "|Group|MotionSystem|IKSystem"
        if (parent_path is None and name == "AdvPy_TorsoControls"
                and self._cmds.objExists(
                    "|Group|MotionSystem|RootSystem|RootFollowMain")):
            parent = "|Group|MotionSystem|RootSystem|RootFollowMain"
        options = {"name": name, "skipSelect": True}
        if parent is not None:
            options["parent"] = parent
        created = self._cmds.createNode("transform", **options)
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
                if not (name in ("Group", "MotionSystem") and self._cmds.objExists(
                    "|Group|DeformationSystem"))
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
                    or (parent[0] if parent else None)
                    != (path.rsplit("|", 1)[0] or None)
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
            if plan.joint_visibility_path is not None:
                joint = plan.joint_visibility_path
                visibility = joint + ".visibility"
                if ((self._cmds.ls(joint, long=True, type="joint") or [])
                        != [joint]
                        or source(visibility) is not None
                        or not bool(self._cmds.getAttr(
                            visibility, settable=True))
                        or not bool(self._cmds.getAttr(visibility))):
                    raise FitSkeletonValidationError(
                        "角色 Body 根关节不可安全连接 jointVis")
            for path in plan.finger_visibility_paths:
                visibility = path + ".visibility"
                if ((self._cmds.ls(path, long=True, type="transform") or [])
                        != [path]
                        or source(visibility) is not None
                        or not bool(self._cmds.getAttr(
                            visibility, settable=True))
                        or not bool(self._cmds.getAttr(visibility))):
                    raise FitSkeletonValidationError(
                        f"手指 FK 根不可安全连接 fingerVis：{path}")
            aim_fk_shape = None
            if plan.aim_fk_control_path is not None:
                head = plan.aim_fk_control_path
                controls = self._cmds.ls(
                    head, long=True, type="transform") or []
                shapes = (self._cmds.listRelatives(
                    head, shapes=True, fullPath=True,
                    type="nurbsCurve") or []) if controls == [head] else []
                wanted = plan.aim_fk_shape_path
                if (shapes != [wanted]
                        or source(wanted + ".visibility") is not None
                        or not bool(self._cmds.getAttr(
                            wanted + ".visibility", settable=True))):
                    raise FitSkeletonValidationError(
                        "头部 FK 控制曲线不可安全连接 aimFKVis")
                aim_fk_shape = wanted
            for arrow in plan.pole_arrows:
                if ((self._cmds.ls(
                        arrow.middle_joint, long=True, type="joint") or [])
                        != [arrow.middle_joint]
                        or (self._cmds.ls(
                            arrow.pole_control, long=True,
                            type="transform") or []) != [arrow.pole_control]):
                    raise FitSkeletonValidationError(
                        "Pole Vector 箭头的中段关节或控制器失效")
            follow = plan.head_aim_follow
            if follow is not None:
                if (self._cmds.ls(follow.target_offset, long=True,
                                  type="transform") or []) != [follow.target_offset]:
                    raise FitSkeletonValidationError("Head Aim 跟随层缺失")
                if (self._cmds.ls(follow.target_control, long=True,
                                  type="transform") or []) != [follow.target_control]:
                    raise FitSkeletonValidationError("Head Aim 目标控制器缺失")
                if (self._cmds.ls(follow.parent_joint, long=True,
                                  type="joint") or []) != [follow.parent_joint]:
                    raise FitSkeletonValidationError("Head Aim 上游关节缺失")
                if (self._cmds.objExists(follow.target_control + ".follow")
                        or source(follow.target_offset + ".offsetParentMatrix")
                        is not None
                        or any(source(follow.target_offset + "." + kind + axis)
                               is not None
                               or not bool(self._cmds.getAttr(
                                   follow.target_offset + "." + kind + axis,
                                   settable=True))
                               for kind in ("translate", "rotate")
                               for axis in "XYZ")):
                    raise FitSkeletonValidationError(
                        "Head Aim 跟随目标通道不可安全接线")

            self._transaction_changed = True
            existing_group = self._cmds.ls(
                plan.group_path, long=True, type="transform") or []
            if existing_group:
                if (existing_group != [plan.group_path]
                        or not self._cmds.objExists(
                            "|Group|DeformationSystem")
                        or self._cmds.nodeType(
                            "|Group|DeformationSystem") != "transform"
                        or (self._cmds.ls(
                            plan.motion_system_path, long=True,
                            type="transform") or [])
                        != [plan.motion_system_path]):
                    raise FitSkeletonValidationError(
                        "角色总控发现不完整的 Group／MotionSystem")
                group = existing_group[0]
            else:
                group = self._cmds.createNode(
                    "transform", name="Group", skipSelect=True,
                )
            motion = (plan.motion_system_path if existing_group else
                      self._cmds.createNode(
                          "transform", name="MotionSystem", parent=group,
                          skipSelect=True))
            main_system = self._cmds.createNode(
                "transform", name="MainSystem", parent=motion,
                skipSelect=True,
            )
            root = self._cmds.createNode(
                "transform",
                name=plan.root_name,
                parent=main_system,
                skipSelect=True,
            )
            fit_shapes = (
                self._cmds.listRelatives(
                    "|Group|FitSkeleton", shapes=True, noIntermediate=True,
                    fullPath=True, type="nurbsCurve") or []
                if self._cmds.objExists("|Group|FitSkeleton") else [])
            fit_shape = fit_shapes[0] if len(fit_shapes) == 1 else None

            def copy_fit_outline(destination: str, expansion: float = 1.0) -> None:
                if fit_shape is None:
                    return
                self._cmds.connectAttr(fit_shape + ".worldSpace[0]",
                                       destination + ".create", force=True)
                self._cmds.getAttr(destination + ".spans")
                self._cmds.disconnectAttr(fit_shape + ".worldSpace[0]",
                                          destination + ".create")
                if expansion != 1.0:
                    self._cmds.scale(
                        expansion, expansion, expansion,
                        destination + ".cv[*]", relative=True,
                        objectSpace=True, pivot=(0, 0, 0))

            extra_parent = root
            for index in range(len(plan.extra_control_paths), 0, -1):
                extra_name = f"AdvPy_MainExtra{index}"
                extra = create_adv_icon(
                    self._cmds, name=extra_name, parent=extra_parent,
                    template="Main_icon", radius=plan.radius * 1.1 ** index,
                    fallback_normal=plan.circle_normal)
                extra = (self._cmds.ls(extra, long=True) or [extra])[0]
                if extra != plan.extra_control_paths[index - 1]:
                    raise RuntimeError("MainExtra 控制层级路径漂移")
                shapes = self._cmds.listRelatives(
                    extra, shapes=True, fullPath=True) or []
                if len(shapes) != 1:
                    raise RuntimeError("MainExtra 曲线 shape 创建失败")
                shape = self._cmds.rename(shapes[0], extra_name + "Shape")
                copy_fit_outline(shape, 1.1 ** index)
                self._cmds.setAttr(shape + ".overrideEnabled", True)
                self._cmds.setAttr(shape + ".overrideColor", 19 + index)
                self._cmds.connectAttr(motion + ".visibility",
                                       shape + ".visibility")
                extra_parent = extra
            offset = self._cmds.createNode(
                "transform",
                name=plan.offset_name,
                parent=extra_parent,
                skipSelect=True,
            )
            control = create_adv_icon(
                self._cmds, name=plan.control_name, parent=offset,
                template="Main_icon", radius=plan.radius,
                fallback_normal=plan.circle_normal)
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
            copy_fit_outline(shape)
            self._cmds.connectAttr(motion + ".visibility",
                                   shape + ".visibility")
            if (
                root != plan.root_path
                or offset != plan.offset_path
                or control != plan.control_path
                or shape.rsplit("|", 1)[-1] != plan.shape_name
            ):
                raise RuntimeError("角色总控层级路径漂移")

            if plan.fit_height is not None:
                self._cmds.addAttr(control, longName="height",
                                   attributeType="double")
                self._cmds.setAttr(control + ".height", plan.fit_height,
                                   lock=True)

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
            scale_node = self._cmds.createNode(
                "multiplyDivide", name=plan.scale_node_name,
                skipSelect=True,
            )
            self._cmds.setAttr(f"{scale_node}.operation", 1)
            scale_input = tuple(f"{control}.scale{axis}" for axis in "XYZ")
            for index, extra_path in enumerate(plan.extra_control_paths, 1):
                extra_scale = self._cmds.createNode(
                    "multiplyDivide", name=f"MainScaleMultiplyDivide{index}",
                    skipSelect=True)
                self._cmds.setAttr(extra_scale + ".operation", 1)
                for axis_index, axis in enumerate("XYZ"):
                    self._cmds.connectAttr(
                        scale_input[axis_index],
                        f"{extra_scale}.input1{axis}")
                    self._cmds.connectAttr(
                        f"{extra_path}.scale{axis}",
                        f"{extra_scale}.input2{axis}")
                scale_input = tuple(
                    f"{extra_scale}.output{axis}" for axis in "XYZ")
            for axis in "XYZ":
                self._cmds.setAttr(f"{scale_node}.input2{axis}", 1.0)
                self._cmds.connectAttr(
                    scale_input["XYZ".index(axis)],
                    f"{scale_node}.input1{axis}",
                )
            motion_decompose = None
            if plan.extra_control_paths:
                relative = self._cmds.createNode(
                    "multMatrix", name="AdvPy_MainExtrasRelativeMM",
                    skipSelect=True)
                motion_decompose = self._cmds.createNode(
                    "decomposeMatrix", name="AdvPy_MainExtrasDecompose",
                    skipSelect=True)
                self._cmds.connectAttr(
                    control + ".worldMatrix[0]", relative + ".matrixIn[0]")
                self._cmds.connectAttr(
                    motion + ".worldInverseMatrix[0]",
                    relative + ".matrixIn[1]")
                self._cmds.connectAttr(
                    relative + ".matrixSum",
                    motion_decompose + ".inputMatrix")
            for path in plan.driven_roots:
                for axis in "XYZ":
                    self._cmds.connectAttr(
                        (f"{motion_decompose}.outputTranslate{axis}"
                         if motion_decompose else f"{control}.translate{axis}"),
                        f"{path}.translate{axis}",
                    )
                    self._cmds.connectAttr(
                        (f"{motion_decompose}.outputRotate{axis}"
                         if motion_decompose else f"{control}.rotate{axis}"),
                        f"{path}.rotate{axis}",
                    )
                    self._cmds.connectAttr(
                        plan.effective_scale_source(axis),
                        f"{path}.scale{axis}",
                    )
            if plan.root_follow_main_path is not None:
                follow_path = plan.root_follow_main_path
                if (self._cmds.ls(follow_path, long=True,
                                   type="transform") or []) != [follow_path]:
                    raise FitSkeletonValidationError(
                        "RootFollowMain 层级在总控创建前缺失")
                if plan.root_follow_use_opm:
                    matrix = self._cmds.createNode(
                        "multMatrix", name=plan.root_follow_matrix_name,
                        skipSelect=True)
                    self._cmds.connectAttr(
                        control + ".worldMatrix[0]",
                        matrix + ".matrixIn[0]")
                    self._cmds.connectAttr(
                        "|Group|MotionSystem|RootSystem"
                        + ".worldInverseMatrix[0]",
                        matrix + ".matrixIn[1]")
                    self._cmds.connectAttr(
                        matrix + ".matrixSum",
                        follow_path + ".offsetParentMatrix")
                else:
                    constraint = self._cmds.parentConstraint(
                        control, follow_path, maintainOffset=False,
                        name=plan.root_follow_constraint_name)
                    if len(constraint) != 1:
                        raise RuntimeError("RootFollowMain 跟随约束创建失败")
                    scale_constraint = self._cmds.scaleConstraint(
                        control, follow_path, maintainOffset=False,
                        name=plan.root_follow_scale_constraint_name)
                    if len(scale_constraint) != 1:
                        raise RuntimeError("RootFollowMain 缩放约束创建失败")
            if plan.global_follow_main_path is not None:
                follow_path = plan.global_follow_main_path
                if (self._cmds.ls(follow_path, long=True,
                                   type="transform") or []) != [follow_path]:
                    raise FitSkeletonValidationError(
                        "GlobalFollowMain 层级在总控创建前缺失")
                if plan.global_follow_use_opm:
                    matrix = self._cmds.createNode(
                        "multMatrix", name=plan.global_follow_matrix_name,
                        skipSelect=True)
                    self._cmds.connectAttr(
                        control + ".worldMatrix[0]",
                        matrix + ".matrixIn[0]")
                    self._cmds.connectAttr(
                        "|Group|MotionSystem|GlobalSystem"
                        + ".worldInverseMatrix[0]",
                        matrix + ".matrixIn[1]")
                    self._cmds.connectAttr(
                        matrix + ".matrixSum",
                        follow_path + ".offsetParentMatrix")
                else:
                    constraint = self._cmds.parentConstraint(
                        control, follow_path, maintainOffset=False,
                        name=plan.global_follow_constraint_name)
                    if len(constraint) != 1:
                        raise RuntimeError("GlobalFollowMain 跟随约束创建失败")
                    scale_constraint = self._cmds.scaleConstraint(
                        control, follow_path, maintainOffset=False,
                        name=plan.global_follow_scale_constraint_name)
                    if len(scale_constraint) != 1:
                        raise RuntimeError("GlobalFollowMain 缩放约束创建失败")
            for plug in plan.scale_destinations:
                if (plan.spine_root_scale is not None
                        and plug in tuple(
                            plan.spine_root_scale.body_root + ".scale" + axis
                            for axis in "XYZ")):
                    continue
                self._cmds.connectAttr(plan.destination_scale_source(plug), plug)
            spine_scale = plan.spine_root_scale
            if spine_scale is not None:
                blend = self._cmds.createNode(
                    "blendColors", name=spine_scale.blend_name, skipSelect=True)
                multiply = self._cmds.createNode(
                    "multiplyDivide", name=spine_scale.multiply_name,
                    skipSelect=True)
                self._cmds.setAttr(multiply + ".operation", 1)
                self._cmds.connectAttr(
                    spine_scale.ik_scale_plug, blend + ".color1")
                self._cmds.connectAttr(
                    spine_scale.fk_scale_plug, blend + ".color2")
                self._cmds.connectAttr(
                    spine_scale.mode_plug, blend + ".blender")
                for axis, color in zip("XYZ", "RGB"):
                    self._cmds.connectAttr(
                        plan.effective_scale_source(axis),
                        multiply + ".input1" + axis)
                    self._cmds.connectAttr(
                        blend + ".output" + color,
                        multiply + ".input2" + axis)
                    self._cmds.connectAttr(
                        multiply + ".output" + axis,
                        spine_scale.body_root + ".scale" + axis)
            for attribute, system_path in plan.visibility_controls:
                if (self._cmds.ls(system_path, long=True,
                                  type="transform") or []) != [system_path]:
                    raise FitSkeletonValidationError(
                        f"角色总控显示层级缺失：{system_path}")
                self._cmds.addAttr(
                    control, longName=attribute, attributeType="bool",
                    defaultValue=True, keyable=False)
                self._cmds.setAttr(
                    f"{control}.{attribute}", channelBox=True)
                self._cmds.connectAttr(
                    f"{control}.{attribute}",
                    f"{system_path}.visibility")
            for system_path in plan.scale_system_paths:
                if (self._cmds.ls(system_path, long=True,
                                  type="transform") or []) != [system_path]:
                    raise FitSkeletonValidationError(
                        f"角色总控缩放层级缺失：{system_path}")
                for axis in "XYZ":
                    self._cmds.connectAttr(
                        f"{plan.scale_node_name}.output{axis}",
                        f"{system_path}.scale{axis}")
            if plan.joint_visibility_path is not None:
                self._cmds.addAttr(
                    control, longName="jointVis", attributeType="bool",
                    defaultValue=True, keyable=False)
                self._cmds.setAttr(
                    control + ".jointVis", channelBox=True)
                self._cmds.connectAttr(
                    control + ".jointVis",
                    plan.joint_visibility_path + ".visibility")
            if plan.has_finger_visibility:
                self._cmds.addAttr(
                    control, longName="fingerVis", attributeType="bool",
                    defaultValue=True, keyable=False)
                self._cmds.setAttr(
                    control + ".fingerVis", channelBox=True)
                for path in plan.finger_visibility_paths:
                    self._cmds.connectAttr(
                        control + ".fingerVis", path + ".visibility")
            self._cmds.addAttr(
                control, longName="aimFKVis", attributeType="bool",
                defaultValue=True, keyable=False)
            self._cmds.setAttr(
                control + ".aimFKVis", channelBox=True)
            if aim_fk_shape is not None:
                self._cmds.connectAttr(
                    control + ".aimFKVis",
                    aim_fk_shape + ".visibility")
            for name in plan.reserved_visibility_attributes:
                self._cmds.addAttr(
                    control, longName=name, attributeType="bool",
                    defaultValue=True, keyable=False)
                self._cmds.setAttr(control + "." + name, channelBox=True)
            if plan.visibility_controls:
                self._cmds.connectAttr(
                    control + ".drvSysVis",
                    "|Group|MotionSystem|DrivingSystem.visibility")
            for arrow in plan.pole_arrows:
                locator = self._cmds.createNode(
                    "transform", name=arrow.locator_name,
                    parent=arrow.pole_control, skipSelect=True)
                self._cmds.createNode(
                    "locator", name=arrow.locator_name + "Shape",
                    parent=locator, skipSelect=True)
                self._cmds.setAttr(locator + ".visibility", False)
                annotation = self._cmds.createNode(
                    "transform", name=arrow.annotation_name,
                    parent=arrow.middle_joint, skipSelect=True)
                annotation_shape = self._cmds.createNode(
                    "annotationShape",
                    name=arrow.annotation_name + "Shape",
                    parent=annotation, skipSelect=True)
                self._cmds.setAttr(
                    annotation_shape + ".overrideEnabled", True)
                self._cmds.setAttr(
                    annotation_shape + ".overrideDisplayType", 2)
                self._cmds.connectAttr(
                    arrow.locator_shape_path + ".worldMatrix[0]",
                    arrow.annotation_shape_path + ".dagObjectMatrix[0]")
                self._cmds.connectAttr(
                    control + ".arrowVis",
                    arrow.annotation_path + ".visibility")
            follow = plan.head_aim_follow
            if follow is not None:
                from maya.api import OpenMaya as om

                def values(matrix):
                    return tuple(float(matrix[row][column])
                                 for row in range(4) for column in range(4))

                def set_matrix(plug, matrix):
                    self._cmds.setAttr(plug, *values(matrix), type="matrix")

                bind = om.MMatrix(self._cmds.xform(
                    follow.target_offset, query=True, worldSpace=True,
                    matrix=True))
                if any(abs(a - b) > 1e-4 for a, b in zip(
                        values(bind), follow.bind_world_matrix)):
                    raise RuntimeError("Head Aim 目标绑定矩阵在总控创建前发生变化")
                main_bind = om.MMatrix(self._cmds.xform(
                    control, query=True, worldSpace=True, matrix=True))
                parent_bind = om.MMatrix(self._cmds.xform(
                    follow.parent_joint, query=True,
                    worldSpace=True, matrix=True))
                self._cmds.addAttr(
                    follow.target_control, longName="follow",
                    attributeType="double", minValue=0.0, maxValue=10.0,
                    defaultValue=10.0, keyable=True)
                static = self._cmds.createNode(
                    "multMatrix", name=follow.static_matrix_name,
                    skipSelect=True)
                set_matrix(static + ".matrixIn[0]",
                           bind * main_bind.inverse())
                self._cmds.connectAttr(
                    control + ".worldMatrix[0]",
                    static + ".matrixIn[1]")
                parent = self._cmds.createNode(
                    "multMatrix", name=follow.parent_matrix_name,
                    skipSelect=True)
                set_matrix(parent + ".matrixIn[0]",
                           bind * parent_bind.inverse())
                self._cmds.connectAttr(
                    follow.parent_joint + ".worldMatrix[0]",
                    parent + ".matrixIn[1]")
                blend = self._cmds.createNode(
                    "blendMatrix", name=follow.blend_name,
                    skipSelect=True)
                self._cmds.connectAttr(
                    static + ".matrixSum", blend + ".inputMatrix")
                self._cmds.connectAttr(
                    parent + ".matrixSum",
                    blend + ".target[0].targetMatrix")
                scale = self._cmds.createNode(
                    "multDoubleLinear", name=follow.scale_name,
                    skipSelect=True)
                self._cmds.setAttr(scale + ".input2", 0.1)
                self._cmds.connectAttr(
                    follow.target_control + ".follow", scale + ".input1")
                self._cmds.connectAttr(
                    scale + ".output", blend + ".target[0].weight")
                local = self._cmds.createNode(
                    "multMatrix", name=follow.local_matrix_name,
                    skipSelect=True)
                self._cmds.connectAttr(
                    blend + ".outputMatrix", local + ".matrixIn[0]")
                self._cmds.connectAttr(
                    follow.target_offset.rsplit("|", 1)[0]
                    + ".worldInverseMatrix[0]", local + ".matrixIn[1]")
                for kind, neutral in (("translate", (0.0, 0.0, 0.0)),
                                      ("rotate", (0.0, 0.0, 0.0)),
                                      ("scale", (1.0, 1.0, 1.0))):
                    self._cmds.setAttr(follow.target_offset + "." + kind,
                                       *neutral, type="double3")
                if follow.use_offset_parent_matrix:
                    self._cmds.connectAttr(
                        local + ".matrixSum",
                        follow.target_offset + ".offsetParentMatrix")
                else:
                    decompose = self._cmds.createNode(
                        "decomposeMatrix", name=follow.decompose_name,
                        skipSelect=True)
                    self._cmds.setAttr(
                        decompose + ".inputRotateOrder",
                        self._cmds.getAttr(
                            follow.target_offset + ".rotateOrder"))
                    self._cmds.connectAttr(
                        local + ".matrixSum",
                        decompose + ".inputMatrix")
                    for kind in ("Translate", "Rotate", "Scale"):
                        self._cmds.connectAttr(
                            decompose + ".output" + kind,
                            follow.target_offset + "." + kind.lower())
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

        group = one_path(plan.group_path, "transform")
        motion = one_path(plan.motion_system_path, "transform")
        main_system = one_path(plan.main_system_path, "transform")
        root = one_path(plan.root_path, "transform")
        offset = one_path(plan.offset_path, "transform")
        control = one_path(plan.control_path, "transform")
        scale_nodes = self._cmds.ls(plan.scale_node_name,
                                    type="multiplyDivide") or []
        if len(scale_nodes) != 1:
            raise FitSkeletonValidationError(
                "角色总控 MainScaleMultiplyDivide 节点缺失或类型错误")
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
        follow_state = None
        follow_matrix_state = None
        if (plan.root_follow_main_path is not None
                and plan.root_follow_use_opm):
            matrix_nodes = self._cmds.ls(plan.root_follow_matrix_name,
                type="multMatrix") or []
            if len(matrix_nodes) == 1:
                follow = plan.root_follow_main_path
                neutral = (
                    all(abs(value) <= 1e-6 for value in
                        (*vector(follow, "translate"),
                         *vector(follow, "rotate")))
                    and all(abs(value - 1.0) <= 1e-6 for value in
                            vector(follow, "scale")))
                follow_matrix_state = (
                    one_path(follow, "transform"), matrix_nodes[0],
                    source(matrix_nodes[0] + ".matrixIn[0]"),
                    source(matrix_nodes[0] + ".matrixIn[1]"),
                    source(follow + ".offsetParentMatrix"),
                    neutral,
                )
        elif plan.root_follow_main_path is not None:
            parent_constraints = self._cmds.ls(
                plan.root_follow_constraint_name, long=True,
                type="parentConstraint") or []
            scale_constraints = self._cmds.ls(
                plan.root_follow_scale_constraint_name, long=True,
                type="scaleConstraint") or []
            if len(parent_constraints) == len(scale_constraints) == 1:
                parent_targets = self._cmds.parentConstraint(
                    parent_constraints[0], query=True,
                    targetList=True) or []
                scale_targets = self._cmds.scaleConstraint(
                    scale_constraints[0], query=True,
                    targetList=True) or []
                parent_resolved = (self._cmds.ls(parent_targets[0],
                                   long=True) or []
                                   if len(parent_targets) == 1 else [])
                scale_resolved = (self._cmds.ls(scale_targets[0],
                                  long=True) or []
                                  if len(scale_targets) == 1 else [])
                follow_state = (
                    parent(parent_constraints[0]),
                    parent_constraints[0].rsplit("|", 1)[-1],
                    scale_constraints[0].rsplit("|", 1)[-1]
                    if parent(scale_constraints[0])
                    == plan.root_follow_main_path else None,
                    parent_resolved[0]
                    if len(parent_resolved) == 1 else None,
                    scale_resolved[0]
                    if len(scale_resolved) == 1 else None,
                )
        global_follow_state = None
        global_matrix_state = None
        if (plan.global_follow_main_path is not None
                and plan.global_follow_use_opm):
            nodes = self._cmds.ls(plan.global_follow_matrix_name,
                                  type="multMatrix") or []
            if len(nodes) == 1:
                follow = plan.global_follow_main_path
                neutral = (
                    all(abs(value) <= 1e-6 for value in
                        (*vector(follow, "translate"),
                         *vector(follow, "rotate")))
                    and all(abs(value - 1.0) <= 1e-6 for value in
                            vector(follow, "scale")))
                global_matrix_state = (
                    one_path(follow, "transform"), nodes[0],
                    source(nodes[0] + ".matrixIn[0]"),
                    source(nodes[0] + ".matrixIn[1]"),
                    source(follow + ".offsetParentMatrix"), neutral,
                )
        elif plan.global_follow_main_path is not None:
            parent_constraints = self._cmds.ls(
                plan.global_follow_constraint_name, long=True,
                type="parentConstraint") or []
            scale_constraints = self._cmds.ls(
                plan.global_follow_scale_constraint_name, long=True,
                type="scaleConstraint") or []
            if len(parent_constraints) == len(scale_constraints) == 1:
                parent_targets = self._cmds.parentConstraint(
                    parent_constraints[0], query=True,
                    targetList=True) or []
                scale_targets = self._cmds.scaleConstraint(
                    scale_constraints[0], query=True,
                    targetList=True) or []
                parent_resolved = (self._cmds.ls(parent_targets[0],
                                   long=True) or []
                                   if len(parent_targets) == 1 else [])
                scale_resolved = (self._cmds.ls(scale_targets[0],
                                  long=True) or []
                                  if len(scale_targets) == 1 else [])
                global_follow_state = (
                    parent(parent_constraints[0]),
                    parent_constraints[0].rsplit("|", 1)[-1],
                    scale_constraints[0].rsplit("|", 1)[-1]
                    if parent(scale_constraints[0])
                    == plan.global_follow_main_path else None,
                    parent_resolved[0]
                    if len(parent_resolved) == 1 else None,
                    scale_resolved[0]
                    if len(scale_resolved) == 1 else None,
                )
        return BodyCharacterGlobalSnapshot(
            group_path=group,
            group_parent_path=parent(group),
            motion_system_path=motion,
            motion_system_parent_path=parent(motion),
            main_system_path=main_system,
            main_system_parent_path=parent(main_system),
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
            fit_height=(float(self._cmds.getAttr(control + ".height"))
                        if self._cmds.attributeQuery("height", node=control,
                                                     exists=True) else None),
            fit_height_locked=(bool(self._cmds.getAttr(
                control + ".height", lock=True))
                if self._cmds.attributeQuery("height", node=control,
                                             exists=True) else False),
            scale_attribute_plug=scale_plug,
            scale_attribute_value=float(self._cmds.getAttr(scale_plug)),
            scale_attribute_minimum=(
                float(minimum[0]) if len(minimum) == 1 else None
            ),
            control_scale_sources=tuple(
                source(f"{control}.scale{axis}") for axis in "XYZ"
            ),
            control_shape_visibility_source=(
                source(shapes[0] + ".visibility")
                if len(shapes) == 1 else None),
            extra_control_states=tuple(
                (one_path(path, "transform"), parent(path),
                 (self._cmds.nodeType(shapes[0])
                  if len(shapes) == 1 and shapes[0].rsplit("|", 1)[-1]
                  == path.rsplit("|", 1)[-1] + "Shape"
                  else None),
                 vector(path, "translate"), vector(path, "rotate"),
                 vector(path, "scale"),
                 (source(shapes[0] + ".visibility")
                  if len(shapes) == 1 else None),
                 (bool(self._cmds.getAttr(shapes[0] + ".overrideEnabled"))
                  if len(shapes) == 1 else None),
                 (int(self._cmds.getAttr(shapes[0] + ".overrideColor"))
                  if len(shapes) == 1 else None))
                for path in plan.extra_control_paths
                for shapes in (self._cmds.listRelatives(
                    path, shapes=True, fullPath=True) or [],)
            ),
            extra_scale_sources=tuple(
                tuple(source(f"MainScaleMultiplyDivide{index}.input{slot}{axis}")
                      for axis in "XYZ" for slot in (1, 2))
                for index in range(1, len(plan.extra_control_paths) + 1)
            ),
            extra_scale_operations=tuple(
                int(self._cmds.getAttr(f"MainScaleMultiplyDivide{index}.operation"))
                for index in range(1, len(plan.extra_control_paths) + 1)
            ),
            extra_motion_sources=(
                (source("AdvPy_MainExtrasRelativeMM.matrixIn[0]"),
                 source("AdvPy_MainExtrasRelativeMM.matrixIn[1]"),
                 source("AdvPy_MainExtrasDecompose.inputMatrix"))
                if plan.extra_control_paths else (None, None, None)),
            root_follow_main_state=follow_state,
            root_follow_matrix_state=follow_matrix_state,
            global_follow_main_state=global_follow_state,
            global_follow_matrix_state=global_matrix_state,
            driven_roots=tuple(driven),
            scale_destination_sources=tuple(
                (plug, source(plug))
                for plug in plan.scale_destinations
            ),
            spine_root_scale_state=(
                (
                    self._cmds.nodeType(plan.spine_root_scale.blend_name),
                    self._cmds.nodeType(plan.spine_root_scale.multiply_name),
                    source(plan.spine_root_scale.blend_name + ".color1"),
                    source(plan.spine_root_scale.blend_name + ".color2"),
                    source(plan.spine_root_scale.blend_name + ".blender"),
                    tuple(source(plan.spine_root_scale.multiply_name
                                 + ".input1" + axis) for axis in "XYZ"),
                    tuple(source(plan.spine_root_scale.multiply_name
                                 + ".input2" + axis) for axis in "XYZ"),
                    int(self._cmds.getAttr(
                        plan.spine_root_scale.multiply_name + ".operation")),
                )
                if plan.spine_root_scale is not None else None
            ),
            scale_node_input_sources=tuple(
                source(f"{plan.scale_node_name}.input1{axis}")
                for axis in "XYZ"
            ),
            scale_node_operation=int(self._cmds.getAttr(
                f"{plan.scale_node_name}.operation")),
            scale_node_input2=tuple(
                float(self._cmds.getAttr(
                    f"{plan.scale_node_name}.input2{axis}"))
                for axis in "XYZ"
            ),
            scale_node_output=tuple(
                float(self._cmds.getAttr(
                    f"{plan.scale_node_name}.output{axis}"))
                for axis in "XYZ"
            ),
            visibility_controls=tuple(
                (
                    attribute,
                    bool(self._cmds.getAttr(
                        f"{control}.{attribute}")),
                    source(f"{system_path}.visibility"),
                )
                for attribute, system_path in plan.visibility_controls
            ),
            scale_system_sources=tuple(
                (f"{system_path}.scale{axis}",
                 source(f"{system_path}.scale{axis}"))
                for system_path in plan.scale_system_paths
                for axis in "XYZ"
            ),
            joint_visibility=(
                (bool(self._cmds.getAttr(control + ".jointVis")),
                 source(plan.joint_visibility_path + ".visibility"))
                if plan.joint_visibility_path is not None else None
            ),
            finger_visibility=tuple(
                (path + ".visibility", source(path + ".visibility"))
                for path in plan.finger_visibility_paths
            ),
            finger_visibility_value=(
                bool(self._cmds.getAttr(control + ".fingerVis"))
                if plan.has_finger_visibility else None
            ),
            aim_fk_visibility=(
                (plan.aim_fk_shape_path,
                 bool(self._cmds.getAttr(control + ".aimFKVis")),
                 source(plan.aim_fk_shape_path + ".visibility"))
                if plan.aim_fk_shape_path is not None else None
            ),
            aim_fk_visibility_value=bool(
                self._cmds.getAttr(control + ".aimFKVis")),
            reserved_visibility_values=tuple(
                (name, bool(self._cmds.getAttr(control + "." + name)))
                for name in plan.reserved_visibility_attributes),
            driving_visibility_source=(
                source("|Group|MotionSystem|DrivingSystem.visibility")
                if plan.visibility_controls else None),
            pole_arrow_states=tuple(
                (one_path(arrow.locator_path, "transform"),
                 one_path(arrow.annotation_path, "transform"),
                 source(arrow.annotation_shape_path + ".dagObjectMatrix[0]"),
                 source(arrow.annotation_path + ".visibility"),
                 not bool(self._cmds.getAttr(
                     arrow.locator_path + ".visibility")),
                 (one_path(arrow.locator_shape_path, "locator")
                  == arrow.locator_shape_path
                  and one_path(arrow.annotation_shape_path,
                               "annotationShape")
                  == arrow.annotation_shape_path
                  and parent(arrow.locator_path) == arrow.pole_control
                  and parent(arrow.annotation_path) == arrow.middle_joint
                  and bool(self._cmds.getAttr(
                      arrow.annotation_shape_path + ".overrideEnabled"))
                  and int(self._cmds.getAttr(
                      arrow.annotation_shape_path + ".overrideDisplayType"))
                  == 2))
                for arrow in plan.pole_arrows),
            head_aim_follow_state=(
                self._capture_body_head_aim_follow(plan.head_aim_follow,
                                                    control, source)
                if plan.head_aim_follow is not None else None),
        )

    def _capture_body_head_aim_follow(self, follow, main, source):
        c = self._cmds
        def matrix(plug):
            values = c.getAttr(plug)
            if len(values) == 1 and isinstance(values[0], (tuple, list)):
                values = values[0]
            return tuple(float(value) for value in values)

        node_types = ((follow.static_matrix_name, "multMatrix"),
                      (follow.parent_matrix_name, "multMatrix"),
                      (follow.blend_name, "blendMatrix"),
                      (follow.scale_name, "multDoubleLinear"),
                      (follow.local_matrix_name, "multMatrix"))
        if not follow.use_offset_parent_matrix:
            node_types += ((follow.decompose_name, "decomposeMatrix"),)
        if any((c.ls(name, type=node_type) or []) != [name]
               for name, node_type in node_types):
            raise FitSkeletonValidationError("Head Aim 跟随矩阵节点缺失")
        bounds = tuple(c.attributeQuery("follow", node=follow.target_control,
                                       **{kind: True}) or []
                       for kind in ("minimum", "maximum"))
        output = (
            source(follow.target_offset + ".offsetParentMatrix"),
            tuple(source(follow.target_offset + "." + kind)
                  for kind in ("translate", "rotate", "scale")),
            (source(follow.decompose_name + ".inputMatrix")
             if not follow.use_offset_parent_matrix else None),
            (int(c.getAttr(follow.decompose_name + ".inputRotateOrder"))
             if not follow.use_offset_parent_matrix else None),
            tuple(tuple(float(value) for value in
                        c.getAttr(follow.target_offset + "." + kind)[0])
                  for kind in ("translate", "rotate", "scale")),
        )
        return (follow.target_control,
                float(c.getAttr(follow.target_control + ".follow")),
                bounds, follow.use_offset_parent_matrix,
                source(follow.static_matrix_name + ".matrixIn[1]"),
                source(follow.parent_matrix_name + ".matrixIn[1]"),
                source(follow.blend_name + ".inputMatrix"),
                source(follow.blend_name + ".target[0].targetMatrix"),
                source(follow.scale_name + ".input1"),
                float(c.getAttr(follow.scale_name + ".input2")),
                source(follow.blend_name + ".target[0].weight"),
                source(follow.local_matrix_name + ".matrixIn[0]"),
                source(follow.local_matrix_name + ".matrixIn[1]"),
                output,
                tuple(float(value) for value in c.xform(
                    follow.target_offset, query=True,
                    worldSpace=True, matrix=True)),
                (matrix(follow.static_matrix_name + ".matrixIn[0]"),
                 matrix(follow.parent_matrix_name + ".matrixIn[0]"),
                 tuple(float(value) for value in c.xform(
                     main, query=True, worldSpace=True, matrix=True)),
                 tuple(float(value) for value in c.xform(
                     follow.parent_joint, query=True,
                     worldSpace=True, matrix=True))))

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

    def remove_existing_body_export_layer(
        self, body: BodySkeletonSnapshot, root_motion: BodyRootMotionPlan,
    ) -> bool:
        """Remove only an intact, tool-owned publication layer for rebuilding."""
        c = self._cmds
        root = root_motion.output_path
        if not (c.ls(root, long=True, type="joint") or []):
            return False
        descendants = set(c.listRelatives(root, allDescendents=True,
                                          fullPath=True) or [])
        joints = set(c.listRelatives(root, allDescendents=True,
                                    fullPath=True, type="joint") or [])
        children = c.listRelatives(root, children=True,
                                   fullPath=True, type="joint") or []
        if not joints or descendants != joints or len(children) != 1:
            raise FitSkeletonValidationError(
                "已有发布层含额外节点或骨架根不唯一，拒绝刷新")
        export_root = children[0]
        metadata = {
            "owner": BODY_EXPORT_OWNER,
            "artifact_kind": BODY_EXPORT_KIND,
            "schema_version": BODY_EXPORT_SCHEMA_VERSION,
            "source_body_root": body.root,
            "joint_count": len(joints),
        }
        if any(not c.objExists(f"{export_root}.{_BODY_EXPORT_PROVENANCE_ATTRIBUTES[key]}")
               or c.getAttr(f"{export_root}.{_BODY_EXPORT_PROVENANCE_ATTRIBUTES[key]}")
                   != value for key, value in metadata.items()):
            raise FitSkeletonValidationError(
                "已有发布骨架的所有权或来源不符，拒绝刷新")
        source_markers = tuple(c.attributeQuery(
            _BODY_EXPORT_SOURCE_ATTRIBUTE, node=path, exists=True)
            for path in joints)
        baked = c.attributeQuery(
            _BODY_EXPORT_BAKE_ATTRIBUTES["bake_schema_version"],
            node=export_root, exists=True)
        if ((baked and any(source_markers))
                or (not baked and not all(source_markers))
                or (baked and c.getAttr(export_root + "." +
                    _BODY_EXPORT_BAKE_ATTRIBUTES["bake_schema_version"])
                    != BODY_EXPORT_BAKE_SCHEMA_VERSION)):
            raise FitSkeletonValidationError(
                "已有发布骨架的来源标记或烘焙状态不完整，拒绝刷新")
        for skin in c.ls(type="skinCluster") or []:
            for influence in c.skinCluster(skin, query=True,
                                           influence=True) or []:
                paths = c.ls(influence, long=True, type="joint") or []
                if any(path in joints or path == root for path in paths):
                    raise FitSkeletonValidationError(
                        "已有发布骨架被 Skin 使用，拒绝刷新：" + skin)
        if any(c.listConnections(path, source=False, destination=True)
               for path in (root, *joints)):
            raise FitSkeletonValidationError(
                "已有发布骨架被其他节点依赖，拒绝刷新")
        with self.transaction("刷新已有游戏发布层"):
            self._transaction_changed = True
            c.delete(root)
        return True

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

    def _capture_fbx_skin_sources(self, influence_map, published_names):
        from .maya_dense_skin import MayaDenseSkinHost

        c = self._cmds
        source_paths = {source: target for source, target in influence_map}
        source_names = {path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]:
                        target for path, target in influence_map}
        if len(source_paths) != len(influence_map) or len(source_names) != len(influence_map):
            raise FitSkeletonValidationError("FBX 蒙皮影响关节映射不唯一")
        root = influence_map[0][0]
        host = MayaDenseSkinHost(namespace=self.namespace)
        rows = []
        mesh_names = set()
        for skin in c.ls(type="skinCluster") or []:
            influences = c.skinCluster(skin, query=True,
                                       influence=True) or []
            resolved = [c.ls(joint, long=True, type="joint") or []
                        for joint in influences]
            owned = [len(paths) == 1 and (paths[0] == root or
                paths[0].startswith(root + "|")) for paths in resolved]
            if not any(owned):
                continue
            if not all(owned) or any(paths[0] not in source_paths
                                     for paths in resolved):
                raise FitSkeletonValidationError(
                    "角色 Skin 混用了发布骨架之外的影响关节：" + skin)
            shapes = c.skinCluster(skin, query=True, geometry=True) or []
            if len(shapes) != 1:
                raise FitSkeletonValidationError("角色 Skin 需要唯一网格：" + skin)
            shape = c.ls(shapes[0], long=True, type="mesh") or []
            mesh = (c.listRelatives(shape[0], parent=True,
                fullPath=True) or []) if len(shape) == 1 else []
            if len(mesh) != 1:
                raise FitSkeletonValidationError("角色 Skin 网格路径不唯一：" + skin)
            mesh_name = mesh[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if mesh_name in mesh_names or mesh_name in published_names:
                raise FitSkeletonValidationError(
                    "FBX 发布网格名称与其他网格或关节冲突：" + mesh_name)
            mesh_names.add(mesh_name)
            data = host.capture_dense_skin(skin)
            if len({name.rsplit(":", 1)[-1]
                    for name in data.influence_names}) != len(data.influence_names):
                raise FitSkeletonValidationError("Skin 影响关节名称不唯一：" + skin)
            skin_fn, _, _, api_names, _ = host._skin_api(skin)
            if api_names != data.influence_names:
                raise RuntimeError("FBX Skin 影响关节顺序在捕获期间变化：" + skin)
            bind_matrices = []
            for influence in skin_fn.influenceObjects():
                logical = skin_fn.indexForInfluenceObject(influence)
                values = c.getAttr(f"{skin}.bindPreMatrix[{logical}]")
                if len(values) == 1 and isinstance(values[0], (tuple, list)):
                    values = values[0]
                bind_matrices.append(tuple(float(value) for value in values))
            bind_matrices = tuple(bind_matrices)
            if any(len(matrix) != 16 for matrix in bind_matrices):
                raise FitSkeletonValidationError(
                    "FBX Skin 绑定逆矩阵不完整：" + skin)
            rows.append((mesh[0], data,
                         int(c.getAttr(skin + ".maxInfluences")),
                         bool(c.getAttr(skin + ".maintainMaxInfluences")),
                         int(c.getAttr(skin + ".skinningMethod")),
                         int(c.getAttr(skin + ".normalizeWeights")),
                         float(c.getAttr(skin + ".envelope")),
                         host.capture_skin_blend_weights(skin),
                         bind_matrices,
                         source_names))
        if not rows:
            raise FitSkeletonValidationError("当前角色没有可发布的 Skin 网格")
        return tuple(rows)

    def _extra_fbx_skin_influences(self, influence_map):
        """Preserve every owned Skin influence absent from the export skeleton."""
        c = self._cmds
        body_root = influence_map[0][0]
        targets = dict(influence_map)
        owned = set()
        for skin in c.ls(type="skinCluster") or []:
            for influence in c.skinCluster(skin, query=True,
                                           influence=True) or []:
                paths = c.ls(influence, long=True, type="joint") or []
                if len(paths) != 1:
                    raise FitSkeletonValidationError(
                        "FBX Skin 影响关节路径不唯一：" + influence)
                path = paths[0]
                if path == body_root or path.startswith(body_root + "|"):
                    owned.add(path)
        missing = owned - targets.keys()
        known_names = {target.rsplit("|", 1)[-1]
                       for target in targets.values()}
        ordered = []
        for source in sorted(missing, key=lambda path: (path.count("|"), path)):
            name = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            if name in known_names:
                raise FitSkeletonValidationError(
                    "FBX Skin 影响关节发布名称重复：" + name)
            parent = (c.listRelatives(source, parent=True,
                                      fullPath=True) or [None])[0]
            while parent not in targets and parent is not None:
                parent = (c.listRelatives(parent, parent=True,
                                          fullPath=True) or [None])[0]
            if parent is None:
                raise FitSkeletonValidationError(
                    "FBX Skin 影响关节不属于可发布 Body：" + source)
            target = targets[parent] + "|" + name
            targets[source] = target
            known_names.add(name)
            ordered.append((source, target))
        return tuple(ordered)

    def _bake_temporary_skin_joints(self, extra_influences, selection, *,
                                    namespace_free=False):
        if not extra_influences:
            return ()
        c = self._cmds.raw if namespace_free else self._cmds
        frames = tuple(range(selection.start_frame, selection.end_frame + 1,
                             selection.sample_by))
        created = []
        for source, target in extra_influences:
            parent, name = target.rsplit("|", 1)
            if c.objExists(target):
                raise FitSkeletonValidationError("FBX 影响关节发布名称冲突：" + target)
            node = c.createNode("joint", name=(":" if namespace_free else "")
                                + name, parent=parent, skipSelect=True)
            node = (c.ls(node, long=True, type="joint") or [None])[0]
            if node != target:
                raise RuntimeError("FBX 影响关节路径漂移：" + target)
            c.setAttr(node + ".rotateOrder",
                      int(self._cmds.getAttr(source + ".rotateOrder")))
            created.append((source, node))
        for frame in frames:
            c.currentTime(frame, edit=True, update=True)
            for source, target in created:
                matrix = self._cmds.xform(source, query=True,
                                          worldSpace=True, matrix=True)
                c.xform(target, worldSpace=True, matrix=matrix)
                for kind in ("translate", "rotate", "scale"):
                    c.setKeyframe(target, attribute=kind, time=frame,
                                  inTangentType="linear", outTangentType="linear")
        return tuple(target for _, target in created)

    def _copy_fbx_skinned_meshes(self, sources, bind_frame, *,
                                 namespace_free=False):
        from array import array
        from maya.api import OpenMaya as om
        from maya.api import OpenMayaAnim as oma

        c = self._cmds.raw if namespace_free else self._cmds
        c.currentTime(bind_frame, edit=True, update=True)
        copied = []
        group = c.createNode("transform",
            name=(":AdvPy_FBXTemporaryMeshGroup" if namespace_free
                  else "AdvPy_FBXTemporaryMeshGroup")) if sources else None
        for index, (mesh, data, maximum, maintain, method,
                    normalization, envelope, blend_weights,
                    bind_matrices, mapping) in enumerate(
                sources, 1):
            target_paths = tuple(mapping[name.rsplit(":", 1)[-1]]
                                 for name in data.influence_names)
            source_envelope = data.skin_name + ".envelope"
            if not c.getAttr(source_envelope, settable=True):
                raise FitSkeletonValidationError(
                    "FBX Skin 的 envelope 被外部输入占用，无法取得原始网格："
                    + data.skin_name)
            c.setAttr(source_envelope, 0.0)
            try:
                clone = c.duplicate(self.scene_address(mesh)
                    if namespace_free else mesh, returnRootsOnly=True,
                    renameChildren=True)[0]
            finally:
                c.setAttr(source_envelope, envelope)
            clone = c.parent(clone, group)[0]
            mesh_name = mesh.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            clone = c.rename(clone, (":" if namespace_free else "")
                             + mesh_name)
            if clone.rsplit("|", 1)[-1].rsplit(":", 1)[-1] != mesh_name:
                raise FitSkeletonValidationError(
                    "FBX 临时网格未能保留源名称：" + mesh_name)
            c.delete(clone, constructionHistory=True)
            name = (":" if namespace_free else "") + f"AdvPy_FBXExportSkin_{index}"
            skin = c.skinCluster(target_paths, clone, toSelectedBones=True,
                bindMethod=0, normalizeWeights=1,
                maximumInfluences=maximum,
                obeyMaxInfluences=False, name=name)[0]
            # Preserve raw source weights before restoring the source's
            # normalization and influence-limit policy.
            c.setAttr(skin + ".maintainMaxInfluences", False)
            c.setAttr(skin + ".normalizeWeights", 0)
            selection = om.MSelectionList()
            selection.add(skin if namespace_free else self.scene_address(skin))
            skin_fn = oma.MFnSkinCluster(selection.getDependNode(0))
            present = {path.fullPathName().rsplit("|", 1)[-1]
                       .rsplit(":", 1)[-1]
                       for path in skin_fn.influenceObjects()}
            for path in target_paths:
                name = path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                if name not in present:
                    c.skinCluster(skin, edit=True, addInfluence=path,
                                  weight=0.0, lockWeights=False)
                    present.add(name)
            shapes = c.skinCluster(skin, query=True, geometry=True) or []
            shape = (c.ls(shapes[0], long=True, type="mesh") or [])[0]
            selection = om.MSelectionList()
            selection.add(shape if namespace_free else self.scene_address(shape))
            dag = selection.getDagPath(0)
            component_fn = om.MFnSingleIndexedComponent()
            component = component_fn.create(om.MFn.kMeshVertComponent)
            component_fn.addElements(range(data.vertex_count))
            source_indices = {name.rsplit(":", 1)[-1]: offset
                              for offset, name in enumerate(data.influence_names)}
            published_to_source = {target.rsplit("|", 1)[-1]: source
                for source, target in mapping.items()}
            target_influences = skin_fn.influenceObjects()
            target_names = tuple(path.fullPathName().rsplit("|", 1)[-1]
                .rsplit(":", 1)[-1] for path in target_influences)
            if set(target_names) != {
                    mapping[name].rsplit("|", 1)[-1]
                    for name in source_indices}:
                raise FitSkeletonValidationError(
                    "FBX 临时 Skin 未保留全部原始影响关节：" + data.skin_name)
            order = tuple(source_indices[published_to_source[name]]
                          for name in target_names)
            for influence, source_index in zip(target_influences, order):
                logical = skin_fn.indexForInfluenceObject(influence)
                c.setAttr(f"{skin}.bindPreMatrix[{logical}]",
                          *bind_matrices[source_index], type="matrix")
            original = array("d")
            original.frombytes(data.values)
            width = len(order)
            values = array("d", (original[vertex * width + offset]
                for vertex in range(data.vertex_count)
                for offset in order))
            skin_fn.setWeights(dag, component,
                om.MIntArray(range(width)),
                om.MDoubleArray(values.tolist()), normalize=False)
            skin_fn.setBlendWeights(
                dag, component, om.MDoubleArray(blend_weights.tolist()))
            c.setAttr(skin + ".skinningMethod", method)
            c.setAttr(skin + ".normalizeWeights", normalization)
            c.setAttr(skin + ".envelope", envelope)
            c.setAttr(skin + ".maintainMaxInfluences", maintain)
            copied.append((c.ls(clone, long=True,
                                 type="transform") or [])[0])
        return tuple(copied)

    def export_fbx_selection(
        self,
        destination: Path,
        selection: BodyFbxExportSelection,
        profile: BodyFbxExportProfile,
        *,
        skin_influence_map: tuple[tuple[str, str], ...] = (),
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
        namespace_free = self.namespace is not None
        published_cmds = (self._cmds.raw if namespace_free
                          else self._cmds)
        if namespace_free and published_cmds.objExists(
                selection.published_root_path):
            raise FitSkeletonValidationError(
                "根命名空间已有 FBX 发布根节点：" +
                selection.published_root_path)
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
        extra_influences = (self._extra_fbx_skin_influences(skin_influence_map)
                            if skin_influence_map else ())
        full_influence_map = skin_influence_map + extra_influences
        skin_sources = (self._capture_fbx_skin_sources(full_influence_map,
            {node.published_name for node in selection.published_nodes}
            | {path.rsplit("|", 1)[-1] for _, path in extra_influences})
            if full_influence_map else ())
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
            mel.eval("FBXExportShapes -v " +
                     ("true;" if skin_sources else "false;"))
            mel.eval("FBXExportSkins -v " +
                     ("true;" if skin_sources else "false;"))
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
                        published_cmds.rename(
                            self.scene_address(node.scene_path)
                            if namespace_free else node.scene_path,
                            (":" if namespace_free else "")
                            + node.published_name,
                            ignoreShape=True,
                        )
                    published_extra = self._bake_temporary_skin_joints(
                        extra_influences, selection,
                        namespace_free=namespace_free)
                    published_paths = (*selection.published_paths,
                                       *published_extra)
                    copied_meshes = self._copy_fbx_skinned_meshes(
                        skin_sources, selection.start_frame,
                        namespace_free=namespace_free)
                    if any(
                        (published_cmds.ls(path, long=True,
                                             type="joint") or [])
                        != [path]
                        for path in selection.published_paths
                    ):
                        raise RuntimeError("FBX 发布名称临时映射复检失败")
                    def sample_matrices(times):
                        poses = []
                        for frame in times:
                            published_cmds.currentTime(frame, edit=True, update=True)
                            poses.append(tuple(tuple(float(value) for value in
                                published_cmds.xform(path, query=True, worldSpace=True,
                                                 matrix=True))
                                for path in published_paths))
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
                        for path in published_paths:
                            attributes = (
                                root_attributes
                                if path == selection.published_root_path
                                else BODY_EXPORT_CHANNEL_ATTRIBUTES
                            )
                            for attribute in attributes:
                                plug = f"{path}.{attribute}"
                                frame_range = (selection.start_frame, selection.end_frame)
                                times = published_cmds.keyframe(
                                    plug, query=True, time=frame_range, timeChange=True
                                ) or []
                                values = published_cmds.keyframe(
                                    plug, query=True, time=frame_range, valueChange=True
                                ) or []
                                in_types = published_cmds.keyTangent(
                                    plug, query=True, time=frame_range,
                                    inTangentType=True) or []
                                out_types = published_cmds.keyTangent(
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
                                    published_cmds.cutKey(plug, time=(frame, frame), option="keys")
                                    removed_linear_keys += 1
                    if profile.euler_filter:
                        baked_frames = tuple(range(selection.start_frame,
                            selection.end_frame + 1, selection.sample_by))
                        before_filter = sample_matrices(baked_frames)
                        for path in published_paths[1:]:
                            curves = []
                            for axis in "XYZ":
                                found = published_cmds.listConnections(
                                    f"{path}.rotate{axis}", source=True,
                                    destination=False, type="animCurve") or []
                                if len(found) != 1:
                                    raise FitSkeletonValidationError(
                                        "FBX Euler Filter 要求每个导出关节都有独立的旋转曲线："
                                        + path)
                                curves.append(found[0])
                            euler_filtered_curves += int(published_cmds.filterCurve(
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
                    published_cmds.select(
                        (*published_paths, *copied_meshes),
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

    def set_body_leg_initial_ik(self, plan: BodyLegBlendPlan) -> None:
        """Match ADV's final Foot default after the complete IK graph exists."""
        self._require_transaction()
        for side in plan.sides:
            plug = f"{plan.settings_path}.{side.attribute}"
            if not self._cmds.objExists(plug):
                raise FitSkeletonValidationError("Leg IK/FK 默认模式属性缺失：" + plug)
            if self._cmds.listConnections(plug, source=True,
                                          destination=False, plugs=True):
                raise FitSkeletonValidationError("Leg IK/FK 默认模式已被驱动：" + plug)
            self._cmds.setAttr(plug, 1.0)
            if abs(float(self._cmds.getAttr(plug)) - 1.0) > 1e-6:
                raise RuntimeError("Leg IK/FK 默认 IK 写后读回失败：" + plug)
        self._transaction_changed = True

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
        parent = "|Group|MotionSystem|TwistSystem"
        if self._cmds.objExists(parent):
            root = self._cmds.createNode(
                "transform", name=name, parent=parent, skipSelect=True)
        else:
            root = self._cmds.createNode(
                "transform", name=name, skipSelect=True)
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
        from .maya_mesh_topology import TOPOLOGY_ATTRIBUTE, mesh_topology_digest

        if self.find_name_collisions(plan.skin_name):
            raise FitSkeletonValidationError(f"Skin Bind 节点名称冲突：{plan.skin_name}")
        mesh_shapes = self._cmds.listRelatives(
            plan.mesh_path, shapes=True, noIntermediate=True,
            fullPath=True, type="mesh") or []
        if len(mesh_shapes) != 1:
            raise FitSkeletonValidationError("Skin Bind 需要唯一可见网格")
        topology = mesh_topology_digest(mesh_shapes[0])
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            created = self._cmds.skinCluster(
                list(plan.influence_paths),
                plan.mesh_path,
                toSelectedBones=True,
                bindMethod={
                    SkinBindMethod.CLOSEST_DISTANCE: 0,
                    SkinBindMethod.CLOSEST_IN_HIERARCHY: 1,
                }[plan.bind_method],
                normalizeWeights={
                    SkinWeightNormalization.INTERACTIVE: 1,
                    SkinWeightNormalization.POST: 2,
                }[plan.normalization],
                maximumInfluences=plan.maximum_influences,
                obeyMaxInfluences=plan.maintain_maximum_influences,
                name=plan.skin_name,
            )
            if not created or created[0] != plan.skin_name:
                raise RuntimeError("Maya 未按计划创建 skinCluster")
            self._cmds.setAttr(
                created[0] + ".skinningMethod",
                {SkinningMethod.CLASSIC_LINEAR: 0,
                 SkinningMethod.DUAL_QUATERNION: 1}[plan.skinning_method])
            self._cmds.addAttr(created[0], longName=TOPOLOGY_ATTRIBUTE,
                               dataType="string")
            self._cmds.setAttr(f"{created[0]}.{TOPOLOGY_ATTRIBUTE}",
                               topology, type="string")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_skin_rebind_state(self, skin: str, mesh: str):
        from adv_py.application.skin_rebind import SkinRebindState
        from .maya_mesh_topology import TOPOLOGY_ATTRIBUTE, mesh_topology_digest

        c = self._cmds
        skins = c.ls(skin, type="skinCluster") or []
        meshes = c.ls(mesh, long=True, type="transform") or []
        if len(skins) != 1 or skins[0] != skin or len(meshes) != 1 or meshes[0] != mesh:
            raise FitSkeletonValidationError("重绑目标 Skin 或网格不存在或名称不唯一")
        if c.referenceQuery(skin, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能修改引用来源中的 Skin")
        if not c.attributeQuery(TOPOLOGY_ATTRIBUTE, node=skin, exists=True):
            raise FitSkeletonValidationError("旧 Skin 缺少绑定拓扑记录，不能自动重绑")
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 fullPath=True, type="mesh") or []
        if len(shapes) != 1:
            raise FitSkeletonValidationError("重绑目标必须有唯一可见网格")
        geometry = c.skinCluster(skin, query=True, geometry=True) or []
        bound = c.ls(geometry[0], long=True, type="mesh") if len(geometry) == 1 else []
        parents = c.listRelatives(bound[0], parent=True, fullPath=True) if bound else []
        if parents != [mesh]:
            raise FitSkeletonValidationError("Skin 与重绑目标网格不匹配")
        history = c.listHistory(shapes[0], pruneDagObjects=True) or []
        skin_history = {node for node in history if c.nodeType(node) == "skinCluster"}
        if skin_history != {skin}:
            raise FitSkeletonValidationError("目标网格有多套 Skin，不能自动重绑")
        influences = []
        for joint in c.skinCluster(skin, query=True, influence=True) or []:
            paths = c.ls(joint, long=True, type="joint") or []
            if len(paths) != 1:
                raise FitSkeletonValidationError("Skin 影响关节缺失或名称不唯一")
            influences.append(paths[0])
        if not influences:
            raise FitSkeletonValidationError("Skin 没有影响关节")
        return SkinRebindState(skin, mesh, tuple(influences),
            int(c.getAttr(f"{skin}.maxInfluences")),
            bool(c.getAttr(f"{skin}.maintainMaxInfluences")),
            c.getAttr(f"{skin}.{TOPOLOGY_ATTRIBUTE}"),
            mesh_topology_digest(shapes[0]))

    def remove_skin_bind_for_rebind(self, skin: str) -> None:
        self._require_transaction()
        self._transaction_changed = True
        self._cmds.delete(skin)

    def capture_skin_bind(self, plan: SkinBindPlan) -> SkinBindSnapshot:
        clusters = self._cmds.ls(plan.skin_name, type="skinCluster") or []
        if len(clusters) != 1:
            raise FitSkeletonValidationError("Skin Bind 结果节点无效")
        skin = clusters[0]
        from .maya_mesh_topology import assert_bound_topology
        geometry = []
        for shape in self._cmds.skinCluster(skin, query=True, geometry=True) or []:
            shape_paths = self._cmds.ls(shape, long=True, type="mesh") or []
            if len(shape_paths) == 1:
                assert_bound_topology(self._cmds, skin, shape_paths[0])
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
        bind_method = {
            0: SkinBindMethod.CLOSEST_DISTANCE,
            1: SkinBindMethod.CLOSEST_IN_HIERARCHY,
        }.get(
            int(self._cmds.getAttr(f"{skin}.bindMethod"))
        )
        normalization = {
            1: SkinWeightNormalization.INTERACTIVE,
            2: SkinWeightNormalization.POST,
        }.get(
            int(self._cmds.getAttr(f"{skin}.normalizeWeights"))
        )
        skinning_method = {
            0: SkinningMethod.CLASSIC_LINEAR,
            1: SkinningMethod.DUAL_QUATERNION,
        }.get(int(self._cmds.getAttr(f"{skin}.skinningMethod")))
        return SkinBindSnapshot(
            skin,
            tuple(geometry),
            tuple(influences),
            int(self._cmds.getAttr(f"{skin}.maxInfluences")),
            bool(self._cmds.getAttr(f"{skin}.maintainMaxInfluences")),
            bind_method,
            normalization,
            skinning_method,
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
        if bound_shape:
            from .maya_mesh_topology import assert_bound_topology
            assert_bound_topology(self._cmds, skin, bound_shape)
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
        align_axes = (self._spine_world_frame(plan.wrist_align_path)[1]
                      if plan.wrist_align_path is not None and
                      self._cmds.objExists(plan.wrist_align_path) else None)
        return BodyArmFkToIkSceneState(existing, writable, value, align_axes)

    def apply_body_arm_fk_to_ik(self, plan: BodyArmFkToIkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_arm_fk_to_ik_state(plan)
        if audit_body_arm_fk_to_ik_preflight(plan, state):
            raise FitSkeletonValidationError("Arm FK→IK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            from .maya_limb_shape import begin_optional_match, finish_match
            shape_state=begin_optional_match(self,"arm",plan.side.value,"ik")
            from .maya_limb_orientation import begin_orientation_match, finish_orientation_match
            orientation_state=begin_orientation_match(self,"arm",plan.side.value)
            self._cmds.xform(plan.pole_control_path, worldSpace=True, translation=plan.pole_position)
            x_axis, y_axis, z_axis = (
                state.wrist_align_axes or plan.wrist_axes)
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
        toe_end_body_axes = ()
        if (plan.toe_end_body_path is not None
                and self._cmds.objExists(plan.toe_end_body_path)):
            matrix = self._cmds.xform(
                plan.toe_end_body_path, query=True,
                worldSpace=True, matrix=True)
            toe_end_body_axes = tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index:index + 3]))
                for index in (0, 4, 8))
        foot_values = tuple(
            (plug, float(self._cmds.getAttr(plug)))
            for plug in plan.foot_attribute_plugs
            if self._cmds.objExists(plug)
        )
        roll_values = tuple(
            (plug, float(self._cmds.getAttr(plug)))
            for plug in plan.roll_rotation_plugs
            if self._cmds.objExists(plug)
        )
        hybrid_poses = []
        for path, _, _ in plan.hybrid_joint_poses:
            if not self._cmds.objExists(path):
                continue
            matrix, axes = self._spine_world_frame(path)
            hybrid_poses.append((path, matrix[12:15], axes))
        match_source_poses = []
        match_sources = tuple(
            source for _, source in plan.hybrid_control_targets) + (
                (plan.ankle_match_axis_source,)
                if plan.ankle_match_axis_source is not None else ()) + (
                (plan.toe_match_axis_source,)
                if plan.toe_match_axis_source is not None else ())
        for source in match_sources:
            if not self._cmds.objExists(source):
                continue
            matrix, axes = self._spine_world_frame(source)
            match_source_poses.append((source, matrix[12:15], axes))
        return BodyLegFkToIkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            ankle_axes,
            toe_body_axes,
            foot_values,
            roll_values,
            toe_end_body_axes,
            tuple(hybrid_poses),
            tuple(match_source_poses),
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
            for plug, value in plan.foot_reset_values or tuple(
                    (plug, 0.0) for plug in plan.foot_attribute_plugs):
                self._cmds.setAttr(plug, value)
            for plug in plan.roll_rotation_plugs:
                self._cmds.setAttr(plug, 0.0)
            self._cmds.xform(
                plan.pole_control_path,
                worldSpace=True,
                translation=plan.pole_position,
            )
            fk_poses = {path: (position, axes)
                        for path, position, axes in state.match_source_poses}
            ankle_position = (fk_poses[
                plan.ankle_match_position_source][0]
                if plan.ankle_match_position_source is not None
                else plan.ankle_position)
            ankle_axes = (fk_poses[plan.ankle_match_axis_source][1]
                          if plan.ankle_match_axis_source is not None
                          else plan.ankle_axes)
            x_axis, y_axis, z_axis = ankle_axes
            matrix = (
                *x_axis, 0.0,
                *y_axis, 0.0,
                *z_axis, 0.0,
                *ankle_position, 1.0,
            )
            self._cmds.xform(plan.ankle_control_path, worldSpace=True, translation=ankle_position)
            self._spine_set_world_rotation(plan.ankle_control_path,matrix)
            if plan.reverse_roll_control_path is not None:
                self._match_body_leg_hybrid_roll(plan)
                for path, source in plan.hybrid_control_targets:
                    control_matrix = self._spine_world_frame(path)[0]
                    axes = fk_poses[source][1]
                    x_axis, y_axis, z_axis = axes
                    target_matrix = (
                        *x_axis, 0.0, *y_axis, 0.0,
                        *z_axis, 0.0, *control_matrix[12:15], 1.0)
                    self._spine_set_world_rotation(path, target_matrix)
            else:
                if plan.toe_sub_path:
                    self._cmds.setAttr(plan.toe_sub_path + ".rotate",
                                       0.0, 0.0, 0.0, type="double3")
                toe_position = tuple(float(value) for value in self._cmds.xform(
                    plan.toe_control_path,
                    query=True,
                    worldSpace=True,
                    translation=True,
                ))
                toe_axes = (fk_poses[plan.toe_match_axis_source][1]
                            if plan.toe_match_axis_source is not None
                            else plan.toe_body_axes)
                toe_x, toe_y, toe_z = toe_axes
                toe_matrix = (
                    *toe_x, 0.0,
                    *toe_y, 0.0,
                    *toe_z, 0.0,
                    *toe_position, 1.0,
                )
                self._spine_set_world_rotation(plan.toe_control_path,toe_matrix)
            if plan.toe_end_ik_driver_path is not None:
                if plan.toe_end_body_axes is None:
                    raise RuntimeError("Leg FK→IK 缺少 ToesEnd 目标朝向")
                end_position = tuple(float(value) for value in self._cmds.xform(
                    plan.toe_end_ik_driver_path, query=True,
                    worldSpace=True, translation=True))
                end_x, end_y, end_z = plan.toe_end_body_axes
                end_matrix = (
                    *end_x, 0.0, *end_y, 0.0, *end_z, 0.0,
                    *end_position, 1.0)
                self._spine_set_world_rotation(
                    plan.toe_end_ik_driver_path, end_matrix)
            self._cmds.setAttr(plan.blend_plug, 1.0)
            finish_orientation_match(self,"leg",plan.side.value,orientation_state)
            finish_match(self,shape_state)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def _match_body_leg_hybrid_roll(self, plan: BodyLegFkToIkPlan) -> None:
        roll_path = plan.reverse_roll_control_path
        handle_name = plan.reverse_roll_handle_name
        if roll_path is None or handle_name is None:
            return
        handles = self._cmds.ls(handle_name, long=True, type="ikHandle") or []
        if len(handles) != 1:
            raise FitSkeletonValidationError("IKHybrid 腿部 Handle 不唯一")
        parent = roll_path.rsplit("|", 1)[0]
        target = plan.body_joint_paths[2]
        direction = 1.0 if plan.side is FitBuildSide.RIGHT else -1.0
        temp1 = self._cmds.createNode(
            "transform", parent=handles[0], skipSelect=True)
        try:
            temp2 = self._cmds.createNode(
                "transform", parent=roll_path, skipSelect=True)
            temp2 = self._cmds.parent(temp2, temp1, absolute=True)[0]
            temp1 = self._cmds.parent(temp1, parent, absolute=True)[0]
            self._cmds.aimConstraint(
                target, temp1, maintainOffset=False,
                aimVector=(-direction, 0.0, 0.0),
                upVector=(0.0, direction, 0.0),
                worldUpType="objectrotation", worldUpObject=target)
            temp2 = (self._cmds.ls(temp2.rsplit("|", 1)[-1], long=True)
                     or [temp2])[0]
            self._spine_set_world_rotation(
                roll_path, self._spine_world_frame(temp2)[0])
        finally:
            if self._cmds.objExists(temp1):
                self._cmds.delete(temp1)

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
        ik_axes = tuple(
            self._spine_world_frame(path)[1]
            for path in plan.ik_source_paths
            if self._cmds.objExists(path))
        return BodyLegIkToFkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            tuple(axes),
            segment_translations,
            ik_axes,
        )

    def _match_limb_fk_driver_axes(self, control: str, driver: str,
                                   target_axes) -> None:
        """Preserve the live control-to-FK-driver orientation offset."""
        from maya.api import OpenMaya as om

        control_axes = self._spine_world_frame(control)[1]
        driver_axes = self._spine_world_frame(driver)[1]

        def rotation(axes):
            return om.MMatrix((
                *axes[0], 0.0, *axes[1], 0.0,
                *axes[2], 0.0, 0.0, 0.0, 0.0, 1.0,
            ))

        matched = rotation(control_axes) * rotation(driver_axes).inverse() * rotation(target_axes)
        position = self._spine_world_frame(control)[0][12:15]
        self._spine_set_world_rotation(
            control, (*(matched[index] for index in range(12)),
                      *position, 1.0))

    def _audit_limb_fk_driver_axes(self, driver_paths, target_axes,
                                   limb_label: str) -> None:
        if len(driver_paths) != len(target_axes):
            raise FitSkeletonValidationError(
                limb_label + " IK→FK 驱动关节数量与 IK 目标不一致")
        for driver, expected in zip(driver_paths, target_axes):
            actual = self._spine_world_frame(driver)[1]
            if any(abs(component - target) > 1e-3
                   for axis, goal in zip(actual, expected)
                   for component, target in zip(axis, goal)):
                raise FitSkeletonValidationError(
                    limb_label + " IK→FK 驱动朝向未对齐：" + driver)

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
            for path, driver, target_axes in zip(
                plan.fk_control_paths, plan.fk_driver_paths,
                state.ik_source_axes,
            ):
                self._match_limb_fk_driver_axes(path, driver, target_axes)
            for plug, value in zip(
                plan.fk_segment_plugs,
                plan.fk_segment_translations,
            ):
                self._cmds.setAttr(plug, value)
            self._audit_limb_fk_driver_axes(
                plan.fk_driver_paths, state.ik_source_axes, "Leg")
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
        ik_axes = tuple(
            self._spine_world_frame(path)[1]
            for path in plan.ik_source_paths
            if self._cmds.objExists(path))
        return BodyArmIkToFkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            tuple(axes),
            segment_translations,
            ik_axes,
        )

    def apply_body_arm_ik_to_fk(self, plan: BodyArmIkToFkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_arm_ik_to_fk_state(plan)
        if audit_body_arm_ik_to_fk_preflight(plan, state):
            raise FitSkeletonValidationError("Arm IK→FK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            from .maya_limb_shape import begin_optional_match, finish_match
            shape_state=begin_optional_match(self,"arm",plan.side.value,"fk")
            for path, driver, target_axes in zip(
                    plan.fk_control_paths, plan.fk_driver_paths,
                    state.ik_source_axes):
                self._match_limb_fk_driver_axes(path, driver, target_axes)
            for plug, value in zip(
                plan.fk_segment_plugs,
                plan.fk_segment_translations,
            ):
                self._cmds.setAttr(plug, value)
            self._audit_limb_fk_driver_axes(
                plan.fk_driver_paths, state.ik_source_axes, "Arm")
            self._cmds.setAttr(plan.blend_plug, 0.0)
            finish_match(self,shape_state)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def _create_body_sub_control(
        self, control: str, sub_name: str, sub_path: str,
    ) -> None:
        main_shapes = self._cmds.listRelatives(
            control, shapes=True, noIntermediate=True,
            fullPath=True, type="nurbsCurve") or []
        if len(main_shapes) != 1:
            raise RuntimeError("Sub 来源控制器须恰有一条曲线")
        sub = self._cmds.duplicateCurve(
            main_shapes[0], constructionHistory=False, local=True)[0]
        sub = self._cmds.rename(sub, sub_name)
        sub = self._cmds.parent(sub, control, relative=True)[0]
        sub = (self._cmds.ls(sub, long=True) or [sub])[0]
        if sub != sub_path:
            raise RuntimeError("Body Sub 控制器路径漂移")
        shapes = self._cmds.listRelatives(
            sub, shapes=True, noIntermediate=True, fullPath=True) or []
        if len(shapes) != 1:
            raise RuntimeError("Body Sub 控制器曲线无效")
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        c.scale(0.9, 0.9, 0.9, shapes[0] + ".cv[*]",
                relative=True, pivot=(0, 0, 0))
        self._cmds.setAttr(shapes[0] + ".overrideEnabled", True)
        self._cmds.setAttr(shapes[0] + ".overrideColor", 30)
        self._cmds.addAttr(control, longName="subControl",
                           attributeType="bool", defaultValue=False)
        self._cmds.setAttr(control + ".subControl",
                           edit=True, channelBox=True)
        self._cmds.connectAttr(control + ".subControl",
                               shapes[0] + ".visibility", force=True)

    def _create_body_extra_layer(
        self, offset: str, name: str, path: str,
    ) -> str:
        extra = self._cmds.createNode(
            "transform", name=name, parent=offset, skipSelect=True)
        extra = (self._cmds.ls(extra, long=True) or [extra])[0]
        if extra != path:
            raise RuntimeError("IK Extra 层路径漂移")
        return extra

    def _add_body_extra_curve(
        self, extra: str, control: str,
    ) -> None:
        main_shapes = self._cmds.listRelatives(
            control, shapes=True, noIntermediate=True,
            fullPath=True, type="nurbsCurve") or []
        if len(main_shapes) != 1:
            raise RuntimeError("Extra 来源控制器须恰有一条曲线")
        temp = self._cmds.duplicateCurve(
            main_shapes[0], constructionHistory=False, local=True)[0]
        shapes = self._cmds.listRelatives(
            temp, shapes=True, noIntermediate=True, fullPath=True) or []
        if len(shapes) != 1:
            raise RuntimeError("IK Extra 来源曲线无效")
        shape = self._cmds.parent(
            shapes[0], extra, shape=True, relative=True)[0]
        shape = self._cmds.rename(
            shape, extra.rsplit("|", 1)[-1] + "Shape")
        shape = (self._cmds.ls(shape, long=True) or [shape])[0]
        if self._cmds.objExists(temp):
            self._cmds.delete(temp)
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        c.scale(1.1, 1.1, 1.1, shape + ".cv[*]",
                relative=True, pivot=(0, 0, 0))
        self._cmds.setAttr(shape + ".overrideEnabled", True)
        self._cmds.setAttr(shape + ".overrideColor", 29)
        self._cmds.addAttr(control, longName="extraControl",
                           attributeType="bool", defaultValue=False)
        self._cmds.setAttr(control + ".extraControl",
                           edit=True, channelBox=True)
        self._cmds.connectAttr(control + ".extraControl",
                               shape + ".visibility", force=True)

    def _capture_body_extra_layer(
        self, extra_path: str | None, control: str,
    ) -> BodyExtraControllerState | None:
        if extra_path is None:
            return None
        nodes = self._cmds.ls(
            extra_path, long=True, type="transform") or []
        if len(nodes) != 1:
            return None
        extra = nodes[0]
        parents = self._cmds.listRelatives(
            extra, parent=True, fullPath=True) or []
        shapes = self._cmds.listRelatives(
            extra, shapes=True, noIntermediate=True,
            fullPath=True) or []
        main_shapes = self._cmds.listRelatives(
            control, shapes=True, noIntermediate=True,
            fullPath=True) or []
        shape_type = (self._cmds.nodeType(shapes[0])
                      if len(shapes) == 1 else "multiple" if shapes else None)
        color = (int(self._cmds.getAttr(shapes[0] + ".overrideColor"))
                 if len(shapes) == 1 else None)
        source = None
        scale = None
        if len(shapes) == 1:
            sources = self._cmds.listConnections(
                shapes[0] + ".visibility", source=True,
                destination=False, plugs=True) or []
            if len(sources) == 1:
                node, attr = sources[0].split(".", 1)
                paths = self._cmds.ls(node, long=True) or []
                if len(paths) == 1:
                    source = paths[0] + "." + attr
            if len(main_shapes) == 1:
                main_cv = self._cmds.xform(
                    main_shapes[0] + ".cv[0]", query=True,
                    objectSpace=True, translation=True)
                extra_cv = self._cmds.xform(
                    shapes[0] + ".cv[0]", query=True,
                    objectSpace=True, translation=True)
                main_radius = sum(float(v) ** 2
                                  for v in main_cv) ** 0.5
                if main_radius > 0:
                    scale = (sum(float(v) ** 2 for v in extra_cv) ** 0.5
                             / main_radius)
        return BodyExtraControllerState(
            extra, parents[0] if len(parents) == 1 else None,
            shapes[0] if len(shapes) == 1 else None,
            shape_type, source, color, scale)

    def _capture_body_ik_sub_control(
        self, control: str, sub_path: str | None,
    ) -> BodySubControllerState | None:
        if sub_path is None:
            children = self._cmds.listRelatives(
                control, children=True, type="transform",
                fullPath=True) or []
            candidates = [path for path in children
                          if "IKSub_" in path.rsplit("|", 1)[-1]]
            if not candidates:
                return None
            sub_path = candidates[0]
        nodes = self._cmds.ls(sub_path, long=True, type="transform") or []
        if len(nodes) != 1:
            return None
        sub = nodes[0]
        parents = self._cmds.listRelatives(
            sub, parent=True, fullPath=True) or []
        shapes = self._cmds.listRelatives(
            sub, shapes=True, noIntermediate=True, fullPath=True) or []
        control_shapes = self._cmds.listRelatives(
            control, shapes=True, noIntermediate=True, fullPath=True) or []
        shape_type = (self._cmds.nodeType(shapes[0])
                      if len(shapes) == 1 else None)
        color = (int(self._cmds.getAttr(shapes[0] + ".overrideColor"))
                 if len(shapes) == 1 else None)
        source = None
        scale = None
        if len(shapes) == 1:
            sources = self._cmds.listConnections(
                shapes[0] + ".visibility", source=True,
                destination=False, plugs=True) or []
            if len(sources) == 1:
                node, attr = sources[0].split(".", 1)
                paths = self._cmds.ls(node, long=True) or []
                if len(paths) == 1:
                    source = paths[0] + "." + attr
            if len(control_shapes) == 1:
                main_cv = self._cmds.xform(
                    control_shapes[0] + ".cv[0]", query=True,
                    objectSpace=True, translation=True)
                sub_cv = self._cmds.xform(
                    shapes[0] + ".cv[0]", query=True,
                    objectSpace=True, translation=True)
                main_radius = sum(float(v) ** 2
                                  for v in main_cv) ** 0.5
                if main_radius > 0:
                    scale = (sum(float(v) ** 2 for v in sub_cv) ** 0.5
                             / main_radius)
        return BodySubControllerState(
            sub, parents[0] if len(parents) == 1 else None,
            shape_type, source, color, scale)

    def create_body_arm_ik(self, spec: BodyArmIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if (spec.wrist_extra_name is None or spec.wrist_extra_path is None
                    or spec.pole_extra_name is None
                    or spec.pole_extra_path is None):
                raise FitSkeletonValidationError("Arm IK 缺少 Extra 层计划")
            for name in (
                    spec.wrist_offset_name, spec.wrist_control_name,
                    spec.pole_offset_name, spec.pole_control_name,
                    spec.handle_name, spec.pole_constraint_name,
                    spec.wrist_constraint_name, spec.wrist_extra_name,
                    spec.pole_extra_name,
                    *((spec.wrist_sub_name,) if spec.wrist_sub_name else ()),
                    *((spec.wrist_align_name,) if spec.wrist_align_name else ())):
                if self.find_name_collisions(name):
                    raise FitSkeletonValidationError(f"Arm IK 名称冲突：{name}")
            if any(not self._cmds.objExists(path) for path in spec.chain):
                raise FitSkeletonValidationError("Arm IK mechanism chain 在执行前失效")
            if (spec.wrist_align_parent_path is not None and
                    not self._cmds.objExists(spec.wrist_align_parent_path)):
                raise FitSkeletonValidationError(
                    "Wrist AlignIKTo 的 FK 父关节缺失")
            self._transaction_changed = True
            wrist_offset = self._cmds.createNode("transform", name=spec.wrist_offset_name, parent=spec.root_path, skipSelect=True)
            wrist_offset = (self._cmds.ls(wrist_offset, long=True) or [wrist_offset])[0]
            x_axis, y_axis, z_axis = spec.wrist_axes
            matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *spec.wrist_position, 1.0)
            self._cmds.xform(wrist_offset, worldSpace=True, matrix=matrix)
            if spec.wrist_extra_name is None or spec.wrist_extra_path is None:
                raise FitSkeletonValidationError("Arm IK 缺少 Extra 层计划")
            wrist_extra = self._create_body_extra_layer(
                wrist_offset, spec.wrist_extra_name, spec.wrist_extra_path)
            wrist = create_adv_icon(
                self._cmds, name=spec.wrist_control_name,
                parent=wrist_extra, template="IK_icon", radius=spec.radius,
                fallback_normal=(1.0, 0.0, 0.0), fallback_sections=12,
                mirror_left=spec.side is FitBuildSide.LEFT)
            wrist = (self._cmds.ls(wrist, long=True) or [wrist])[0]
            pole_offset = self._cmds.createNode("transform", name=spec.pole_offset_name, parent=spec.root_path, skipSelect=True)
            pole_offset = (self._cmds.ls(pole_offset, long=True) or [pole_offset])[0]
            self._cmds.xform(pole_offset, worldSpace=True, translation=spec.pole_position)
            if spec.pole_extra_name is None or spec.pole_extra_path is None:
                raise FitSkeletonValidationError("Arm Pole 缺少 Extra 层计划")
            pole_extra = self._create_body_extra_layer(
                pole_offset, spec.pole_extra_name, spec.pole_extra_path)
            pole = create_adv_icon(
                self._cmds, name=spec.pole_control_name,
                parent=pole_extra, template="Pole_icon",
                radius=spec.radius,
                fallback_normal=(0.0, 0.0, 1.0),
                mirror_left=spec.side is FitBuildSide.LEFT)
            pole = (self._cmds.ls(pole, long=True) or [pole])[0]
            if wrist != spec.wrist_control_path or pole != spec.pole_control_path:
                raise RuntimeError("Arm IK 控制路径漂移")
            if spec.wrist_extra_curve:
                self._add_body_extra_curve(
                    wrist_extra, wrist)
            if spec.wrist_sub_path is not None:
                if spec.wrist_sub_name is None:
                    raise FitSkeletonValidationError("Arm IK Sub 缺少名称")
                self._create_body_sub_control(
                    wrist, spec.wrist_sub_name, spec.wrist_sub_path)
            if spec.wrist_align_name is not None:
                aligned = self._cmds.createNode(
                    "transform", name=spec.wrist_align_name,
                    parent=spec.wrist_align_parent_path, skipSelect=True)
                aligned = (self._cmds.ls(aligned, long=True) or [aligned])[0]
                if aligned != spec.wrist_align_path:
                    raise RuntimeError("Wrist AlignIKTo 路径漂移")
                self._cmds.xform(aligned, worldSpace=True, matrix=matrix)
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

    def body_arm_align_helper_mode(self, plan: BodyArmIkPlan) -> bool:
        found = tuple(bool(spec.wrist_align_path and
                           len(self._cmds.ls(
                               spec.wrist_align_path, long=True,
                               type="transform") or []) == 1)
                      for spec in plan.limbs)
        if len(found) != 2 or found[0] != found[1]:
            raise FitSkeletonValidationError(
                "双侧 Wrist AlignIKTo 辅助层版本不一致")
        return found[0]

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
            align_nodes = (self._cmds.ls(
                spec.wrist_align_path, long=True, type="transform") or []
                if spec.wrist_align_path else [])
            aligned = align_nodes[0] if len(align_nodes) == 1 else None
            align_parents = (self._cmds.listRelatives(
                aligned, parent=True, fullPath=True) or []
                if aligned else [])
            align_matrix, align_axes = (self._spine_world_frame(aligned)
                                        if aligned else (None, None))
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
                self._capture_body_ik_sub_control(
                    wrist, spec.wrist_sub_path),
                self._capture_body_extra_layer(
                    spec.wrist_extra_path, wrist),
                self._capture_body_extra_layer(
                    spec.pole_extra_path, pole),
                wrist_align_path=aligned,
                wrist_align_parent_path=(align_parents[0]
                                         if align_parents else None),
                wrist_align_position=(align_matrix[12:15]
                                      if align_matrix else None),
                wrist_align_axes=align_axes,
            ))
        return BodyArmIkSnapshot(roots[0], tuple(states))

    def create_body_leg_ik(self, spec: BodyLegIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if (spec.ankle_extra_name is None or spec.ankle_extra_path is None
                    or spec.pole_extra_name is None
                    or spec.pole_extra_path is None):
                raise FitSkeletonValidationError("Leg IK 缺少 Extra 层计划")
            names = (
                spec.ankle_offset_name,
                spec.ankle_control_name,
                spec.pole_offset_name,
                spec.pole_control_name,
                spec.handle_name,
                spec.pole_constraint_name,
                spec.ankle_constraint_name,
                spec.ankle_extra_name,
                spec.pole_extra_name,
                *((spec.ankle_sub_name,) if spec.ankle_sub_name else ()),
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
            if spec.ankle_extra_name is None or spec.ankle_extra_path is None:
                raise FitSkeletonValidationError("Leg IK 缺少 Extra 层计划")
            ankle_extra = self._create_body_extra_layer(
                ankle_offset, spec.ankle_extra_name,
                spec.ankle_extra_path)
            ankle = create_adv_icon(
                self._cmds, name=spec.ankle_control_name,
                parent=ankle_extra, template="IK_icon", radius=spec.radius,
                fallback_normal=(1.0, 0.0, 0.0), fallback_sections=12,
                mirror_left=spec.side is FitBuildSide.LEFT)
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
            if spec.pole_extra_name is None or spec.pole_extra_path is None:
                raise FitSkeletonValidationError("Leg Pole 缺少 Extra 层计划")
            pole_extra = self._create_body_extra_layer(
                pole_offset, spec.pole_extra_name,
                spec.pole_extra_path)
            pole = create_adv_icon(
                self._cmds, name=spec.pole_control_name,
                parent=pole_extra, template="Pole_icon",
                radius=spec.radius,
                fallback_normal=(0.0, 0.0, 1.0),
                mirror_left=spec.side is FitBuildSide.LEFT)
            pole = (self._cmds.ls(pole, long=True) or [pole])[0]
            if (
                ankle != spec.ankle_control_path
                or pole != spec.pole_control_path
            ):
                raise RuntimeError("Leg IK 控制路径漂移")
            if spec.ankle_extra_curve:
                self._add_body_extra_curve(
                    ankle_extra, ankle)
            if spec.ankle_sub_path is not None:
                if spec.ankle_sub_name is None:
                    raise FitSkeletonValidationError("Leg IK Sub 缺少名称")
                self._create_body_sub_control(
                    ankle, spec.ankle_sub_name, spec.ankle_sub_path)
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
                ankle_sub=self._capture_body_ik_sub_control(
                    ankle, spec.ankle_sub_path),
                ankle_extra=self._capture_body_extra_layer(
                    spec.ankle_extra_path, ankle),
                pole_extra=self._capture_body_extra_layer(
                    spec.pole_extra_path, pole),
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
                side.control_parent_path,
                side.ankle_driver_path,
                side.toe_driver_path,
                side.toe_end_driver_path,
                side.ankle_constraint_name,
            ))
            if side.qtoes_driver_path:
                required.append(side.qtoes_driver_path)
            required.extend(driver for step in side.intermediate_handles
                            for driver in (step.start_driver_path,
                                           step.end_driver_path))
            required.extend(joint for chain in (
                side.toe_solver_joint_list or (),
                side.toe_end_solver_joint_list or (),
                side.qtoes_solver_joint_list or (),
                *(step.solver_joint_list
                  for step in side.intermediate_handles),
            ) for joint in chain)
            if len(handles) == 1:
                required.append(handles[0])
                if side.pivots[0].roll_control_name:
                    twist = handles[0] + ".twist"
                    if self._cmds.listConnections(
                            twist, source=True, destination=False,
                            plugs=True) or []:
                        occupied_rotations.append(twist)
            else:
                required.append(side.handle_name)
            names = [pivot.name for pivot in side.pivots
                     if not pivot.roll_control_name]
            names.extend(
                name for pivot in side.pivots
                for name in (pivot.roll_offset_name, pivot.roll_extra_name,
                             pivot.roll_control_name,
                             pivot.roll_roller_name) if name)
            if side.rock:
                names.extend((side.rock.inner_name, side.rock.outer_name))
            names.extend(
                pivot.multiplier_name
                for pivot in side.pivots
                if pivot.multiplier_name
            )
            if side.hybrid is not None:
                names.extend(side.hybrid.node_names)
                required.extend(joint for chain in (
                    side.hybrid.initial_solver_joint_list or (),
                    *(segment.solver_joint_list or ()
                      for segment in side.hybrid.segments),
                ) for joint in chain)
                required.append(
                    side.hybrid.segments[0].sampler1_offset_path
                    .rsplit("|", 1)[0])
                required.extend((side.hybrid.initial_start_driver_path,
                                 side.hybrid.initial_end_driver_path))
                required.extend(
                    driver for segment in side.hybrid.segments
                    for driver in (segment.start_driver_path,
                                   segment.end_driver_path))
            else:
                names.extend((side.toe_offset_name, side.toe_control_name))
                if side.toe_extra_name:
                    names.append(side.toe_extra_name)
                    if side.toe_extra_curve:
                        names.append(side.toe_extra_name + "Shape")
                if side.toe_sub_name:
                    names.extend((side.toe_sub_name,
                                  side.toe_sub_name + "Shape"))
                names.extend((side.toe_handle_name, side.toe_effector_name))
                names.extend((side.toe_end_handle_name,
                              side.toe_end_effector_name))
                names.extend(name for step in side.intermediate_handles
                             for name in (step.handle_name,
                                          step.effector_name))
            if side.qtoes_handle_name:
                names.extend((side.qtoes_handle_name,
                              side.qtoes_effector_name))
            names.extend(node.name for node in side.roll.nodes)
            names.extend(helper.name for helper in side.align_helpers)
            required.extend(helper.parent_path for helper in side.align_helpers)
            for manual in side.manual_pivots:
                names.extend((manual.offset_name, manual.control_name,
                              manual.reverse_name, manual.matrix_name,
                              manual.inverse_name))
            if side.high_heel:
                high = side.high_heel
                names.extend((high.offset1_name, high.offset2_name,
                              high.drive1_name, high.drive2_name,
                              high.drive3_name, high.negate_name,
                              high.constraint_name,
                              high.point_constraint_name))
            collisions.extend(
                name for name in names if self.find_name_collisions(name)
            )
            for path in (
                side.ankle_control_path,
                side.control_parent_path,
                side.ankle_driver_path,
                side.toe_driver_path,
                side.toe_end_driver_path,
                *(driver for step in side.intermediate_handles
                  for driver in (step.start_driver_path,
                                 step.end_driver_path)),
                *((side.qtoes_driver_path,)
                  if side.qtoes_driver_path else ()),
                *((driver for segment in side.hybrid.segments
                   for driver in (segment.start_driver_path,
                                  segment.end_driver_path))
                  if side.hybrid is not None else ()),
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
            rotation_drivers = (
                tuple(dict.fromkeys((
                    side.hybrid.initial_end_driver_path,
                    *(segment.end_driver_path
                      for segment in side.hybrid.segments))))
                if side.hybrid is not None else (
                    *(step.end_driver_path
                      for step in side.intermediate_handles),
                    side.toe_driver_path))
            for driver in rotation_drivers:
                for axis in "XYZ":
                    plug = f"{driver}.rotate{axis}"
                    sources = self._cmds.listConnections(
                        plug, source=True, destination=False,
                        plugs=True) or []
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
            for helper in spec.align_helpers:
                node = self._cmds.createNode(
                    "transform", name=helper.name,
                    parent=helper.parent_path, skipSelect=True)
                node = (self._cmds.ls(node, long=True) or [node])[0]
                if node != helper.path:
                    raise RuntimeError("AlignIKTo 路径漂移：" + helper.name)
                x_axis, y_axis, z_axis = helper.world_axes
                self._cmds.xform(
                    node, worldSpace=True,
                    matrix=(*x_axis, 0.0, *y_axis, 0.0,
                            *z_axis, 0.0, *helper.world_position, 1.0))
            for attribute in spec.attributes:
                if attribute == "footPivotsVis":
                    self._cmds.addAttr(
                        spec.ankle_control_path, longName=attribute,
                        attributeType="bool", defaultValue=True,
                        keyable=False)
                    self._cmds.setAttr(
                        spec.ankle_control_path + ".footPivotsVis",
                        channelBox=True)
                    continue
                options = {}
                if (attribute == spec.roll.master_attribute
                        and attribute == "footRoll"):
                    options = {
                        "minValue": spec.roll.minimum,
                        "maxValue": spec.roll.maximum,
                    }
                self._cmds.addAttr(
                    spec.ankle_control_path,
                    longName=attribute,
                    attributeType="double",
                    defaultValue=spec.attribute_default(attribute),
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
            manual_by_target = {item.target_name: item
                                for item in spec.manual_pivots}

            def create_manual_control(manual):
                offset = self._cmds.createNode(
                    "transform", name=manual.offset_name,
                    parent=manual.offset_parent_path, skipSelect=True)
                offset = (self._cmds.ls(offset, long=True) or [offset])[0]
                if offset != manual.offset_path:
                    raise RuntimeError("Foot Pivot Offset 路径漂移")
                self._cmds.xform(offset, worldSpace=True,
                                translation=manual.world_position)
                if manual.world_axes is None:
                    self._cmds.xform(offset, worldSpace=True,
                                    rotation=manual.world_rotation)
                else:
                    x_axis, y_axis, z_axis = manual.world_axes
                    self._cmds.xform(
                        offset, worldSpace=True,
                        matrix=(*x_axis, 0.0, *y_axis, 0.0,
                                *z_axis, 0.0, *manual.world_position, 1.0))
                control = self._cmds.curve(
                    name=manual.control_name, degree=1,
                    point=((0, 0, 0), (1, -4, 0), (-1, -4, 0), (0, 0, 0)),
                    knot=(0, 1, 2, 3))
                self._cmds.parent(control, offset, relative=True)
                control = (self._cmds.ls(control, long=True) or [control])[0]
                if control != manual.control_path:
                    raise RuntimeError("Foot Pivot 控制路径漂移")
                self._cmds.scale(manual.radius, manual.radius,
                                 manual.radius, control + ".cv[*]",
                                 relative=True)
                shapes = self._cmds.listRelatives(
                    control, shapes=True, noIntermediate=True,
                    fullPath=True, type="nurbsCurve") or []
                if len(shapes) != 1:
                    raise RuntimeError("Foot Pivot 曲线不唯一")
                self._cmds.setAttr(shapes[0] + ".overrideEnabled", True)
                self._cmds.setAttr(shapes[0] + ".overrideColor", 24)
                self._cmds.connectAttr(
                    spec.ankle_control_path + ".footPivotsVis",
                    shapes[0] + ".visibility")
                return control

            def finish_manual_control(manual):
                reverse = self._cmds.createNode(
                    "transform", name=manual.reverse_name,
                    parent=manual.target_path, skipSelect=True)
                reverse = (self._cmds.ls(reverse, long=True) or [reverse])[0]
                if reverse != manual.reverse_path:
                    raise RuntimeError("Foot Pivot Reverse 路径漂移")
                matrix = self._cmds.createNode(
                    "multMatrix", name=manual.matrix_name)
                inverse = self._cmds.createNode(
                    "inverseMatrix", name=manual.inverse_name)
                self._cmds.connectAttr(
                    manual.control_path + ".worldMatrix[0]",
                    matrix + ".matrixIn[0]")
                self._cmds.connectAttr(
                    manual.offset_path + ".worldInverseMatrix[0]",
                    matrix + ".matrixIn[1]")
                self._cmds.connectAttr(
                    matrix + ".matrixSum", inverse + ".inputMatrix")
                self._cmds.connectAttr(
                    inverse + ".outputMatrix",
                    reverse + ".offsetParentMatrix")

            if spec.rock:
                for name, path, parent, position, source in (
                    (spec.rock.inner_name, spec.rock.inner_path,
                     spec.control_parent_path, spec.rock.inner_position,
                     spec.rock.inner_source),
                    (spec.rock.outer_name, spec.rock.outer_path,
                     spec.rock.inner_path, spec.rock.outer_position,
                     spec.rock.outer_source),
                ):
                    manual = manual_by_target.get(name)
                    if manual is not None:
                        create_manual_control(manual)
                        parent = manual.control_path
                    created = self._cmds.createNode(
                        "transform", name=name, parent=parent,
                        skipSelect=True)
                    created = (self._cmds.ls(created, long=True)
                               or [created])[0]
                    if created != path:
                        raise RuntimeError("Foot Rock 路径漂移")
                    self._cmds.setAttr(created + ".rotateOrder", 5)
                    self._cmds.xform(
                        created, worldSpace=True, translation=position)
                    self._cmds.xform(
                        created, worldSpace=True,
                        rotation=spec.rock.world_rotation)
                    self._cmds.connectAttr(
                        source, created + ".rotate"
                        + spec.rock.rotation_axis)
                    if manual is not None:
                        finish_manual_control(manual)
            for pivot in spec.pivots:
                if pivot.roll_control_name:
                    roll_parent = pivot.roll_offset_path.rsplit("|", 1)[0]
                    offset = self._cmds.createNode(
                        "transform", name=pivot.roll_offset_name,
                        parent=roll_parent, skipSelect=True)
                    offset = (self._cmds.ls(offset, long=True) or [offset])[0]
                    if offset != pivot.roll_offset_path:
                        raise RuntimeError("Foot Roll Offset 路径漂移")
                    self._cmds.xform(
                        offset, worldSpace=True,
                        translation=pivot.world_position)
                    if pivot.roll_world_axes is None:
                        self._cmds.xform(
                            offset, worldSpace=True,
                            rotation=pivot.roll_world_rotation)
                    else:
                        x_axis, y_axis, z_axis = pivot.roll_world_axes
                        self._cmds.xform(
                            offset, worldSpace=True,
                            matrix=(*x_axis, 0.0, *y_axis, 0.0,
                                    *z_axis, 0.0, *pivot.world_position, 1.0))
                    if (spec.high_heel is not None
                            and pivot.role is BodyLegFootPivotRole.HEEL):
                        high = spec.high_heel
                        offset1 = self._cmds.createNode(
                            "transform", name=high.offset1_name,
                            parent=offset, skipSelect=True)
                        offset1 = (self._cmds.ls(offset1, long=True)
                                   or [offset1])[0]
                        if offset1 != high.offset1_path:
                            raise RuntimeError("HighHeel Offset1 路径漂移")
                        self._cmds.xform(offset1, worldSpace=True,
                                        translation=high.ankle_position)
                        offset2 = self._cmds.createNode(
                            "transform", name=high.offset2_name,
                            parent=offset1, skipSelect=True)
                        offset2 = (self._cmds.ls(offset2, long=True)
                                   or [offset2])[0]
                        if offset2 != high.offset2_path:
                            raise RuntimeError("HighHeel Offset2 路径漂移")
                        self._cmds.xform(offset2, worldSpace=True,
                                        translation=high.toe_position)
                    manual = manual_by_target.get(pivot.name)
                    if manual is not None:
                        create_manual_control(manual)
                    extra_parent = (manual.control_path if manual is not None
                                    else offset)
                    if pivot.roll_roller_name:
                        extra_parent = self._cmds.createNode(
                            "transform", name=pivot.roll_roller_name,
                            parent=extra_parent, skipSelect=True)
                        extra_parent = (self._cmds.ls(extra_parent, long=True)
                                        or [extra_parent])[0]
                        if extra_parent != pivot.roll_roller_path:
                            raise RuntimeError("Foot Roll Roller 路径漂移")
                        self._cmds.connectAttr(
                            pivot.roll_roller_source,
                            extra_parent + ".rotateX")
                    extra = self._cmds.createNode(
                        "transform", name=pivot.roll_extra_name,
                        parent=extra_parent, skipSelect=True)
                    extra = (self._cmds.ls(extra, long=True) or [extra])[0]
                    if extra != pivot.roll_extra_path:
                        raise RuntimeError("Foot Roll Extra 路径漂移")
                    control = create_adv_icon(
                        self._cmds, name=pivot.roll_control_name,
                        parent=extra, template="Roll_icon",
                        radius=pivot.roll_radius,
                        fallback_normal=(0.0, 1.0, 0.0),
                        mirror_left=spec.side is FitBuildSide.LEFT)
                    control = (self._cmds.ls(control, long=True)
                               or [control])[0]
                    if control != pivot.roll_control_path:
                        raise RuntimeError("Foot Roll 控制路径漂移")
                    if manual is not None:
                        finish_manual_control(manual)
                if not pivot.roll_control_name:
                    created = self._cmds.createNode(
                        "transform",
                        name=pivot.name,
                        parent=pivot.parent_path,
                        skipSelect=True,
                    )
                    created = (self._cmds.ls(created, long=True)
                               or [created])[0]
                    if created != pivot.path:
                        raise RuntimeError("Foot pivot 路径漂移")
                    self._cmds.xform(
                        created, worldSpace=True,
                        translation=pivot.world_position)
                if pivot.multiplier_name:
                    attribute_plug = f"{spec.ankle_control_path}.{pivot.attribute}"
                    multiplier = self._cmds.createNode(
                        "multDoubleLinear",
                        name=pivot.multiplier_name,
                        skipSelect=True,
                    )
                    self._cmds.connectAttr(attribute_plug, f"{multiplier}.input1")
                    self._cmds.setAttr(f"{multiplier}.input2", pivot.multiplier)
                    self._cmds.connectAttr(f"{multiplier}.output", pivot.target_plug)
                elif pivot.source_plug:
                    self._cmds.connectAttr(pivot.source_plug, pivot.target_plug)
            if spec.hybrid is not None:
                self._create_body_leg_foot_hybrid_side(spec)
                return
            toe_offset = self._cmds.createNode(
                "transform",
                name=spec.toe_offset_name,
                parent=spec.toe_offset_path.rsplit("|", 1)[0],
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
            toe_parent = toe_offset
            if spec.source_toe_icon:
                toe_parent = self._cmds.createNode(
                    "transform", name=spec.toe_extra_name,
                    parent=toe_offset, skipSelect=True)
                toe_parent = (self._cmds.ls(toe_parent, long=True)
                              or [toe_parent])[0]
                if toe_parent != spec.toe_extra_path:
                    raise RuntimeError("Toe IK Extra 路径漂移")
            toe_control = create_adv_icon(
                self._cmds, name=spec.toe_control_name,
                parent=toe_parent,
                template="FK_icon" if spec.source_toe_icon else "IK_icon",
                radius=spec.toe_control_radius,
                fallback_normal=(0.0, 1.0, 0.0),
                axis_offset=(original_fit_icon_axis_offset(
                    self._cmds, ("Toes",)) if spec.source_toe_icon
                    else (0.0, 0.0, 0.0)),
                mirror_left=spec.side is FitBuildSide.LEFT)
            toe_control = (
                self._cmds.ls(toe_control, long=True) or [toe_control]
            )[0]
            if (
                toe_offset != spec.toe_offset_path
                or toe_control != spec.toe_control_path
            ):
                raise RuntimeError("Toe IK 控制路径漂移")
            if spec.source_toe_icon:
                self._cmds.setAttr(
                    toe_control + ".rotateOrder",
                    spec.toe_control_rotate_order)
                for node in (toe_parent, toe_control):
                    self._cmds.addAttr(
                        node, longName="ikLocal", attributeType="bool",
                        defaultValue=True)
                shapes = self._cmds.listRelatives(
                    toe_control, shapes=True, noIntermediate=True,
                    fullPath=True, type="nurbsCurve") or []
                if len(shapes) != 1:
                    raise RuntimeError("Toe IK 图标曲线不唯一")
                self._cmds.setAttr(shapes[0] + ".overrideEnabled", True)
                self._cmds.setAttr(shapes[0] + ".overrideColor", 13)
                if spec.toe_extra_curve:
                    self._add_body_extra_curve(toe_parent, toe_control)
                if spec.toe_sub_path:
                    self._create_body_sub_control(
                        toe_control, spec.toe_sub_name,
                        spec.toe_sub_path)
            handles = self._cmds.ls(spec.handle_name, long=True, type="ikHandle") or []
            if len(handles) != 1:
                raise FitSkeletonValidationError("Leg IK Handle 在执行前失效")
            self._cmds.parent(handles[0], spec.final_handle_parent_path, absolute=True)
            final_handles = self._cmds.ls(
                spec.handle_name, long=True, type="ikHandle") or []
            if (len(final_handles) != 1
                    or final_handles[0].rsplit("|", 1)[0]
                    != spec.final_handle_parent_path):
                raise RuntimeError("Foot IK Handle 改挂路径漂移")
            final_handle_path = final_handles[0]
            self._create_body_leg_foot_high_heel(
                spec, final_handle_path)
            if spec.pivots[0].roll_control_name:
                self._cmds.connectAttr(
                    spec.ankle_control_path + ".swivel",
                    spec.handle_name + ".twist")
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
            if spec.qtoes_driver_path:
                qtoes_handle, qtoes_effector = self._cmds.ikHandle(
                    name=spec.qtoes_handle_name,
                    startJoint=spec.ankle_driver_path,
                    endEffector=spec.qtoes_driver_path,
                    solver="ikSCsolver",
                    sticky="sticky",
                )
                self._cmds.rename(qtoes_effector,
                                  spec.qtoes_effector_name)
                self._cmds.parent(qtoes_handle,
                                  spec.qtoes_handle_parent_path,
                                  absolute=True)
                self._cmds.setAttr(
                    spec.qtoes_handle_name + ".visibility", False)
                self._cmds.setAttr(
                    spec.qtoes_effector_name + ".visibility", False)
            for step in spec.intermediate_handles:
                segment_handle, segment_effector = self._cmds.ikHandle(
                    name=step.handle_name,
                    startJoint=step.start_driver_path,
                    endEffector=step.end_driver_path,
                    solver="ikSCsolver",
                    sticky="sticky",
                )
                self._cmds.rename(segment_effector, step.effector_name)
                self._cmds.parent(segment_handle, step.parent_path,
                                  absolute=True)
                self._cmds.setAttr(step.handle_name + ".visibility", False)
                self._cmds.setAttr(step.effector_name + ".visibility", False)
            toe_handle, toe_effector = self._cmds.ikHandle(
                name=spec.toe_handle_name,
                startJoint=spec.toe_handle_start_path,
                endEffector=spec.toe_driver_path,
                solver="ikSCsolver",
                sticky="sticky",
            )
            self._cmds.rename(toe_effector, spec.toe_effector_name)
            self._cmds.parent(toe_handle, spec.toe_handle_parent_path,
                              absolute=True)
            self._cmds.setAttr(spec.toe_handle_name + ".visibility", False)
            self._cmds.setAttr(spec.toe_effector_name + ".visibility", False)
            toe_end_handle, toe_end_effector = self._cmds.ikHandle(
                name=spec.toe_end_handle_name,
                startJoint=spec.toe_driver_path,
                endEffector=spec.toe_end_driver_path,
                solver="ikSCsolver",
                sticky="sticky",
            )
            self._cmds.rename(toe_end_effector, spec.toe_end_effector_name)
            self._cmds.parent(toe_end_handle,
                              spec.toe_end_handle_control_path,
                              absolute=True)
            self._cmds.setAttr(spec.toe_end_handle_name + ".visibility", False)
            self._cmds.setAttr(spec.toe_end_effector_name + ".visibility", False)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def _create_body_leg_foot_high_heel(
        self, spec: BodyLegFootSideSpec, final_handle_path: str,
    ) -> None:
        if spec.high_heel is not None:
            high = spec.high_heel
            control_plug = (spec.ankle_control_path
                            + ".footPivotsHighHeel")
            negate = self._cmds.createNode(
                "multiplyDivide", name=high.negate_name)
            self._cmds.setAttr(negate + ".input2X", -1.0)
            self._cmds.connectAttr(control_plug, negate + ".input1X")
            self._cmds.connectAttr(control_plug,
                                   high.offset1_path + ".rotateX")
            self._cmds.connectAttr(negate + ".outputX",
                                   high.offset2_path + ".rotateX")
            drive_parent = high.drive1_path.rsplit("|", 1)[0]
            drive1 = self._cmds.createNode(
                "transform", name=high.drive1_name,
                parent=drive_parent, skipSelect=True)
            drive1 = (self._cmds.ls(drive1, long=True) or [drive1])[0]
            if drive1 != high.drive1_path:
                raise RuntimeError("HighHeel Drive1 路径漂移")
            self._cmds.xform(drive1, worldSpace=True,
                            translation=high.ankle_position)
            drive2 = self._cmds.createNode(
                "transform", name=high.drive2_name,
                parent=drive1, skipSelect=True)
            drive2 = (self._cmds.ls(drive2, long=True) or [drive2])[0]
            if drive2 != high.drive2_path:
                raise RuntimeError("HighHeel Drive2 路径漂移")
            self._cmds.xform(drive2, worldSpace=True,
                            translation=high.toe_position)
            drive3 = self._cmds.createNode(
                "transform", name=high.drive3_name,
                parent=drive2, skipSelect=True)
            drive3 = (self._cmds.ls(drive3, long=True) or [drive3])[0]
            if drive3 != high.drive3_path:
                raise RuntimeError("HighHeel Drive3 路径漂移")
            self._cmds.xform(drive3, worldSpace=True,
                            translation=high.ankle_position)
            self._cmds.connectAttr(control_plug, drive1 + ".rotateX")
            orient = self._cmds.orientConstraint(
                drive_parent, drive2, name=high.constraint_name)[0]
            heel_pivot = next(p for p in spec.pivots
                              if p.role is BodyLegFootPivotRole.HEEL)
            heading = heel_pivot.roll_world_rotation[1]
            self._cmds.setAttr(
                orient + ".offsetY", heading)
            self._cmds.pointConstraint(
                drive1, drive3, name=high.point_constraint_name)
            self._cmds.connectAttr(
                drive3 + ".translate",
                final_handle_path + ".translate",
                force=True)

    def _create_body_leg_foot_hybrid_side(
        self, spec: BodyLegFootSideSpec,
    ) -> None:
        hybrid = spec.hybrid
        if hybrid is None:
            raise RuntimeError("Foot IKHybrid 计划缺失")
        handles = self._cmds.ls(
            spec.handle_name, long=True, type="ikHandle") or []
        if len(handles) != 1:
            raise FitSkeletonValidationError("Leg IK Handle 在执行前失效")
        self._cmds.parent(handles[0], spec.final_handle_parent_path,
                          absolute=True)
        final_handles = self._cmds.ls(
            spec.handle_name, long=True, type="ikHandle") or []
        if (len(final_handles) != 1 or
                final_handles[0].rsplit("|", 1)[0] !=
                spec.final_handle_parent_path):
            raise RuntimeError("Foot IKHybrid Handle 改挂路径漂移")
        self._create_body_leg_foot_high_heel(
            spec, final_handles[0])
        self._cmds.connectAttr(
            spec.ankle_control_path + ".swivel",
            spec.handle_name + ".twist")
        constraints = self._cmds.ls(
            spec.ankle_constraint_name, type="orientConstraint") or []
        if len(constraints) != 1:
            raise FitSkeletonValidationError("Ankle IK 朝向约束在执行前失效")
        self._cmds.delete(constraints[0])
        self._cmds.orientConstraint(
            spec.ankle_orientation_source_path,
            spec.ankle_driver_path,
            maintainOffset=False, name=spec.ankle_constraint_name)

        def create_at(name, path, parent, position, axes):
            node = self._cmds.createNode(
                "transform", name=name, parent=parent,
                skipSelect=True)
            node = (self._cmds.ls(node, long=True) or [node])[0]
            if node != path:
                raise RuntimeError("Foot IKHybrid 节点路径漂移：" + name)
            x_axis, y_axis, z_axis = axes
            self._cmds.xform(
                node, worldSpace=True,
                matrix=(*x_axis, 0.0, *y_axis, 0.0,
                        *z_axis, 0.0, *position, 1.0))
            return node

        def create_child(name, path, parent):
            node = self._cmds.createNode(
                "transform", name=name, parent=parent,
                skipSelect=True)
            node = (self._cmds.ls(node, long=True) or [node])[0]
            if node != path:
                raise RuntimeError("Foot IKHybrid 节点路径漂移：" + name)
            return node

        for segment in hybrid.segments:
            offset = create_at(
                segment.control_offset_name,
                segment.control_offset_path,
                segment.control_offset_path.rsplit("|", 1)[0],
                segment.source_position, segment.source_axes)
            control = create_adv_icon(
                self._cmds, name=segment.control_name,
                parent=offset, template="IKhybrid_icon",
                radius=segment.radius,
                fallback_normal=(0.0, 1.0, 0.0),
                mirror_left=spec.side is FitBuildSide.LEFT)
            control = (self._cmds.ls(control, long=True) or [control])[0]
            if control != segment.control_path:
                raise RuntimeError("Foot IKHybrid 控制路径漂移")
            sampler1_offset = create_at(
                segment.sampler1_offset_name,
                segment.sampler1_offset_path,
                segment.sampler1_offset_path.rsplit("|", 1)[0],
                segment.end_position, segment.end_axes)
            sampler1 = create_child(
                segment.sampler1_name, segment.sampler1_path,
                sampler1_offset)
            sampler2_offset = create_at(
                segment.sampler2_offset_name,
                segment.sampler2_offset_path,
                segment.sampler2_offset_path.rsplit("|", 1)[0],
                segment.source_position, segment.source_axes)
            sampler2 = create_child(
                segment.sampler2_name, segment.sampler2_path,
                sampler2_offset)
            self._cmds.connectAttr(control + ".rotate",
                                   sampler2 + ".rotate")
            self._cmds.parentConstraint(
                sampler2, sampler1, maintainOffset=True,
                name=segment.sampler2_parent_constraint)
            wrapper_offset = create_at(
                segment.wrapper_offset_name,
                segment.wrapper_offset_path,
                segment.wrapper_offset_path.rsplit("|", 1)[0],
                segment.end_position, segment.end_axes)
            wrapper = create_child(
                segment.wrapper_name, segment.wrapper_path,
                wrapper_offset)
            self._cmds.connectAttr(sampler1 + ".translate",
                                   wrapper + ".translate")
            self._cmds.connectAttr(sampler1 + ".rotate",
                                   wrapper + ".rotate")

        def create_handle(name, effector_name, start, end, parent):
            handle, effector = self._cmds.ikHandle(
                name=name, startJoint=start, endEffector=end,
                solver="ikSCsolver", sticky="sticky")
            self._cmds.rename(effector, effector_name)
            self._cmds.parent(handle, parent, absolute=True)
            self._cmds.setAttr(name + ".visibility", False)
            self._cmds.setAttr(effector_name + ".visibility", False)

        create_handle(
            hybrid.initial_handle_name,
            hybrid.initial_effector_name,
            hybrid.initial_start_driver_path,
            hybrid.initial_end_driver_path,
            hybrid.initial_handle_parent_path)
        for segment in hybrid.segments:
            create_handle(
                segment.handle_name, segment.effector_name,
                segment.start_driver_path, segment.end_driver_path,
                segment.handle_parent_path)

    def body_leg_toe_extra_mode(self, ik: BodyLegIkPlan) -> bool:
        found = []
        for limb in ik.limbs:
            suffix = limb.side.value
            matches = self._cmds.ls(
                f"AdvPy_ToeIKExtra_{suffix}", long=True,
                type="transform") or []
            descendants = [path for path in matches if path.startswith(
                limb.ankle_control_path + "|")]
            found.append(len(descendants) == 1)
        if len(found) != 2 or found[0] != found[1]:
            raise FitSkeletonValidationError("双侧 Toe IK 控制层版本不一致")
        return found[0]

    def body_leg_roll_control_mode(self, ik: BodyLegIkPlan) -> bool:
        found = []
        for limb in ik.limbs:
            suffix = limb.side.value
            suffix_path = (f"|AdvPy_RollOffsetToesEnd_{suffix}"
                           f"|AdvPy_RollRollerToesEnd_{suffix}"
                           f"|AdvPy_RollExtraToesEnd_{suffix}"
                           f"|AdvPy_RollToesEnd_{suffix}")
            matches = self._cmds.ls(
                f"AdvPy_RollToesEnd_{suffix}", long=True,
                type="transform") or []
            found.append(sum(path.startswith(
                limb.ankle_control_path + "|")
                and path.endswith(suffix_path) for path in matches) == 1)
        if len(found) != 2 or found[0] != found[1]:
            raise FitSkeletonValidationError("双侧 Roll 控制层版本不一致")
        return found[0]

    def body_leg_manual_pivot_sides(
        self, ik: BodyLegIkPlan
    ) -> frozenset[FitBuildSide]:
        result = set()
        for limb in ik.limbs:
            control = limb.ankle_control_path
            if self._cmds.attributeQuery(
                    "footPivotsVis", node=control, exists=True):
                result.add(limb.side)
        return frozenset(result)

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
                roll_paths = (pivot.roll_offset_path, pivot.roll_extra_path,
                              pivot.roll_control_path)
                roll_nodes = []
                roll_parents = []
                roller_node = None
                roller_parent = None
                roller_source = None
                if pivot.roll_control_name:
                    for roll_path in roll_paths:
                        matches = self._cmds.ls(
                            roll_path, long=True, type="transform") or []
                        if len(matches) != 1:
                            raise FitSkeletonValidationError(
                                "Foot Roll 控制节点集合无效")
                        roll_nodes.append(matches[0])
                        parents = self._cmds.listRelatives(
                            matches[0], parent=True, fullPath=True) or []
                        roll_parents.append(parents[0] if parents else None)
                    if pivot.roll_roller_name:
                        rollers = self._cmds.ls(
                            pivot.roll_roller_path, long=True,
                            type="transform") or []
                        if len(rollers) != 1:
                            raise FitSkeletonValidationError(
                                "Foot Roll Roller 节点集合无效")
                        roller_node = rollers[0]
                        roller_parents = self._cmds.listRelatives(
                            roller_node, parent=True, fullPath=True) or []
                        roller_parent = (roller_parents[0]
                                         if roller_parents else None)
                        roller_sources = self._cmds.listConnections(
                            roller_node + ".rotateX", source=True,
                            destination=False, plugs=True,
                            skipConversionNodes=True) or []
                        roller_source = (self._canonical_plug(
                            roller_sources[0])
                            if len(roller_sources) == 1 else None)
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
                    roll_offset_path=roll_nodes[0] if roll_nodes else None,
                    roll_offset_parent_path=roll_parents[0] if roll_parents else None,
                    roll_extra_path=roll_nodes[1] if roll_nodes else None,
                    roll_extra_parent_path=roll_parents[1] if roll_parents else None,
                    roll_control_path=roll_nodes[2] if roll_nodes else None,
                    roll_control_parent_path=roll_parents[2] if roll_parents else None,
                    roll_control_position=(tuple(float(value) for value in
                        self._cmds.xform(roll_nodes[2], query=True,
                                         worldSpace=True, translation=True))
                        if roll_nodes else None),
                    roll_control_shape=(
                        "nurbsCurve" if len(self._cmds.listRelatives(
                            roll_nodes[2], shapes=True, noIntermediate=True,
                            fullPath=True, type="nurbsCurve") or []) == 1
                        else None) if roll_nodes else None,
                    roll_roller_path=roller_node,
                    roll_roller_parent_path=roller_parent,
                    roll_roller_rotation_source=roller_source,
                    roll_offset_world_rotation=(tuple(float(value) for value in
                        self._cmds.xform(roll_nodes[0], query=True,
                                         worldSpace=True, rotation=True))
                        if roll_nodes else None),
                    roll_offset_world_axes=(
                        self._spine_world_frame(roll_nodes[0])[1]
                        if roll_nodes and pivot.roll_world_axes is not None
                        else None),
                    roll_control_rotation=(tuple(float(value) for value in
                        self._cmds.getAttr(roll_nodes[2] + ".rotate")[0])
                        if roll_nodes else None),
                ))
            handles = self._cmds.ls(spec.handle_name, long=True, type="ikHandle") or []
            if len(handles) != 1:
                raise FitSkeletonValidationError("Foot IK Handle 节点集合无效")
            swivel_inputs = self._cmds.listConnections(
                handles[0] + ".twist", source=True,
                destination=False, plugs=True,
                skipConversionNodes=True) or []
            swivel_source = (self._canonical_plug(swivel_inputs[0])
                             if len(swivel_inputs) == 1 else None)
            ankle_name = spec.ankle_control_path.rsplit("|", 1)[-1]
            namespace = (ankle_name.rsplit(":", 1)[0] + ":"
                         if ":" in ankle_name else "")
            pole_aim_swivel = (
                f"{namespace}AdvPy_PoleAimSwivelCM_{spec.side.value}")
            if self._cmds.objExists(pole_aim_swivel):
                swivel_inputs = self._cmds.listConnections(
                    pole_aim_swivel + ".inputRotateX", source=True,
                    destination=False, plugs=True,
                    skipConversionNodes=True) or []
                swivel_source = (self._canonical_plug(swivel_inputs[0])
                                 if len(swivel_inputs) == 1 else None)
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
            align_states = self._capture_body_leg_foot_align_helpers(spec)
            if spec.hybrid is not None:
                sides.append(self._capture_body_leg_foot_hybrid_side(
                    spec, values, tuple(pivots),
                    parents[0] if parents else None,
                    ankle_orientation, swivel_source, align_states))
                continue
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
            toe_extras = (self._cmds.ls(
                spec.toe_extra_path, long=True, type="transform") or []
                if spec.toe_extra_path else [])
            toe_extra_parent = (self._cmds.listRelatives(
                toe_extras[0], parent=True, fullPath=True) or []
                if len(toe_extras) == 1 else [])
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
            rock_pivots = []
            if spec.rock:
                for path in (spec.rock.inner_path,
                             spec.rock.outer_path):
                    matches = self._cmds.ls(
                        path, long=True, type="transform") or []
                    if len(matches) != 1:
                        raise FitSkeletonValidationError(
                            "Foot Rock 节点集合无效")
                    node = matches[0]
                    rock_parents = self._cmds.listRelatives(
                        node, parent=True, fullPath=True) or []
                    rock_sources = self._cmds.listConnections(
                        node + ".rotate" + spec.rock.rotation_axis,
                        source=True, destination=False, plugs=True,
                        skipConversionNodes=True) or []
                    rock_pivots.append(BodyLegFootRockPivotState(
                        node,
                        rock_parents[0] if rock_parents else None,
                        tuple(float(value) for value in self._cmds.xform(
                            node, query=True, worldSpace=True,
                            translation=True)),
                        tuple(float(value) for value in self._cmds.xform(
                            node, query=True, worldSpace=True,
                            rotation=True)),
                        self._canonical_plug(rock_sources[0])
                        if len(rock_sources) == 1 else None,
                        int(self._cmds.getAttr(
                            node + ".rotateOrder"))))
            toe_handles = self._cmds.ls(
                spec.toe_handle_name, long=True, type="ikHandle") or []
            if len(toe_handles) != 1:
                raise FitSkeletonValidationError("Toes IK Handle 节点集合无效")
            toe_parents = self._cmds.listRelatives(
                toe_handles[0], parent=True, fullPath=True) or []
            toe_joint_list = tuple(
                (self._cmds.ls(joint, long=True) or [joint])[0]
                for joint in (self._cmds.ikHandle(
                    toe_handles[0], query=True, jointList=True) or []))
            toe_end_handles = self._cmds.ls(
                spec.toe_end_handle_name, long=True, type="ikHandle") or []
            if len(toe_end_handles) != 1:
                raise FitSkeletonValidationError("ToesEnd IK Handle 节点集合无效")
            toe_end_parents = self._cmds.listRelatives(
                toe_end_handles[0], parent=True, fullPath=True) or []
            toe_end_joint_list = tuple(
                (self._cmds.ls(joint, long=True) or [joint])[0]
                for joint in (self._cmds.ikHandle(
                    toe_end_handles[0], query=True, jointList=True) or []))
            intermediate_handles = []
            for step in spec.intermediate_handles:
                matches = self._cmds.ls(
                    step.handle_name, long=True, type="ikHandle") or []
                if len(matches) != 1:
                    raise FitSkeletonValidationError(
                        "逐段脚趾 IK Handle 节点集合无效")
                handle = matches[0]
                parents = self._cmds.listRelatives(
                    handle, parent=True, fullPath=True) or []
                joint_list = tuple(
                    (self._cmds.ls(joint, long=True) or [joint])[0]
                    for joint in (self._cmds.ikHandle(
                        handle, query=True, jointList=True) or []))
                intermediate_handles.append((
                    step.handle_name,
                    parents[0] if parents else None,
                    joint_list,
                    self._cmds.ikHandle(handle, query=True, solver=True)))
            qtoes_parent = None
            qtoes_joint_list = ()
            qtoes_solver = None
            if spec.qtoes_driver_path:
                qtoes_handles = self._cmds.ls(
                    spec.qtoes_handle_name, long=True,
                    type="ikHandle") or []
                if len(qtoes_handles) != 1:
                    raise FitSkeletonValidationError(
                        "QToes IK Handle 节点集合无效")
                qtoes_parents = self._cmds.listRelatives(
                    qtoes_handles[0], parent=True, fullPath=True) or []
                qtoes_parent = qtoes_parents[0] if qtoes_parents else None
                qtoes_joint_list = tuple(
                    (self._cmds.ls(joint, long=True) or [joint])[0]
                    for joint in (self._cmds.ikHandle(
                        qtoes_handles[0], query=True,
                        jointList=True) or []))
                qtoes_solver = self._cmds.ikHandle(
                    qtoes_handles[0], query=True, solver=True)

            def source_of(target):
                connections = self._cmds.listConnections(
                    target, source=True, destination=False, plugs=True,
                    skipConversionNodes=True) or []
                return (self._canonical_plug(connections[0])
                        if len(connections) == 1 else None)

            def transform_at(path):
                matches = self._cmds.ls(
                    path, long=True, type="transform") or []
                if len(matches) != 1:
                    return None, None
                parents = self._cmds.listRelatives(
                    matches[0], parent=True, fullPath=True) or []
                return matches[0], parents[0] if parents else None

            manual_states, high_state = (
                self._capture_body_leg_foot_manual_state(
                    spec, handles[0], source_of, transform_at))

            sides.append(BodyLegFootSideState(
                spec.side,
                values,
                tuple(pivots),
                parents[0] if parents else None,
                *ankle_orientation,
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
                toe_parents[0] if toe_parents else None,
                toe_joint_list,
                self._cmds.ikHandle(toe_handles[0], query=True,
                                    solver=True),
                toe_end_parents[0] if toe_end_parents else None,
                toe_end_joint_list,
                self._cmds.ikHandle(toe_end_handles[0], query=True,
                                    solver=True),
                toe_extra_path=(toe_extras[0]
                                if len(toe_extras) == 1 else None),
                toe_extra_parent_path=(toe_extra_parent[0]
                                       if toe_extra_parent else None),
                toe_control_rotate_order=int(self._cmds.getAttr(
                    toe_controls[0] + ".rotateOrder")),
                toe_control_color=(int(self._cmds.getAttr(
                    toe_shapes[0] + ".overrideColor"))
                    if len(toe_shapes) == 1 else None),
                toe_ik_local=(bool(self._cmds.getAttr(
                    toe_controls[0] + ".ikLocal"))
                    if self._cmds.attributeQuery(
                        "ikLocal", node=toe_controls[0], exists=True)
                    else None),
                toe_extra_ik_local=(bool(self._cmds.getAttr(
                    toe_extras[0] + ".ikLocal"))
                    if len(toe_extras) == 1 and self._cmds.attributeQuery(
                        "ikLocal", node=toe_extras[0], exists=True)
                    else None),
                toe_sub=self._capture_body_ik_sub_control(
                    toe_controls[0], spec.toe_sub_path or None),
                toe_extra_visual=self._capture_body_extra_layer(
                    spec.toe_extra_path or None, toe_controls[0]),
                swivel_source=swivel_source,
                rock_pivots=tuple(rock_pivots),
                manual_pivots=tuple(manual_states),
                high_heel=high_state,
                align_helpers=align_states,
                qtoes_handle_parent_path=qtoes_parent,
                qtoes_handle_joint_list=qtoes_joint_list,
                qtoes_handle_solver=qtoes_solver,
                intermediate_handles=tuple(intermediate_handles),
            ))
        return BodyLegFootSnapshot(tuple(sides))

    def _capture_body_leg_foot_align_helpers(
        self, spec: BodyLegFootSideSpec,
    ) -> tuple[BodyLegFootAlignState, ...]:
        states = []
        for helper in spec.align_helpers:
            found = self._cmds.ls(
                helper.path, long=True, type="transform") or []
            node = found[0] if len(found) == 1 else None
            parents = (self._cmds.listRelatives(
                node, parent=True, fullPath=True) or []
                if node else [])
            matrix, axes = (self._spine_world_frame(node)
                            if node else (None, None))
            states.append(BodyLegFootAlignState(
                node, parents[0] if parents else None,
                matrix[12:15] if matrix else None, axes))
        return tuple(states)

    def _capture_body_leg_foot_manual_state(
        self, spec, handle_path, source_of, transform_at,
    ):
        manual_states = []
        for manual in spec.manual_pivots:
            manual_offset, offset_parent = transform_at(
                manual.offset_path)
            manual_control, control_parent = transform_at(
                manual.control_path)
            manual_reverse, reverse_parent = transform_at(
                manual.reverse_path)
            manual_shapes = (self._cmds.listRelatives(
                manual_control, shapes=True, noIntermediate=True,
                fullPath=True, type="nurbsCurve") or []
                if manual_control else [])
            shape = manual_shapes[0] if len(manual_shapes) == 1 else None
            connections = tuple((target, source_of(target)) for target in (
                manual.matrix_name + ".matrixIn[0]",
                manual.matrix_name + ".matrixIn[1]",
                manual.inverse_name + ".inputMatrix",
                manual.reverse_path + ".offsetParentMatrix"))
            manual_states.append(BodyLegFootManualPivotState(
                manual.target_name, manual_offset, offset_parent,
                manual_control, control_parent,
                manual_reverse, reverse_parent,
                "nurbsCurve" if shape else None,
                int(self._cmds.getAttr(shape + ".overrideColor"))
                if shape else None,
                source_of(shape + ".visibility") if shape else None,
                tuple(float(value) for value in self._cmds.xform(
                    manual_control, query=True, worldSpace=True,
                    translation=True)) if manual_control else None,
                tuple(float(value) for value in self._cmds.xform(
                    manual_offset, query=True, worldSpace=True,
                    rotation=True)) if manual_offset else None,
                tuple(float(value) for value in self._cmds.getAttr(
                    manual_control + ".translate")[0])
                if manual_control else None,
                tuple(float(value) for value in self._cmds.getAttr(
                    manual_control + ".rotate")[0])
                if manual_control else None,
                connections,
                (self._spine_world_frame(manual_offset)[1]
                 if manual_offset and manual.world_axes is not None
                 else None)))

        high_state = None
        if spec.high_heel is not None:
            high = spec.high_heel
            high_paths = tuple(
                (path, *transform_at(path)) for path in (
                    high.offset1_path, high.offset2_path,
                    high.drive1_path, high.drive2_path,
                    high.drive3_path))
            high_connections = tuple(
                (target, source_of(target)) for target in (
                    high.negate_name + ".input1X",
                    high.offset1_path + ".rotateX",
                    high.offset2_path + ".rotateX",
                    high.drive1_path + ".rotateX",
                    handle_path + ".translate"))
            orient_targets = (self._cmds.orientConstraint(
                high.constraint_name, query=True, targetList=True) or []
                if self._cmds.objExists(high.constraint_name) else [])
            point_targets = (self._cmds.pointConstraint(
                high.point_constraint_name, query=True,
                targetList=True) or []
                if self._cmds.objExists(high.point_constraint_name)
                else [])
            high_state = BodyLegFootHighHeelState(
                high_paths, high_connections,
                float(self._cmds.getAttr(
                    high.negate_name + ".input2X"))
                if self._cmds.objExists(high.negate_name) else None,
                float(self._cmds.getAttr(
                    high.constraint_name + ".offsetY"))
                if self._cmds.objExists(high.constraint_name) else None,
                ((self._cmds.ls(orient_targets[0], long=True) or
                  [orient_targets[0]])[0]
                 if len(orient_targets) == 1 else None),
                ((self._cmds.ls(point_targets[0], long=True) or
                  [point_targets[0]])[0]
                 if len(point_targets) == 1 else None))

        return tuple(manual_states), high_state

    def _capture_body_leg_foot_hybrid_side(
        self, spec: BodyLegFootSideSpec, values, pivots,
        handle_parent, ankle_orientation, swivel_source, align_states,
    ) -> BodyLegFootSideState:
        hybrid = spec.hybrid
        if hybrid is None:
            raise RuntimeError("Foot IKHybrid 计划缺失")

        def node_parent(path):
            matches = self._cmds.ls(
                path, long=True, type="transform") or []
            if len(matches) != 1:
                return None, None
            parents = self._cmds.listRelatives(
                matches[0], parent=True, fullPath=True) or []
            return matches[0], parents[0] if parents else None

        def source_of(plug):
            sources = self._cmds.listConnections(
                plug, source=True, destination=False,
                plugs=True, skipConversionNodes=True) or []
            return self._canonical_plug(sources[0]) if len(sources) == 1 else None

        nodes = []
        connections = []
        targets = []
        shapes = []
        control_axes = []
        for segment in hybrid.segments:
            for path in (segment.control_offset_path, segment.control_path,
                         segment.sampler1_offset_path, segment.sampler1_path,
                         segment.sampler2_offset_path, segment.sampler2_path,
                         segment.wrapper_offset_path, segment.wrapper_path):
                nodes.append((path, *node_parent(path)))
            for target in (segment.sampler2_path + ".rotate",
                           segment.wrapper_path + ".translate",
                           segment.wrapper_path + ".rotate"):
                connections.append((target, source_of(target)))
            constraint = self._cmds.ls(
                segment.sampler2_parent_constraint,
                type="parentConstraint") or []
            assigned = (self._cmds.parentConstraint(
                constraint[0], query=True, targetList=True) or []
                if len(constraint) == 1 else [])
            target_path = ((self._cmds.ls(assigned[0], long=True)
                            or [assigned[0]])[0]
                           if len(assigned) == 1 else None)
            targets.append((segment.sampler2_parent_constraint,
                            target_path))
            controls = self._cmds.ls(
                segment.control_path, long=True,
                type="transform") or []
            control_shapes = (self._cmds.listRelatives(
                controls[0], shapes=True, noIntermediate=True,
                fullPath=True, type="nurbsCurve") or []
                if len(controls) == 1 else [])
            shapes.append((segment.control_path,
                           "nurbsCurve" if control_shapes else None))
            control_axes.append((
                segment.control_path,
                self._spine_world_frame(controls[0])[1]
                if len(controls) == 1 else None))

        handles = []
        for name in (hybrid.initial_handle_name,
                     *(segment.handle_name for segment in hybrid.segments)):
            found = self._cmds.ls(
                name, long=True, type="ikHandle") or []
            if len(found) != 1:
                handles.append((name, None, (), None))
                continue
            parents = self._cmds.listRelatives(
                found[0], parent=True, fullPath=True) or []
            joint_list = tuple(
                (self._cmds.ls(joint, long=True) or [joint])[0]
                for joint in (self._cmds.ikHandle(
                    found[0], query=True, jointList=True) or []))
            handles.append((name, parents[0] if parents else None,
                            joint_list, self._cmds.ikHandle(
                                found[0], query=True, solver=True)))

        roll_nodes = []
        for node_spec in spec.roll.nodes:
            found = self._cmds.ls(node_spec.name) or []
            roll_nodes.append(BodyLegFootRollNodeState(
                node_spec.name,
                self._cmds.nodeType(found[0]) if len(found) == 1 else None,
                tuple((target, source_of(target))
                      for _, target in node_spec.input_connections),
                tuple((plug, float(self._cmds.getAttr(plug))
                       if self._cmds.objExists(plug) else None)
                      for plug, _ in node_spec.numeric_values)))
        roll_state = BodyLegFootRollState(
            spec.roll.master_plug,
            float(self._cmds.getAttr(spec.roll.master_plug)),
            tuple(roll_nodes))

        rock_pivots = []
        if spec.rock is not None:
            for path in (spec.rock.inner_path, spec.rock.outer_path):
                node, parent = node_parent(path)
                rock_pivots.append(BodyLegFootRockPivotState(
                    node, parent,
                    tuple(float(value) for value in self._cmds.xform(
                        node, query=True, worldSpace=True,
                        translation=True)) if node else None,
                    tuple(float(value) for value in self._cmds.xform(
                        node, query=True, worldSpace=True,
                        rotation=True)) if node else None,
                    source_of(node + ".rotate" + spec.rock.rotation_axis)
                    if node else None,
                    int(self._cmds.getAttr(node + ".rotateOrder"))
                    if node else None))

        limb_handles = self._cmds.ls(
            spec.handle_name, long=True, type="ikHandle") or []
        if len(limb_handles) != 1:
            raise FitSkeletonValidationError(
                "Leg IK Handle 在 Foot 回读时缺失")
        manual_states, high_state = (
            self._capture_body_leg_foot_manual_state(
                spec, limb_handles[0], source_of, node_parent))

        return BodyLegFootSideState(
            spec.side, values, pivots, handle_parent,
            *ankle_orientation,
            None, None, None, None,
            spec.toe_control_position, spec.toe_control_axes,
            (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), None,
            roll_state,
            swivel_source=swivel_source,
            rock_pivots=tuple(rock_pivots),
            manual_pivots=manual_states,
            high_heel=high_state,
            align_helpers=align_states,
            hybrid=BodyLegFootHybridState(
                tuple(nodes), tuple(connections), tuple(targets),
                tuple(handles), tuple(shapes), tuple(control_axes)))

    def _canonical_plug(self, plug: str) -> str:
        node, attribute = plug.split(".", 1)
        paths = self._cmds.ls(node, long=True) or [node]
        return f"{paths[0]}.{attribute}"

    def create_body_arm_mechanism_root(self, name: str) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Arm 机制链根名称冲突：{name}")
        self._transaction_changed = True
        parent = "|Group|MotionSystem|FKIKSystem"
        if self._cmds.objExists(parent):
            created = self._cmds.createNode(
                "transform", name=name, parent=parent, skipSelect=True)
        else:
            created = self._cmds.createNode(
                "transform", name=name, skipSelect=True)
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
        source_ancestors: set[str] = set()
        for spec in plan.joints:
            ancestor = spec.source_joint.rsplit("|", 1)[0]
            while ancestor:
                source_ancestors.add(ancestor)
                ancestor = ancestor.rsplit("|", 1)[0]
        inbetween_parts = tuple(sorted(
            ancestor for ancestor in source_ancestors
            if (self._cmds.objExists(ancestor)
                and self._cmds.attributeQuery(
                    "advPyAuxiliaryInfluenceKind", node=ancestor,
                    exists=True)
                and self._cmds.getAttr(
                    ancestor + ".advPyAuxiliaryInfluenceKind")
                == "fit-inbetween-v1")))
        return BodyArmMechanismSnapshot(
            roots[0], tuple(states), inbetween_parts)

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

    def create_body_generic_fk(self, plan) -> None:
        if not plan.controls:
            return
        parent = plan.root_path.rsplit("|", 1)[0]
        name = plan.root_path.rsplit("|", 1)[-1]
        if self.create_body_control_root(name, parent_path=parent) != plan.root_path:
            raise RuntimeError("通用 FK 控制根路径漂移")
        for spec in plan.controls:
            self._create_body_limb_fk_control(spec, "Generic")
        for path in plan.hidden_controls:
            self.hide_body_fk_control(path)

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
            if (self.find_name_collisions(spec.name)
                    or (spec.follow_matrix_name is not None
                        and self.find_name_collisions(
                            spec.follow_matrix_name))
                    or (spec.follow_constraint_name is not None
                        and self.find_name_collisions(
                            spec.follow_constraint_name))):
                raise FitSkeletonValidationError(
                    f"Hand FK 根节点名称冲突：{spec.name}"
                )
            wrists = self._cmds.ls(
                spec.wrist_joint, long=True, type="joint") or []
            parents = self._cmds.ls(spec.parent_path, long=True) or []
            if (wrists != [spec.wrist_joint]
                    or parents != [spec.parent_path]
                    or self._cmds.nodeType(parents[0]) not in
                    ("joint", "transform")):
                raise FitSkeletonValidationError(
                    f"Hand FK Wrist 或控制父级失效：{spec.parent_path}"
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
            if spec.source_icon_size:
                self._cmds.addAttr(root, longName="advPyHandSourceIconSize",
                                   attributeType="bool", defaultValue=True)
            if spec.follow_matrix_name is not None:
                follow = self._cmds.createNode(
                    "multMatrix", name=spec.follow_matrix_name,
                    skipSelect=True)
                self._cmds.connectAttr(
                    spec.wrist_joint + ".worldMatrix[0]",
                    follow + ".matrixIn[0]")
                self._cmds.connectAttr(
                    root + ".parentInverseMatrix[0]",
                    follow + ".matrixIn[1]")
                self._cmds.connectAttr(
                    follow + ".matrixSum", root + ".offsetParentMatrix")
            if spec.follow_constraint_name is not None:
                constraints = self._cmds.parentConstraint(
                    spec.wrist_joint, root, maintainOffset=False,
                    name=spec.follow_constraint_name)
                if (len(constraints) != 1
                        or constraints[0].rsplit("|", 1)[-1]
                        != spec.follow_constraint_name):
                    raise RuntimeError("Hand FK Wrist 约束名称漂移")
                constraint_path = root + "|" + spec.follow_constraint_name
                if (self._cmds.ls(constraints[0], long=True,
                                  type="parentConstraint") or []) != [
                                      constraint_path]:
                    raise RuntimeError("Hand FK Wrist 约束父级路径漂移")
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
            *((spec.extra_name,) if spec.extra_name is not None else ()),
            *((spec.aim_name,) if spec.aim_name is not None else ()),
            spec.control_name,
            spec.constraint_name,
            *((spec.sub_control_name,) if spec.sub_control_name is not None else ()),
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
            self._cmds.setAttr(offset + ".rotateOrder", spec.rotate_order)
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
            if spec.aim_path is not None:
                if spec.aim_name is None:
                    raise FitSkeletonValidationError("FK Aim 层缺少名称")
                control_parent = self._cmds.createNode(
                    "transform", name=spec.aim_name, parent=offset,
                    skipSelect=True)
                control_parent = (self._cmds.ls(
                    control_parent, long=True) or [control_parent])[0]
                if control_parent != spec.aim_path:
                    raise RuntimeError("FK Aim 层路径漂移")
                self._cmds.setAttr(
                    control_parent + ".rotateOrder", spec.rotate_order)
            if spec.extra_path is not None:
                if spec.extra_name is None:
                    raise FitSkeletonValidationError("FK Extra 层缺少名称")
                control_parent = self._create_body_extra_layer(
                    control_parent, spec.extra_name, spec.extra_path)
                self._cmds.setAttr(
                    control_parent + ".rotateOrder", spec.rotate_order)
            if pose_name is not None:
                control_parent = self._cmds.createNode(
                    "transform",
                    name=pose_name,
                    parent=control_parent,
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
            control = create_adv_icon(
                self._cmds, name=spec.control_name,
                parent=control_parent,
                template=body_controller_icon_template(
                    "FK", spec.control_name),
                radius=spec.radius,
                fallback_normal=(1.0, 0.0, 0.0), fallback_sections=12,
                axis_offset=original_fit_icon_axis_offset(
                    self._cmds, spec.fit_joint_names),
                mirror_left=spec.side is FitBuildSide.LEFT)
            control = (self._cmds.ls(control, long=True) or [control])[0]
            if offset != spec.offset_path or control != spec.control_path:
                raise RuntimeError(
                    f"{limb_label} FK 控制路径漂移：{spec.control_name}"
                )
            self._cmds.setAttr(control + ".rotateOrder", spec.rotate_order)
            self._cmds.setAttr(driven[0] + ".rotateOrder", spec.rotate_order)
            if spec.extra_curve:
                if spec.extra_path is None:
                    raise FitSkeletonValidationError("FK Extra 曲线缺少层路径")
                self._add_body_extra_curve(
                    spec.extra_path, control)
            if spec.sub_control_path is not None:
                if spec.sub_control_name is None:
                    raise FitSkeletonValidationError("FK Sub 控制器缺少名称")
                self._create_body_sub_control(
                    control, spec.sub_control_name,
                    spec.sub_control_path)
            orientation_source = (
                spec.sub_control_path or control)
            if spec.source_override_path is not None:
                if spec.source_override_path.startswith(control + "|"):
                    source_parent = spec.source_override_path.rsplit("|", 1)[0]
                    if source_parent not in (control, spec.sub_control_path):
                        raise FitSkeletonValidationError(
                            "FK 约束接收层必须直接位于控制器或 Sub 下")
                    orientation_source = self._cmds.createNode(
                        "transform",
                        name=spec.source_override_path.rsplit("|", 1)[-1],
                        parent=source_parent,
                        skipSelect=True,
                    )
                    orientation_source = (
                        self._cmds.ls(orientation_source, long=True)
                        or [orientation_source]
                    )[0]
                    if orientation_source != spec.source_override_path:
                        raise RuntimeError("FK 约束接收层路径漂移")
                else:
                    matches = self._cmds.ls(
                        spec.source_override_path, long=True,
                        type="transform") or []
                    if matches != [spec.source_override_path]:
                        raise FitSkeletonValidationError(
                            "FK 约束来源不存在：" + spec.source_override_path)
                    orientation_source = matches[0]
            self._cmds.orientConstraint(
                orientation_source,
                driven[0],
                maintainOffset=False,
                name=spec.constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def create_body_fk_global(self, spec: BodyFkGlobalSpec) -> None:
        self._require_transaction()
        c = self._cmds
        for path in (spec.control, spec.offset, spec.extra, GLOBAL_FOLLOW):
            if (c.ls(path, long=True, type="transform") or []) != [path]:
                raise FitSkeletonValidationError("Global FK 层缺失：" + path)
        if (c.listConnections(spec.extra + ".offsetParentMatrix",
                              source=True, destination=False) or []):
            raise FitSkeletonValidationError(
                "Global FK Extra 已有 OPM 输入：" + spec.extra)
        if any(self.find_name_collisions(name) for name in spec.node_names):
            raise FitSkeletonValidationError(
                "Global FK 矩阵节点名称冲突：" + spec.control)
        if c.attributeQuery("Global", node=spec.control, exists=True):
            raise FitSkeletonValidationError(
                "Global FK 控制属性已存在：" + spec.control)
        self._transaction_changed = True
        bind_matrix = tuple(float(value) for value in c.xform(
            spec.offset, query=True, worldSpace=True, matrix=True))
        if len(bind_matrix) != 16:
            raise RuntimeError("Global FK 绑定矩阵无效")
        c.addAttr(spec.control, longName="Global", attributeType="double",
                  minValue=0, maxValue=10,
                  defaultValue=spec.default_weight, keyable=True)
        if spec.translate:
            c.addAttr(spec.control, longName="GlobalTranslate",
                      attributeType="double", minValue=0, maxValue=10,
                      defaultValue=spec.default_weight, keyable=True)
        mm = c.createNode("multMatrix", name=spec.matrix_name,
                          skipSelect=True)
        c.setAttr(mm + ".matrixIn[0]", *bind_matrix, type="matrix")
        c.connectAttr(GLOBAL_FOLLOW + ".worldMatrix[0]",
                      mm + ".matrixIn[1]")
        c.connectAttr(spec.offset + ".worldInverseMatrix[0]",
                      mm + ".matrixIn[2]")
        rot_pick = c.createNode("pickMatrix", name=spec.rotate_pick_name,
                                skipSelect=True)
        c.setAttr(rot_pick + ".useTranslate", False)
        c.setAttr(rot_pick + ".useScale", False)
        c.setAttr(rot_pick + ".useShear", False)
        c.connectAttr(mm + ".matrixSum", rot_pick + ".inputMatrix")
        rot_blend = c.createNode("blendMatrix", name=spec.rotate_blend_name,
                                 skipSelect=True)
        c.connectAttr(rot_pick + ".outputMatrix",
                      rot_blend + ".target[0].targetMatrix")
        rot_uc = c.createNode("unitConversion",
                              name=spec.rotate_conversion_name,
                              skipSelect=True)
        c.setAttr(rot_uc + ".conversionFactor", 0.1)
        c.connectAttr(spec.control + ".Global", rot_uc + ".input")
        c.connectAttr(rot_uc + ".output",
                      rot_blend + ".target[0].weight")
        output = rot_blend + ".outputMatrix"
        if spec.translate:
            pos_pick = c.createNode("pickMatrix",
                                    name=spec.position_pick_name,
                                    skipSelect=True)
            c.setAttr(pos_pick + ".useRotate", False)
            c.setAttr(pos_pick + ".useScale", False)
            c.setAttr(pos_pick + ".useShear", False)
            c.connectAttr(mm + ".matrixSum", pos_pick + ".inputMatrix")
            pos_blend = c.createNode("blendMatrix",
                                     name=spec.position_blend_name,
                                     skipSelect=True)
            c.connectAttr(pos_pick + ".outputMatrix",
                          pos_blend + ".target[0].targetMatrix")
            pos_uc = c.createNode("unitConversion",
                                  name=spec.position_conversion_name,
                                  skipSelect=True)
            c.setAttr(pos_uc + ".conversionFactor", 0.1)
            c.connectAttr(spec.control + ".GlobalTranslate",
                          pos_uc + ".input")
            c.connectAttr(pos_uc + ".output",
                          pos_blend + ".target[0].weight")
            compose = c.createNode("multMatrix", name=spec.compose_name,
                                   skipSelect=True)
            c.connectAttr(rot_blend + ".outputMatrix",
                          compose + ".matrixIn[0]")
            c.connectAttr(pos_blend + ".outputMatrix",
                          compose + ".matrixIn[1]")
            output = compose + ".matrixSum"
        c.connectAttr(output, spec.extra + ".offsetParentMatrix")

    def capture_body_fk_global(
        self, spec: BodyFkGlobalSpec,
    ) -> BodyFkGlobalState:
        c = self._cmds

        def source(plug: str) -> str | None:
            values = c.listConnections(plug, source=True,
                                       destination=False, plugs=True) or []
            return values[0] if len(values) == 1 else None

        def flags(node: str) -> tuple[bool, bool, bool, bool] | None:
            if not c.objExists(node):
                return None
            return tuple(bool(c.getAttr(node + ".use" + name))
                         for name in ("Translate", "Rotate", "Scale", "Shear"))

        def channel_range(name: str) -> tuple[float, float] | None:
            if not (c.attributeQuery(name, node=spec.control,
                                     exists=True)
                    and c.attributeQuery(name, node=spec.control,
                                         minExists=True)
                    and c.attributeQuery(name, node=spec.control,
                                         maxExists=True)):
                return None
            minimum = c.attributeQuery(name, node=spec.control,
                                       minimum=True) or []
            maximum = c.attributeQuery(name, node=spec.control,
                                       maximum=True) or []
            return ((float(minimum[0]), float(maximum[0]))
                    if len(minimum) == len(maximum) == 1 else None)

        bind_matrix = None
        if c.objExists(spec.matrix_name):
            values = c.getAttr(spec.matrix_name + ".matrixIn[0]")
            if (isinstance(values, (list, tuple)) and len(values) == 1
                    and isinstance(values[0], (list, tuple))):
                values = values[0]
            if isinstance(values, (list, tuple)):
                bind_matrix = tuple(float(value) for value in values)

        return BodyFkGlobalState(
            control=spec.control,
            extra=spec.extra,
            extra_parent=((c.listRelatives(spec.extra, parent=True,
                                           fullPath=True) or [None])[0]
                          if c.objExists(spec.extra) else None),
            weight=(float(c.getAttr(spec.control + ".Global"))
                    if c.attributeQuery("Global", node=spec.control,
                                        exists=True) else None),
            translate_weight=(
                float(c.getAttr(spec.control + ".GlobalTranslate"))
                if c.attributeQuery("GlobalTranslate", node=spec.control,
                                    exists=True) else None),
            weight_range=channel_range("Global"),
            translate_weight_range=(channel_range("GlobalTranslate")
                                    if spec.translate else None),
            weight_keyable=(bool(c.getAttr(spec.control + ".Global",
                                           keyable=True))
                            if c.attributeQuery("Global", node=spec.control,
                                                exists=True) else False),
            translate_weight_keyable=(
                bool(c.getAttr(spec.control + ".GlobalTranslate",
                               keyable=True))
                if spec.translate and c.attributeQuery(
                    "GlobalTranslate", node=spec.control, exists=True)
                else (False if spec.translate else None)),
            nodes=tuple((name, c.nodeType(name) if c.objExists(name) else "")
                        for name in spec.node_names),
            sources=tuple((plug, source(plug)) for plug, _ in
                          body_fk_global_sources(spec)),
            rotate_pick_flags=flags(spec.rotate_pick_name),
            position_pick_flags=(flags(spec.position_pick_name)
                                 if spec.translate else None),
            conversion_factors=tuple(
                float(c.getAttr(name + ".conversionFactor"))
                if c.objExists(name) else float("nan")
                for name in ((spec.rotate_conversion_name,
                              spec.position_conversion_name)
                             if spec.translate else
                             (spec.rotate_conversion_name,))),
            bind_world_matrix=bind_matrix,
        )

    def read_fit_fk_lock_channels(self, joint: str) -> tuple[str, ...]:
        c = self._cmds
        if (c.ls(joint, long=True, type="joint") or []) != [joint]:
            raise FitSkeletonValidationError(
                "FK 锁定来源 Fit 关节缺失：" + joint)
        return tuple(attribute for attribute in (
            kind + axis for kind in ("translate", "rotate", "scale")
            for axis in "XYZ")
            if c.getAttr(joint + "." + attribute, lock=True))

    def apply_body_fk_channel_locks(
        self, spec: BodyFkChannelLockSpec,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        if ((c.ls(spec.control, long=True, type="transform") or [])
                != [spec.control]
                or not set(spec.attributes) <= FK_LOCK_ATTRIBUTES):
            raise FitSkeletonValidationError(
                "FK 锁定目标或通道无效：" + spec.control)
        for attribute in spec.attributes:
            plug = spec.control + "." + attribute
            if (not c.objExists(plug)
                    or c.listConnections(plug, source=True,
                                         destination=False)):
                raise FitSkeletonValidationError(
                    "FK 锁定通道不可写：" + plug)
        self._transaction_changed = True
        for attribute in spec.attributes:
            plug = spec.control + "." + attribute
            if not (c.getAttr(plug, lock=True)
                    and not c.getAttr(plug, keyable=True)):
                c.setAttr(plug, lock=True, keyable=False)

    def capture_body_fk_channel_locks(
        self, spec: BodyFkChannelLockSpec,
    ) -> bool:
        c = self._cmds
        return ((c.ls(spec.control, long=True, type="transform") or [])
                == [spec.control]
                and all(c.getAttr(spec.control + "." + attribute,
                                  lock=True)
                        and not c.getAttr(spec.control + "." + attribute,
                                          keyable=True)
                        for attribute in spec.attributes))

    def hide_body_fk_control(self, control: str) -> None:
        self._require_transaction()
        c = self._cmds
        if (c.ls(control, long=True, type="transform") or []) != [control]:
            raise FitSkeletonValidationError("No Control 目标控制器缺失："
                                             + control)
        shapes = c.listRelatives(control, shapes=True, fullPath=True,
                                 type="nurbsCurve") or []
        if not shapes or c.attributeQuery("advPyNoControl", node=control,
                                         exists=True):
            raise FitSkeletonValidationError("No Control 目标曲线状态无效："
                                             + control)
        self._transaction_changed = True
        c.addAttr(control, longName="advPyNoControl",
                  attributeType="bool")
        c.setAttr(control + ".advPyNoControl", True, lock=True)
        for shape in shapes:
            c.setAttr(shape + ".visibility", False, lock=True)

    def capture_hidden_body_fk_control(self, control: str) -> bool:
        c = self._cmds
        if (c.ls(control, long=True, type="transform") or []) != [control]:
            return False
        if (not c.attributeQuery("advPyNoControl", node=control,
                                 exists=True)
                or not c.getAttr(control + ".advPyNoControl")):
            return False
        shapes = c.listRelatives(control, shapes=True, fullPath=True,
                                 type="nurbsCurve") or []
        return bool(shapes) and all(
            not c.getAttr(shape + ".visibility")
            and c.getAttr(shape + ".visibility", lock=True)
            for shape in shapes)

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
        def input_source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug, source=True, destination=False, plugs=True) or []
            return (self._canonical_plug(values[0])
                    if len(values) == 1 else None)

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
                follow_matrix_sources=(
                    tuple(input_source(plug) for plug in (
                        spec.follow_matrix_name + ".matrixIn[0]",
                        spec.follow_matrix_name + ".matrixIn[1]",
                        path + ".offsetParentMatrix"))
                    if spec.follow_matrix_name else
                    (None, None, input_source(path + ".offsetParentMatrix"))
                ),
                follow_constraint_targets=(
                    tuple(self._resolve_connected_node(node) for node in
                          (self._cmds.parentConstraint(
                              spec.follow_constraint_name, query=True,
                              targetList=True) or []))
                    if spec.follow_constraint_name else ()
                ),
                follow_constraint_channels=(
                    tuple(input_source(f"{path}.{kind}{axis}")
                          for kind in ("translate", "rotate")
                          for axis in "XYZ")
                    if spec.follow_constraint_name else ()
                ),
                source_icon_size=(
                    self._cmds.attributeQuery("advPyHandSourceIconSize",
                                              node=path, exists=True)
                    and bool(self._cmds.getAttr(
                        path + ".advPyHandSourceIconSize"))
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
        parents = (self._cmds.listRelatives(
            roots[0], parent=True, fullPath=True) or []) if len(roots) == 1 else []
        expected_parent = plan.root_path.rsplit("|", 1)[0]
        if (roots != [plan.root_path]
                or parents != ([expected_parent] if expected_parent else [])):
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
            sub_path = None
            sub_parent = None
            sub_shape_type = None
            sub_visibility_source = None
            sub_color = None
            sub_shape_scale = None
            if spec.sub_control_path is None:
                children = self._cmds.listRelatives(
                    control, children=True, type="transform",
                    fullPath=True) or []
                unexpected = [path for path in children if path.rsplit(
                    "|", 1)[-1].startswith("AdvPy_") and "FKSub_" in path]
                if unexpected:
                    sub_path = unexpected[0]
            else:
                sub_nodes = self._cmds.ls(
                    spec.sub_control_path, long=True, type="transform") or []
                if len(sub_nodes) == 1:
                    sub_path = sub_nodes[0]
                    sub_parents = self._cmds.listRelatives(
                        sub_path, parent=True, fullPath=True) or []
                    sub_parent = sub_parents[0] if len(sub_parents) == 1 else None
                    sub_shapes = self._cmds.listRelatives(
                        sub_path, shapes=True, noIntermediate=True,
                        fullPath=True) or []
                    if len(sub_shapes) == 1:
                        sub_shape_type = self._cmds.nodeType(sub_shapes[0])
                        sub_color = int(self._cmds.getAttr(
                            sub_shapes[0] + ".overrideColor"))
                        sources = self._cmds.listConnections(
                            sub_shapes[0] + ".visibility", source=True,
                            destination=False, plugs=True) or []
                        if len(sources) == 1:
                            source_node, source_attribute = sources[0].split(
                                ".", 1)
                            source_paths = self._cmds.ls(
                                source_node, long=True) or []
                            if len(source_paths) == 1:
                                sub_visibility_source = (
                                    source_paths[0] + "." + source_attribute)
                        if len(shapes) == 1:
                            parent_cv = self._cmds.xform(
                                shapes[0] + ".cv[0]", query=True,
                                objectSpace=True, translation=True)
                            sub_cv = self._cmds.xform(
                                sub_shapes[0] + ".cv[0]", query=True,
                                objectSpace=True, translation=True)
                            parent_radius = sum(float(x) ** 2
                                                for x in parent_cv) ** 0.5
                            if parent_radius > 0:
                                sub_shape_scale = (
                                    sum(float(x) ** 2 for x in sub_cv) ** 0.5
                                    / parent_radius)
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
                    icon_template=(self._cmds.getAttr(
                        control + ".advPyIconTemplate") if
                        self._cmds.attributeQuery(
                            "advPyIconTemplate", node=control,
                            exists=True) else None),
                    icon_mirrored=(bool(self._cmds.getAttr(
                        control + ".advPyIconMirrored")) if
                        self._cmds.attributeQuery(
                            "advPyIconMirrored", node=control,
                            exists=True) else None),
                    local_scale=tuple(float(value) for value in
                        self._cmds.getAttr(control + ".scale")[0]),
                    sub_control_path=sub_path,
                    sub_parent_path=sub_parent,
                    sub_shape_type=sub_shape_type,
                    sub_visibility_source=sub_visibility_source,
                    sub_color=sub_color,
                    sub_shape_scale=sub_shape_scale,
                    extra=self._capture_body_extra_layer(
                        spec.extra_path, control),
                    rotate_orders=tuple(
                        (path, int(self._cmds.getAttr(
                            path + ".rotateOrder")))
                        for path in (spec.offset_path,
                                     *((spec.aim_path,)
                                       if spec.aim_path else ()),
                                     *((spec.extra_path,)
                                       if spec.extra_path else ()),
                                     spec.control_path)),
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
