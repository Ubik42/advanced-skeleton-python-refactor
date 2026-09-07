import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import (
    BuildBodyArmMechanisms,
    BuildBodyArmFkControls,
    BuildBodyArmFkMechanismControls,
    BuildBodyArmIkControls,
    BuildBodyArmBlend,
    BuildBodyArmRig,
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
    BodyArmIkSnapshot,
    BodyArmIkState,
    BodyArmBlendJointState,
    BodyArmBlendSideState,
    BodyArmBlendSnapshot,
    BodyArmVisibilitySideState,
    BodyArmVisibilitySnapshot,
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
    FitOrientationSnapshot,
    FitSkeletonValidationError,
    FitUpAxis,
    default_fit_skeleton_settings,
    predict_fit_template_hierarchy,
    synthetic_body_source_fit_template,
    plan_body_arm_fk_controls,
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
        faulty_arm_ik=False,
        faulty_arm_blend=False,
        faulty_arm_visibility=False,
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
        self.arm_ik_root = None
        self.arm_ik_states = []
        self.faulty_arm_ik = faulty_arm_ik
        self.arm_blend_snapshot = None
        self.faulty_arm_blend = faulty_arm_blend
        self.arm_visibility_snapshot = None
        self.faulty_arm_visibility = faulty_arm_visibility

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
        if self.arm_ik_root and self.arm_ik_root.rsplit("|", 1)[-1] == name:
            existing_controls.append(self.arm_ik_root)
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
        before_arm_ik_root = self.arm_ik_root
        before_arm_ik_states = list(self.arm_ik_states)
        before_arm_blend_snapshot = self.arm_blend_snapshot
        before_arm_visibility_snapshot = self.arm_visibility_snapshot
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
            self.arm_ik_root = before_arm_ik_root
            self.arm_ik_states = before_arm_ik_states
            self.arm_blend_snapshot = before_arm_blend_snapshot
            self.arm_visibility_snapshot = before_arm_visibility_snapshot
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
            joints = tuple(BodyArmBlendJointState(j.constraint_name, j.body_joint, (j.fk_driver, j.ik_driver), f"{side.reverse_name}.outputX", plug) for j in side.joints)
            sides.append(BodyArmBlendSideState(side.side, plug, 0.0, side.reverse_name, plug, joints))
        self.arm_blend_snapshot = BodyArmBlendSnapshot(plan.settings_path, tuple(sides))

    def capture_body_arm_blend(self, plan):
        del plan
        if self.faulty_arm_blend and self.arm_blend_snapshot:
            first = replace(self.arm_blend_snapshot.sides[0], reverse_input_source=None)
            return replace(self.arm_blend_snapshot, sides=(first,) + self.arm_blend_snapshot.sides[1:])
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

    def test_complete_arm_rig_builds_in_one_transaction(self):
        host = FakeBodySkeletonHost()
        body = BuildOrientedBodySkeleton(host).apply().snapshot
        result = BuildBodyArmRig(host).apply()
        self.assertEqual(host.transaction_count, 2)
        self.assertEqual(len(result.mechanisms.joints), 12)
        self.assertEqual(len(result.fk_controls.controls), 6)
        self.assertEqual(len(result.ik.limbs), 2)
        self.assertEqual(len(result.visibility.sides), 2)
        self.assertTrue(all(side.fk_visibility_source.endswith(".outputX") for side in result.visibility.sides))
        self.assertEqual(result.body, body)

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


if __name__ == "__main__":
    unittest.main()
