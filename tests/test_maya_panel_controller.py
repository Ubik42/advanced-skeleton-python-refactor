import unittest

from adv_py.core import FitJointField
from adv_py.product.maya_panel_controller import parse_fit_metadata_value


class FitMetadataPanelValueTests(unittest.TestCase):
    def test_parses_supported_value_categories(self):
        self.assertEqual(parse_fit_metadata_value("twist_joints", "3"),
                         (FitJointField.TWIST_JOINTS, 3))
        self.assertEqual(parse_fit_metadata_value("no_mirror", "false"),
                         (FitJointField.NO_MIRROR, False))
        self.assertEqual(parse_fit_metadata_value("global_weight", "1.25"),
                         (FitJointField.GLOBAL_WEIGHT, 1.25))
        self.assertEqual(parse_fit_metadata_value("ik_local_mode", "addCtrl"),
                         (FitJointField.IK_LOCAL_MODE, "addCtrl"))

    def test_remove_ignores_text_and_invalid_values_are_clear(self):
        self.assertEqual(parse_fit_metadata_value(
            "bendy_controls", "ignored", remove=True),
            (FitJointField.BENDY_CONTROLS, None))
        with self.assertRaisesRegex(ValueError, "必须是整数"):
            parse_fit_metadata_value("twist_joints", "1.5")
        with self.assertRaisesRegex(ValueError, "true"):
            parse_fit_metadata_value("no_mirror", "yes")
        with self.assertRaises(ValueError):
            parse_fit_metadata_value("ik_local_mode", "")


if __name__ == "__main__":
    unittest.main()
