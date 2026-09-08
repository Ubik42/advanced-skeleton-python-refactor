import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from adv_py.application import ExportBodyFbx
from adv_py.core import (
    FBX_BINARY_MAGIC,
    FitUpAxis,
    audit_body_fbx_export_readiness,
    inspect_body_fbx_bytes,
    plan_body_export_skeleton,
    plan_body_export_skeleton_bake,
    plan_body_fbx_export_selection,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from test_body_export_skeleton import (
    make_bake_samples,
    make_baked_export_snapshot,
    make_body,
    make_root_motion_plan,
)


class FakeFbxHost:
    def __init__(self, *, dependencies=()):
        self.body = make_body()
        root_motion = make_root_motion_plan()
        export = plan_body_export_skeleton(self.body, root_motion)
        self.bake = plan_body_export_skeleton_bake(
            export, root_motion, start_frame=1, end_frame=3
        )
        self.baked = make_baked_export_snapshot(
            self.bake, make_bake_samples(self.bake)
        )
        self.dependencies = dependencies
        self.export_calls = 0

    def scene_up_axis(self):
        return FitUpAxis.Z

    def capture_body_skeleton(self, root_name):
        return self.body

    def capture_baked_body_export_skeleton(self, plan):
        return self.baked

    def capture_body_export_dependency_plugs(self, body_root, export_paths):
        return self.dependencies

    def prepare_fbx_export_runtime(self):
        return "test-fbx-1"

    def export_fbx_selection(self, destination, selection):
        self.export_calls += 1
        destination.write_bytes(FBX_BINARY_MAGIC + b"\x00" * 256)


class BodyFbxExportTests(unittest.TestCase):
    def test_selection_and_readiness_require_complete_independent_bake(self):
        host = FakeFbxHost()
        selection = plan_body_fbx_export_selection(host.bake)

        self.assertEqual(selection.node_count, 4)
        self.assertEqual(selection.node_paths[0], "|AdvPy_GameRootMotion")
        self.assertEqual(
            audit_body_fbx_export_readiness(host.bake, host.baked, ()), ()
        )

        broken = replace(
            host.baked,
            joints=(replace(host.baked.joints[0], source_message_exists=True),)
            + host.baked.joints[1:],
        )
        codes = {
            issue.code
            for issue in audit_body_fbx_export_readiness(
                host.bake, broken, ("|Root_M.message -> export.message",)
            )
        }
        self.assertEqual(
            codes, {"fbx_source_message_remains", "fbx_body_dependency_remains"}
        )

    def test_artifact_inspection_accepts_fbx_and_rejects_unknown_bytes(self):
        artifact = inspect_body_fbx_bytes(FBX_BINARY_MAGIC + b"\x00" * 256)

        self.assertEqual(artifact.encoding, "binary")
        self.assertEqual(len(artifact.content_sha256), 64)
        with self.assertRaises(ValueError):
            inspect_body_fbx_bytes(b"not an fbx" * 30)

    def test_application_publishes_once_without_overwrite(self):
        host = FakeFbxHost()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "character.fbx"

            result = ExportBodyFbx(host).apply(
                destination, start_frame=1, end_frame=3
            )

            self.assertTrue(destination.is_file())
            self.assertEqual(result.artifact.encoding, "binary")
            self.assertEqual(result.plugin_version, "test-fbx-1")
            self.assertEqual(host.export_calls, 1)
            with self.assertRaises(FitSkeletonValidationError):
                ExportBodyFbx(host).apply(
                    destination, start_frame=1, end_frame=3
                )
            self.assertEqual(host.export_calls, 1)

    def test_application_blocks_body_dependency_before_loading_plugin(self):
        host = FakeFbxHost(dependencies=("body -> export",))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "character.fbx"

            with self.assertRaises(FitSkeletonValidationError):
                ExportBodyFbx(host).apply(
                    destination, start_frame=1, end_frame=3
                )

            self.assertFalse(destination.exists())
            self.assertEqual(host.export_calls, 0)


if __name__ == "__main__":
    unittest.main()
