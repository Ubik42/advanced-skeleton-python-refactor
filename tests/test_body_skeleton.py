import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import (
    BuildBodyArmMechanisms,
    BuildBodyLegMechanisms,
    BuildBodyLegFkMechanismControls,
    BuildBodyLegIkControls,
    BuildBodyLegBlend,
    BuildBodyLegVisibility,
    BuildBodyLegRig,
    BuildBodyLegFoot,
    BuildBodyArmFkControls,
    BuildBodyArmFkMechanismControls,
    BuildBodyArmIkControls,
    BuildBodyArmBlend,
    BuildBodyArmRig,
    MatchBodyArmFkToIk,
    MatchBodyLegFkToIk,
    MatchBodyLegIkToFk,
    MatchBodyArmIkToFk,
    BuildBodySkeleton,
    BuildOrientedBodySkeleton,
    InspectBodyRebuildSafety,
    InspectBodySkeletonProvenance,
    OrientBodySkeleton,
    ReplaceOwnedBodySkeleton,
)
from adv_py.core import (
    BodyArmMechanismJointState,
    BodyArmMechanismSnapshot,
    BodyLegMechanismJointState,
    BodyLegMechanismRole,
    BodyLegMechanismSnapshot,
    BodyLegFkControlSnapshot,
    BodyLegFkControlState,
    BodyLegIkSnapshot,
    BodyLegIkState,
    BodyLegBlendJointState,
    BodyLegBlendSideState,
    BodyLegBlendSnapshot,
    BodyLegVisibilityInputState,
    BodyLegVisibilitySideState,
    BodyLegVisibilitySnapshot,
    BodyLegFootInputState,
    BodyLegFootValidationError,
    BodyLegFootPivotState,
    BodyLegFootRollNodeState,
    BodyLegFootRollState,
    BodyLegFootSideState,
    BodyLegFootSnapshot,
    BodyArmIkSnapshot,
    BodyArmIkState,
    BodyArmBlendJointState,
    BodyArmBlendSideState,
    BodyArmBlendSnapshot,
    BodyArmVisibilitySideState,
    BodyArmVisibilitySnapshot,
    BodyArmFkToIkSceneState,
    BodyLegFkToIkSceneState,
    BodyLegIkToFkSceneState,
    BodyArmIkToFkSceneState,
    BodyArmStretchSideState,
    BodyArmStretchSnapshot,
    BodyLegStretchSideState,
    BodyLegStretchSnapshot,
    BodyArmTwistJointState,
    BodyArmTwistSegmentState,
    BodyArmTwistSnapshot,
    BodyLegTwistJointState,
    BodyLegTwistSegmentState,
    BodyLegTwistSnapshot,
    BodyArmVolumeSideState,
    BodyArmVolumeSnapshot,
    IDENTITY_AXES,
    BodyJointState,
    BodyExternalDependency,
    BodyExternalDependencyKind,
    BodyArmFkControlSnapshot,
    BodyArmFkControlState,
    BodyControlValidationError,
    BodyRebuildSceneState,
    BodySkeletonSnapshot,
    BodySkeletonProvenanceState,
    BodySkeletonValidationError,
    FitJointMetadata,
    FitJointOrientationState,
    FitBuildSide,
    FitOrientationSnapshot,
    FitSkeletonValidationError,
    FitUpAxis,
    default_fit_skeleton_settings,
    predict_fit_template_hierarchy,
    synthetic_body_source_fit_template,
    plan_body_arm_fk_controls,
    audit_body_leg_fk_to_ik_preflight,
    segmented_foot_roll,
)


class FakeBodySkeletonHost:
    def __init__(
        self,
        *,
        faulty_capture=False,
        faulty_after_orientation=False,
        faulty_provenance=False,
        faulty_arm_fk=False,
        faulty_arm_mechanisms=False,
        faulty_leg_mechanisms=False,
        faulty_leg_fk=False,
        faulty_leg_ik=False,
        faulty_leg_blend=False,
        faulty_leg_visibility=False,
        faulty_leg_stretch=False,
        blocked_leg_visibility=False,
        faulty_leg_match=False,
        faulty_leg_foot=False,
        blocked_leg_foot=False,
        faulty_arm_ik=False,
        faulty_arm_blend=False,
        faulty_arm_visibility=False,
        faulty_arm_match=False,
        faulty_arm_translation=False,
        faulty_arm_stretch=False,
        faulty_arm_twist=False,
        faulty_arm_twist_runtime=False,
        faulty_leg_twist=False,
        faulty_leg_twist_runtime=False,
        faulty_arm_volume=False,
    ):
        template = synthetic_body_source_fit_template(FitUpAxis.Z)
        hierarchy = predict_fit_template_hierarchy(template, "|FitSkeleton")
        self.fit_snapshot = FitOrientationSnapshot(
            hierarchy,
            FitUpAxis.Z,
            tuple(
                FitJointOrientationState(
                    node.path,
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                    IDENTITY_AXES,
                )
                for node in hierarchy.joints
            ),
            tuple(FitJointMetadata(node.path) for node in hierarchy.joints),
        )
        angled_axes = (
            (0.8, 0.6, 0.0),
            (-0.6, 0.8, 0.0),
            (0.0, 0.0, 1.0),
        )
        self.fit_snapshot = replace(
            self.fit_snapshot,
            joints=tuple(
                replace(state, world_axes=angled_axes)
                if state.joint.endswith("|Scapula")
                else state
                for state in self.fit_snapshot.joints
            ),
        )
        self.settings = default_fit_skeleton_settings(hierarchy.container)
        labels_by_name = {spec.name: spec.label for spec in template.joints}
        self.labels = {
            node.path: labels_by_name[node.short_name] for node in hierarchy.joints
        }
        self.collisions = {}
        self.body = []
        self.transaction_count = 0
        self.faulty_capture = faulty_capture
        self.faulty_after_orientation = faulty_after_orientation
        self.orientation_write_count = 0
        self.faulty_provenance = faulty_provenance
        self.provenance = None
        self.in_transaction = False
        self.extra_dag_paths = ()
        self.external_dependencies = ()
        self.delete_count = 0
        self.control_root = None
        self.arm_fk_states = []
        self.faulty_arm_fk = faulty_arm_fk
        self.mechanism_root = None
        self.arm_mechanism_states = []
        self.faulty_arm_mechanisms = faulty_arm_mechanisms
        self.leg_mechanism_root = None
        self.leg_mechanism_states = []
        self.faulty_leg_mechanisms = faulty_leg_mechanisms
        self.leg_control_root = None
        self.leg_fk_states = []
        self.faulty_leg_fk = faulty_leg_fk
        self.leg_ik_root = None
        self.leg_ik_states = []
        self.faulty_leg_ik = faulty_leg_ik
        self.leg_blend_snapshot = None
        self.faulty_leg_blend = faulty_leg_blend
        self.leg_visibility_snapshot = None
        self.faulty_leg_visibility = faulty_leg_visibility
        self.leg_stretch_snapshot = None
        self.faulty_leg_stretch = faulty_leg_stretch
        self.blocked_leg_visibility = blocked_leg_visibility
        self.faulty_leg_match = faulty_leg_match
        self.leg_match_applied = False
        self.leg_foot_snapshot = None
        self.faulty_leg_foot = faulty_leg_foot
        self.blocked_leg_foot = blocked_leg_foot
        self.arm_ik_root = None
        self.arm_ik_states = []
        self.faulty_arm_ik = faulty_arm_ik
        self.arm_blend_snapshot = None
        self.faulty_arm_blend = faulty_arm_blend
        self.arm_visibility_snapshot = None
        self.faulty_arm_visibility = faulty_arm_visibility
        self.faulty_arm_match = faulty_arm_match
        self.arm_match_applied = False
        self.arm_match_segment_translations = None
        self.leg_match_segment_translations = None
        self.faulty_arm_translation = faulty_arm_translation
        self.arm_stretch_snapshot = None
        self.faulty_arm_stretch = faulty_arm_stretch
        self.twist_root = None
        self.arm_twist_segments = []
        self.arm_twist_states = []
        self.faulty_arm_twist = faulty_arm_twist
        self.faulty_arm_twist_runtime = faulty_arm_twist_runtime
        self.leg_twist_root = None
        self.leg_twist_segments = []
        self.leg_twist_states = []
        self.faulty_leg_twist = faulty_leg_twist
        self.faulty_leg_twist_runtime = faulty_leg_twist_runtime
        self.arm_volume_snapshot = None
        self.faulty_arm_volume = faulty_arm_volume

    def capture_fit_orientation(self, container_name):
        del container_name
        return self.fit_snapshot

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    def read_joint_label(self, joint):
        return self.labels.get(joint)

    def find_name_collisions(self, name):
        existing_body = tuple(
            state.path for state in self.body if state.name == name
        )
        existing_controls = []
        if self.control_root and self.control_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.control_root)
        for state in self.arm_fk_states:
            for path in (state.offset_path, state.control_path):
                if path.rsplit("|", 1)[-1] == name:
                    existing_controls.append(path)
            if state.constraint_name == name:
                existing_controls.append(name)
        if self.mechanism_root and self.mechanism_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.mechanism_root)
        for state in self.arm_mechanism_states:
            if state.path.rsplit("|", 1)[-1] == name:
                existing_controls.append(state.path)
        if self.leg_mechanism_root and self.leg_mechanism_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.leg_mechanism_root)
        for state in self.leg_mechanism_states:
            if state.path.rsplit("|", 1)[-1] == name:
                existing_controls.append(state.path)
        if (
            self.leg_control_root
            and self.leg_control_root.rsplit("|", 1)[-1] == name
        ):
            existing_controls.append(self.leg_control_root)
        for state in self.leg_fk_states:
            for path in (state.offset_path, state.control_path):
                if path.rsplit("|", 1)[-1] == name:
                    existing_controls.append(path)
            if state.constraint_name == name:
                existing_controls.append(name)
        if self.leg_ik_root and self.leg_ik_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.leg_ik_root)
        if self.arm_ik_root and self.arm_ik_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.arm_ik_root)
        if self.twist_root and self.twist_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.twist_root)
        for state in self.arm_twist_states:
            if state.path.rsplit("|", 1)[-1] == name:
                existing_controls.append(state.path)
            if state.constraint_name == name:
                existing_controls.append(name)
        if (
            self.leg_twist_root
            and self.leg_twist_root.rsplit("|", 1)[-1] == name
        ):
            existing_controls.append(self.leg_twist_root)
        for state in self.leg_twist_states:
            if state.path.rsplit("|", 1)[-1] == name:
                existing_controls.append(state.path)
            if state.constraint_name == name:
                existing_controls.append(name)
        return (
            tuple(self.collisions.get(name, ()))
            + existing_body
            + tuple(existing_controls)
        )

    @contextmanager
    def transaction(self, label):
        del label
        before = list(self.body)
        before_provenance = self.provenance
        before_control_root = self.control_root
        before_arm_fk_states = list(self.arm_fk_states)
        before_mechanism_root = self.mechanism_root
        before_arm_mechanism_states = list(self.arm_mechanism_states)
        before_leg_mechanism_root = self.leg_mechanism_root
        before_leg_mechanism_states = list(self.leg_mechanism_states)
        before_leg_control_root = self.leg_control_root
        before_leg_fk_states = list(self.leg_fk_states)
        before_leg_ik_root = self.leg_ik_root
        before_leg_ik_states = list(self.leg_ik_states)
        before_leg_blend_snapshot = self.leg_blend_snapshot
        before_leg_visibility_snapshot = self.leg_visibility_snapshot
        before_leg_match_applied = self.leg_match_applied
        before_leg_match_segment_translations = self.leg_match_segment_translations
        before_leg_stretch_snapshot = self.leg_stretch_snapshot
        before_leg_foot_snapshot = self.leg_foot_snapshot
        before_arm_ik_root = self.arm_ik_root
        before_arm_ik_states = list(self.arm_ik_states)
        before_arm_blend_snapshot = self.arm_blend_snapshot
        before_arm_visibility_snapshot = self.arm_visibility_snapshot
        before_arm_match_applied = self.arm_match_applied
        before_arm_match_segment_translations = self.arm_match_segment_translations
        before_arm_stretch_snapshot = self.arm_stretch_snapshot
        before_twist_root = self.twist_root
        before_arm_twist_segments = list(self.arm_twist_segments)
        before_arm_twist_states = list(self.arm_twist_states)
        before_leg_twist_root = self.leg_twist_root
        before_leg_twist_segments = list(self.leg_twist_segments)
        before_leg_twist_states = list(self.leg_twist_states)
        before_arm_volume_snapshot = self.arm_volume_snapshot
        self.transaction_count += 1
        self.in_transaction = True
        try:
            yield
        except Exception:
            self.body = before
            self.provenance = before_provenance
            self.control_root = before_control_root
            self.arm_fk_states = before_arm_fk_states
            self.mechanism_root = before_mechanism_root
            self.arm_mechanism_states = before_arm_mechanism_states
            self.leg_mechanism_root = before_leg_mechanism_root
            self.leg_mechanism_states = before_leg_mechanism_states
            self.leg_control_root = before_leg_control_root
            self.leg_fk_states = before_leg_fk_states
            self.leg_ik_root = before_leg_ik_root
            self.leg_ik_states = before_leg_ik_states
            self.leg_blend_snapshot = before_leg_blend_snapshot
            self.leg_visibility_snapshot = before_leg_visibility_snapshot
            self.leg_match_applied = before_leg_match_applied
            self.leg_match_segment_translations = before_leg_match_segment_translations
            self.leg_stretch_snapshot = before_leg_stretch_snapshot
            self.leg_foot_snapshot = before_leg_foot_snapshot
            self.arm_ik_root = before_arm_ik_root
            self.arm_ik_states = before_arm_ik_states
            self.arm_blend_snapshot = before_arm_blend_snapshot
            self.arm_visibility_snapshot = before_arm_visibility_snapshot
            self.arm_match_applied = before_arm_match_applied
            self.arm_match_segment_translations = before_arm_match_segment_translations
            self.arm_stretch_snapshot = before_arm_stretch_snapshot
            self.twist_root = before_twist_root
            self.arm_twist_segments = before_arm_twist_segments
            self.arm_twist_states = before_arm_twist_states
            self.leg_twist_root = before_leg_twist_root
            self.leg_twist_segments = before_leg_twist_segments
            self.leg_twist_states = before_leg_twist_states
            self.arm_volume_snapshot = before_arm_volume_snapshot
            raise
        finally:
            self.in_transaction = False

    def create_body_joint(self, spec):
        self.body.append(
            BodyJointState(
                spec.path,
                spec.name,
                spec.parent_path,
                spec.side,
                spec.world_position,
                spec.label,
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
            )
        )
        return spec.path

    def capture_body_skeleton(self, root_name):
        root = f"|{root_name}"
        joints = tuple(self.body)
        should_corrupt = self.faulty_capture or (
            self.faulty_after_orientation and self.orientation_write_count > 0
        )
        if should_corrupt and self.in_transaction and joints:
            joints = (
                replace(joints[0], world_position=(99.0, 0.0, 0.0)),
            ) + joints[1:]
        if self.faulty_arm_match and self.arm_match_applied and self.in_transaction:
            joints = tuple(
                replace(joint, world_position=(99.0, 0.0, 0.0))
                if joint.name == "Wrist_R"
                else joint
                for joint in joints
            )
        if self.faulty_leg_match and self.leg_match_applied and self.in_transaction:
            joints = tuple(
                replace(joint, world_position=(99.0, 0.0, 0.0))
                if joint.name == "Ankle_R"
                else joint
                for joint in joints
            )
        return BodySkeletonSnapshot(root, joints, self.provenance)

    def set_body_joint_world_axes(self, change):
        self.orientation_write_count += 1
        self.body = [
            replace(state, world_axes=change.desired_world_axes)
            if state.path == change.joint
            else state
            for state in self.body
        ]

    def set_body_joint_world_position(self, joint, position):
        self.body = [
            replace(state, world_position=position)
            if state.path == joint
            else state
            for state in self.body
        ]

    def write_body_provenance(self, root, provenance):
        del root
        count = provenance.body_joint_count
        if self.faulty_provenance:
            count += 1
        self.provenance = BodySkeletonProvenanceState(
            provenance.owner,
            provenance.artifact_kind,
            provenance.schema_version,
            provenance.source_container,
            count,
        )

    def capture_body_rebuild_state(self, root_name):
        root = f"|{root_name}"
        return BodyRebuildSceneState(
            root,
            tuple(state.path for state in self.body) + self.extra_dag_paths,
            self.external_dependencies,
        )

    def delete_owned_body(self, root):
        del root
        self.delete_count += 1
        self.body = []
        self.provenance = None

    def create_body_control_root(self, name):
        if name == "AdvPy_LegFKControls":
            self.leg_control_root = f"|{name}"
            return self.leg_control_root
        self.control_root = f"|{name}"
        return self.control_root

    def create_body_arm_fk_control(self, spec):
        self.arm_fk_states.append(
            BodyArmFkControlState(
                offset_path=spec.offset_path,
                offset_parent_path=spec.parent_path,
                control_path=spec.control_path,
                control_parent_path=spec.offset_path,
                constraint_name=spec.constraint_name,
                source_control=spec.control_path,
                driven_joint=spec.driven_joint,
                world_position=spec.world_position,
                world_axes=spec.world_axes,
                local_translation=(0.0, 0.0, 0.0),
                local_rotation=(0.0, 0.0, 0.0),
                shape_type="nurbsCurve",
            )
        )

    def capture_body_arm_fk_controls(self, plan):
        del plan
        states = tuple(self.arm_fk_states)
        if self.faulty_arm_fk and states:
            states = (replace(states[0], shape_type=None),) + states[1:]
        return BodyArmFkControlSnapshot(self.control_root, states)

    def create_body_arm_mechanism_root(self, name):
        self.mechanism_root = f"|{name}"
        return self.mechanism_root

    def create_body_arm_mechanism_joint(self, spec):
        self.arm_mechanism_states.append(
            BodyArmMechanismJointState(
                path=spec.path,
                parent_path=spec.parent_path,
                side=spec.side,
                source_joint=spec.source_joint,
                world_position=spec.world_position,
                world_axes=spec.world_axes,
                rotation=(0.0, 0.0, 0.0),
            )
        )
        return spec.path

    def capture_body_arm_mechanisms(self, plan):
        del plan
        states = tuple(self.arm_mechanism_states)
        if self.faulty_arm_mechanisms and states:
            states = (replace(states[0], source_joint=None),) + states[1:]
        return BodyArmMechanismSnapshot(self.mechanism_root, states)

    def create_body_leg_mechanism_root(self, name):
        self.leg_mechanism_root = f"|{name}"
        return self.leg_mechanism_root

    def create_body_leg_mechanism_joint(self, spec):
        self.leg_mechanism_states.append(BodyLegMechanismJointState(
            spec.path,
            spec.parent_path,
            spec.side,
            spec.source_joint,
            spec.world_position,
            spec.world_axes,
            (0.0, 0.0, 0.0),
        ))
        return spec.path

    def capture_body_leg_mechanisms(self, plan):
        del plan
        states = tuple(self.leg_mechanism_states)
        if self.faulty_leg_mechanisms and states:
            states = (replace(states[0], source_joint=None),) + states[1:]
        return BodyLegMechanismSnapshot(self.leg_mechanism_root, states)

    def create_body_leg_fk_control(self, spec):
        self.leg_fk_states.append(BodyLegFkControlState(
            offset_path=spec.offset_path,
            offset_parent_path=spec.parent_path,
            control_path=spec.control_path,
            control_parent_path=spec.offset_path,
            constraint_name=spec.constraint_name,
            source_control=spec.control_path,
            driven_joint=spec.driven_joint,
            world_position=spec.world_position,
            world_axes=spec.world_axes,
            local_translation=(0.0, 0.0, 0.0),
            local_rotation=(0.0, 0.0, 0.0),
            shape_type="nurbsCurve",
        ))

    def capture_body_leg_fk_controls(self, plan):
        del plan
        states = tuple(self.leg_fk_states)
        if self.faulty_leg_fk and states:
            states = (replace(states[0], shape_type=None),) + states[1:]
        return BodyLegFkControlSnapshot(self.leg_control_root, states)

    def create_body_leg_ik_root(self, name):
        self.leg_ik_root = f"|{name}"
        return self.leg_ik_root

    def create_body_leg_ik(self, spec):
        self.leg_ik_states.append(BodyLegIkState(
            spec.side,
            spec.ankle_control_path,
            spec.ankle_offset_path,
            spec.pole_control_path,
            spec.pole_offset_path,
            spec.handle_name,
            spec.pole_constraint_name,
            spec.ankle_control_path,
            spec.chain[:2],
            spec.pole_control_path,
            spec.ankle_position,
            spec.pole_position,
            "nurbsCurve",
            "nurbsCurve",
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            spec.ankle_constraint_name,
            spec.ankle_control_path,
            spec.chain[2],
        ))

    def capture_body_leg_ik(self, plan):
        del plan
        states = tuple(self.leg_ik_states)
        if self.faulty_leg_ik and states:
            states = (replace(states[0], pole_source=None),) + states[1:]
        return BodyLegIkSnapshot(self.leg_ik_root, states)

    def create_body_leg_blend(self, plan):
        sides = []
        for side in plan.sides:
            plug = f"{plan.settings_path}.{side.attribute}"
            joints = tuple(BodyLegBlendJointState(
                joint.constraint_name,
                joint.body_joint,
                (joint.fk_driver, joint.ik_driver),
                f"{side.reverse_name}.outputX",
                plug,
                joint.translation_constraint_name,
                (
                    (joint.fk_driver, joint.ik_driver)
                    if joint.translation_constraint_name
                    else ()
                ),
                (
                    f"{side.reverse_name}.outputX"
                    if joint.translation_constraint_name
                    else None
                ),
                plug if joint.translation_constraint_name else None,
                joint.body_joint if joint.translation_constraint_name else None,
            ) for joint in side.joints)
            sides.append(BodyLegBlendSideState(
                side.side,
                plug,
                0.0,
                side.reverse_name,
                plug,
                joints,
            ))
        self.leg_blend_snapshot = BodyLegBlendSnapshot(
            plan.settings_path,
            tuple(sides),
        )

    def capture_body_leg_blend(self, plan):
        del plan
        if self.faulty_leg_blend and self.leg_blend_snapshot:
            side = self.leg_blend_snapshot.sides[0]
            joints = list(side.joints)
            index = next(
                index for index, joint in enumerate(joints)
                if joint.translation_constraint_name
            )
            joints[index] = replace(
                joints[index],
                translation_ik_weight_source=None,
            )
            return replace(
                self.leg_blend_snapshot,
                sides=(replace(side, joints=tuple(joints)),)
                + self.leg_blend_snapshot.sides[1:],
            )
        return self.leg_blend_snapshot

    def capture_body_leg_visibility_input(self, plan):
        sources = tuple(
            plug for side in plan.sides
            for plug in (side.reverse_output_plug, side.blend_plug)
        )
        targets = tuple(
            f"{path}.visibility" for side in plan.sides
            for path in (side.fk_offset_path, *side.ik_offset_paths)
        )
        if self.blocked_leg_visibility:
            targets = targets[1:]
        return BodyLegVisibilityInputState(sources, targets)

    def create_body_leg_visibility(self, plan):
        self.leg_visibility_snapshot = BodyLegVisibilitySnapshot(tuple(
            BodyLegVisibilitySideState(
                side.side,
                side.reverse_output_plug,
                (side.blend_plug, side.blend_plug),
            )
            for side in plan.sides
        ))

    def capture_body_leg_visibility(self, plan):
        del plan
        if self.faulty_leg_visibility and self.leg_visibility_snapshot:
            first = replace(
                self.leg_visibility_snapshot.sides[0],
                fk_visibility_source=None,
            )
            return replace(
                self.leg_visibility_snapshot,
                sides=(first,) + self.leg_visibility_snapshot.sides[1:],
            )
        return self.leg_visibility_snapshot

    def create_body_leg_stretch(self, plan):
        states = []
        for spec in plan.sides:
            plug = f"{plan.settings_path}.{spec.attribute}"
            states.append(BodyLegStretchSideState(
                spec.side,
                plug,
                1.0,
                spec.start_path,
                spec.start_position,
                spec.distance_name,
                (
                    f"{spec.start_path}.worldMatrix[0]",
                    f"{spec.target_control_path}.worldMatrix[0]",
                ),
                spec.ratio_name,
                f"{spec.distance_name}.distance",
                spec.rest_scale_name,
                spec.rest_length,
                f"{plan.settings_path}.{plan.global_scale_attribute}",
                1,
                f"{spec.rest_scale_name}.outputX",
                2,
                spec.clamp_name,
                f"{spec.ratio_name}.outputX",
                1.0,
                1000000.0,
                spec.blend_name,
                f"{spec.clamp_name}.outputR",
                plug,
                1.0,
                spec.segment_name,
                spec.base_translations,
                (
                    f"{spec.blend_name}.outputR",
                    f"{spec.blend_name}.outputR",
                ),
                (
                    f"{spec.segment_name}.outputX",
                    f"{spec.segment_name}.outputY",
                ),
                1,
            ))
        self.leg_stretch_snapshot = BodyLegStretchSnapshot(
            plan.settings_path,
            f"{plan.settings_path}.{plan.global_scale_attribute}",
            plan.global_scale_default,
            tuple(states),
        )

    def capture_body_leg_stretch(self, plan):
        del plan
        if self.faulty_leg_stretch and self.leg_stretch_snapshot:
            first = replace(
                self.leg_stretch_snapshot.sides[0],
                clamp_input_source=None,
            )
            return replace(
                self.leg_stretch_snapshot,
                sides=(first,) + self.leg_stretch_snapshot.sides[1:],
            )
        return self.leg_stretch_snapshot

    def capture_body_leg_foot_input(self, plan):
        collisions = tuple(
            name
            for side in plan.sides
            for name in (
                *(pivot.name for pivot in side.pivots),
                *(pivot.multiplier_name for pivot in side.pivots if pivot.multiplier_name),
                side.toe_constraint_name,
                side.toe_offset_name,
                side.toe_control_name,
                *(node.name for node in side.roll.nodes),
            )
            if self.find_name_collisions(name)
        )
        existing = (
            (f"{plan.sides[0].ankle_control_path}.heelRoll",)
            if self.blocked_leg_foot else ()
        )
        return BodyLegFootInputState(
            name_collisions=collisions,
            existing_attribute_plugs=existing,
        )

    def create_body_leg_foot_side(self, spec):
        pivots = tuple(BodyLegFootPivotState(
            pivot.role,
            pivot.path,
            pivot.parent_path,
            pivot.world_position,
            pivot.source_plug,
            (
                f"{spec.ankle_control_path}.{pivot.attribute}"
                if pivot.multiplier_name else None
            ),
            pivot.multiplier if pivot.multiplier_name else None,
        ) for pivot in spec.pivots)
        state = BodyLegFootSideState(
            spec.side,
            tuple(
                (f"{spec.ankle_control_path}.{attribute}", 0.0)
                for attribute in spec.attributes
            ),
            pivots,
            spec.final_handle_parent_path,
            spec.ankle_constraint_name,
            spec.ankle_orientation_source_path,
            spec.ankle_driver_path,
            spec.toe_constraint_name,
            spec.toe_orientation_source_path,
            spec.toe_driver_path,
            spec.toe_offset_path,
            next(
                pivot.path for pivot in spec.pivots
                if pivot.role.value == "toe"
            ),
            spec.toe_control_path,
            spec.toe_offset_path,
            spec.toe_control_position,
            spec.toe_control_axes,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            "nurbsCurve",
            BodyLegFootRollState(
                spec.roll.master_plug,
                0.0,
                tuple(
                    BodyLegFootRollNodeState(
                        node.name,
                        node.node_type,
                        tuple(
                            (target, source)
                            for source, target in node.input_connections
                        ),
                        tuple(
                            (plug, value)
                            for plug, value in node.numeric_values
                        ),
                    )
                    for node in spec.roll.nodes
                ),
            ),
        )
        sides = self.leg_foot_snapshot.sides if self.leg_foot_snapshot else ()
        self.leg_foot_snapshot = BodyLegFootSnapshot((*sides, state))
        self.leg_ik_states = [
            replace(
                value,
                handle_parent_path=spec.final_handle_parent_path,
                ankle_source=spec.ankle_orientation_source_path,
            )
            if value.side is spec.side else value
            for value in self.leg_ik_states
        ]

    def capture_body_leg_foot(self, plan):
        del plan
        if self.faulty_leg_foot and self.leg_foot_snapshot:
            side = self.leg_foot_snapshot.sides[0]
            pivot = replace(side.pivots[0], rotation_source=None)
            side = replace(side, pivots=(pivot,) + side.pivots[1:])
            return replace(
                self.leg_foot_snapshot,
                sides=(side,) + self.leg_foot_snapshot.sides[1:],
            )
        return self.leg_foot_snapshot

    def create_body_arm_ik_root(self, name):
        self.arm_ik_root = f"|{name}"
        return self.arm_ik_root

    def create_body_arm_ik(self, spec):
        self.arm_ik_states.append(BodyArmIkState(
            spec.side, spec.wrist_control_path, spec.wrist_offset_path,
            spec.pole_control_path, spec.pole_offset_path, spec.handle_name,
            spec.pole_constraint_name, spec.wrist_control_path, spec.chain[:2],
            spec.pole_control_path, spec.wrist_position, spec.pole_position,
            "nurbsCurve", "nurbsCurve", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
            spec.wrist_constraint_name, spec.wrist_control_path, spec.chain[2],
        ))

    def capture_body_arm_ik(self, plan):
        del plan
        states = tuple(self.arm_ik_states)
        if self.faulty_arm_ik and states:
            states = (replace(states[0], pole_source=None),) + states[1:]
        return BodyArmIkSnapshot(self.arm_ik_root, states)

    def create_body_arm_blend(self, plan):
        sides = []
        for side in plan.sides:
            plug = f"{plan.settings_path}.{side.attribute}"
            joints = tuple(BodyArmBlendJointState(
                j.constraint_name,
                j.body_joint,
                (j.fk_driver, j.ik_driver),
                f"{side.reverse_name}.outputX",
                plug,
                j.translation_constraint_name,
                (j.fk_driver, j.ik_driver) if j.translation_constraint_name else (),
                f"{side.reverse_name}.outputX" if j.translation_constraint_name else None,
                plug if j.translation_constraint_name else None,
                j.body_joint if j.translation_constraint_name else None,
            ) for j in side.joints)
            sides.append(BodyArmBlendSideState(side.side, plug, 0.0, side.reverse_name, plug, joints))
        self.arm_blend_snapshot = BodyArmBlendSnapshot(plan.settings_path, tuple(sides))

    def capture_body_arm_blend(self, plan):
        del plan
        if self.faulty_arm_blend and self.arm_blend_snapshot:
            first = replace(self.arm_blend_snapshot.sides[0], reverse_input_source=None)
            return replace(self.arm_blend_snapshot, sides=(first,) + self.arm_blend_snapshot.sides[1:])
        if self.faulty_arm_translation and self.arm_blend_snapshot:
            side = self.arm_blend_snapshot.sides[0]
            joints = list(side.joints)
            index = next(index for index, joint in enumerate(joints) if joint.translation_constraint_name)
            joints[index] = replace(joints[index], translation_ik_weight_source=None)
            return replace(self.arm_blend_snapshot, sides=(replace(side, joints=tuple(joints)),) + self.arm_blend_snapshot.sides[1:])
        return self.arm_blend_snapshot

    def create_body_arm_visibility(self, plan):
        self.arm_visibility_snapshot = BodyArmVisibilitySnapshot(tuple(
            BodyArmVisibilitySideState(
                side.side,
                side.reverse_output_plug,
                (side.blend_plug, side.blend_plug),
            )
            for side in plan.sides
        ))

    def capture_body_arm_visibility(self, plan):
        del plan
        if self.faulty_arm_visibility and self.arm_visibility_snapshot:
            first = replace(self.arm_visibility_snapshot.sides[0], fk_visibility_source=None)
            return replace(self.arm_visibility_snapshot, sides=(first,) + self.arm_visibility_snapshot.sides[1:])
        return self.arm_visibility_snapshot

    def capture_body_arm_fk_to_ik_state(self, plan):
        side = next(value for value in self.arm_blend_snapshot.sides if value.side is plan.side)
        return BodyArmFkToIkSceneState(plan.required_paths, plan.required_writable_plugs, side.attribute_value)

    def apply_body_arm_fk_to_ik(self, plan):
        self.arm_match_applied = True
        sides = tuple(
            replace(side, attribute_value=1.0) if side.side is plan.side else side
            for side in self.arm_blend_snapshot.sides
        )
        self.arm_blend_snapshot = replace(self.arm_blend_snapshot, sides=sides)

    def capture_body_leg_fk_to_ik_state(self, plan):
        side = next(
            value for value in self.leg_blend_snapshot.sides
            if value.side is plan.side
        )
        return BodyLegFkToIkSceneState(
            plan.required_paths,
            plan.required_writable_plugs,
            side.attribute_value,
            plan.body_joint_positions,
            plan.ankle_axes,
            plan.toe_body_axes,
            next(
                value.attribute_values
                for value in self.leg_foot_snapshot.sides
                if value.side is plan.side
            ),
        )

    def apply_body_leg_fk_to_ik(self, plan):
        self.leg_match_applied = True
        foot_sides = tuple(
            replace(
                side,
                attribute_values=tuple(
                    (plug, 0.0)
                    for plug in plan.foot_attribute_plugs
                ),
            )
            if side.side is plan.side else side
            for side in self.leg_foot_snapshot.sides
        )
        self.leg_foot_snapshot = replace(
            self.leg_foot_snapshot, sides=foot_sides
        )
        sides = tuple(
            replace(side, attribute_value=1.0)
            if side.side is plan.side else side
            for side in self.leg_blend_snapshot.sides
        )
        self.leg_blend_snapshot = replace(
            self.leg_blend_snapshot, sides=sides
        )

    def capture_body_leg_ik_to_fk_state(self, plan):
        side = next(
            value for value in self.leg_blend_snapshot.sides
            if value.side is plan.side
        )
        return BodyLegIkToFkSceneState(
            plan.required_paths,
            plan.required_writable_plugs,
            side.attribute_value,
            plan.body_joint_positions,
            plan.body_joint_axes,
            self.leg_match_segment_translations
            or plan.fk_segment_translations,
        )

    def apply_body_leg_ik_to_fk(self, plan):
        self.leg_match_applied = True
        self.leg_match_segment_translations = plan.fk_segment_translations
        sides = tuple(
            replace(side, attribute_value=0.0)
            if side.side is plan.side else side
            for side in self.leg_blend_snapshot.sides
        )
        self.leg_blend_snapshot = replace(
            self.leg_blend_snapshot, sides=sides
        )

    def capture_body_arm_ik_to_fk_state(self, plan):
        side = next(value for value in self.arm_blend_snapshot.sides if value.side is plan.side)
        return BodyArmIkToFkSceneState(
            plan.required_paths,
            plan.required_writable_plugs,
            side.attribute_value,
            plan.body_joint_positions,
            plan.body_joint_axes,
            self.arm_match_segment_translations or plan.fk_segment_translations,
        )

    def apply_body_arm_ik_to_fk(self, plan):
        self.arm_match_applied = True
        self.arm_match_segment_translations = plan.fk_segment_translations
        sides = tuple(
            replace(side, attribute_value=0.0) if side.side is plan.side else side
            for side in self.arm_blend_snapshot.sides
        )
        self.arm_blend_snapshot = replace(self.arm_blend_snapshot, sides=sides)

    def create_body_arm_stretch(self, plan):
        states = []
        for spec in plan.sides:
            plug = f"{plan.settings_path}.{spec.attribute}"
            states.append(BodyArmStretchSideState(
                spec.side,
                plug,
                1.0,
                spec.start_path,
                spec.start_position,
                spec.distance_name,
                (f"{spec.start_path}.worldMatrix[0]", f"{spec.wrist_control_path}.worldMatrix[0]"),
                spec.ratio_name,
                f"{spec.distance_name}.distance",
                spec.rest_scale_name,
                spec.rest_length,
                f"{plan.settings_path}.{plan.global_scale_attribute}",
                1,
                f"{spec.rest_scale_name}.outputX",
                2,
                spec.clamp_name,
                f"{spec.ratio_name}.outputX",
                1.0,
                1000000.0,
                spec.blend_name,
                f"{spec.clamp_name}.outputR",
                plug,
                1.0,
                spec.segment_name,
                spec.base_translations,
                (f"{spec.blend_name}.outputR", f"{spec.blend_name}.outputR"),
                (f"{spec.segment_name}.outputX", f"{spec.segment_name}.outputY"),
                1,
            ))
        self.arm_stretch_snapshot = BodyArmStretchSnapshot(
            plan.settings_path,
            f"{plan.settings_path}.{plan.global_scale_attribute}",
            plan.global_scale_default,
            tuple(states),
        )

    def capture_body_arm_stretch(self, plan):
        del plan
        if self.faulty_arm_stretch and self.arm_stretch_snapshot:
            first = replace(self.arm_stretch_snapshot.sides[0], clamp_input_source=None)
            return replace(self.arm_stretch_snapshot, sides=(first,) + self.arm_stretch_snapshot.sides[1:])
        return self.arm_stretch_snapshot

    def create_body_arm_twist_root(self, name):
        self.twist_root = f"|{name}"
        return self.twist_root

    def prepare_body_arm_twist_runtime(self):
        if self.faulty_arm_twist_runtime:
            raise FitSkeletonValidationError("Arm twist 需要 Maya 自带 quatNodes 插件")

    def create_body_arm_twist_segment(self, spec):
        self.arm_twist_segments.append(BodyArmTwistSegmentState(
            side=spec.side,
            segment=spec.segment,
            path=spec.path,
            parent_path=spec.parent_path,
            constraint_name=spec.constraint_name,
            targets=(spec.start_joint,),
            driven_path=spec.path,
            compose_name=spec.compose_name,
            rotate_source=f"{spec.end_joint}.rotate",
            rotate_order_source=f"{spec.end_joint}.rotateOrder",
            decompose_name=spec.decompose_name,
            decompose_source=f"{spec.compose_name}.outputMatrix",
            quaternion_name=spec.quaternion_name,
            quaternion_axis_source=(
                f"{spec.decompose_name}.outputQuat{spec.axis}"
            ),
            quaternion_w_source=f"{spec.decompose_name}.outputQuatW",
            axis=spec.axis,
        ))

    def create_body_arm_twist_joint(self, spec):
        self.arm_twist_states.append(BodyArmTwistJointState(
            side=spec.side,
            segment=spec.segment,
            path=spec.path,
            parent_path=spec.parent_path,
            world_position=spec.world_position,
            constraint_name=spec.constraint_name,
            targets=(spec.start_joint, spec.end_joint),
            weights=(1.0 - spec.fraction, spec.fraction),
            driven_joint=spec.path,
            multiplier_name=spec.multiplier_name,
            twist_source=f"{spec.quaternion_name}.outputRotate{spec.axis}",
            multiplier_scale=spec.fraction,
            rotate_axis_source=f"{spec.multiplier_name}.output",
            orthogonal_rotations=(0.0, 0.0),
            axis=spec.axis,
        ))

    def capture_body_arm_twist(self, plan):
        del plan
        states = tuple(self.arm_twist_states)
        if self.faulty_arm_twist and states:
            states = (
                replace(states[0], orthogonal_rotations=(1.0, 0.0)),
            ) + states[1:]
        return BodyArmTwistSnapshot(
            self.twist_root,
            tuple(self.arm_twist_segments),
            states,
        )

    def create_body_leg_twist_root(self, name):
        self.leg_twist_root = f"|{name}"
        return self.leg_twist_root

    def prepare_body_leg_twist_runtime(self):
        if self.faulty_leg_twist_runtime:
            raise FitSkeletonValidationError(
                "Leg twist 需要 Maya 自带 quatNodes 插件"
            )

    def create_body_leg_twist_segment(self, spec):
        self.leg_twist_segments.append(BodyLegTwistSegmentState(
            side=spec.side,
            segment=spec.segment,
            path=spec.path,
            parent_path=spec.parent_path,
            constraint_name=spec.constraint_name,
            targets=(spec.start_joint,),
            driven_path=spec.path,
            compose_name=spec.compose_name,
            rotate_source=f"{spec.end_joint}.rotate",
            rotate_order_source=f"{spec.end_joint}.rotateOrder",
            decompose_name=spec.decompose_name,
            decompose_source=f"{spec.compose_name}.outputMatrix",
            quaternion_name=spec.quaternion_name,
            quaternion_axis_source=(
                f"{spec.decompose_name}.outputQuat{spec.axis}"
            ),
            quaternion_w_source=f"{spec.decompose_name}.outputQuatW",
            axis=spec.axis,
        ))

    def create_body_leg_twist_joint(self, spec):
        self.leg_twist_states.append(BodyLegTwistJointState(
            side=spec.side,
            segment=spec.segment,
            path=spec.path,
            parent_path=spec.parent_path,
            world_position=spec.world_position,
            constraint_name=spec.constraint_name,
            targets=(spec.start_joint, spec.end_joint),
            weights=(1.0 - spec.fraction, spec.fraction),
            driven_joint=spec.path,
            multiplier_name=spec.multiplier_name,
            twist_source=f"{spec.quaternion_name}.outputRotate{spec.axis}",
            multiplier_scale=spec.fraction,
            rotate_axis_source=f"{spec.multiplier_name}.output",
            orthogonal_rotations=(0.0, 0.0),
            axis=spec.axis,
        ))

    def capture_body_leg_twist(self, plan):
        del plan
        states = tuple(self.leg_twist_states)
        if self.faulty_leg_twist and states:
            states = (
                replace(states[0], orthogonal_rotations=(1.0, 0.0)),
            ) + states[1:]
        return BodyLegTwistSnapshot(
            self.leg_twist_root,
            tuple(self.leg_twist_segments),
            states,
        )

    def create_body_arm_volume(self, plan):
        states = []
        for spec in plan.sides:
            plug = f"{plan.settings_path}.{spec.attribute}"
            states.append(BodyArmVolumeSideState(
                spec.side,
                plug,
                1.0,
                spec.mode_blend_name,
                spec.stretch_ratio_source,
                f"{plan.settings_path}.{spec.mode_attribute}",
                1.0,
                spec.power_name,
                f"{spec.mode_blend_name}.outputR",
                spec.exponent,
                3,
                spec.blend_name,
                f"{spec.power_name}.outputX",
                plug,
                1.0,
                tuple(
                    (
                        path,
                        f"{spec.blend_name}.outputR",
                        f"{spec.blend_name}.outputR",
                    )
                    for path in spec.helper_joints
                ),
            ))
        self.arm_volume_snapshot = BodyArmVolumeSnapshot(
            plan.settings_path,
            tuple(states),
        )

    def capture_body_arm_volume(self, plan):
        del plan
        if self.faulty_arm_volume and self.arm_volume_snapshot:
            first = replace(
                self.arm_volume_snapshot.sides[0],
                power_operation=1,
            )
            return replace(
                self.arm_volume_snapshot,
                sides=(first,) + self.arm_volume_snapshot.sides[1:],
            )
        return self.arm_volume_snapshot


def build_basic_leg_without_foot(host):
    """Compose the pre-v0.60 Leg stages for the standalone Foot extension tests."""
    BuildBodyLegMechanisms(host).apply()
    BuildBodyLegFkMechanismControls(host).apply()
    BuildBodyLegBlend(host).apply()
    BuildBodyLegIkControls(host).apply()
    BuildBodyLegVisibility(host).apply()


class BodySkeletonTests(unittest.TestCase):
    def test_previews_and_builds_thirty_joints_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        use_case = BuildBodySkeleton(host)

        preview = use_case.plan()

        self.assertTrue(preview.ready)
        self.assertEqual(len(preview.specs), 30)
        self.assertFalse(host.body)
        result = use_case.apply()
        self.assertEqual(len(result.snapshot.joints), 30)
        self.assertEqual(host.transaction_count, 1)
        self.assertIs(host.fit_snapshot, result.plan.symmetry.source)

    def test_name_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        host.collisions["Hip_L"] = ("|Existing|Hip_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 0)
        self.assertFalse(host.body)

    def test_post_verification_failure_rolls_back_all_body_joints(self):
        host = FakeBodySkeletonHost(faulty_capture=True)

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.body)

    def test_orients_right_and_left_behavior_frames_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        BuildBodySkeleton(host).apply()
        use_case = OrientBodySkeleton(host)

        preview = use_case.plan()

        self.assertEqual(len(preview.changes), 13)
        before_positions = {
            state.path: state.world_position for state in preview.before.joints
        }
        result = use_case.apply()
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(
            {state.path: state.world_position for state in result.verified.joints},
            before_positions,
        )
        right = next(
            state for state in result.verified.joints if state.name == "Scapula_R"
        )
        left = next(
            state for state in result.verified.joints if state.name == "Scapula_L"
        )
        self.assertEqual(right.world_axes[0], (0.8, 0.6, 0.0))
        self.assertEqual(left.world_axes[0], (-0.8, 0.6, 0.0))
        self.assertFalse(use_case.plan().changes)

    def test_locked_body_joint_orient_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildBodySkeleton(host).apply()
        host.body = [
            replace(state, writable_joint_orient_axes=frozenset({"x", "y"}))
            if state.name == "Scapula_L"
            else state
            for state in host.body
        ]

        with self.assertRaisesRegex(
            BodySkeletonValidationError,
            "jointOrient 不可完整写入",
        ):
            OrientBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)

    def test_body_orientation_postcheck_failure_rolls_back_axes(self):
        host = FakeBodySkeletonHost()
        BuildBodySkeleton(host).apply()
        before = tuple(host.body)
        host.faulty_capture = True

        with self.assertRaisesRegex(RuntimeError, "朝向后复检失败"):
            OrientBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(tuple(host.body), before)

    def test_atomic_body_build_creates_and_orients_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        use_case = BuildOrientedBodySkeleton(host)

        preview = use_case.plan()

        self.assertTrue(preview.ready)
        self.assertFalse(host.body)
        result = use_case.apply()
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(len(result.snapshot.joints), 30)
        self.assertEqual(len(result.orientation_changes), 13)
        self.assertFalse(OrientBodySkeleton(host).plan().changes)
        audit = InspectBodySkeletonProvenance(host).execute()
        self.assertTrue(audit.owned)
        self.assertEqual(audit.snapshot.provenance, result.snapshot.provenance)

    def test_atomic_body_build_collision_stops_before_transaction(self):
        host = FakeBodySkeletonHost()
        host.collisions["Hip_L"] = ("|Existing|Hip_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildOrientedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 0)
        self.assertFalse(host.body)

    def test_atomic_orientation_failure_removes_created_body(self):
        host = FakeBodySkeletonHost(faulty_after_orientation=True)

        with self.assertRaisesRegex(RuntimeError, "朝向后复检失败"):
            BuildOrientedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.body)

    def test_atomic_provenance_failure_removes_created_body(self):
        host = FakeBodySkeletonHost(faulty_provenance=True)

        with self.assertRaisesRegex(RuntimeError, "关节数量不一致"):
            BuildOrientedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.body)
        self.assertIsNone(host.provenance)

    def test_rebuild_safety_accepts_an_unmodified_owned_body(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        before_transactions = host.transaction_count

        audit = InspectBodyRebuildSafety(host).execute()

        self.assertTrue(audit.safe_to_replace)
        self.assertFalse(audit.issues)
        self.assertEqual(host.transaction_count, before_transactions)

    def test_rebuild_safety_reports_dag_and_external_dependencies(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.extra_dag_paths = ("|Root_M|UserAttachment",)
        host.external_dependencies = (
            BodyExternalDependency(
                BodyExternalDependencyKind.CONNECTION,
                "|Root_M.message",
                "ExternalConsumer.input",
            ),
        )

        audit = InspectBodyRebuildSafety(host).execute()
        codes = {issue.code for issue in audit.issues}

        self.assertFalse(audit.safe_to_replace)
        self.assertIn("unexpected_dag_descendant", codes)
        self.assertIn("external_connection", codes)

    def test_replaces_owned_body_and_ignores_only_its_name_collisions(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        use_case = ReplaceOwnedBodySkeleton(host)

        preview = use_case.plan()

        self.assertTrue(preview.ready)
        self.assertEqual(len(preview.owned_name_collisions), 30)
        self.assertFalse(preview.build.build.name_collisions)
        result = use_case.apply()
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(host.delete_count, 1)
        self.assertEqual(len(result.build.snapshot.joints), 30)
        self.assertTrue(InspectBodyRebuildSafety(host).execute().safe_to_replace)

    def test_rebuild_dependency_blocks_before_replacement_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.external_dependencies = (
            BodyExternalDependency(
                BodyExternalDependencyKind.CONNECTION,
                "|Root_M.message",
                "ExternalConsumer.input",
            ),
        )

        with self.assertRaisesRegex(FitSkeletonValidationError, "外部依赖"):
            ReplaceOwnedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(host.delete_count, 0)
        self.assertEqual(len(host.body), 30)

    def test_rebuild_failure_restores_previous_owned_body(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        previous_body = tuple(host.body)
        previous_provenance = host.provenance
        host.faulty_provenance = True

        with self.assertRaisesRegex(RuntimeError, "关节数量不一致"):
            ReplaceOwnedBodySkeleton(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(tuple(host.body), previous_body)
        self.assertEqual(host.provenance, previous_provenance)

    def test_builds_bilateral_arm_fk_controls_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        use_case = BuildBodyArmFkControls(host)

        preview = use_case.plan(control_radius=2.0)

        self.assertTrue(preview.ready)
        self.assertEqual(len(preview.controls.controls), 6)
        result = use_case.apply(control_radius=2.0)
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(len(result.snapshot.controls), 6)
        self.assertEqual(result.body, body)
        elbow_right = next(
            state
            for state in result.snapshot.controls
            if state.control_path.endswith("AdvPy_ElbowFK_R")
        )
        self.assertTrue(
            elbow_right.offset_parent_path.endswith("AdvPy_ShoulderFK_R")
        )

    def test_arm_fk_name_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_ElbowFK_L"] = ("|User|AdvPy_ElbowFK_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyArmFkControls(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.control_root)

    def test_arm_fk_postcheck_failure_rolls_back_controls(self):
        host = FakeBodySkeletonHost(faulty_arm_fk=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyArmFkControls(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.control_root)
        self.assertFalse(host.arm_fk_states)

    def test_builds_bilateral_fk_ik_arm_mechanism_chains_atomically(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot

        preview = BuildBodyArmMechanisms(host).plan()
        result = BuildBodyArmMechanisms(host).apply()

        self.assertTrue(preview.ready)
        self.assertEqual(len(preview.mechanisms.joints), 12)
        self.assertEqual(len(result.snapshot.joints), 12)
        self.assertEqual(result.body, body)
        self.assertEqual(host.transaction_count, 2)
        wrist_ik_left = next(
            state
            for state in result.snapshot.joints
            if state.path.endswith("AdvPy_WristIKDriver_L")
        )
        self.assertTrue(wrist_ik_left.parent_path.endswith("AdvPy_ElbowIKDriver_L"))

    def test_arm_mechanism_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_ElbowFKDriver_R"] = ("|User|AdvPy_ElbowFKDriver_R",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyArmMechanisms(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.mechanism_root)

    def test_arm_mechanism_postcheck_failure_rolls_back_all_drivers(self):
        host = FakeBodySkeletonHost(faulty_arm_mechanisms=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyArmMechanisms(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.mechanism_root)
        self.assertFalse(host.arm_mechanism_states)

    def test_builds_bilateral_fk_ik_leg_mechanism_chains_atomically(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot

        result = BuildBodyLegMechanisms(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(result.body, body)
        self.assertEqual(result.snapshot.root_path, "|AdvPy_LegMechanisms")
        self.assertEqual(len(result.snapshot.joints), 20)
        self.assertEqual(
            {state.side for state in result.snapshot.joints},
            {FitBuildSide.RIGHT, FitBuildSide.LEFT},
        )
        self.assertEqual(
            {spec.role for spec in result.plan.mechanisms.joints},
            {BodyLegMechanismRole.FK, BodyLegMechanismRole.IK},
        )
        toes_end_ik = next(
            state for state in result.snapshot.joints
            if state.path.endswith("AdvPy_ToesEndIKDriver_R")
        )
        self.assertTrue(
            toes_end_ik.parent_path.endswith("AdvPy_ToesIKDriver_R")
        )

    def test_leg_mechanism_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_HipFKDriver_R"] = ("|Existing|AdvPy_HipFKDriver_R",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名节点"):
            BuildBodyLegMechanisms(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)

    def test_leg_mechanism_postcheck_failure_rolls_back_all_drivers(self):
        host = FakeBodySkeletonHost(faulty_leg_mechanisms=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyLegMechanisms(host).apply()

        self.assertIsNone(host.leg_mechanism_root)
        self.assertFalse(host.leg_mechanism_states)

    def test_leg_fk_controls_drive_only_fk_mechanisms(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        mechanisms = BuildBodyLegMechanisms(host).apply().snapshot

        preview = BuildBodyLegFkMechanismControls(host).plan(control_radius=2.25)
        result = BuildBodyLegFkMechanismControls(host).apply(control_radius=2.25)

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 3)
        self.assertEqual(len(result.snapshot.controls), 8)
        body_paths = {state.path for state in body.joints}
        ik_paths = {
            state.path for state in mechanisms.joints if "IKDriver" in state.path
        }
        self.assertTrue(all(
            "FKDriver" in state.driven_joint
            and state.driven_joint not in body_paths | ik_paths
            for state in result.snapshot.controls
        ))
        knee_left = next(
            state for state in result.snapshot.controls
            if state.control_path.endswith("AdvPy_KneeFK_L")
        )
        self.assertTrue(knee_left.offset_parent_path.endswith("AdvPy_HipFK_L"))
        toes_right = next(
            state for state in result.snapshot.controls
            if state.control_path.endswith("AdvPy_ToesFK_R")
        )
        self.assertTrue(
            toes_right.offset_parent_path.endswith("AdvPy_AnkleFK_R")
            and toes_right.driven_joint.endswith("AdvPy_ToesFKDriver_R")
        )

    def test_leg_fk_control_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()
        host.collisions["AdvPy_KneeFK_L"] = ("|User|AdvPy_KneeFK_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegFkMechanismControls(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_control_root)

    def test_leg_fk_control_postcheck_failure_rolls_back_controls(self):
        host = FakeBodySkeletonHost(faulty_leg_fk=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyLegFkMechanismControls(host).apply()

        self.assertEqual(host.transaction_count, 3)
        self.assertIsNone(host.leg_control_root)
        self.assertFalse(host.leg_fk_states)

    def test_builds_bilateral_leg_rp_ik_controls(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()

        preview = BuildBodyLegIkControls(host).plan(control_radius=2.25)
        result = BuildBodyLegIkControls(host).apply(control_radius=2.25)

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 3)
        self.assertEqual(len(result.snapshot.limbs), 2)
        self.assertTrue(all(
            "IKDriver" in path
            for state in result.snapshot.limbs
            for path in state.joint_list
        ))
        self.assertTrue(all(
            state.ankle_source == state.ankle_control_path
            and state.ankle_driven_joint.endswith(
                f"AdvPy_AnkleIKDriver_{state.side.value}"
            )
            for state in result.snapshot.limbs
        ))

    def test_leg_ik_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()
        host.collisions["AdvPy_LegPV_L"] = ("|User|AdvPy_LegPV_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegIkControls(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_ik_root)

    def test_leg_ik_postcheck_failure_rolls_back(self):
        host = FakeBodySkeletonHost(faulty_leg_ik=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyLegIkControls(host).apply()

        self.assertEqual(host.transaction_count, 3)
        self.assertIsNone(host.leg_ik_root)
        self.assertFalse(host.leg_ik_states)

    def test_builds_independent_leg_fk_ik_body_blends(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()

        preview = BuildBodyLegBlend(host).plan()
        result = BuildBodyLegBlend(host).apply()

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 3)
        self.assertEqual(len(result.snapshot.sides), 2)
        self.assertEqual(
            {state.attribute_plug for state in result.snapshot.sides},
            {
                "|AdvPy_LegSettings.legIkFk_R",
                "|AdvPy_LegSettings.legIkFk_L",
            },
        )
        for side in result.snapshot.sides:
            self.assertEqual(len(side.joints), 4)
            translated = {
                joint.translation_driven_joint.rsplit("|", 1)[-1]
                for joint in side.joints
                if joint.translation_constraint_name
            }
            self.assertEqual(
                translated,
                {f"Knee_{side.side.value}", f"Ankle_{side.side.value}"},
            )
            toes = next(
                joint for joint in side.joints
                if joint.body_joint.endswith(f"Toes_{side.side.value}")
            )
            self.assertTrue(
                toes.targets[0].endswith(
                    f"AdvPy_ToesFKDriver_{side.side.value}"
                )
                and toes.targets[1].endswith(
                    f"AdvPy_ToesIKDriver_{side.side.value}"
                )
                and toes.translation_constraint_name is None
            )

    def test_leg_blend_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()
        host.collisions["AdvPy_LegSettings"] = ("|User|AdvPy_LegSettings",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegBlend(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_blend_snapshot)

    def test_leg_blend_postcheck_failure_rolls_back(self):
        host = FakeBodySkeletonHost(faulty_leg_blend=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyLegBlend(host).apply()

        self.assertEqual(host.transaction_count, 3)
        self.assertIsNone(host.leg_blend_snapshot)

    def test_builds_bilateral_leg_fk_ik_mode_visibility(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()
        BuildBodyLegFkMechanismControls(host).apply()
        BuildBodyLegIkControls(host).apply()
        BuildBodyLegBlend(host).apply()

        preview = BuildBodyLegVisibility(host).plan()
        result = BuildBodyLegVisibility(host).apply()

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 6)
        self.assertEqual(len(result.snapshot.sides), 2)
        for side in result.snapshot.sides:
            self.assertTrue(side.fk_visibility_source.endswith(".outputX"))
            self.assertEqual(len(set(side.ik_visibility_sources)), 1)
            self.assertTrue(side.ik_visibility_sources[0].endswith(
                f".legIkFk_{side.side.value}"
            ))

    def test_leg_visibility_unwritable_target_blocks_before_transaction(self):
        host = FakeBodySkeletonHost(blocked_leg_visibility=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()
        BuildBodyLegFkMechanismControls(host).apply()
        BuildBodyLegIkControls(host).apply()
        BuildBodyLegBlend(host).apply()

        with self.assertRaisesRegex(FitSkeletonValidationError, "不可写"):
            BuildBodyLegVisibility(host).apply()

        self.assertEqual(host.transaction_count, 5)
        self.assertIsNone(host.leg_visibility_snapshot)

    def test_leg_visibility_postcheck_failure_rolls_back(self):
        host = FakeBodySkeletonHost(faulty_leg_visibility=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegMechanisms(host).apply()
        BuildBodyLegFkMechanismControls(host).apply()
        BuildBodyLegIkControls(host).apply()
        BuildBodyLegBlend(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyLegVisibility(host).apply()

        self.assertEqual(host.transaction_count, 6)
        self.assertIsNone(host.leg_visibility_snapshot)

    def test_fk_controls_drive_fk_mechanisms_instead_of_body(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        BuildBodyArmMechanisms(host).apply()

        preview = BuildBodyArmFkMechanismControls(host).plan(control_radius=2.0)
        result = BuildBodyArmFkMechanismControls(host).apply(control_radius=2.0)

        self.assertTrue(preview.ready)
        self.assertEqual(len(result.snapshot.controls), 6)
        self.assertEqual(host.transaction_count, 3)
        self.assertTrue(
            all("FKDriver" in state.driven_joint for state in result.snapshot.controls)
        )
        body_paths = {state.path for state in body.joints}
        self.assertFalse(
            any(state.driven_joint in body_paths for state in result.snapshot.controls)
        )

    def test_fk_control_explicit_driver_mapping_must_be_complete(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot

        with self.assertRaisesRegex(BodyControlValidationError, "缺少来源"):
            plan_body_arm_fk_controls(body, driven_joint_by_source={})

    def test_fk_mechanism_control_preflight_rejects_tampered_driver(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()
        host.arm_mechanism_states[0] = replace(
            host.arm_mechanism_states[0],
            source_joint=None,
        )

        with self.assertRaisesRegex(FitSkeletonValidationError, "来源"):
            BuildBodyArmFkMechanismControls(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.control_root)

    def test_fk_mechanism_control_postcheck_failure_rolls_back_controls(self):
        host = FakeBodySkeletonHost(faulty_arm_fk=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyArmFkMechanismControls(host).apply()

        self.assertEqual(host.transaction_count, 3)
        self.assertIsNone(host.control_root)
        self.assertFalse(host.arm_fk_states)

    def test_builds_bilateral_rp_ik_controls_on_ik_mechanisms(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()

        preview = BuildBodyArmIkControls(host).plan()
        result = BuildBodyArmIkControls(host).apply()

        self.assertTrue(preview.ready)
        self.assertEqual(len(result.snapshot.limbs), 2)
        self.assertEqual(host.transaction_count, 3)
        self.assertTrue(all("IKDriver" in path for state in result.snapshot.limbs for path in state.joint_list))
        self.assertTrue(all(state.wrist_source == state.wrist_control_path for state in result.snapshot.limbs))

    def test_arm_ik_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()
        host.collisions["AdvPy_ArmIK_R"] = ("|User|AdvPy_ArmIK_R",)
        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyArmIkControls(host).apply()
        self.assertEqual(host.transaction_count, 2)

    def test_arm_ik_postcheck_failure_rolls_back(self):
        host = FakeBodySkeletonHost(faulty_arm_ik=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()
        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyArmIkControls(host).apply()
        self.assertEqual(host.transaction_count, 3)
        self.assertIsNone(host.arm_ik_root)

    def test_builds_independent_arm_fk_ik_body_blends(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()
        result = BuildBodyArmBlend(host).apply()
        self.assertEqual(len(result.snapshot.sides), 2)
        self.assertEqual(sum(len(side.joints) for side in result.snapshot.sides), 6)
        self.assertEqual(host.transaction_count, 3)

    def test_arm_blend_postcheck_failure_rolls_back(self):
        host = FakeBodySkeletonHost(faulty_arm_blend=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()
        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyArmBlend(host).apply()
        self.assertIsNone(host.arm_blend_snapshot)

    def test_arm_translation_blend_postcheck_failure_rolls_back(self):
        host = FakeBodySkeletonHost(faulty_arm_translation=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmMechanisms(host).apply()
        with self.assertRaisesRegex(RuntimeError, "位移权重"):
            BuildBodyArmBlend(host).apply()
        self.assertIsNone(host.arm_blend_snapshot)

    def test_complete_arm_rig_builds_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        result = BuildBodyArmRig(host).apply()
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(len(result.mechanisms.joints), 12)
        self.assertEqual(len(result.fk_controls.controls), 6)
        self.assertEqual(len(result.ik.limbs), 2)
        self.assertEqual(sum(joint.translation_constraint_name is not None for side in result.blend.sides for joint in side.joints), 4)
        self.assertEqual(len(result.stretch.sides), 2)
        self.assertEqual(len(result.twist.segments), 4)
        self.assertEqual(len(result.twist.joints), 8)
        self.assertEqual(len(result.volume.sides), 2)
        self.assertEqual(len(result.visibility.sides), 2)
        self.assertTrue(all(side.fk_visibility_source.endswith(".outputX") for side in result.visibility.sides))
        self.assertEqual(result.body, body)

    def test_complete_basic_leg_rig_builds_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot

        preview = BuildBodyLegRig(host).plan()
        result = BuildBodyLegRig(host).apply()

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(len(result.mechanisms.joints), 20)
        self.assertEqual(len(result.fk_controls.controls), 8)
        self.assertEqual(len(result.ik.limbs), 2)
        self.assertEqual(len(result.blend.sides), 2)
        self.assertEqual(len(result.visibility.sides), 2)
        self.assertEqual(len(result.stretch.sides), 2)
        self.assertEqual(len(result.twist.segments), 4)
        self.assertEqual(len(result.twist.joints), 8)
        self.assertTrue(all(
            state.axis in "XYZ" for state in result.twist.segments
        ))
        self.assertTrue(all(
            spec.target_control_path.endswith(f"AdvPy_LegIK_{spec.side.value}")
            for spec in result.plan.stretch.sides
        ))
        self.assertTrue(all(
            spec.segment_channels == ("Z", "Z")
            for spec in result.plan.stretch.sides
        ))
        self.assertEqual(len(result.foot.sides), 2)
        self.assertEqual(
            sum(len(side.pivots) for side in result.foot.sides),
            10,
        )
        self.assertEqual(result.body, body)

    def test_complete_basic_leg_rig_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_LegPV_L"] = ("|User|AdvPy_LegPV_L",)

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertIsNone(host.leg_control_root)
        self.assertIsNone(host.leg_ik_root)

    def test_complete_basic_leg_rig_late_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_leg_visibility=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "显隐阶段"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertFalse(host.leg_mechanism_states)
        self.assertIsNone(host.leg_control_root)
        self.assertFalse(host.leg_fk_states)
        self.assertIsNone(host.leg_blend_snapshot)
        self.assertIsNone(host.leg_ik_root)
        self.assertFalse(host.leg_ik_states)
        self.assertIsNone(host.leg_visibility_snapshot)
        self.assertIsNone(host.leg_stretch_snapshot)
        self.assertIsNone(host.leg_twist_root)
        self.assertFalse(host.leg_twist_segments)
        self.assertFalse(host.leg_twist_states)
        self.assertIsNone(host.leg_foot_snapshot)

    def test_complete_leg_rig_twist_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_leg_twist=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "twist 阶段"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertIsNone(host.leg_control_root)
        self.assertIsNone(host.leg_blend_snapshot)
        self.assertIsNone(host.leg_ik_root)
        self.assertIsNone(host.leg_stretch_snapshot)
        self.assertIsNone(host.leg_twist_root)
        self.assertFalse(host.leg_twist_segments)
        self.assertFalse(host.leg_twist_states)

    def test_leg_twist_runtime_failure_stops_before_rig_transaction(self):
        host = FakeBodySkeletonHost(faulty_leg_twist_runtime=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(FitSkeletonValidationError, "quatNodes"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertIsNone(host.leg_twist_root)

    def test_complete_leg_rig_twist_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_LowerLegTwistProject_R"] = (
            "|User|AdvPy_LowerLegTwistProject_R",
        )

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertIsNone(host.leg_twist_root)

    def test_complete_leg_rig_stretch_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_LegStretchRatio_R"] = (
            "|User|AdvPy_LegStretchRatio_R",
        )

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertIsNone(host.leg_stretch_snapshot)

    def test_complete_leg_rig_stretch_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_leg_stretch=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "stretch 阶段"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertFalse(host.leg_mechanism_states)
        self.assertIsNone(host.leg_control_root)
        self.assertFalse(host.leg_fk_states)
        self.assertIsNone(host.leg_blend_snapshot)
        self.assertIsNone(host.leg_ik_root)
        self.assertFalse(host.leg_ik_states)
        self.assertIsNone(host.leg_visibility_snapshot)
        self.assertIsNone(host.leg_stretch_snapshot)
        self.assertIsNone(host.leg_foot_snapshot)

    def test_complete_leg_rig_foot_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_FootBallPivot_L"] = (
            "|User|AdvPy_FootBallPivot_L",
        )

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertIsNone(host.leg_foot_snapshot)

    def test_complete_leg_rig_toe_orientation_collision_blocks_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        host.collisions["AdvPy_LegIKToesOrient_R"] = (
            "|User|AdvPy_LegIKToesOrient_R",
        )

        with self.assertRaisesRegex(FitSkeletonValidationError, "同名"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.leg_mechanism_root)

    def test_complete_leg_rig_foot_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_leg_foot=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "Foot 阶段"):
            BuildBodyLegRig(host).apply()

        self.assertEqual(host.transaction_count, 2)
        self.assertIsNone(host.leg_mechanism_root)
        self.assertFalse(host.leg_mechanism_states)
        self.assertIsNone(host.leg_control_root)
        self.assertFalse(host.leg_fk_states)
        self.assertIsNone(host.leg_blend_snapshot)
        self.assertIsNone(host.leg_ik_root)
        self.assertFalse(host.leg_ik_states)
        self.assertIsNone(host.leg_visibility_snapshot)
        self.assertIsNone(host.leg_stretch_snapshot)
        self.assertIsNone(host.leg_foot_snapshot)

    def test_extends_basic_leg_rig_with_bilateral_foot_pivots(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        build_basic_leg_without_foot(host)

        preview = BuildBodyLegFoot(host).plan()
        result = BuildBodyLegFoot(host).apply()

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 7)
        self.assertEqual(len(result.snapshot.sides), 2)
        self.assertEqual(sum(len(side.pivots) for side in result.snapshot.sides), 10)
        expected_positions = {
            joint.world_position
            for joint in body.joints
            if joint.name.rsplit("_", 1)[0] in {
                "Heel", "FootSideOuter", "FootSideInner", "ToesEnd", "Toes"
            }
        }
        self.assertEqual(
            {pivot.world_position for side in result.snapshot.sides for pivot in side.pivots},
            expected_positions,
        )
        self.assertTrue(all(
            side.handle_parent_path == side.pivots[-1].path
            for side in result.snapshot.sides
        ))
        self.assertTrue(all(
            len(side.attribute_values) == 6
            and all(value == 0.0 for _, value in side.attribute_values)
            for side in result.snapshot.sides
        ))
        self.assertTrue(all(
            len(side.roll.nodes) == 7
            and side.roll.master_plug.endswith(".footRoll")
            for side in result.snapshot.sides
        ))
        self.assertTrue(all(
            side.ankle_orientation_source == side.pivots[-1].path
            and side.ankle_driven_joint.endswith(
                f"AdvPy_AnkleIKDriver_{side.side.value}"
            )
            and side.toe_orientation_source
            == side.toe_control_path
            and side.toe_driven_joint.endswith(
                f"AdvPy_ToesIKDriver_{side.side.value}"
            )
            for side in result.snapshot.sides
        ))

    def test_foot_existing_attribute_blocks_before_transaction(self):
        host = FakeBodySkeletonHost(blocked_leg_foot=True)
        BuildOrientedBodySkeleton(host).apply()
        build_basic_leg_without_foot(host)

        with self.assertRaisesRegex(FitSkeletonValidationError, "属性已存在"):
            BuildBodyLegFoot(host).apply()

        self.assertEqual(host.transaction_count, 6)
        self.assertIsNone(host.leg_foot_snapshot)

    def test_segmented_foot_roll_profile_keeps_manual_phases_explicit(self):
        self.assertEqual(segmented_foot_roll(-30.0), (-30.0, 0.0, 0.0))
        self.assertEqual(segmented_foot_roll(20.0), (0.0, 20.0, 0.0))
        self.assertEqual(segmented_foot_roll(70.0), (0.0, 45.0, 25.0))
        self.assertEqual(segmented_foot_roll(500.0), (0.0, 45.0, 315.0))

    def test_segmented_foot_roll_rejects_invalid_profile(self):
        with self.assertRaises(BodyLegFootValidationError):
            segmented_foot_roll(10.0, ball_break_angle=0.0)
        with self.assertRaises(BodyLegFootValidationError):
            segmented_foot_roll(float("nan"))

    def test_foot_postcheck_failure_restores_original_handle_parent(self):
        host = FakeBodySkeletonHost(faulty_leg_foot=True)
        BuildOrientedBodySkeleton(host).apply()
        build_basic_leg_without_foot(host)
        original_parents = tuple(
            state.handle_parent_path for state in host.leg_ik_states
        )

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyLegFoot(host).apply()

        self.assertEqual(host.transaction_count, 7)
        self.assertIsNone(host.leg_foot_snapshot)
        self.assertEqual(
            tuple(state.handle_parent_path for state in host.leg_ik_states),
            original_parents,
        )

    def test_complete_arm_rig_late_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_arm_ik=True)
        BuildOrientedBodySkeleton(host).apply()
        with self.assertRaisesRegex(RuntimeError, "IK 阶段"):
            BuildBodyArmRig(host).apply()
        self.assertIsNone(host.mechanism_root)
        self.assertIsNone(host.control_root)
        self.assertIsNone(host.arm_blend_snapshot)
        self.assertIsNone(host.arm_ik_root)

    def test_complete_arm_rig_visibility_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_arm_visibility=True)
        BuildOrientedBodySkeleton(host).apply()
        with self.assertRaisesRegex(RuntimeError, "显隐阶段"):
            BuildBodyArmRig(host).apply()
        self.assertIsNone(host.mechanism_root)
        self.assertIsNone(host.control_root)
        self.assertIsNone(host.arm_blend_snapshot)
        self.assertIsNone(host.arm_ik_root)
        self.assertIsNone(host.arm_visibility_snapshot)

    def test_complete_arm_rig_stretch_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_arm_stretch=True)
        BuildOrientedBodySkeleton(host).apply()
        with self.assertRaisesRegex(RuntimeError, "stretch 阶段"):
            BuildBodyArmRig(host).apply()
        self.assertIsNone(host.mechanism_root)
        self.assertIsNone(host.control_root)
        self.assertIsNone(host.arm_blend_snapshot)
        self.assertIsNone(host.arm_ik_root)
        self.assertIsNone(host.arm_visibility_snapshot)
        self.assertIsNone(host.arm_stretch_snapshot)

    def test_complete_arm_rig_twist_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_arm_twist=True)
        BuildOrientedBodySkeleton(host).apply()
        with self.assertRaisesRegex(RuntimeError, "twist 阶段"):
            BuildBodyArmRig(host).apply()
        self.assertIsNone(host.mechanism_root)
        self.assertIsNone(host.control_root)
        self.assertIsNone(host.arm_blend_snapshot)
        self.assertIsNone(host.arm_ik_root)
        self.assertIsNone(host.arm_stretch_snapshot)
        self.assertIsNone(host.twist_root)
        self.assertFalse(host.arm_twist_segments)
        self.assertFalse(host.arm_twist_states)

    def test_arm_twist_runtime_failure_stops_before_rig_transaction(self):
        host = FakeBodySkeletonHost(faulty_arm_twist_runtime=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(FitSkeletonValidationError, "quatNodes"):
            BuildBodyArmRig(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertIsNone(host.mechanism_root)
        self.assertIsNone(host.twist_root)

    def test_complete_arm_rig_volume_failure_rolls_back_every_stage(self):
        host = FakeBodySkeletonHost(faulty_arm_volume=True)
        BuildOrientedBodySkeleton(host).apply()

        with self.assertRaisesRegex(RuntimeError, "体积保持阶段"):
            BuildBodyArmRig(host).apply()

        self.assertIsNone(host.mechanism_root)
        self.assertIsNone(host.twist_root)
        self.assertIsNone(host.arm_volume_snapshot)

    def test_matches_right_arm_fk_to_ik_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmRig(host).apply()
        result = MatchBodyArmFkToIk(host).apply(FitBuildSide.RIGHT)
        values = {side.side: side.attribute_value for side in result.blend.sides}
        self.assertEqual(host.transaction_count, 3)
        self.assertEqual(values[FitBuildSide.RIGHT], 1.0)
        self.assertEqual(values[FitBuildSide.LEFT], 0.0)

    def test_fk_to_ik_requires_current_fk_mode_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmRig(host).apply()
        host.apply_body_arm_fk_to_ik(MatchBodyArmFkToIk(host).plan(FitBuildSide.RIGHT).match)
        with self.assertRaisesRegex(FitSkeletonValidationError, "不是 FK 模式"):
            MatchBodyArmFkToIk(host).apply(FitBuildSide.RIGHT)
        self.assertEqual(host.transaction_count, 2)

    def test_fk_to_ik_pose_failure_rolls_back_blend(self):
        host = FakeBodySkeletonHost(faulty_arm_match=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmRig(host).apply()
        with self.assertRaisesRegex(RuntimeError, "关节位置跳变"):
            MatchBodyArmFkToIk(host).apply(FitBuildSide.RIGHT)
        right = next(side for side in host.arm_blend_snapshot.sides if side.side is FitBuildSide.RIGHT)
        self.assertEqual(right.attribute_value, 0.0)
        self.assertFalse(host.arm_match_applied)

    def test_matches_right_leg_fk_to_ik_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()

        result = MatchBodyLegFkToIk(host).apply(FitBuildSide.RIGHT)

        values = {side.side: side.attribute_value for side in result.blend.sides}
        self.assertEqual(host.transaction_count, 3)
        self.assertEqual(values[FitBuildSide.RIGHT], 1.0)
        self.assertEqual(values[FitBuildSide.LEFT], 0.0)

    def test_leg_fk_to_ik_requires_current_fk_mode_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()
        match = MatchBodyLegFkToIk(host).plan(FitBuildSide.RIGHT).match
        host.apply_body_leg_fk_to_ik(match)

        with self.assertRaisesRegex(FitSkeletonValidationError, "不是 FK 模式"):
            MatchBodyLegFkToIk(host).apply(FitBuildSide.RIGHT)

        self.assertEqual(host.transaction_count, 2)

    def test_leg_fk_to_ik_detects_toe_pose_drift_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()
        plan = MatchBodyLegFkToIk(host).plan(FitBuildSide.RIGHT).match
        state = host.capture_body_leg_fk_to_ik_state(plan)
        state = replace(
            state,
            toe_body_axes=((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
        )
        issues = audit_body_leg_fk_to_ik_preflight(plan, state)

        self.assertIn("pose_drift", {issue.code for issue in issues})
        self.assertEqual(host.transaction_count, 2)

    def test_leg_fk_to_ik_matches_through_explicit_toe_ik_control(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()
        build = MatchBodyLegFkToIk(host).plan(FitBuildSide.RIGHT)
        plan = build.match

        self.assertTrue(build.ready)
        self.assertTrue(plan.toe_control_path.endswith("AdvPy_ToeIK_R"))
        self.assertEqual(
            {
                f"{plan.toe_control_path}.rotate{axis}"
                for axis in "XYZ"
            }
            & set(plan.required_writable_plugs),
            {
                f"{plan.toe_control_path}.rotate{axis}"
                for axis in "XYZ"
            },
        )

    def test_leg_fk_to_ik_pose_failure_rolls_back_blend(self):
        host = FakeBodySkeletonHost(faulty_leg_match=True)
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()

        with self.assertRaisesRegex(RuntimeError, "关节位置跳变"):
            MatchBodyLegFkToIk(host).apply(FitBuildSide.RIGHT)

        right = next(
            side for side in host.leg_blend_snapshot.sides
            if side.side is FitBuildSide.RIGHT
        )
        self.assertEqual(right.attribute_value, 0.0)
        self.assertFalse(host.leg_match_applied)

    def test_matches_right_leg_ik_to_fk_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()
        MatchBodyLegFkToIk(host).apply(FitBuildSide.RIGHT)

        result = MatchBodyLegIkToFk(host).apply(FitBuildSide.RIGHT)

        values = {side.side: side.attribute_value for side in result.blend.sides}
        self.assertEqual(host.transaction_count, 4)
        self.assertEqual(values[FitBuildSide.RIGHT], 0.0)
        self.assertEqual(values[FitBuildSide.LEFT], 0.0)
        self.assertEqual(len(result.plan.match.fk_control_paths), 4)
        self.assertEqual(
            host.leg_match_segment_translations,
            result.plan.match.fk_segment_translations,
        )

    def test_leg_ik_to_fk_requires_current_ik_mode_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()

        with self.assertRaisesRegex(FitSkeletonValidationError, "不是 IK 模式"):
            MatchBodyLegIkToFk(host).apply(FitBuildSide.RIGHT)

        self.assertEqual(host.transaction_count, 2)

    def test_leg_ik_to_fk_pose_failure_rolls_back_blend(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyLegRig(host).apply()
        MatchBodyLegFkToIk(host).apply(FitBuildSide.RIGHT)
        host.faulty_leg_match = True

        with self.assertRaisesRegex(RuntimeError, "关节位置跳变"):
            MatchBodyLegIkToFk(host).apply(FitBuildSide.RIGHT)

        right = next(
            side for side in host.leg_blend_snapshot.sides
            if side.side is FitBuildSide.RIGHT
        )
        self.assertEqual(right.attribute_value, 1.0)

    def test_matches_right_arm_ik_to_fk_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmRig(host).apply()
        MatchBodyArmFkToIk(host).apply(FitBuildSide.RIGHT)
        result = MatchBodyArmIkToFk(host).apply(FitBuildSide.RIGHT)
        values = {side.side: side.attribute_value for side in result.blend.sides}
        self.assertEqual(host.transaction_count, 4)
        self.assertEqual(values[FitBuildSide.RIGHT], 0.0)
        self.assertEqual(values[FitBuildSide.LEFT], 0.0)
        self.assertEqual(
            host.arm_match_segment_translations,
            result.plan.match.fk_segment_translations,
        )

    def test_ik_to_fk_requires_current_ik_mode_before_transaction(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmRig(host).apply()
        with self.assertRaisesRegex(FitSkeletonValidationError, "不是 IK 模式"):
            MatchBodyArmIkToFk(host).apply(FitBuildSide.RIGHT)
        self.assertEqual(host.transaction_count, 2)

    def test_ik_to_fk_pose_failure_rolls_back_blend(self):
        host = FakeBodySkeletonHost()
        BuildOrientedBodySkeleton(host).apply()
        BuildBodyArmRig(host).apply()
        MatchBodyArmFkToIk(host).apply(FitBuildSide.RIGHT)
        host.faulty_arm_match = True
        with self.assertRaisesRegex(RuntimeError, "关节位置跳变"):
            MatchBodyArmIkToFk(host).apply(FitBuildSide.RIGHT)
        right = next(side for side in host.arm_blend_snapshot.sides if side.side is FitBuildSide.RIGHT)
        self.assertEqual(right.attribute_value, 1.0)
        self.assertIsNone(host.arm_match_segment_translations)


if __name__ == "__main__":
    unittest.main()
