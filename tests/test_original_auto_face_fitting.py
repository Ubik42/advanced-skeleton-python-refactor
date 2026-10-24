"""Offline native template boundaries and continuous AutoFit sequencing."""
from contextlib import contextmanager
import unittest

from adv_py.application.original_auto_face_fitting import AutoFitOriginalFace
from adv_py.core.original_auto_face_fitting import (
    ORIGINAL_AUTO_FACE_PROFILES, detect_original_auto_face_profile,
    original_auto_face_input, original_auto_face_steps,
    original_auto_face_tongue_points,
)


class AutoFaceRecipeTests(unittest.TestCase):
    def test_detection_uses_topology_and_native_last_match(self):
        self.assertIsNone(detect_original_auto_face_profile({'CC_Base_Body': 14163}))
        self.assertEqual(detect_original_auto_face_profile({'CC_Base_Body': 56412}).code, 'CC5')
        self.assertEqual(detect_original_auto_face_profile({
            'CC_Base_Body': 14164, 'head_lod0_mesh': 24049, 'GNM_Head': 17821}).code, 'GNM')

    def test_gnm_component_eyes_and_extra_main_use_native_mesh(self):
        profile = ORIGINAL_AUTO_FACE_PROFILES[3]
        self.assertEqual(profile.right_eye, ('GNM_Head.f[12782:13153]', 'GNM_Head.f[17278:17661]'))
        for side in ('Right', 'Left'):
            rows = original_auto_face_steps(profile, side)
            main2 = [row for row in rows if (row.section, row.part) == ('EyeLid', 'Main2')]
            self.assertEqual(len(main2), 1)
            self.assertEqual(main2[0].shading_group, '')
            self.assertTrue(all(value.startswith('GNM_Head.e[') for value in main2[0].selection))
            self.assertTrue(all(value.startswith('GNM_Head.e[')
                for row in rows if row.section in ('Pupil', 'Iris') for value in row.selection))

    def test_center_and_lip_rows_only_run_once_in_original_order(self):
        profile = ORIGINAL_AUTO_FACE_PROFILES[0]
        right = original_auto_face_steps(profile, 'Right')
        left = original_auto_face_steps(profile, 'Left')
        self.assertEqual([row.part for row in right if row.section == 'Lip'], ['Outer', 'Main', 'Inner'])
        self.assertFalse(any(row.section in ('Lip', 'Jaw', 'Nose', 'Throat') for row in left))
        self.assertEqual(right[0].section, 'EyeBall')
        self.assertEqual([row.section for row in right[-2:]], ['Pupil', 'Iris'])
        self.assertTrue(next(row for row in right if row.section == 'Jaw').batch)
        self.assertEqual(next(row for row in right if row.section == 'Nose').shading_group, 'asBlueSG')

    def test_fixed_input_ranges_and_tongue_offsets_are_retained(self):
        cc4, mh, cc5, gnm = ORIGINAL_AUTO_FACE_PROFILES
        self.assertEqual(original_auto_face_input(cc4, 'UpperTeeth'), ('CC_Base_Teeth.f[0:1180]',))
        self.assertEqual(original_auto_face_input(cc5, 'LowerTeeth'), ('CC_Base_Teeth.f[4724:9683]',))
        self.assertEqual(original_auto_face_input(gnm, 'Tongue'), ('GNM_Head.f[14566:15477]',))
        self.assertEqual(original_auto_face_tongue_points(mh), (
            ('teeth_lod0_mesh.vtx[1284]', 0), ('teeth_lod0_mesh.vtx[1281]', -.9),
            ('teeth_lod0_mesh.vtx[1278]', -.9), ('teeth_lod0_mesh.vtx[1275]', -.5),
            ('teeth_lod0_mesh.vtx[1076]', 0)))


class TraceAutoFaceHost:
    def __init__(self, *, profile=ORIGINAL_AUTO_FACE_PROFILES[0], confirmed=True, prepared=True):
        self.profile, self.confirmed, self.prepared = profile, confirmed, prepared
        self.trace = []
        self.active = False

    def detect_original_auto_face_profile(self):
        return self.profile

    def confirm_original_auto_face_fitting(self, profile):
        self.trace.append('confirm')
        return self.confirmed

    @contextmanager
    def transaction(self, label):
        if self.active:
            raise AssertionError('Nested AutoFit transaction')
        self.active = True
        self.trace.append('open')
        try:
            yield
        finally:
            self.active = False
            self.trace.append('close')

    def prepare_original_auto_face_inputs(self, profile):
        self.trace.append('inputs')
        return self.prepared

    def set_original_auto_face_side(self, side):
        self.trace.append(side)

    def create_original_auto_face_step(self, step):
        if not self.active:
            raise AssertionError('Fit row outside transaction')
        self.trace.append((step.section, step.part))

    def finish_original_auto_face_fitting(self, profile):
        self.trace.append('tongue-final')

    def build_original_auto_face_if_confirmed(self):
        if self.active:
            raise AssertionError('Build must own its transaction')
        self.trace.append('build-prompt')
        return None


class AutoFaceFlowTests(unittest.TestCase):
    def test_fit_rows_share_one_chunk_and_build_prompt_follows_final_tongue(self):
        host = TraceAutoFaceHost()
        result = AutoFitOriginalFace(host).apply()
        self.assertTrue(result.finished)
        self.assertEqual(host.trace[:3], ['confirm', 'open', 'inputs'])
        self.assertLess(host.trace.index('Right'), host.trace.index('Left'))
        self.assertEqual(host.trace[-3:], ['tongue-final', 'close', 'build-prompt'])
        self.assertEqual(host.trace.count('open'), 1)
        self.assertEqual(len(result.rows), len(original_auto_face_steps(host.profile, 'Right'))
            + len(original_auto_face_steps(host.profile, 'Left')))

    def test_unknown_or_declined_profile_never_opens_a_transaction(self):
        for host in (TraceAutoFaceHost(profile=None), TraceAutoFaceHost(confirmed=False)):
            self.assertIsNone(AutoFitOriginalFace(host).apply())
            self.assertNotIn('open', host.trace)

    def test_metahuman_cancel_keeps_inputs_without_fit_or_build(self):
        host = TraceAutoFaceHost(profile=ORIGINAL_AUTO_FACE_PROFILES[1], prepared=False)
        result = AutoFitOriginalFace(host).apply()
        self.assertFalse(result.finished)
        self.assertEqual(result.rows, ())
        self.assertEqual(host.trace, ['confirm', 'open', 'inputs', 'close'])
