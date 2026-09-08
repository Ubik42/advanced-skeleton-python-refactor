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
    plan_body_root_motion,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from test_body_export_skeleton import (
    make_bake_samples,
    make_baked_export_snapshot,
    make_body,
    make_root_motion_plan,
)


class FakeFbxHost:
    def __init__(self, *, dependencies=(), collisions=()):
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
        self.collisions = collisions
        self.export_calls = 0
        self.last_selection = None

    def scene_up_axis(self):
        return FitUpAxis.Z

    def capture_body_skeleton(self, root_name):
        return self.body

    def capture_baked_body_export_skeleton(self, plan):
        return self.baked

    def capture_body_export_dependency_plugs(self, body_root, export_paths):
        return self.dependencies

    def capture_body_fbx_published_collisions(self, selection):
        return self.collisions

    def prepare_fbx_export_runtime(self):
        return "test-fbx-1"

    def export_fbx_selection(self, destination, selection):
        self.export_calls += 1
        self.last_selection = selection
        destination.write_bytes(FBX_BINARY_MAGIC + b"\x00" * 256)


class BodyFbxExportTests(unittest.TestCase):
    def test_selection_and_readiness_require_complete_independent_bake(self):
        host = FakeFbxHost()
        selection = plan_body_fbx_export_selection(host.bake)

        self.assertEqual(selection.node_count, 4)
        self.assertEqual(selection.node_paths[0], "|AdvPy_GameRootMotion")
        self.assertEqual(selection.published_root_path, "|RootMotion")
        self.assertEqual(
            selection.published_paths,
            (
                "|RootMotion",
                "|RootMotion|Root_M",
                "|RootMotion|Root_M|Spine1_M",
                "|RootMotion|Root_M|Spine1_M|Head_M",
            ),
        )
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
            self.assertFalse(any(
                "AdvPy_EXP_" in path
                for path in host.last_selection.published_paths
            ))
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

    def test_application_blocks_published_root_collision(self):
        host = FakeFbxHost(collisions=("|RootMotion",))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "character.fbx"

            plan = ExportBodyFbx(host).plan(
                destination, start_frame=1, end_frame=3
            )

            self.assertFalse(plan.ready)
            self.assertEqual(plan.published_name_collisions, ("|RootMotion",))
            self.assertFalse(destination.exists())
            self.assertEqual(host.export_calls, 0)

    def test_published_root_name_must_be_portable(self):
        host = FakeFbxHost()

        with self.assertRaises(ValueError):
            plan_body_fbx_export_selection(
                host.bake, published_root_name="角色:Root Motion"
            )

    def test_published_names_strip_scene_namespace_and_output_prefix(self):
        body = make_body()

        def namespaced(path):
            return "|" + "|".join(
                f"RigA:{part}" for part in path.removeprefix("|").split("|")
            )

        namespaced_body = replace(
            body,
            root=namespaced(body.root),
            joints=tuple(
                replace(
                    joint,
                    path=namespaced(joint.path),
                    name=f"RigA:{joint.name}",
                    parent_path=(
                        namespaced(joint.parent_path)
                        if joint.parent_path is not None
                        else None
                    ),
                )
                for joint in body.joints
            ),
        )
        root_motion = plan_body_root_motion(
            source_root_path=namespaced_body.root,
            up_axis=FitUpAxis.Z,
        )
        export = plan_body_export_skeleton(namespaced_body, root_motion)
        bake = plan_body_export_skeleton_bake(
            export, root_motion, start_frame=1, end_frame=3
        )

        selection = plan_body_fbx_export_selection(bake)

        self.assertTrue(any("RigA:" in path for path in selection.node_paths))
        self.assertFalse(any("RigA:" in path for path in selection.published_paths))
        self.assertFalse(any(
            "AdvPy_EXP_" in path for path in selection.published_paths
        ))


if __name__ == "__main__":
    unittest.main()
