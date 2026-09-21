import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from adv_py.application import ExportBodyFbx
from adv_py.core import (
    FBX_BINARY_HEADER,
    BodyFbxAppliedProfile,
    BodyFbxCurvePolicy,
    BodyFbxEncoding,
    BodyFbxExportProfile,
    BodyFbxNamingProfile,
    BodyFbxFileVersion,
    BodyFbxLinearUnit,
    BodyRootMotionKeyState,
    FitUpAxis,
    audit_body_fbx_export_readiness,
    inspect_body_fbx_bytes,
    plan_body_export_skeleton,
    plan_body_export_skeleton_bake,
    plan_body_fbx_export_selection,
    plan_body_root_motion,
    redundant_linear_key_frames,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from test_body_export_skeleton import (
    make_bake_samples,
    make_baked_export_snapshot,
    make_body,
    make_root_motion_plan,
)


class FakeFbxHost:
    def __init__(
        self,
        *,
        dependencies=(),
        collisions=(),
        scene_unit=BodyFbxLinearUnit.CENTIMETER,
    ):
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
        self.scene_unit = scene_unit
        self.export_calls = 0
        self.last_selection = None

    def scene_up_axis(self):
        return FitUpAxis.Z

    def scene_linear_unit(self):
        return self.scene_unit

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

    def export_fbx_selection(self, destination, selection, profile):
        self.export_calls += 1
        self.last_selection = selection
        if profile.encoding is BodyFbxEncoding.ASCII:
            destination.write_bytes(
                b"; FBX 7.7.0 project file\nFBXVersion: "
                + str(profile.format_version).encode("ascii")
                + b"\n"
                + b" " * 256
            )
        else:
            destination.write_bytes(
                FBX_BINARY_HEADER
                + profile.format_version.to_bytes(4, "little")
                + b"\x00" * 256
            )
        return BodyFbxAppliedProfile(
            file_version=profile.file_version.value,
            up_axis=profile.up_axis.value.lower(),
            scale_factor=profile.scale_factor_from(self.scene_unit),
            encoding=profile.encoding.value,
        )


class BodyFbxExportTests(unittest.TestCase):
    def test_lossless_linear_policy_keeps_bends_and_endpoints(self):
        def keys(values):
            return tuple(BodyRootMotionKeyState(frame=index, value=value,
                in_tangent="linear", out_tangent="linear")
                for index, value in enumerate(values, 1))

        self.assertEqual(redundant_linear_key_frames(keys((0., 2., 4., 6.))), (2, 3))
        self.assertEqual(redundant_linear_key_frames(keys((0., 2., 5., 6.))), ())
        self.assertEqual(redundant_linear_key_frames(keys((0., 2., 4., 7.))), (2,))
        self.assertEqual(redundant_linear_key_frames(keys((3., 3., 3.))), (2,))
        self.assertEqual(BodyFbxExportProfile(BodyFbxFileVersion.FBX_2020,
            FitUpAxis.Z, BodyFbxLinearUnit.CENTIMETER).curve_policy,
            BodyFbxCurvePolicy.SAMPLED_LINEAR)
        with self.assertRaises(ValueError):
            BodyFbxExportProfile(BodyFbxFileVersion.FBX_2020,
                FitUpAxis.Z, BodyFbxLinearUnit.CENTIMETER,
                curve_policy="lossless_linear")

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
        artifact = inspect_body_fbx_bytes(
            FBX_BINARY_HEADER + (7700).to_bytes(4, "little") + b"\x00" * 256
        )

        self.assertEqual(artifact.encoding, "binary")
        self.assertEqual(artifact.format_version, 7700)
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
            self.assertEqual(result.artifact.format_version, 7700)
            self.assertEqual(result.plugin_version, "test-fbx-1")
            self.assertEqual(
                result.plan.profile,
                BodyFbxExportProfile(
                    BodyFbxFileVersion.FBX_2020,
                    FitUpAxis.Z,
                    BodyFbxLinearUnit.CENTIMETER,
                ),
            )
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

    def test_engine_naming_profile_maps_export_joints_and_rejects_collisions(self):
        host=FakeFbxHost()
        naming=BodyFbxNamingProfile('GameRoot',(('Root_M','pelvis'),('Spine1_M','spine_01'),('Head_M','head')))
        selection=plan_body_fbx_export_selection(host.bake,published_root_name=naming.root_name,
                                                  published_joint_names=naming.joint_names)
        self.assertEqual(tuple(node.published_name for node in selection.published_nodes),
                         ('GameRoot','pelvis','spine_01','head'))
        with tempfile.TemporaryDirectory() as directory:
            plan=ExportBodyFbx(host).plan(Path(directory)/'character.fbx',start_frame=1,end_frame=3,
                                           naming_profile=naming)
            self.assertEqual(plan.selection,selection)
        with self.assertRaisesRegex(ValueError,'重复'):
            BodyFbxNamingProfile('GameRoot',(('Root_M','pelvis'),('Head_M','pelvis')))
        with self.assertRaisesRegex(ValueError,'之外'):
            plan_body_fbx_export_selection(host.bake,published_joint_names=(('NoJoint','missing'),))
        with self.assertRaisesRegex(ValueError,'重复'):
            plan_body_fbx_export_selection(host.bake,published_joint_names=(('Head_M','Spine1_M'),))

    def test_custom_ascii_y_up_meter_profile_is_applied_and_verified(self):
        host = FakeFbxHost()
        profile = BodyFbxExportProfile(
            BodyFbxFileVersion.FBX_2018,
            FitUpAxis.Y,
            BodyFbxLinearUnit.METER,
            BodyFbxEncoding.ASCII,
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "character.fbx"

            result = ExportBodyFbx(host).apply(
                destination,
                start_frame=1,
                end_frame=3,
                profile=profile,
            )

            self.assertEqual(result.applied_profile.scale_factor, 100.0)
            self.assertEqual(result.applied_profile.up_axis, "y")
            self.assertEqual(result.artifact.encoding, "ascii")
            self.assertEqual(result.artifact.format_version, 7500)

    def test_default_meter_scene_profile_uses_identity_scale(self):
        host = FakeFbxHost(scene_unit=BodyFbxLinearUnit.METER)
        with tempfile.TemporaryDirectory() as directory:
            result = ExportBodyFbx(host).apply(
                Path(directory) / "meter-scene.fbx",
                start_frame=1,
                end_frame=3,
            )

        self.assertEqual(result.plan.profile.linear_unit, BodyFbxLinearUnit.METER)
        self.assertEqual(result.applied_profile.scale_factor, 1.0)


if __name__ == "__main__":
    unittest.main()
