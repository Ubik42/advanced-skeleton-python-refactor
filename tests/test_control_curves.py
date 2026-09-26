import unittest
from contextlib import contextmanager

from adv_py.application import (
    AutoScaleControlCurves, ColorControlCurves, MirrorControlCurves,
    ScaleControlCurves, SwapControlCurves,
)
from adv_py.core import (
    ControlCurveAutoScaleMetric, ControlCurveColorMode, ControlCurveColorState,
    ControlCurveMirrorPair,
    ControlCurveShapeColorState,
    ControlCurveShapeState, ControlCurveState, ControlCurveValidationError,
    SIDE_PALETTE, TYPE_PALETTE, control_curve_side, control_curve_type,
    plan_control_curve_auto_scale, plan_control_curve_colors,
    plan_control_curve_mirror, plan_control_curve_scale,
    plan_control_curve_swap,
)


IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0.,
            0., 0., 1., 0., 0., 0., 0., 1.)


def state(control="|Control", points=((1., 0., 0.), (0., 2., 0.))):
    return ControlCurveState(control, IDENTITY, (
        ControlCurveShapeState(control + "|ControlShape", 1, 0, points),))


class Host:
    def __init__(self):
        self.states = {"|Control": state()}
        self.transactions = []

    def capture_control_curves(self, controls, *, strict):
        found = tuple(self.states[name] for name in controls if name in self.states)
        if strict and len(found) != len(controls):
            raise ControlCurveValidationError("missing")
        return found

    @contextmanager
    def transaction(self, label):
        self.transactions.append(label)
        yield

    def set_control_curve_points(self, shape, points):
        name, current = next((name, current)
            for name, current in self.states.items()
            if any(item.path == shape for item in current.shapes))
        self.states[name] = ControlCurveState(
            current.control, current.world_matrix,
            (ControlCurveShapeState(shape, 1, 0, points),))

    def measure_control_curve_auto_scale(self, controls, mesh, semantic_keys, *,
                                         strict):
        semantics = dict(semantic_keys)
        return tuple(ControlCurveAutoScaleMetric(
            self.states[name], semantics.get(name, ()), 2., 3.,
            (10., 20., 30.), "z") for name in controls)

    def replace_control_curve_shapes(self, source, target):
        source_state = self.states[source]
        target_state = self.states[target]
        self.states[target] = ControlCurveState(
            target, target_state.world_matrix,
            tuple(ControlCurveShapeState(
                target + f"|Shape{index}", shape.degree, shape.form,
                shape.points) for index, shape in enumerate(
                    source_state.shapes, 1)))


class ColorHost:
    def __init__(self):
        self.states = {
            "|Arm_FK_R": ControlCurveColorState("|Arm_FK_R", (), (
                ControlCurveShapeColorState(
                    "|Arm_FK_R|Shape", False, False, (0., 0., 0.)),)),
        }
        self.transactions = []

    def capture_control_curve_colors(self, controls, semantic_keys, *, strict):
        semantics = dict(semantic_keys)
        found = []
        for name in controls:
            if name in self.states:
                current = self.states[name]
                found.append(ControlCurveColorState(
                    current.control, semantics.get(name, current.semantic_keys),
                    current.shapes))
        if strict and len(found) != len(controls):
            raise ControlCurveValidationError("missing")
        return tuple(found)

    @contextmanager
    def transaction(self, label):
        self.transactions.append(label)
        yield

    def set_control_curve_color(self, shape, color):
        current = self.states["|Arm_FK_R"]
        self.states[current.control] = ControlCurveColorState(
            current.control, current.semantic_keys,
            (ControlCurveShapeColorState(shape, True, True, color),))


class ControlCurveScaleTests(unittest.TestCase):
    def test_plan_scales_local_cvs_and_preserves_transform(self):
        plan = plan_control_curve_scale((state(),), 1.5)
        self.assertEqual(plan.after[0].world_matrix, IDENTITY)
        self.assertEqual(plan.after[0].shapes[0].points,
                         ((1.5, 0., 0.), (0., 3., 0.)))
        with self.assertRaises(ControlCurveValidationError):
            plan_control_curve_scale((state(),), 0.)

    def test_application_writes_and_verifies_one_transaction(self):
        host = Host()
        result = ScaleControlCurves(host).apply(("|Control",), 2.)
        self.assertEqual(len(host.transactions), 1)
        self.assertEqual(result.verified[0].shapes[0].points,
                         ((2., 0., 0.), (0., 4., 0.)))


class ControlCurveColorTests(unittest.TestCase):
    def test_side_and_type_classification_use_semantics_and_paths(self):
        right_fk = ControlCurveColorState("|Rig|Arm_FK_R", ("arm.fk.Wrist_R",), (
            ControlCurveShapeColorState("|Rig|Arm_FK_R|Shape", False, False,
                                        (0., 0., 0.)),))
        left_pole = ControlCurveColorState("|Rig|Pole_L", ("arm.pole.L",), (
            ControlCurveShapeColorState("|Rig|Pole_L|Shape", False, False,
                                        (0., 0., 0.)),))
        self.assertEqual(control_curve_side(right_fk), "right")
        self.assertEqual(control_curve_type(right_fk), "fk")
        self.assertEqual(control_curve_side(left_pole), "left")
        self.assertEqual(control_curve_type(left_pole), "pole")

    def test_plan_applies_stable_side_and_type_palettes(self):
        current = ColorHost().states["|Arm_FK_R"]
        side = plan_control_curve_colors((current,), ControlCurveColorMode.SIDE)
        self.assertEqual(side.after[0].shapes[0].color, SIDE_PALETTE["right"])
        typed = plan_control_curve_colors((ControlCurveColorState(
            current.control, ("arm.fk.Wrist_R",), current.shapes),), "type")
        self.assertEqual(typed.after[0].shapes[0].color, TYPE_PALETTE["fk"])

    def test_application_writes_rgb_override_and_verifies(self):
        host = ColorHost()
        result = ColorControlCurves(host).apply(
            ("|Arm_FK_R",), "type",
            (("|Arm_FK_R", ("arm.fk.Wrist_R",)),))
        self.assertEqual(len(host.transactions), 1)
        shape = result.verified[0].shapes[0]
        self.assertTrue(shape.override_enabled and shape.rgb_enabled)
        self.assertEqual(shape.color, TYPE_PALETTE["fk"])


class ControlCurveAutoScaleTests(unittest.TestCase):
    def test_plan_uses_surface_distance_and_global_horizontal_extent(self):
        local = ControlCurveAutoScaleMetric(
            state(), ("arm.fk.Wrist_R",), 2., 3., (10., 20., 30.), "z")
        global_state = state("|Global")
        global_metric = ControlCurveAutoScaleMetric(
            global_state, ("global.translateX",), 2., 3.,
            (10., 20., 30.), "z")
        plan = plan_control_curve_auto_scale("|Skin", (local, global_metric))
        self.assertAlmostEqual(plan.changes[0].target_world_radius, 3.45)
        self.assertAlmostEqual(plan.changes[1].target_world_radius, 12.)

    def test_application_writes_each_planned_factor_and_verifies(self):
        host = Host()
        result = AutoScaleControlCurves(host).apply(
            ("|Control",), "|Skin",
            (("|Control", ("arm.fk.Wrist_R",)),))
        self.assertEqual(len(host.transactions), 1)
        self.assertAlmostEqual(result.plan.changes[0].factor, 1.725)
        self.assertTrue(all(
            abs(value - expected) <= 1e-9
            for point, wanted in zip(result.verified[0].shapes[0].points,
                                     ((1.725, 0., 0.), (0., 3.45, 0.)))
            for value, expected in zip(point, wanted)))


class ControlCurveMirrorTests(unittest.TestCase):
    def test_plan_reflects_world_x_then_converts_to_target_local(self):
        right_matrix = IDENTITY[:12] + (-2., 0., 0., 1.)
        left_matrix = IDENTITY[:12] + (2., 0., 0., 1.)
        right = ControlCurveState("|Control_R", right_matrix, (
            ControlCurveShapeState("|Control_R|Shape", 1, 0,
                                   ((1., 2., 0.), (0., 3., 0.))),))
        left = ControlCurveState("|Control_L", left_matrix, (
            ControlCurveShapeState("|Control_L|Shape", 1, 0,
                                   ((0., 0., 0.), (0., 1., 0.))),))
        plan = plan_control_curve_mirror((ControlCurveMirrorPair(right, left),))
        self.assertEqual(plan.after[0].shapes[0].points,
                         ((-1., 2., 0.), (0., 3., 0.)))

    def test_application_updates_only_target_and_verifies(self):
        host = Host()
        source = state("|Control_R", ((1., 0., 0.), (0., 2., 0.)))
        target = state("|Control_L", ((4., 0., 0.), (0., 5., 0.)))
        host.states = {source.control: source, target.control: target}
        result = MirrorControlCurves(host).apply(
            ((source.control, target.control),))
        self.assertEqual(host.states[source.control], source)
        self.assertEqual(result.verified[0].control, target.control)


class ControlCurveSwapTests(unittest.TestCase):
    def test_plan_rejects_source_as_target(self):
        source = state("|Custom")
        with self.assertRaises(ControlCurveValidationError):
            plan_control_curve_swap(source, (source,))

    def test_application_replaces_geometry_and_preserves_target_transform(self):
        host = Host()
        source = state("|Custom", ((2., 0., 0.), (0., 3., 0.)))
        target = state("|Control", ((1., 0., 0.), (0., 1., 0.)))
        host.states = {source.control: source, target.control: target}
        result = SwapControlCurves(host).apply(source.control, (target.control,))
        self.assertEqual(result.verified[0].world_matrix, target.world_matrix)
        self.assertEqual(result.verified[0].shapes[0].points,
                         source.shapes[0].points)
        self.assertEqual(host.states[source.control], source)


if __name__ == "__main__":
    unittest.main()
