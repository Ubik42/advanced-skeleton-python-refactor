from array import array
import unittest

from adv_py.core.dense_skin_transfer import (
    DenseSkinWeights, reorder_dense_skin, validate_dense_skin,
)


class DenseSkinTransferTests(unittest.TestCase):
    def test_reordered_influence_rows_preserve_every_weight(self):
        source = DenseSkinWeights("old", 2, ("A", "B", "C"),
            array("d", (0.1, 0.2, 0.7, 0.8, 0.2, 0.0)).tobytes())
        target = reorder_dense_skin(source, "new", ("C", "A", "B"))
        self.assertEqual(tuple(memoryview(target.values).cast("d")),
                         (0.7, 0.1, 0.2, 0.0, 0.8, 0.2))
        self.assertEqual(target.vertex_count, 2)

    def test_tiny_source_roundoff_is_preserved(self):
        source = DenseSkinWeights("old", 1, ("A", "B"),
            array("d", (-2e-9, 1.000000002)).tobytes())
        validate_dense_skin(source)
        self.assertEqual(reorder_dense_skin(source, "new", ("B", "A")).values,
                         array("d", (1.000000002, -2e-9)).tobytes())

    def test_missing_influence_and_invalid_weight_rejected(self):
        source = DenseSkinWeights("old", 1, ("A", "B"),
            array("d", (0.4, 0.6)).tobytes())
        with self.assertRaises(ValueError):
            reorder_dense_skin(source, "new", ("A", "C"))
        invalid = DenseSkinWeights("old", 1, ("A", "B"),
            array("d", (-0.01, 1.01)).tobytes())
        with self.assertRaises(ValueError):
            validate_dense_skin(invalid)


if __name__ == "__main__":
    unittest.main()
