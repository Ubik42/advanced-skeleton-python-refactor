"""Sparse anchors preserve topology and exact marked positions."""
import unittest

from adv_py.core import FaceLandmark, FaceMeshSnapshot, deform_face_landmarks


class FaceLandmarkTests(unittest.TestCase):
    def neutral(self):
        return FaceMeshSnapshot("|FaceNeutral", 4, "a" * 64,
            ((0., 0., 0.), (1., 0., 0.), (2., 0., 0.), (3., 0., 0.)))

    def test_anchor_exact_and_nearby_falloff(self):
        points = deform_face_landmarks(self.neutral(),
            (FaceLandmark(0, (0., 0., 1.), 2.),))
        self.assertEqual(points[0], (0., 0., 1.))
        self.assertGreater(points[1][2], 0.)
        self.assertLess(points[1][2], 1.)
        self.assertEqual(points[2], (2., 0., 0.))
        self.assertEqual(points[3], (3., 0., 0.))

    def test_rejects_duplicate_or_unusable_landmarks(self):
        neutral = self.neutral()
        with self.assertRaises(ValueError):
            deform_face_landmarks(neutral,
                (FaceLandmark(0, (0., 0., 1.), 1.),
                 FaceLandmark(0, (0., 1., 0.), 1.)))
        with self.assertRaises(ValueError):
            deform_face_landmarks(neutral,
                (FaceLandmark(4, (0., 0., 1.), 1.),))
        with self.assertRaises(ValueError):
            deform_face_landmarks(neutral,
                (FaceLandmark(0, (0., 0., 0.), 1.),))


if __name__ == "__main__":
    unittest.main()
