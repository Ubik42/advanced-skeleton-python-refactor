import json
from pathlib import Path
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import (
    BODY_HAND_POSE_PRESET_SUFFIX,
    ApplyBodyHandPosePreset,
    BuildBodyHandFkControls,
    ExportBodyHandPose,
    ImportBodyHandPose,
    InspectBodyHandPosePresetLibrary,
    MirrorBodyHandPose,
    SaveBodyHandPosePreset,
)
from adv_py.core import (
    BODY_HAND_DIGITS,
    BODY_HAND_CURL_WEIGHTS,
    BodyHandCurlState,
    BodyHandAggregatePoseChannelState,
    BodyHandFkControlSnapshot,
    BodyHandFkControlState,
    BodyHandFkInputSnapshot,
    BodyHandFkJointInputState,
    BodyHandFkRootState,
    BodyHandPoseAttributeState,
    BodyHandPoseLayerState,
    BodyHandPoseSnapshot,
    BodyHandFkPoseChannelState,
    BodyHandPoseChannelSnapshot,
    BodyHandPoseAccessMode,
    BodyHandPoseDocumentValidationError,
    BodyHandSpreadState,
    BodyJointState,
    BodyRebuildSceneState,
    BodySkeletonSnapshot,
    BodySkeletonProvenanceState,
    FitJointMetadata,
    FitJointOrientationState,
    FitBuildSide,
    FitOrientationSnapshot,
    FitSkeletonValidationError,
    FitUpAxis,
    IDENTITY_AXES,
    audit_body_hand_fk_controls,
    audit_body_hand_fk_input,
    audit_body_hand_pose_channels,
    audit_body_hand_pose_controls,
    body_hand_pose_document_from_json,
    body_hand_pose_document_from_snapshot,
    body_hand_pose_document_to_json,
    default_fit_skeleton_settings,
    expand_fit_symmetry,
    oriented_body_provenance,
    plan_body_hand_fk_controls,
    plan_body_hand_pose_controls,
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


def _namespace_path(path, namespace):
    if path is None:
        return None
    return "|" + "|".join(
        f"{namespace}:{part}"
        for part in path.split("|")
        if part
    )


def _namespaced_body(body, namespace):
    return replace(
        body,
        root=_namespace_path(body.root, namespace),
        joints=tuple(
            replace(
                joint,
                path=_namespace_path(joint.path, namespace),
                parent_path=_namespace_path(joint.parent_path, namespace),
            )
            for joint in body.joints
        ),
    )


def _pose_snapshot(plan):
    return BodyHandPoseSnapshot(
        layers=tuple(
            BodyHandPoseLayerState(
                spec.path,
                spec.parent_path,
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                (1.0, 1.0, 1.0),
            )
            for spec in plan.layers
        ),
        attributes=tuple(
            BodyHandPoseAttributeState(
                spec.plug,
                spec.default,
                spec.minimum,
                spec.maximum,
                True,
            )
            for spec in plan.attributes
        ),
        curls=tuple(
            BodyHandCurlState(
                spec.node_name,
                "blendWeighted",
                spec.source_plugs,
                spec.weights,
                spec.destination_plug,
                f"{spec.node_name}.output",
            )
            for spec in plan.curls
        ),
        spreads=tuple(
            BodyHandSpreadState(
                spec.node_name,
                "multDoubleLinear",
                spec.source_plug,
                spec.factor,
                spec.destination_plug,
                f"{spec.node_name}.output",
            )
            for spec in plan.spreads
        ),
    )


class FakeBodyHandFkHost:
    def __init__(
        self,
        *,
        faulty_capture=False,
        faulty_pose=False,
        locked_joint=None,
    ):
        self.fit, body = _hand_scene()
        self.body = body
        self.settings = default_fit_skeleton_settings("|FitSkeleton")
        self.collisions = {}
        self.roots = []
        self.controls = []
        self.pose = None
        self.transaction_count = 0
        self.faulty_capture = faulty_capture
        self.faulty_pose = faulty_pose
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
        before_pose = self.pose
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.roots = before_roots
            self.controls = before_controls
            self.pose = before_pose
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
            control_parent_path=(
                spec.control_parent_path or spec.offset_path
            ),
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

    def create_body_hand_pose(self, plan):
        self.pose = _pose_snapshot(plan)

    def capture_body_hand_pose(self, plan):
        del plan
        if self.faulty_pose and self.pose and self.pose.curls:
            return replace(
                self.pose,
                curls=(replace(
                    self.pose.curls[0],
                    destination_source=None,
                ),) + self.pose.curls[1:],
            )
        return self.pose


class FakeBodyHandPoseDocumentHost(FakeBodyHandFkHost):
    def __init__(self):
        super().__init__()
        self.channels = None
        self.last_keyframe = None
        built = BuildBodyHandFkControls(self).apply()
        self.transaction_count = 0
        self.channels = BodyHandPoseChannelSnapshot(
            aggregates=tuple(
                BodyHandAggregatePoseChannelState(
                    spec.side,
                    spec.name,
                    spec.plug,
                    spec.default,
                    spec.minimum,
                    spec.maximum,
                    True,
                    None,
                    None,
                    True,
                )
                for spec in built.plan.pose.attributes
            ),
            controls=tuple(
                BodyHandFkPoseChannelState(
                    spec.side,
                    next(
                        digit
                        for digit in BODY_HAND_DIGITS
                        if digit.value in spec.control_name
                    ),
                    next(
                        segment
                        for segment in ("1", "2", "3")
                        if f"{segment}FK_" in spec.control_name
                    ),
                    spec.control_path,
                    (0.0, 0.0, 0.0),
                    frozenset({"x", "y", "z"}),
                    (None, None, None),
                    (None, None, None),
                    frozenset({"x", "y", "z"}),
                )
                for spec in built.plan.controls.controls
            ),
        )

    def capture_body_hand_pose_channels(self, hand, pose):
        del hand, pose
        return self.channels

    @contextmanager
    def transaction(self, label):
        del label
        before = self.channels
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.channels = before
            raise

    def apply_body_hand_pose_changes(self, changes, *, keyframe=False):
        self.last_keyframe = keyframe
        aggregate_targets = {
            (change.side, change.name): change.after
            for change in changes.aggregates
        }
        control_targets = {
            (change.side, change.digit, change.segment): change.after
            for change in changes.controls
        }
        self.channels = BodyHandPoseChannelSnapshot(
            aggregates=tuple(
                replace(
                    state,
                    value=aggregate_targets.get(
                        (state.side, state.name),
                        state.value,
                    ),
                )
                for state in self.channels.aggregates
            ),
            controls=tuple(
                replace(
                    state,
                    rotation=control_targets.get(
                        (state.side, state.digit, state.segment),
                        state.rotation,
                    ),
                )
                for state in self.channels.controls
            ),
        )


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

    def test_namespaced_hand_plan_keeps_semantic_channel_keys(self):
        _, body = _hand_scene()
        hand = plan_body_hand_fk_controls(
            _namespaced_body(body, "Shot:Hero"),
            namespace="Shot:Hero",
        )
        pose = plan_body_hand_pose_controls(hand)
        channels = BodyHandPoseChannelSnapshot(
            aggregates=tuple(
                BodyHandAggregatePoseChannelState(
                    spec.side,
                    spec.name,
                    spec.plug,
                    0.0,
                    spec.minimum,
                    spec.maximum,
                    True,
                    None,
                )
                for spec in pose.attributes
            ),
            controls=tuple(
                BodyHandFkPoseChannelState(
                    spec.side,
                    next(
                        digit
                        for digit in BODY_HAND_DIGITS
                        if digit.value in spec.control_name
                    ),
                    next(
                        segment
                        for segment in ("1", "2", "3")
                        if f"{segment}FK_" in spec.control_name
                    ),
                    spec.control_path,
                    (0.0, 0.0, 0.0),
                    frozenset({"x", "y", "z"}),
                    (None, None, None),
                )
                for spec in hand.controls
            ),
        )

        self.assertTrue(all(
            root.name.startswith("Shot:Hero:")
            for root in hand.roots
        ))
        self.assertTrue(all(
            spec.node_name.startswith("Shot:Hero:")
            for spec in pose.curls + pose.spreads
        ))
        self.assertFalse(audit_body_hand_pose_channels(hand, pose, channels))
        document = body_hand_pose_document_from_snapshot(channels)
        self.assertNotIn("Shot:Hero", body_hand_pose_document_to_json(document))
        with self.assertRaisesRegex(ValueError, "namespace"):
            plan_body_hand_fk_controls(body, namespace="Shot::Hero")

    def test_pose_plan_layers_curl_and_spread_on_fk_offsets(self):
        _, body = _hand_scene()
        hand = plan_body_hand_fk_controls(body)
        pose = plan_body_hand_pose_controls(hand)

        self.assertEqual(len(pose.layers), 30)
        self.assertEqual(len(pose.attributes), 14)
        self.assertEqual(len(pose.curls), 30)
        self.assertEqual(len(pose.spreads), 8)
        self.assertEqual(
            {spec.weights[0] for spec in pose.curls},
            {weight for _, weight in BODY_HAND_CURL_WEIGHTS},
        )
        self.assertTrue(all(
            spec.destination_plug.endswith(".rotateZ")
            for spec in pose.curls
        ))
        self.assertTrue(all(
            spec.destination_plug.endswith(".rotateY")
            for spec in pose.spreads
        ))
        factors = {
            (spec.side.value, spec.digit.value): spec.factor
            for spec in pose.spreads
        }
        self.assertEqual(factors[("R", "Thumb")], 1.0)
        self.assertEqual(factors[("L", "Thumb")], -1.0)
        self.assertEqual(factors[("R", "Pinky")], -1.0)
        self.assertEqual(factors[("L", "Pinky")], 1.0)

    def test_pose_audit_reports_wrong_curl_output(self):
        _, body = _hand_scene()
        pose = plan_body_hand_pose_controls(
            plan_body_hand_fk_controls(body)
        )
        ready = _pose_snapshot(pose)
        broken = replace(
            ready,
            curls=(replace(
                ready.curls[0],
                destination_source="Wrong.output",
            ),) + ready.curls[1:],
        )

        self.assertFalse(audit_body_hand_pose_controls(pose, ready))
        self.assertIn(
            "hand_curl_wiring_mismatch",
            {
                issue.code
                for issue in audit_body_hand_pose_controls(pose, broken)
            },
        )

    def test_pose_structure_audit_can_ignore_current_animation_values(self):
        _, body = _hand_scene()
        pose = plan_body_hand_pose_controls(plan_body_hand_fk_controls(body))
        ready = _pose_snapshot(pose)
        posed = replace(
            ready,
            layers=(replace(
                ready.layers[0],
                local_rotation=(0.0, 0.0, 20.0),
            ),) + ready.layers[1:],
            attributes=(replace(
                ready.attributes[0],
                value=30.0,
            ),) + ready.attributes[1:],
        )

        self.assertTrue(audit_body_hand_pose_controls(pose, posed))
        self.assertFalse(audit_body_hand_pose_controls(
            pose,
            posed,
            check_initial_pose=False,
        ))

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
        self.assertEqual(len(result.pose.layers), 30)
        self.assertEqual(len(result.pose.attributes), 14)
        self.assertEqual(len(result.pose.curls), 30)
        self.assertEqual(len(result.pose.spreads), 8)
        self.assertFalse(
            audit_body_hand_fk_controls(preview.controls, result.snapshot)
        )

    def test_collision_or_locked_target_blocks_before_transaction(self):
        collision_host = FakeBodyHandFkHost()
        collision_host.collisions["AdvPy_HandCurl_Index2_L"] = (
            "AdvPy_HandCurl_Index2_L",
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
        self.assertIsNone(host.pose)

    def test_pose_postcheck_failure_rolls_back_complete_hand(self):
        host = FakeBodyHandFkHost(faulty_pose=True)

        with self.assertRaisesRegex(RuntimeError, "聚合姿态构建后复检失败"):
            BuildBodyHandFkControls(host).apply()

        self.assertEqual(host.transaction_count, 1)
        self.assertFalse(host.roots)
        self.assertFalse(host.controls)
        self.assertIsNone(host.pose)

    def test_pose_document_round_trip_is_semantic_and_tamper_evident(self):
        host = FakeBodyHandPoseDocumentHost()
        document = body_hand_pose_document_from_snapshot(host.channels)
        text = body_hand_pose_document_to_json(document)

        self.assertEqual(body_hand_pose_document_from_json(text), document)
        self.assertNotIn("|Root_M", text)
        self.assertNotIn("AdvPy_", text)
        data = json.loads(text)
        data["aggregates"][0]["value"] = 10.0
        with self.assertRaisesRegex(
            BodyHandPoseDocumentValidationError,
            "摘要",
        ):
            body_hand_pose_document_from_json(json.dumps(data))

    def test_pose_export_is_atomic_and_refuses_overwrite(self):
        host = FakeBodyHandPoseDocumentHost()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "hand-pose.json"
            result = ExportBodyHandPose(host).apply(target)

            self.assertGreater(result.bytes_written, 0)
            self.assertEqual(host.transaction_count, 0)
            self.assertEqual(
                body_hand_pose_document_from_json(target.read_text("utf-8")),
                result.plan.document,
            )
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                ExportBodyHandPose(host).apply(target)

    def test_named_pose_library_saves_lists_and_applies_a_chinese_preset(self):
        host = FakeBodyHandPoseDocumentHost()
        aggregate = next(
            item for item in host.channels.aggregates
            if item.side is FitBuildSide.RIGHT
        )
        control = next(
            item for item in host.channels.controls
            if item.side is FitBuildSide.RIGHT
        )
        host.channels = replace(
            host.channels,
            aggregates=tuple(
                replace(item, value=25.0) if item is aggregate else item
                for item in host.channels.aggregates
            ),
            controls=tuple(
                replace(item, rotation=(3.0, 4.0, 5.0))
                if item is control
                else item
                for item in host.channels.controls
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            for invalid_name in (
                "../pose",
                "CON",
                " pose",
                "pose\u202e",
            ):
                with self.assertRaises(ValueError):
                    SaveBodyHandPosePreset(host).plan(
                        directory,
                        invalid_name,
                    )
            self.assertFalse(tuple(Path(directory).iterdir()))

            saved = SaveBodyHandPosePreset(host).apply(directory, "握拳Test")
            snapshot = InspectBodyHandPosePresetLibrary().execute(directory)
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                SaveBodyHandPosePreset(host).apply(directory, "握拳test")

            self.assertEqual(saved.plan.name, "握拳Test")
            self.assertEqual(
                saved.plan.destination.name,
                f"握拳Test{BODY_HAND_POSE_PRESET_SUFFIX}",
            )
            self.assertEqual(len(snapshot.presets), 1)
            self.assertEqual(snapshot.presets[0].name, "握拳Test")
            self.assertEqual(
                snapshot.presets[0].document,
                saved.export_result.plan.document,
            )
            self.assertEqual(host.transaction_count, 0)

            host.channels = replace(
                host.channels,
                aggregates=tuple(
                    replace(item, value=-10.0)
                    if item.side is FitBuildSide.RIGHT
                    and item.name == aggregate.name
                    else item
                    for item in host.channels.aggregates
                ),
                controls=tuple(
                    replace(item, rotation=(-1.0, -2.0, -3.0))
                    if item.side is FitBuildSide.RIGHT
                    and item.digit is control.digit
                    and item.segment == control.segment
                    else item
                    for item in host.channels.controls
                ),
            )
            preview = ApplyBodyHandPosePreset(host).plan(
                directory,
                "握拳test",
                target_side=FitBuildSide.RIGHT,
            )
            applied = ApplyBodyHandPosePreset(host).apply(
                directory,
                "握拳test",
                target_side=FitBuildSide.RIGHT,
            )
            repeated = ApplyBodyHandPosePreset(host).apply(
                directory,
                "握拳test",
                target_side=FitBuildSide.RIGHT,
            )
            corrupt = Path(directory) / (
                f"损坏{BODY_HAND_POSE_PRESET_SUFFIX}"
            )
            corrupt.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "损坏"):
                InspectBodyHandPosePresetLibrary().execute(directory)
            with self.assertRaisesRegex(ValueError, "损坏"):
                ApplyBodyHandPosePreset(host).apply(directory, "损坏")

        self.assertEqual(preview.changed_channel_count, 2)
        self.assertEqual(preview.preset.name, "握拳Test")
        self.assertEqual(applied.changed_channel_count, 2)
        self.assertEqual(repeated.changed_channel_count, 0)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(
            body_hand_pose_document_from_snapshot(host.channels),
            applied.import_result.plan.expected_document,
        )

    def test_pose_import_restores_values_once_and_repeat_is_noop(self):
        host = FakeBodyHandPoseDocumentHost()
        first_aggregate = host.channels.aggregates[0]
        first_control = host.channels.controls[0]
        host.channels = replace(
            host.channels,
            aggregates=(replace(first_aggregate, value=25.0),)
            + host.channels.aggregates[1:],
            controls=(replace(
                first_control,
                rotation=(3.0, 4.0, 5.0),
            ),) + host.channels.controls[1:],
        )
        saved = host.channels
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "hand-pose.json"
            ExportBodyHandPose(host).apply(target)
            host.channels = replace(
                host.channels,
                aggregates=(replace(first_aggregate, value=-10.0),)
                + host.channels.aggregates[1:],
                controls=(replace(
                    first_control,
                    rotation=(-1.0, -2.0, -3.0),
                ),) + host.channels.controls[1:],
            )

            result = ImportBodyHandPose(host).apply(target)
            repeated = ImportBodyHandPose(host).apply(target)

        self.assertEqual(result.changed_channel_count, 2)
        self.assertEqual(repeated.changed_channel_count, 0)
        self.assertEqual(host.channels, saved)
        self.assertEqual(host.transaction_count, 1)

    def test_pose_import_rejects_unsafe_channel_before_transaction(self):
        host = FakeBodyHandPoseDocumentHost()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "hand-pose.json"
            ExportBodyHandPose(host).apply(target)
            host.channels = replace(
                host.channels,
                controls=(replace(
                    host.channels.controls[0],
                    writable_rotation_axes=frozenset({"x", "y"}),
                ),) + host.channels.controls[1:],
            )

            with self.assertRaisesRegex(ValueError, "rotate"):
                ImportBodyHandPose(host).apply(target)

        self.assertEqual(host.transaction_count, 0)

    def test_pose_import_targets_one_side_and_ignores_other_side_drivers(self):
        host = FakeBodyHandPoseDocumentHost()
        right_aggregate = next(
            item for item in host.channels.aggregates
            if item.side is FitBuildSide.RIGHT
        )
        left_aggregate = next(
            item for item in host.channels.aggregates
            if item.side is FitBuildSide.LEFT
        )
        right_control = next(
            item for item in host.channels.controls
            if item.side is FitBuildSide.RIGHT
        )
        left_control = next(
            item for item in host.channels.controls
            if item.side is FitBuildSide.LEFT
        )
        host.channels = replace(
            host.channels,
            aggregates=tuple(
                replace(item, value=25.0)
                if item is right_aggregate
                else replace(item, value=-12.0)
                if item is left_aggregate
                else item
                for item in host.channels.aggregates
            ),
            controls=tuple(
                replace(item, rotation=(3.0, 4.0, 5.0))
                if item is right_control
                else replace(item, rotation=(6.0, 7.0, 8.0))
                if item is left_control
                else item
                for item in host.channels.controls
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "bilateral-hand-pose.json"
            ExportBodyHandPose(host).apply(target)
            host.channels = replace(
                host.channels,
                aggregates=tuple(
                    replace(item, value=-10.0)
                    if item.side is FitBuildSide.RIGHT
                    and item.name == right_aggregate.name
                    else replace(
                        item,
                        value=5.0,
                        writable=False,
                        incoming_source="LeftDriver.output",
                        incoming_source_type="multiplyDivide",
                        keyframe_writable=False,
                    )
                    if item.side is FitBuildSide.LEFT
                    and item.name == left_aggregate.name
                    else item
                    for item in host.channels.aggregates
                ),
                controls=tuple(
                    replace(item, rotation=(-1.0, -2.0, -3.0))
                    if item.side is FitBuildSide.RIGHT
                    and item.digit is right_control.digit
                    and item.segment == right_control.segment
                    else replace(
                        item,
                        rotation=(-4.0, -5.0, -6.0),
                        writable_rotation_axes=frozenset(),
                        rotation_sources=(
                            "LeftX.output",
                            "LeftY.output",
                            "LeftZ.output",
                        ),
                        rotation_source_types=(
                            "expression",
                            "expression",
                            "expression",
                        ),
                        keyframe_writable_rotation_axes=frozenset(),
                    )
                    if item.side is FitBuildSide.LEFT
                    and item.digit is left_control.digit
                    and item.segment == left_control.segment
                    else item
                    for item in host.channels.controls
                ),
            )
            left_before = tuple(
                item for item in (
                    *host.channels.aggregates,
                    *host.channels.controls,
                )
                if item.side is FitBuildSide.LEFT
            )

            with self.assertRaisesRegex(ValueError, "请求模式"):
                ImportBodyHandPose(host).plan(target)
            with self.assertRaisesRegex(ValueError, "目标侧"):
                ImportBodyHandPose(host).plan(target, target_side="R")
            result = ImportBodyHandPose(host).apply(
                target,
                target_side=FitBuildSide.RIGHT,
            )
            repeated = ImportBodyHandPose(host).apply(
                target,
                target_side=FitBuildSide.RIGHT,
            )

        left_after = tuple(
            item for item in (
                *host.channels.aggregates,
                *host.channels.controls,
            )
            if item.side is FitBuildSide.LEFT
        )
        self.assertEqual(result.changed_channel_count, 2)
        self.assertEqual(repeated.changed_channel_count, 0)
        self.assertIs(result.plan.target_side, FitBuildSide.RIGHT)
        self.assertEqual(
            body_hand_pose_document_from_snapshot(host.channels),
            result.plan.expected_document,
        )
        self.assertEqual(left_after, left_before)
        self.assertEqual(host.transaction_count, 1)

    def test_pose_mirror_copies_source_semantics_to_the_other_side(self):
        host = FakeBodyHandPoseDocumentHost()
        right_aggregate = next(
            item for item in host.channels.aggregates
            if item.side is FitBuildSide.RIGHT
            and item.name == "handCurl"
        )
        left_aggregate = next(
            item for item in host.channels.aggregates
            if item.side is FitBuildSide.LEFT
            and item.name == right_aggregate.name
        )
        right_control = next(
            item for item in host.channels.controls
            if item.side is FitBuildSide.RIGHT
        )
        left_control = next(
            item for item in host.channels.controls
            if item.side is FitBuildSide.LEFT
            and item.digit is right_control.digit
            and item.segment == right_control.segment
        )
        host.channels = replace(
            host.channels,
            aggregates=tuple(
                replace(
                    item,
                    value=25.0,
                    writable=False,
                    incoming_source="SourceCurl.output",
                    incoming_source_type="multiplyDivide",
                    keyframe_writable=False,
                )
                if item is right_aggregate
                else replace(item, value=-10.0)
                if item is left_aggregate
                else item
                for item in host.channels.aggregates
            ),
            controls=tuple(
                replace(
                    item,
                    rotation=(3.0, 4.0, 5.0),
                    writable_rotation_axes=frozenset(),
                    rotation_sources=(
                        "SourceX.output",
                        "SourceY.output",
                        "SourceZ.output",
                    ),
                    rotation_source_types=(
                        "expression",
                        "expression",
                        "expression",
                    ),
                    keyframe_writable_rotation_axes=frozenset(),
                )
                if item is right_control
                else replace(item, rotation=(-1.0, -2.0, -3.0))
                if item is left_control
                else item
                for item in host.channels.controls
            ),
        )
        source_before = (right_aggregate, right_control)
        source_before = tuple(
            next(
                item for item in values
                if item.side is FitBuildSide.RIGHT
                and getattr(item, "name", None)
                == getattr(reference, "name", None)
                and getattr(item, "digit", None)
                == getattr(reference, "digit", None)
                and getattr(item, "segment", None)
                == getattr(reference, "segment", None)
            )
            for reference, values in zip(
                source_before,
                (host.channels.aggregates, host.channels.controls),
            )
        )

        with self.assertRaisesRegex(ValueError, "镜像源侧"):
            MirrorBodyHandPose(host).plan(source_side="R")
        result = MirrorBodyHandPose(host).apply(
            source_side=FitBuildSide.RIGHT,
        )
        repeated = MirrorBodyHandPose(host).apply(
            source_side=FitBuildSide.RIGHT,
        )

        source_after = tuple(
            next(
                item for item in values
                if item.side is FitBuildSide.RIGHT
                and getattr(item, "name", None)
                == getattr(reference, "name", None)
                and getattr(item, "digit", None)
                == getattr(reference, "digit", None)
                and getattr(item, "segment", None)
                == getattr(reference, "segment", None)
            )
            for reference, values in zip(
                source_before,
                (host.channels.aggregates, host.channels.controls),
            )
        )
        mirrored_aggregate = next(
            item for item in host.channels.aggregates
            if item.side is FitBuildSide.LEFT
            and item.name == right_aggregate.name
        )
        mirrored_control = next(
            item for item in host.channels.controls
            if item.side is FitBuildSide.LEFT
            and item.digit is right_control.digit
            and item.segment == right_control.segment
        )
        self.assertEqual(result.changed_channel_count, 2)
        self.assertEqual(repeated.changed_channel_count, 0)
        self.assertIs(result.plan.target_side, FitBuildSide.LEFT)
        self.assertTrue(all(
            change.side is FitBuildSide.LEFT
            for change in (
                *result.plan.changes.aggregates,
                *result.plan.changes.controls,
            )
        ))
        self.assertEqual(mirrored_aggregate.value, 25.0)
        self.assertEqual(mirrored_control.rotation, (-3.0, -4.0, 5.0))
        self.assertEqual(source_after, source_before)
        self.assertEqual(
            body_hand_pose_document_from_snapshot(host.channels),
            result.plan.expected_document,
        )
        self.assertEqual(host.transaction_count, 1)

    def test_pose_import_keys_native_animation_sources(self):
        host = FakeBodyHandPoseDocumentHost()
        source_aggregate = host.channels.aggregates[0]
        source_control = host.channels.controls[0]
        host.channels = replace(
            host.channels,
            aggregates=(replace(source_aggregate, value=25.0),)
            + host.channels.aggregates[1:],
            controls=(replace(
                source_control,
                rotation=(3.0, 4.0, 5.0),
            ),) + host.channels.controls[1:],
        )
        desired = body_hand_pose_document_from_snapshot(host.channels)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "animated-hand-pose.json"
            ExportBodyHandPose(host).apply(target)
            host.channels = replace(
                host.channels,
                aggregates=(replace(
                    source_aggregate,
                    value=-10.0,
                    writable=False,
                    incoming_source="AnimCurl.output",
                    incoming_source_type="animCurveTU",
                    keyframe_writable=True,
                ),) + host.channels.aggregates[1:],
                controls=(replace(
                    source_control,
                    rotation=(-1.0, -2.0, -3.0),
                    writable_rotation_axes=frozenset(),
                    rotation_sources=(
                        "AnimX.output",
                        "AnimY.output",
                        "AnimZ.output",
                    ),
                    rotation_source_types=(
                        "animCurveTA",
                        "animCurveTA",
                        "animCurveTA",
                    ),
                    keyframe_writable_rotation_axes=frozenset({"x", "y", "z"}),
                ),) + host.channels.controls[1:],
            )

            with self.assertRaisesRegex(ValueError, "请求模式"):
                ImportBodyHandPose(host).apply(target)
            keyed = ImportBodyHandPose(host).apply(target, keyframe=True)
            repeated = ImportBodyHandPose(host).apply(target, keyframe=True)

        self.assertEqual(keyed.changed_channel_count, 2)
        self.assertEqual(
            keyed.plan.access_mode,
            BodyHandPoseAccessMode.KEYFRAME_WRITE,
        )
        self.assertEqual(repeated.changed_channel_count, 0)
        self.assertEqual(
            body_hand_pose_document_from_snapshot(host.channels),
            desired,
        )
        self.assertTrue(host.last_keyframe)
        self.assertEqual(host.transaction_count, 1)

    def test_pose_keyframe_rejects_non_animation_driver_before_transaction(self):
        host = FakeBodyHandPoseDocumentHost()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "driven-hand-pose.json"
            ExportBodyHandPose(host).apply(target)
            first = host.channels.aggregates[0]
            host.channels = replace(
                host.channels,
                aggregates=(replace(
                    first,
                    value=10.0,
                    writable=False,
                    incoming_source="Driven.output",
                    incoming_source_type="multiplyDivide",
                    keyframe_writable=False,
                ),) + host.channels.aggregates[1:],
            )
            capture = Path(directory) / "driven-capture.json"

            ExportBodyHandPose(host).apply(capture)
            with self.assertRaisesRegex(ValueError, "请求模式"):
                ImportBodyHandPose(host).apply(target, keyframe=True)

        self.assertEqual(host.transaction_count, 0)


if __name__ == "__main__":
    unittest.main()
