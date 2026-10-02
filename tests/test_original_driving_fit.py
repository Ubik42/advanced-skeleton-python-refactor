import unittest
from adv_py.core.original_driving_fit import (
    OriginalDrivingFitSystem, original_fit_driven_destination,
    order_original_fit_driving_systems,
)
from adv_py.core.driving_systems import original_sdk_attribute, original_sdk_control


class OriginalDrivingFitTests(unittest.TestCase):
    def test_saved_prefix_and_curve_suffix_keep_original_target(self):
        self.assertEqual(original_fit_driven_destination('hero:prefix_SDKFKElbow_R_rotateX12'),
                         ('SDKFKElbow_R_rotateX12', 'FKElbow_R', 'rotateX'))
        self.assertEqual(original_sdk_control('SDKFKElbow_R_rotateX12'), 'FKElbow_R')
        self.assertEqual(original_sdk_attribute('SDKFKElbow_R_rotateX12'), 'rotateX')

    def test_nested_native_name_ignores_trailing_empty_token(self):
        name = 'bwDrivingSystem1_R_driver1_input_1_'
        self.assertEqual(original_fit_driven_destination(name),
                         (name, 'bwDrivingSystem1_R_driver1', 'input[1]'))
        self.assertEqual(original_sdk_control(name), 'DrivingSystem1_R')
        self.assertEqual(original_sdk_attribute(name), 'driver1')

    def test_original_single_digit_index_rule_is_not_expanded(self):
        self.assertEqual(original_fit_driven_destination('bwDriver_R_driver_input_9_')[2], 'input[9]')
        # Native restore warns and continues when this becomes empty.
        self.assertEqual(original_fit_driven_destination('bwDriver_R_driver_input_12_')[2], '')

    def test_original_depth_sort_is_stable_and_keeps_99_pass_limit(self):
        systems = tuple(OriginalDrivingFitSystem(name, (), depth) for name, depth in
                        (('deep', 5), ('first', 3), ('last', 3), ('omitted', 99), ('base', 0)))
        self.assertEqual(tuple(row.control for row in order_original_fit_driving_systems(systems)),
                         ('base', 'first', 'last', 'deep'))
