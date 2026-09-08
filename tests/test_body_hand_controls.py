import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import BuildBodyHandFkControls
from adv_py.core import (
    BODY_HAND_DIGITS,
    BodyHandFkControlSnapshot,
    BodyHandFkControlState,
    BodyHandFkInputSnapshot,
    BodyHandFkJointInputState,
    BodyHandFkRootState,
    BodyJointState,
    BodyRebuildSceneState,
    BodySkeletonSnapshot,
    BodySkeletonProvenanceState,
    FitJointMetadata,
    FitJointOrientationState,
    FitOrientationSnapshot,
    FitSkeletonValidationError,
    FitUpAxis,
    IDENTITY_AXES,
    audit_body_hand_fk_controls,
    audit_body_hand_fk_input,
    default_fit_skeleton_settings,
    expand_fit_symmetry,
    oriented_body_provenance,
    plan_body_hand_fk_controls,
    predict_fit_template_hierarchy,
    synthetic_body_with_hand_source_fit_template,
)


def _hand_scene():
    template = synthetic_body_with_hand_source_fit_template(FitUpAxis.Z)
    hierarchy = predict_fit_template_hierarchy(template, "|FitSkeleton")
    labels = {joint.name: joint.label for joint in template.joints}
    fit = FitOrientationSnapshot(
        hierarchy=hierarchy,
        up_axis=FitUpAxis.Z,
        joints=tuple(
            FitJointOrientationState(
                joint=node.path,
                joint_orient=(0.0, 0.0, 0.0),
                rotation=(0.0, 0.0, 0.0),
                world_axes=IDENTITY_AXES,
            )
            for node in hierarchy.joints
        ),
        metadata=tuple(
            FitJointMetadata(node.path) for node in hierarchy.joints
        ),
    )
    instances = expand_fit_symmetry(
        hierarchy,
        fit.metadata,
        world_axes_by_joint={state.joint: state.world_axes for state in fit.joints},
    )
    provenance = oriented_body_provenance("|FitSkeleton", len(instances))
    provenance_state = BodySkeletonProvenanceState(
        provenance.owner,
        provenance.artifact_kind,
        provenance.schema_version,
        provenance.source_container,
        provenance.body_joint_count,
    )
    body = BodySkeletonSnapshot(
        root="|Root_M",
        joints=tuple(
            BodyJointState(
                path=instance.output_path,
                name=instance.output_name,
                parent_path=instance.parent_output_path,
                side=instance.side,
                world_position=instance.world_position,
                label=labels[instance.source_joint.rsplit("|", 1)[-1]],
                joint_orient=(0.0, 0.0, 0.0),
                rotation=(0.0, 0.0, 0.0),
                world_axes=instance.world_axes,
            )
            for instance in instances
        ),
        provenance=provenance_state,
    )
    return fit, body


class FakeBodyHandFkHost:
    def __init__(self, *, faulty_capture=False, locked_joint=None):
        self.fit, body = _hand_scene()
        self.body = body
        self.settings = default_fit_skeleton_settings("|FitSkeleton")
        self.collisions = {}
        self.roots = []
        self.controls = []
        self.transaction_count = 0
        self.faulty_capture = faulty_capture
        self.locked_joint = locked_joint

    def capture_fit_orientation(self, container_name):
        del container_name
        return self.fit

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    def capture_body_skeleton(self, root_name):
        del root_name
        return self.body

    def capture_body_rebuild_state(self, root_name):
        return BodyRebuildSceneState(
            f"|{root_name}",
            tuple(joint.path for joint in self.body.joints),
            (),
        )

    def find_name_collisions(self, name):
        return tuple(self.collisions.get(name, ()))

    def capture_body_hand_fk_input(self, plan):
        return BodyHandFkInputSnapshot(tuple(
            BodyHandFkJointInputState(
                joint=control.driven_joint,
                writable_rotation_axes=(
                    frozenset({"x", "y"})
                    if control.driven_joint == self.locked_joint
                    else frozenset({"x", "y", "z"})
                ),
                rotation_sources=(None, None, None),
            )
            for control in plan.controls
        ))

    @contextmanager
    def transaction(self, label):
        del label
        before_roots = list(self.roots)
        before_controls = list(self.controls)
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.roots = before_roots
            self.controls = before_controls
            raise

    def create_body_hand_fk_root(self, spec):
        self.roots.append(BodyHandFkRootState(
            path=spec.path,
            parent_path=spec.parent_path,
            world_position=spec.world_position,
            world_axes=spec.world_axes,
            local_translation=(0.0, 0.0, 0.0),
            local_rotation=(0.0, 0.0, 0.0),
            local_scale=(1.0, 1.0, 1.0),
        ))
        return spec.path

    def create_body_hand_fk_control(self, spec):
        self.controls.append(BodyHandFkControlState(
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

    def capture_body_hand_fk_controls(self, plan):
        del plan
        controls = tuple(self.controls)
        if self.faulty_capture and controls:
            controls = (replace(controls[0], shape_type=None),) + controls[1:]
        return BodyHandFkControlSnapshot(tuple(self.roots), controls)


class BodyHandControlTests(unittest.TestCase):
    def test_plans_two_wrist_roots_and_thirty_hierarchical_controls(self):
        _, body = _hand_scene()
        plan = plan_body_hand_fk_controls(body, radius=0.3)

        self.assertEqual(len(plan.roots), 2)
        self.assertEqual(len(plan.controls), 30)
        self.assertEqual(
            {root.parent_path.rsplit("|", 1)[-1] for root in plan.roots},
            {"Wrist_R", "Wrist_L"},
        )
        for digit in BODY_HAND_DIGITS:
            controls = [
                control
                for control in plan.controls
                if f"AdvPy_{digit.value}" in control.control_name
                and control.side.value == "R"
            ]
            self.assertEqual(len(controls), 3)
            self.assertEqual(controls[1].parent_path, controls[0].control_path)
            self.assertEqual(controls[2].parent_path, controls[1].control_path)
            self.assertGreater(controls[0].radius, controls[1].radius)
            self.assertGreater(controls[1].radius, controls[2].radius)

    def test_input_audit_reports_locked_or_connected_rotation(self):
        _, body = _hand_scene()
        plan = plan_body_hand_fk_controls(body)
        ready = BodyHandFkInputSnapshot(tuple(
            BodyHandFkJointInputState(
                control.driven_joint,
                frozenset({"x", "y", "z"}),
                (None, None, None),
            )
            for control in plan.controls
        ))
        first = ready.joints[0]
        broken = replace(
            ready,
            joints=(replace(
                first,
                writable_rotation_axes=frozenset({"x", "y"}),
                rotation_sources=("Driver.output", None, None),
            ),) + ready.joints[1:],
        )

        self.assertFalse(audit_body_hand_fk_input(plan, ready))
        self.assertEqual(
            {issue.code for issue in audit_body_hand_fk_input(plan, broken)},
            {"hand_input_rotation_locked", "hand_input_rotation_connected"},
        )

    def test_builds_all_controls_in_one_transaction(self):
        host = FakeBodyHandFkHost()
        use_case = BuildBodyHandFkControls(host)

        preview = use_case.plan(control_radius=0.4)
        result = use_case.apply(control_radius=0.4)

        self.assertTrue(preview.ready)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(len(result.snapshot.roots), 2)
        self.assertEqual(len(result.snapshot.controls), 30)
        self.assertFalse(
            audit_body_hand_fk_controls(preview.controls, result.snapshot)
        )

    def test_collision_or_locked_target_blocks_before_transaction(self):
        collision_host = FakeBodyHandFkHost()
        collision_host.collisions["AdvPy_Index2FK_L"] = (
            "|User|AdvPy_Index2FK_L",
        )
        locked_host = FakeBodyHandFkHost()
        plan = plan_body_hand_fk_controls(locked_host.body)
        locked_host.locked_joint = plan.controls[0].driven_joint

        with self.assertRaises(FitSkeletonValidationError):
            BuildBodyHandFkControls(collision_host).apply()
        with self.assertRaisesRegex(FitSkeletonValidationError, "不可完整写入"):
            BuildBodyHandFkControls(locked_host).apply()

        self.assertEqual(collision_host.transaction_count, 0)
        self.assertEqual(locked_host.transaction_count, 0)

    def test_postcheck_failure_rolls_back_roots_and_controls(self):
        host = FakeBodyHandFkHost(faulty_capture=True)

        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BuildBodyHandFkControls(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.roots)
        self.assertFalse(host.controls)


if __name__ == "__main__":
    unittest.main()
