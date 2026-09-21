from dataclasses import replace
import unittest

from adv_py.application import BuildBodyCharacterRig, BuildOrientedBodySkeleton
from adv_py.core.body_torso import plan_body_torso
from adv_py.core.body_character_global import plan_body_character_global, BodyCharacterGlobalValidationError
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_container import FitUpAxis
from test_body_skeleton import FakeBodySkeletonHost


class BodyTorsoTests(unittest.TestCase):
    def setUp(self):
        self.host = FakeBodySkeletonHost(with_hand=True)
        self.body = BuildOrientedBodySkeleton(self.host).apply().snapshot
        self.character = BuildBodyCharacterRig(self.host).plan()

    def plan(self, body=None, **options):
        return plan_body_torso(body or self.body, self.character.arm, self.character.leg, **options)

    def test_hierarchy_and_limb_origins_are_explicit(self):
        plan = self.plan()
        self.assertEqual(len(plan.controls.controls), 7)
        self.assertEqual(len(plan.attachments), 16)
        self.assertEqual(len(plan.node_names), len(set(plan.node_names)))
        controls = {spec.driven_joint.rsplit("|", 1)[-1]: spec for spec in plan.controls.controls}
        self.assertEqual(controls["Head_M"].parent_path, controls["Neck_M"].control_path)
        self.assertEqual(controls["Scapula_L"].parent_path, controls["Chest_M"].control_path)
        self.assertEqual(plan.pelvis_translation.target, self.body.root)
        origins = [spec for spec in plan.attachments if spec.translation_only]
        self.assertEqual(len(origins), 12)
        self.assertTrue(all(spec.kind == "parentConstraint" for spec in origins))
        self.assertFalse(any("IKControls" in spec.target for spec in plan.attachments))

    def test_missing_or_wrong_parent_is_rejected(self):
        missing = replace(self.body, joints=tuple(j for j in self.body.joints if j.name != "Neck_M"))
        wrong = replace(self.body, joints=tuple(
            replace(j, parent_path=self.body.root) if j.name == "Head_M" else j
            for j in self.body.joints
        ))
        for body in (missing, wrong):
            with self.assertRaises(FitSkeletonValidationError):
                self.plan(body)

    def test_invalid_radius_rejected(self):
        for radius in (0, -1, True, float("nan"), float("inf")):
            with self.assertRaises(FitSkeletonValidationError):
                self.plan(radius=radius)

    def test_head_aim_adds_independent_blend_frame_and_forward_target(self):
        plan=self.plan(head_aim=True)
        aim=plan.head_aim
        control=next(c for c in plan.controls.controls if c.control_path==aim.head_control)
        self.assertEqual(control.control_parent_path,aim.pivot)
        self.assertEqual(aim.pivot,control.offset_path+'|AdvPy_HeadAimBlend')
        delta=tuple(a-b for a,b in zip(aim.position,control.world_position))
        self.assertGreater(delta[1],0.)
        self.assertAlmostEqual(delta[0],0.)
        self.assertAlmostEqual(delta[2],0.)
        self.assertEqual(len(plan.node_names),len(set(plan.node_names)))
        self.assertFalse(aim.target.startswith(aim.offset+'|'))

    def test_head_aim_requires_boolean_opt_in(self):
        for value in (1,'yes',None):
            with self.assertRaises(FitSkeletonValidationError):self.plan(head_aim=value)

    def test_global_root_via_controls_requires_explicit_scale(self):
        options = dict(up_axis=FitUpAxis.Z, body_root="|Root_M",
                       driven_roots=("|AdvPy_TorsoControls",), body_root_via_controls=True)
        with self.assertRaises(BodyCharacterGlobalValidationError):
            plan_body_character_global(**options, scale_destinations=("|Settings.scale",))
        plan = plan_body_character_global(**options, scale_destinations=tuple(f"|Root_M.scale{a}" for a in "XYZ"))
        self.assertNotIn("|Root_M", plan.driven_roots)


if __name__ == "__main__":
    unittest.main()
