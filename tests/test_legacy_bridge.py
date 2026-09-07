import unittest

from adv_py.legacy.bridge import _mel_literal


class LegacyBridgeTests(unittest.TestCase):
    def test_quotes_strings_and_arrays(self) -> None:
        self.assertEqual(_mel_literal('a"b'), '"a\\"b"')
        self.assertEqual(_mel_literal([1, True, "x"]), '{1,1,"x"}')

    def test_rejects_unknown_types(self) -> None:
        with self.assertRaises(TypeError):
            _mel_literal(object())


if __name__ == "__main__":
    unittest.main()
