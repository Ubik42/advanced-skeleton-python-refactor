"""Timed phoneme to viseme sampling semantics."""
import unittest

from adv_py.core import (FaceShapeKind, PhonemeCue,
    phoneme_cues_to_performance)


MANIFEST = (("smile_R", FaceShapeKind.EXPRESSION),
            ("viseme_A", FaceShapeKind.VISEME),
            ("viseme_B", FaceShapeKind.VISEME))
MAPPING = (("a", "viseme_A"), ("b", "viseme_B"))


class PhonemeVisemeTests(unittest.TestCase):
    def test_adjacent_cues_crossfade_without_expression_channel(self):
        clip = phoneme_cues_to_performance(MANIFEST, "film",
            (PhonemeCue("a", 10, 14), PhonemeCue("b", 14, 18)),
            MAPPING, transition_frames=2)
        self.assertEqual(clip.channels, MANIFEST[1:])
        values = dict(clip.samples)
        self.assertEqual(values[8], (0., 0.))
        self.assertEqual(values[12], (1., 0.))
        self.assertEqual(values[14], (.5, .5))
        self.assertEqual(values[16], (0., 1.))
        self.assertEqual(values[20], (0., 0.))
        self.assertTrue(all(0. <= sum(row) <= 1. for row in values.values()))

    def test_pause_has_zero_weight(self):
        clip = phoneme_cues_to_performance(MANIFEST, "film",
            (PhonemeCue("a", 10, 12), PhonemeCue("b", 20, 22)),
            MAPPING, transition_frames=2)
        self.assertEqual(dict(clip.samples)[16], (0., 0.))

    def test_rejects_missing_or_non_viseme_mapping_and_overlap(self):
        cues = (PhonemeCue("a", 10, 14),)
        with self.assertRaises(ValueError):
            phoneme_cues_to_performance(MANIFEST, "film", cues,
                                        (("b", "viseme_B"),))
        with self.assertRaises(ValueError):
            phoneme_cues_to_performance(MANIFEST, "film", cues,
                                        (("a", "smile_R"),))
        with self.assertRaises(ValueError):
            phoneme_cues_to_performance(MANIFEST, "film",
                (PhonemeCue("a", 10, 14), PhonemeCue("b", 13, 17)),
                MAPPING)


if __name__ == "__main__":
    unittest.main()
