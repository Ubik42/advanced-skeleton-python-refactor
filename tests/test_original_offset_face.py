"""Source Offset Face landmarks and locked-weight transplant boundaries."""
import unittest

from adv_py.core.original_locked_skin_copy import original_locked_copy_weights
from adv_py.core.original_offset_face import (
    OriginalOffsetFaceImportOptions, original_offset_face_landmarks,
    original_offset_face_geometry, original_offset_face_name_swap,
    original_offset_face_head_choices,
)


class NativeLockedCopyTests(unittest.TestCase):
    def test_locked_values_survive_and_remaining_weights_keep_copied_ratio(self):
        result = original_locked_copy_weights((.4,.3,.3, .7,.2,.1), (.2,.6,.2, .1,.3,.6), 3, (0,))
        for actual, expected in zip(result, (.4,.45,.15, .7,.1,.2)):
            self.assertAlmostEqual(actual, expected)

    def test_native_full_lock_and_zero_unlocked_fallback(self):
        self.assertEqual(original_locked_copy_weights((1.,.2,0.), (.1,.2,.7), 3, (0,)), (1.,.2,0.))
        self.assertEqual(original_locked_copy_weights((.25,.25,.5), (1.,0.,0.), 3, (0,)), (.25,.75,0.))

    def test_all_locked_row_below_one_keeps_original_without_fabricated_influence(self):
        self.assertEqual(original_locked_copy_weights((.2,.3), (.6,.4), 2, (0,1)), (.2,.3))

    def test_weights_require_complete_vertex_rows(self):
        with self.assertRaises(ValueError):
            original_locked_copy_weights((.2,.8), (.2,.3,.5), 2, (0,))


class NativeOffsetFaceTests(unittest.TestCase):
    def test_base_vertices_are_selection_ordinals_with_first_tie_winning(self):
        selected = ('Head.vtx[530]', 'Head.e[2]', 'Head.vtx[29]', 'Head.vtx[99]')
        plan = original_offset_face_landmarks(selected, ((1,6,2), (0,9,8), (-1,9,-4)))
        self.assertEqual(plan.vertices, ('Head.vtx[530]', 'Head.vtx[29]', 'Head.vtx[99]'))
        self.assertEqual(plan.base_vertex_indices, '1 2 1')

    def test_vertex_range_is_one_selected_token_native_requires_three(self):
        with self.assertRaises(ValueError):
            original_offset_face_landmarks(('Head.vtx[0:2]',), ((0,0,0),))

    def test_geometry_preserves_source_order_and_duplicates(self):
        self.assertEqual(original_offset_face_geometry('Face', 'Teeth Teeth Tongue'),
                         ('Teeth','Teeth','Tongue','Face'))
        self.assertEqual(original_offset_face_geometry('Face', 'Face Teeth'), ('Face','Teeth'))

    def test_name_swap_replaces_first_match_and_head_priorities_match_source(self):
        options = OriginalOffsetFaceImportOptions('FaceLeft', 'Head_L', True)
        self.assertEqual(original_offset_face_name_swap('Head_A_A', options), 'Head_B_A')
        joints = ('|Root|Head_R', '|Root|Head_L', '|Root|HeadEnd_L', '|FitSkeleton|Head', '|Root|Hand')
        self.assertEqual(original_offset_face_head_choices(joints)[:2], ('|Root|Head_L','|Root|Head_R'))
        self.assertEqual(original_offset_face_head_choices(joints, has_imported_face=True)[:2],
                         ('|Root|Head_R','|Root|Head_L'))
