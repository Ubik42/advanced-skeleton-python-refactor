"""Offline source branch checks. No Maya process or scene is created."""
from contextlib import contextmanager
import math
import unittest

from adv_py.core.original_eye_lid_fit import order_original_eye_lid_loop
from adv_py.core.original_face_fitting_update import (
    ORIGINAL_FACE_FITTING_UPDATE_ROWS, original_face_fit_row,
    original_face_fit_reselect_node,
)


class OriginalEyeLidFitTests(unittest.TestCase):
    def ring(self):
        points = {0: (-1., 0., 0.), 1: (-2., -10., 0.), 2: (-3., 10., 0.),
                  3: (-4., -10., 0.), 4: (-5., 0., 0.), 5: (-4., 1., 0.),
                  6: (-3., 1., 0.), 7: (-2., 1., 0.)}
        return tuple((i, i, (i + 1) % 8) for i in range(8)), points

    def test_max_y_branch_wins_even_when_its_average_is_lower(self):
        edges, points = self.ring()
        result = order_original_eye_lid_loop(edges, points)
        self.assertEqual(result.upper_vertices, (0, 1, 2, 3, 4))
        self.assertEqual(result.lower_vertices, (0, 7, 6, 5, 4))

    def test_one_manual_corner_does_not_invent_a_new_opposite_endpoint(self):
        edges, points = self.ring()
        result = order_original_eye_lid_loop(edges, points, corner_vertices=(1,))
        self.assertEqual(result.upper_vertices[0], 1)
        self.assertEqual(result.upper_vertices[-1], 4)
        self.assertEqual(result.lower_vertices[-1], 4)

    def test_native_manual_iteration_retains_the_last_two_corners(self):
        edges, points = self.ring()
        result = order_original_eye_lid_loop(edges, points, corner_vertices=(0, 4, 1))
        self.assertEqual((result.upper_vertices[0], result.upper_vertices[-1]), (1, 4))

    def test_extra_main_ignores_manual_eye_lid_corner_branch(self):
        edges, points = self.ring()
        result = order_original_eye_lid_loop(edges, points,
            corner_vertices=(1, 3), extra_main=True)
        self.assertEqual((result.upper_vertices[0], result.upper_vertices[-1]), (0, 4))

    def test_left_uses_reflected_start_and_end_order(self):
        edges, points = self.ring()
        points = {index: (-x, y, z) for index, (x, y, z) in points.items()}
        result = order_original_eye_lid_loop(edges, points, side='Left')
        self.assertEqual(result.upper_vertices, (0, 1, 2, 3, 4))

    def test_source_199_and_500_traversal_caps_are_retained(self):
        count = 400
        edges = tuple((index, index, (index + 1) % count) for index in range(count))
        points = {index: (-4. + 2. * math.cos(index * math.tau / count),
                          math.sin(index * math.tau / count), 0.) for index in range(count)}
        result = order_original_eye_lid_loop(edges, points)
        self.assertEqual(sorted((len(result.upper_vertices), len(result.lower_vertices))), [200, 201])


class OriginalFaceFitEntryTests(unittest.TestCase):
    def test_reselect_forced_right_overrides_current_left(self):
        self.assertEqual(original_face_fit_reselect_node('Lip_R', 'Main',
            has_non_sym=True, side='Left'), 'FaceFitLipMain')
        self.assertEqual(original_face_fit_reselect_node('Lip', 'Main',
            has_non_sym=True, side='Left'), 'FaceFitLipMainLeft')
        self.assertEqual(original_face_fit_reselect_node('Lip', 'Main',
            has_non_sym=False, side='Left'), 'FaceFitLipMain')

    def test_optional_rows_follow_native_column_order(self):
        rows = ORIGINAL_FACE_FITTING_UPDATE_ROWS
        self.assertLess(rows.index('LipInner'), rows.index('JawPivot'))
        self.assertLess(rows.index('Nostril'), rows.index('EyeBrowInner'))
        self.assertLess(rows.index('ForeHead'), rows.index('Pupil'))
        self.assertLess(rows.index('Tongue'), rows.index('EyeBrowMid1'))
        self.assertEqual(original_face_fit_row('EyeLidMain2'), ('EyeLidMain2', ''))
        self.assertEqual(original_face_fit_row('LipOuter'), ('Lip', 'Outer'))

    def test_canonical_empty_eyelash_does_not_revive_legacy_value(self):
        from adv_py.adapters.maya_face_teeth import MayaFaceTeethMixin
        class Commands:
            values = {'FaceFitSkeleton.Eyelash': '', 'FaceFitSkeleton.EyeLash': 'oldMesh'}
            def objExists(self, plug): return plug in self.values
            def getAttr(self, plug): return self.values[plug]
        class Host(MayaFaceTeethMixin):
            _cmds = Commands()
            def _fit(self, **flags): return 'FaceFitSkeleton'
        self.assertEqual(Host().original_face_part_text('EyeLash'), '')
        del Host._cmds.values['FaceFitSkeleton.Eyelash']
        self.assertEqual(Host().original_face_part_text('Eyelash'), 'oldMesh')

    def test_face_fitting_cancel_does_not_open_or_mutate_a_chunk(self):
        from adv_py.application.original_face_fitting_update import UpdateOriginalFaceFitting
        class Host:
            def confirm_original_face_fitting_update(self): return False
            def transaction(self, label): raise AssertionError('cancel opened a chunk')
        self.assertIsNone(UpdateOriginalFaceFitting(Host()).apply())

    def test_single_influence_is_removed_before_empty_skin_deletion(self):
        from adv_py.adapters.maya_original_eye_ball_fit import remove_original_skin_influence
        class Commands:
            calls = []
            def objExists(self, node): return True
            def listConnections(self, *args, **flags): return ['Eye_R']
            def ls(self, node, **flags): return ['eye-uuid']
            def skinCluster(self, *args, **flags): self.calls.append(('remove', flags['removeInfluence']))
            def delete(self, node): self.calls.append(('delete', node))
        c = Commands()
        remove_original_skin_influence(c, 'Eye_R', 'skin')
        self.assertEqual(c.calls, [('remove', 'Eye_R'), ('delete', 'skin')])

    def test_optional_eye_lid_does_not_become_a_required_fit_layer(self):
        from adv_py.application.face_pre import EyeLidLayer, OptionalEyeLidLayer
        self.assertEqual(tuple(layer.value for layer in EyeLidLayer), ('Outer', 'Main', 'Inner'))
        self.assertEqual(OptionalEyeLidLayer.MAIN2.value, 'Main2')


if __name__ == '__main__':
    unittest.main()
