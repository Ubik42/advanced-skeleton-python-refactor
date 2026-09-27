import unittest

from adv_py.core.face_build_requirements import (
    FaceInclude, required_face_fit_nodes)


class FaceBuildRequirementsTests(unittest.TestCase):
    def test_include_regions_match_original_build_preflight(self):
        self.assertEqual(len(required_face_fit_nodes(FaceInclude.ALL)), 27)
        self.assertEqual(len(required_face_fit_nodes(FaceInclude.SKIP_ABOVE)), 23)
        self.assertEqual(len(required_face_fit_nodes(FaceInclude.SKIP_BELOW)), 8)
        self.assertEqual(required_face_fit_nodes(FaceInclude.EYES_ONLY), (
            "FitEyeBall", "FaceFitEyeLidOuter", "FaceFitEyeLidMain",
            "FaceFitEyeLidInner"))

    def test_non_symmetric_mode_requires_corresponding_left_fit(self):
        required = required_face_fit_nodes(FaceInclude.EYES_ONLY, True)
        self.assertEqual(required[4:], tuple(name + "Left" for name in
                         required[:4]))
        self.assertEqual(len(required_face_fit_nodes(FaceInclude.ALL, True)), 54)
