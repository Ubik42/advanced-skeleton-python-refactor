import unittest
from dataclasses import replace

from adv_py.core import (
    BodyCharacterDrivenRootState,
    BodyCharacterGlobalSnapshot,
    BodyCharacterGlobalValidationError,
    FitUpAxis,
    audit_body_character_global,
    plan_body_character_global,
)


DRIVEN_ROOTS = (
    "|Root_M",
    "|AdvPy_ArmMechanisms",
    "|AdvPy_ArmFKControls",
    "|AdvPy_ArmIKControls",
    "|AdvPy_ArmTwistJoints",
    "|AdvPy_LegMechanisms",
    "|AdvPy_LegFKControls",
    "|AdvPy_LegIKControls",
    "|AdvPy_LegTwistJoints",
)
SCALE_DESTINATIONS = (
    "AdvPy_ArmSettings.armGlobalScale",
    "AdvPy_LegSettings.legGlobalScale",
)


def make_plan():
    return plan_body_character_global(
        up_axis=FitUpAxis.Z,
        body_root="|Root_M",
        driven_roots=DRIVEN_ROOTS,
        scale_destinations=SCALE_DESTINATIONS,
    )


def make_snapshot(plan):
    translate = tuple(
        f"{plan.control_path}.translate{axis}" for axis in "XYZ"
    )
    rotate = tuple(
        f"{plan.control_path}.rotate{axis}" for axis in "XYZ"
    )
    scale = (plan.scale_source,) * 3
    return BodyCharacterGlobalSnapshot(
        group_path=plan.group_path,
        group_parent_path=None,
        motion_system_path=plan.motion_system_path,
        motion_system_parent_path=plan.group_path,
        main_system_path=plan.main_system_path,
        main_system_parent_path=plan.motion_system_path,
        root_path=plan.root_path,
        root_parent_path=plan.main_system_path,
        root_translation=(0.0, 0.0, 0.0),
        root_rotation=(0.0, 0.0, 0.0),
        root_scale=(1.0, 1.0, 1.0),
        offset_path=plan.offset_path,
        offset_parent_path=plan.root_path,
        offset_translation=(0.0, 0.0, 0.0),
        offset_rotation=(0.0, 0.0, 0.0),
        offset_scale=(1.0, 1.0, 1.0),
        control_path=plan.control_path,
        control_parent_path=plan.offset_path,
        control_shape_type="nurbsCurve",
        control_shape_visibility_source=(
            plan.motion_system_path + ".visibility"),
        control_translation=(0.0, 0.0, 0.0),
        control_rotation=(0.0, 0.0, 0.0),
        control_scale=(1.0, 1.0, 1.0),
        scale_attribute_plug=plan.scale_source,
        scale_attribute_value=1.0,
        scale_attribute_minimum=0.0001,
        control_scale_sources=scale,
        driven_roots=tuple(
            BodyCharacterDrivenRootState(
                path,
                None,
                translate,
                rotate,
                scale,
            )
            for path in plan.driven_roots
        ),
        scale_destination_sources=tuple(
            (plug, plan.scale_source)
            for plug in plan.scale_destinations
        ),
        scale_node_input_sources=tuple(
            f"{plan.control_path}.scale{axis}" for axis in "XYZ"),
        scale_node_operation=1,
        scale_node_input2=(1.0, 1.0, 1.0),
        scale_node_output=(1.0, 1.0, 1.0),
        aim_fk_visibility_value=True,
        reserved_visibility_values=tuple(
            (name, True) for name in plan.reserved_visibility_attributes),
    )


class BodyCharacterGlobalTests(unittest.TestCase):
    def test_source_single_root_height_includes_ground(self):
        from adv_py.core.body_character_global import fit_character_height
        self.assertEqual(fit_character_height(((0., 5., -2.),)), 5.)
        self.assertEqual(fit_character_height(((0., 0., 0.),)), 0.)
        self.assertEqual(fit_character_height(((0., -.5, 0.),)), .5)

    def test_matrix_follow_needs_no_duplicate_local_scale_input(self):
        plan = plan_body_character_global(
            up_axis=FitUpAxis.Y, body_root='|Group|DeformationSystem|Root_M',
            driven_roots=('|Group|MotionSystem|FKSystem',),
            scale_destinations=(), body_root_via_controls=True,
            root_follow_main_path='|Group|MotionSystem|RootSystem|RootFollowMain',
            root_follow_use_opm=True, fit_height=0.)
        self.assertEqual(plan.scale_destinations, ())
        with self.assertRaises(BodyCharacterGlobalValidationError):
            plan_body_character_global(
                up_axis=FitUpAxis.Y, body_root='|Group|DeformationSystem|Root_M',
                driven_roots=('|Group|MotionSystem|FKSystem',),
                scale_destinations=(), body_root_via_controls=True)

    def test_plan_defines_z_up_control_and_complete_root_set(self):
        plan = make_plan()

        self.assertEqual(plan.circle_normal, (0.0, 0.0, 1.0))
        self.assertEqual(plan.control_path, (
            "|Group|MotionSystem|MainSystem|AdvPy_CharacterControls"
            "|AdvPy_GlobalOffset|AdvPy_Global"
        ))
        self.assertEqual(plan.driven_roots, DRIVEN_ROOTS)
        self.assertEqual(plan.scale_destinations, SCALE_DESTINATIONS)

    def test_plan_rejects_ambiguous_or_non_root_inputs(self):
        invalid = (
            (DRIVEN_ROOTS + ("|Root_M",), SCALE_DESTINATIONS, 12.0),
            (("|Root_M|Nested",), SCALE_DESTINATIONS, 12.0),
            (DRIVEN_ROOTS, (), 12.0),
            (DRIVEN_ROOTS, SCALE_DESTINATIONS, 0.0),
        )
        for roots, destinations, radius in invalid:
            with self.subTest(roots=roots, destinations=destinations, radius=radius):
                with self.assertRaises(BodyCharacterGlobalValidationError):
                    plan_body_character_global(
                        up_axis=FitUpAxis.Z,
                        body_root="|Root_M",
                        driven_roots=roots,
                        scale_destinations=destinations,
                        radius=radius,
                    )

    def test_audit_reports_a_broken_driven_scale_source(self):
        plan = make_plan()
        snapshot = make_snapshot(plan)
        self.assertEqual(audit_body_character_global(plan, snapshot), ())

        broken_root = replace(
            snapshot.driven_roots[0],
            scale_sources=(None, None, None),
        )
        broken = replace(
            snapshot,
            driven_roots=(broken_root,) + snapshot.driven_roots[1:],
        )

        self.assertIn(
            "driven_root_wiring_mismatch",
            {issue.code for issue in audit_body_character_global(plan, broken)},
        )


if __name__ == "__main__":
    unittest.main()
