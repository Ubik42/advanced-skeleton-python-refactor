import unittest

from adv_py.core.face_eyelid_skin import eyelid_skin_factors


class EyeLidSkinFactorsTests(unittest.TestCase):
    def test_main_arcs_drive_separately_and_boundaries_stay_on_head(self):
        adjacency = {index: set() for index in range(25)}
        positions = {index: (float(index % 5), float(index // 5), 0.)
                     for index in range(25)}
        for row in range(5):
            for column in range(5):
                index = row * 5 + column
                for neighbor in ((index + 1,) if column < 4 else ()) + (
                        (index + 5,) if row < 4 else ()):
                    adjacency[index].add(neighbor)
                    adjacency[neighbor].add(index)
        boundary = {index for index in range(25)
                    if index // 5 in (0, 4) or index % 5 in (0, 4)}
        boundary.add(12)
        factors = eyelid_skin_factors(adjacency, positions, set(range(25)),
                    boundary, (6, 7, 8), (16, 17, 18))
        self.assertEqual(factors[7], (.85, 0.))
        self.assertEqual(factors[17], (0., .85))
        self.assertEqual(factors[12], (0., 0.))
        self.assertTrue(all(factors[index] == (0., 0.) for index in boundary))
