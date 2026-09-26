import unittest

from adv_py.core.model_checker import (
    ModelHistoryNode, ModelTransformState, inspect_model_history,
    inspect_model_symmetry, inspect_model_transforms,
)


class ModelCheckerTests(unittest.TestCase):
    def test_parent_transform_and_pivot_are_reported(self):
        state = ModelTransformState("|Parent|Mesh", (0, 0, 0), (0, 0, 0),
                                    (1, 2, 1), (0.25, 0, 0), (0, 0, 0))
        issues = inspect_model_transforms((state,))
        self.assertEqual([(i.attribute, i.expected) for i in issues],
                         [("scaleY", 1), ("rotatePivotX", 0)])

    def test_history_exceptions_match_game_engine_mode(self):
        nodes = tuple(ModelHistoryNode(name, kind) for name, kind in (
            ("polyCube1", "polyCube"), ("skinCluster1", "skinCluster"),
            ("deltaMush1", "deltaMush"), ("asResetTransform1", "multiplyDivide")))
        self.assertEqual([n.name for n in inspect_model_history(nodes)],
                         ["polyCube1"])
        self.assertEqual([n.name for n in inspect_model_history(nodes, game_engine=True)],
                         ["polyCube1", "deltaMush1"])

    def test_mirror_tolerance_and_negative_side(self):
        points = ((-1, 0, 0), (1, 0, 0), (-1, 1, 0), (1, 1.01, 0))
        issues = inspect_model_symmetry(points, (1, 1, 3, 3))
        self.assertEqual([(i.vertex, i.closest_vertex) for i in issues], [(2, 3)])


if __name__ == "__main__":
    unittest.main()
