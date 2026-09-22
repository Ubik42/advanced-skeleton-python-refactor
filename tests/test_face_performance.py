"""Portable face performance document contract."""
import json
import unittest

from adv_py.core import (FacePerformance, FaceShapeKind,
    face_performance_from_json, face_performance_to_json)


class FacePerformanceTests(unittest.TestCase):
    def sample(self):
        return FacePerformance(
            (("smile_R", FaceShapeKind.EXPRESSION),
             ("viseme_A", FaceShapeKind.VISEME)),
            "film", ((1, (0., 0.)), (5, (1., .4)), (10, (.2, 1.))))

    def test_roundtrip_and_tamper_rejection(self):
        original = self.sample()
        document = face_performance_to_json(original)
        self.assertEqual(face_performance_from_json(document), original)
        changed = json.loads(document)
        changed["payload"]["samples"][1][1][0] = .5
        with self.assertRaises(ValueError):
            face_performance_from_json(json.dumps(changed))

    def test_rejects_wrong_channel_and_frame_data(self):
        original = self.sample()
        with self.assertRaises(ValueError):
            FacePerformance((original.channels[0], original.channels[0]),
                            "film", original.samples)
        with self.assertRaises(ValueError):
            FacePerformance(original.channels, "film",
                ((1, (0., 0.)), (1, (1., .4))))
        with self.assertRaises(ValueError):
            FacePerformance(original.channels, "film",
                ((1, (0., 0.)), (5, (1.2, .4))))

    def test_rejects_unknown_document_field(self):
        changed = json.loads(face_performance_to_json(self.sample()))
        changed["unexpected"] = True
        with self.assertRaises(ValueError):
            face_performance_from_json(json.dumps(changed))


if __name__ == "__main__":
    unittest.main()
