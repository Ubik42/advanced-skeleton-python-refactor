import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from adv_py.application import (
    CreateAndImportFitSkeleton,
    ExportFitSkeleton,
    ImportFitSkeleton,
    MergeFitSkeleton,
)
from adv_py.core import (
    FIT_SKELETON_NONPORTABLE_SETTING_FIELDS,
    FitContainerDisplayStyle,
    FitContainerShape,
    FitContainerState,
    FitHierarchyNode,
    FitHierarchySnapshot,
    FitJointField,
    FitJointMetadata,
    FitJointOrientationState,
    FitLocalDirection,
    FitOrientationAxisConfiguration,
    FitOrientationSnapshot,
    FitSkeletonField,
    FitSkeletonJointDocument,
    FitSkeletonJointMetadataValue,
    FitSkeletonSettingChannelState,
    FitUpAxis,
    JointLabel,
    default_fit_skeleton_settings,
    fit_skeleton_document_from_json,
    fit_skeleton_document_from_snapshot,
    fit_skeleton_document_to_json,
    fit_skeleton_documents_match,
)


IDENTITY_AXES = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)
TURNED_AXES = (
    (0.0, 1.0, 0.0),
    (-1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0),
)


def _settings(container, *, source):
    settings = default_fit_skeleton_settings(container)
    if not source:
        return settings
    return replace(
        settings,
        settings=tuple(
            replace(item, value=0.35)
            if item.field is FitSkeletonField.VIS_GAP
            else replace(item, value=True)
            if item.field is FitSkeletonField.VIS_GEOMETRY
            else item
            for item in settings.settings
        ),
    )


def _source_joints():
    label = JointLabel.parse
    return (
        FitSkeletonJointDocument(
            "Root",
            None,
            (0.0, 0.0, 0.0),
            IDENTITY_AXES,
            label("Root"),
            (
                FitSkeletonJointMetadataValue(
                    FitJointField.GLOBAL_TRANSLATE,
                    True,
                ),
            ),
        ),
        FitSkeletonJointDocument(
            "Spine1",
            "Root",
            (0.0, 0.0, 5.0),
            TURNED_AXES,
            label("Spine"),
            (
                FitSkeletonJointMetadataValue(
                    FitJointField.TWIST_JOINTS,
                    2,
                ),
                FitSkeletonJointMetadataValue(
                    FitJointField.BENDY_CONTROLS,
                    1,
                ),
            ),
        ),
        FitSkeletonJointDocument(
            "Spine2",
            "Spine1",
            (0.0, 0.0, 4.0),
            TURNED_AXES,
            label("Spine"),
        ),
    )


class FakeFitSkeletonDocumentHost:
    def __init__(self, *, populated):
        self.container = "|FitSkeleton"
        self.joints = _source_joints() if populated else ()
        self.settings = _settings(self.container, source=populated)
        self.axis_configuration = FitOrientationAxisConfiguration(
            FitLocalDirection.POSITIVE_X,
            FitLocalDirection.POSITIVE_Y,
            False,
        )
        self.blocked_settings = set()
        self.external_collisions = {}
        self.transaction_count = 0
        self.scene_read_count = 0

    def scene_up_axis(self):
        return FitUpAxis.Z

    def inspect_fit_container(self, name):
        del name
        self.scene_read_count += 1
        return FitContainerState(
            self.container,
            "FitSkeleton",
            FitContainerShape.RING,
            FitContainerDisplayStyle.FIT,
            frozenset({"tx", "ty", "tz", "rx", "ry", "rz"}),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (6.0, 6.0, 0.0),
        )

    def _paths(self):
        paths = {}
        for joint in self.joints:
            parent = self.container if joint.parent is None else paths[joint.parent]
            paths[joint.name] = f"{parent}|{joint.name}"
        return paths

    def capture_fit_orientation(self, container_name):
        del container_name
        paths = self._paths()
        world_positions = {}
        nodes = []
        states = []
        metadata = []
        for joint in self.joints:
            parent = self.container if joint.parent is None else paths[joint.parent]
            parent_world = world_positions.get(parent, (0.0, 0.0, 0.0))
            world = tuple(
                first + second
                for first, second in zip(parent_world, joint.local_position)
            )
            path = paths[joint.name]
            world_positions[path] = world
            nodes.append(
                FitHierarchyNode(
                    path,
                    joint.name,
                    parent,
                    joint.local_position,
                    world,
                )
            )
            states.append(
                FitJointOrientationState(
                    path,
                    (0.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0),
                    joint.world_axes,
                )
            )
            values = {item.field.value: item.value for item in joint.metadata}
            metadata.append(
                FitJointMetadata(
                    joint=path,
                    present_fields=frozenset(
                        item.field for item in joint.metadata
                    ),
                    **values,
                )
            )
        hierarchy = FitHierarchySnapshot(self.container, tuple(nodes))
        return FitOrientationSnapshot(
            hierarchy,
            FitUpAxis.Z,
            tuple(states),
            tuple(metadata),
            self.axis_configuration,
        )

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    def read_joint_label(self, joint):
        by_path = {
            path: item.label
            for item, path in zip(self.joints, self._paths().values())
        }
        return by_path.get(joint)

    def capture_fit_skeleton_setting_channels(self, container_name):
        del container_name
        return tuple(
            FitSkeletonSettingChannelState(
                item.field,
                item.value,
                item.field not in self.blocked_settings,
                ("Driver.output",)
                if item.field in self.blocked_settings
                else (),
            )
            for item in self.settings.settings
        )

    def find_name_collisions(self, name):
        own = tuple(
            path
            for joint_name, path in self._paths().items()
            if joint_name == name
        )
        return own + tuple(self.external_collisions.get(name, ()))

    @contextmanager
    def transaction(self, label):
        del label
        before = (self.joints, self.settings)
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.joints, self.settings = before
            raise

    def set_fit_skeleton_setting(self, container, setting):
        del container
        self.settings = replace(
            self.settings,
            settings=tuple(
                setting if item.field is setting.field else item
                for item in self.settings.settings
            ),
        )

    def create_fit_joint(self, parent, spec):
        path = f"{parent}|{spec.name}"
        self.joints += (
            FitSkeletonJointDocument(
                spec.name,
                spec.parent,
                spec.local_position,
                IDENTITY_AXES,
                spec.label,
            ),
        )
        return path

    def _replace_joint(self, name, **values):
        self.joints = tuple(
            replace(item, **values) if item.name == name else item
            for item in self.joints
        )

    def set_joint_label(self, joint, label):
        self._replace_joint(joint.rsplit("|", 1)[-1], label=label)

    def apply_fit_joint_edit(self, joint, edit):
        name = joint.rsplit("|", 1)[-1]
        record = next(item for item in self.joints if item.name == name)
        values = {
            item.field: item.value
            for item in record.metadata
        }
        values[edit.field] = edit.value
        metadata = tuple(
            FitSkeletonJointMetadataValue(field, values[field])
            for field in FitJointField
            if field in values
        )
        self._replace_joint(name, metadata=metadata)

    def set_fit_joint_world_axes(self, joint, world_axes):
        self._replace_joint(
            joint.rsplit("|", 1)[-1],
            world_axes=world_axes,
        )

    def add_fit_orientation_axis_configuration(
        self,
        container,
        configuration,
    ):
        if container != self.container:
            raise ValueError("容器不存在")
        self.axis_configuration = configuration


class FakeNewFitSkeletonHost(FakeFitSkeletonDocumentHost):
    def __init__(self):
        super().__init__(populated=False)
        self.container_exists = False
        self.settings = replace(self.settings, settings=())

    def inspect_fit_container(self, name):
        if not self.container_exists:
            raise ValueError(f"容器不存在：{name}")
        return super().inspect_fit_container(name)

    def find_name_collisions(self, name):
        collisions = list(super().find_name_collisions(name))
        if self.container_exists and name == self.container.rsplit("|", 1)[-1]:
            collisions.append(self.container)
        return tuple(collisions)

    @contextmanager
    def transaction(self, label):
        del label
        before = (
            self.container,
            self.container_exists,
            self.joints,
            self.settings,
            self.axis_configuration,
        )
        self.transaction_count += 1
        try:
            yield
        except Exception:
            (
                self.container,
                self.container_exists,
                self.joints,
                self.settings,
                self.axis_configuration,
            ) = before
            raise

    def create_fit_container(self, spec):
        if self.container_exists:
            raise ValueError("容器已经存在")
        self.container = f"|{spec.name}"
        self.container_exists = True
        self.settings = replace(self.settings, container=self.container)
        return self.container

    def add_fit_skeleton_setting(self, container, setting):
        if not self.container_exists or container != self.container:
            raise ValueError("容器不存在")
        self.settings = replace(
            self.settings,
            settings=self.settings.settings + (setting,),
        )


def _document(host):
    snapshot = host.capture_fit_orientation(host.container)
    labels = tuple(
        (node.path, host.read_joint_label(node.path))
        for node in snapshot.hierarchy.joints
    )
    return fit_skeleton_document_from_snapshot(
        snapshot,
        host.settings,
        labels,
    )


class FitSkeletonIoTests(unittest.TestCase):
    def test_document_round_trip_is_path_free_and_tamper_evident(self):
        document = _document(FakeFitSkeletonDocumentHost(populated=True))
        text = fit_skeleton_document_to_json(document)
        restored = fit_skeleton_document_from_json(text)

        self.assertEqual(restored, document)
        self.assertNotIn("|FitSkeleton", text)
        for field in FIT_SKELETON_NONPORTABLE_SETTING_FIELDS:
            self.assertNotIn(field.value, text)

        data = json.loads(text)
        data["joints"][1]["local_position"][2] = 9.0
        with self.assertRaisesRegex(ValueError, "摘要"):
            fit_skeleton_document_from_json(json.dumps(data))

    def test_export_then_import_restores_settings_metadata_labels_and_axes(self):
        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FakeFitSkeletonDocumentHost(populated=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "角色.fit.json"
            exported = ExportFitSkeleton(source).apply(path)
            preview = ImportFitSkeleton(target).plan(path)
            imported = ImportFitSkeleton(target).apply(path)

            self.assertGreater(exported.bytes_written, 0)
            self.assertTrue(preview.ready)
            self.assertEqual(preview.joint_count, 3)
            self.assertEqual(preview.changed_setting_count, 2)
            self.assertTrue(
                fit_skeleton_documents_match(
                    imported.verified_document,
                    exported.plan.document,
                )
            )
            self.assertEqual(target.transaction_count, 1)
            self.assertEqual(target.joints[0].metadata[0].value, True)
            self.assertEqual(target.joints[1].world_axes, TURNED_AXES)
            self.assertEqual(target.joints[1].label.text, "Spine")
            with self.assertRaisesRegex(ValueError, "必须为空"):
                ImportFitSkeleton(target).apply(path)
            self.assertEqual(target.transaction_count, 1)
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                ExportFitSkeleton(source).apply(path)

    def test_corrupt_file_and_driven_setting_stop_before_transaction(self):
        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FakeFitSkeletonDocumentHost(populated=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "角色.fit.json"
            ExportFitSkeleton(source).apply(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["joints"][0]["label"] = "Other"
            corrupt = Path(directory) / "损坏.fit.json"
            corrupt.write_text(json.dumps(data), encoding="utf-8")
            target.scene_read_count = 0
            with self.assertRaisesRegex(ValueError, "损坏"):
                ImportFitSkeleton(target).plan(corrupt)
            self.assertEqual(target.scene_read_count, 0)

            target.blocked_settings.add(FitSkeletonField.VIS_GAP)
            preview = ImportFitSkeleton(target).plan(path)
            self.assertFalse(preview.ready)
            with self.assertRaisesRegex(ValueError, "不可安全写入"):
                ImportFitSkeleton(target).apply(path)
            self.assertEqual(target.transaction_count, 0)
            self.assertFalse(target.joints)

    def test_postcheck_failure_rolls_back_settings_and_all_joints(self):
        class FaultyHost(FakeFitSkeletonDocumentHost):
            def set_fit_joint_world_axes(self, joint, world_axes):
                del world_axes
                super().set_fit_joint_world_axes(joint, IDENTITY_AXES)

        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FaultyHost(populated=False)
        before_settings = target.settings
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "角色.fit.json"
            ExportFitSkeleton(source).apply(path)
            with self.assertRaisesRegex(RuntimeError, "语义复检失败"):
                ImportFitSkeleton(target).apply(path)

        self.assertEqual(target.transaction_count, 1)
        self.assertFalse(target.joints)
        self.assertEqual(target.settings, before_settings)

    def test_additive_merge_preserves_existing_joint_and_is_idempotent(self):
        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FakeFitSkeletonDocumentHost(populated=False)
        target.joints = _source_joints()[:1]
        target.settings = _settings(target.container, source=True)
        existing_root = target.joints[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "完整角色.fit.json"
            exported = ExportFitSkeleton(source).apply(path)
            preview = MergeFitSkeleton(target).plan(path)
            merged = MergeFitSkeleton(target).apply(path)

            self.assertTrue(preview.ready)
            self.assertEqual(preview.added_joint_count, 2)
            self.assertEqual(target.joints[0], existing_root)
            self.assertTrue(
                fit_skeleton_documents_match(
                    merged.verified_document,
                    exported.plan.document,
                )
            )
            self.assertEqual(target.transaction_count, 1)

            repeated = MergeFitSkeleton(target).apply(path)
            self.assertEqual(repeated.plan.added_joint_count, 0)
            self.assertFalse(repeated.joint_paths)
            self.assertEqual(target.transaction_count, 1)

    def test_merge_conflict_and_external_name_collision_stop_before_transaction(self):
        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FakeFitSkeletonDocumentHost(populated=False)
        target.joints = _source_joints()[:2]
        target.settings = _settings(target.container, source=True)
        target._replace_joint("Spine1", local_position=(0.0, 0.0, 6.0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "完整角色.fit.json"
            ExportFitSkeleton(source).apply(path)
            conflict = MergeFitSkeleton(target).plan(path)
            self.assertFalse(conflict.ready)
            self.assertIn("joint_conflict", {
                issue.code for issue in conflict.document_merge.issues
            })
            with self.assertRaisesRegex(ValueError, "同名 Fit joint"):
                MergeFitSkeleton(target).apply(path)
            self.assertEqual(target.transaction_count, 0)

            target.joints = _source_joints()[:1]
            target.external_collisions["Spine1"] = ("|Other|Spine1",)
            collision = MergeFitSkeleton(target).plan(path)
            self.assertFalse(collision.ready)
            with self.assertRaisesRegex(ValueError, "场景节点重名"):
                MergeFitSkeleton(target).apply(path)
            self.assertEqual(target.transaction_count, 0)

    def test_merge_postcheck_failure_rolls_back_only_new_joints(self):
        class FaultyMergeHost(FakeFitSkeletonDocumentHost):
            def set_fit_joint_world_axes(self, joint, world_axes):
                del world_axes
                super().set_fit_joint_world_axes(joint, IDENTITY_AXES)

        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FaultyMergeHost(populated=False)
        target.joints = _source_joints()[:1]
        target.settings = _settings(target.container, source=True)
        before = target.joints
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "完整角色.fit.json"
            ExportFitSkeleton(source).apply(path)
            with self.assertRaisesRegex(RuntimeError, "合并后语义复检失败"):
                MergeFitSkeleton(target).apply(path)

        self.assertEqual(target.transaction_count, 1)
        self.assertEqual(target.joints, before)

    def test_create_and_import_builds_container_settings_and_joints_once(self):
        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FakeNewFitSkeletonHost()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "新角色.fit.json"
            exported = ExportFitSkeleton(source).apply(path)
            preview = CreateAndImportFitSkeleton(target).plan(path)
            created = CreateAndImportFitSkeleton(target).apply(path)

            self.assertTrue(preview.ready)
            self.assertEqual(preview.joint_count, 3)
            self.assertEqual(target.scene_read_count, 1)
            self.assertTrue(target.container_exists)
            self.assertEqual(
                len(target.settings.settings),
                len(FitSkeletonField),
            )
            self.assertTrue(
                fit_skeleton_documents_match(
                    created.verified_document,
                    exported.plan.document,
                )
            )
            self.assertEqual(target.transaction_count, 1)

            repeated = CreateAndImportFitSkeleton(target).plan(path)
            self.assertFalse(repeated.ready)
            with self.assertRaisesRegex(ValueError, "场景节点重名"):
                CreateAndImportFitSkeleton(target).apply(path)
            self.assertEqual(target.transaction_count, 1)

    def test_create_import_restores_nondefault_axes_and_rejects_conflicts(self):
        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FakeNewFitSkeletonHost()
        target.external_collisions["Root"] = ("|Other|Root",)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "新角色.fit.json"
            ExportFitSkeleton(source).apply(path)
            collision = CreateAndImportFitSkeleton(target).plan(path)
            self.assertFalse(collision.ready)
            self.assertEqual(target.transaction_count, 0)
            self.assertFalse(target.container_exists)

            source.axis_configuration = FitOrientationAxisConfiguration(
                FitLocalDirection.POSITIVE_Y,
                FitLocalDirection.POSITIVE_Z,
                False,
            )
            nondefault_path = Path(directory) / "非默认轴.fit.json"
            ExportFitSkeleton(source).apply(nondefault_path)
            target.external_collisions.clear()
            nondefault = CreateAndImportFitSkeleton(target).plan(
                nondefault_path
            )
            self.assertTrue(nondefault.ready)
            created = CreateAndImportFitSkeleton(target).apply(
                nondefault_path
            )
            self.assertEqual(
                created.verified.orientation.axis_configuration,
                source.axis_configuration,
            )
            self.assertEqual(target.transaction_count, 1)
            self.assertTrue(target.container_exists)

            class YUpNewHost(FakeNewFitSkeletonHost):
                def scene_up_axis(self):
                    return FitUpAxis.Y

            mismatch = YUpNewHost()
            mismatch_preview = CreateAndImportFitSkeleton(mismatch).plan(path)
            self.assertFalse(mismatch_preview.ready)
            self.assertIn("Up Axis", "；".join(mismatch_preview.blockers))
            self.assertEqual(mismatch.transaction_count, 0)
            self.assertFalse(mismatch.container_exists)

    def test_create_import_postcheck_failure_removes_container_and_tree(self):
        class FaultyCreateHost(FakeNewFitSkeletonHost):
            def set_fit_joint_world_axes(self, joint, world_axes):
                del world_axes
                super().set_fit_joint_world_axes(joint, IDENTITY_AXES)

        source = FakeFitSkeletonDocumentHost(populated=True)
        target = FaultyCreateHost()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "新角色.fit.json"
            ExportFitSkeleton(source).apply(path)
            with self.assertRaisesRegex(RuntimeError, "语义复检失败"):
                CreateAndImportFitSkeleton(target).apply(path)

        self.assertEqual(target.transaction_count, 1)
        self.assertFalse(target.container_exists)
        self.assertFalse(target.joints)
        self.assertFalse(target.settings.settings)


if __name__ == "__main__":
    unittest.main()
