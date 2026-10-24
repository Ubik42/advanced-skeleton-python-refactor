import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from adv_py.core.original_driving_fit import (
    OriginalDrivingFitSystem, original_fit_driven_destination,
    order_original_fit_driving_systems,
)
from adv_py.core.driving_systems import original_sdk_attribute, original_sdk_control


class OriginalDrivingFitTests(unittest.TestCase):
    def test_staged_uuid_duplicate_does_not_inherit_old_character_sets(self):
        from adv_py.adapters.maya_driving_fit_restore import MayaDrivingFitRestoreMixin
        from adv_py.core.original_driving_fit import OriginalDrivingFitCurve
        events = []
        raw = SimpleNamespace(
            ls=lambda identity, **flags: ['old:SDKFKCup_L_rotateX1'],
            nodeType=lambda node: 'animCurveUA',
            listSets=lambda **flags: ['old:AllSet', 'UserSDKSet'],
            objExists=lambda name: True,
            listConnections=lambda node, **flags: ['old:FitSkeleton.drivingSystem[21]']
                if node.startswith('old:') else ['old:FitSkeleton.drivingSystem[57]'],
            disconnectAttr=lambda *args: events.append(('disconnect', args)),
            duplicate=lambda source, **flags: ['stage:SDKFKCup_L_rotateX1'],
            sets=lambda node, **flags: events.append((node, flags)) or True)
        commands = SimpleNamespace(raw=raw,
            identity=SimpleNamespace(owns=lambda node: False,
                to_local=lambda node: node.removeprefix('stage:')),
            _creation_namespace=lambda: nullcontext(),
            objExists=lambda node: False, warning=lambda message: None)
        host = MayaDrivingFitRestoreMixin()
        host._cmds = commands
        host._require_transaction = lambda: None
        host.scene_address = lambda name: 'stage:' + name
        host.optimize_original_driving_controllers = lambda: None
        row = OriginalDrivingFitCurve('SDKFKCup_L_rotateX1', 'SDKFKCup_L_rotateX1',
            'cup', 'FKCup_L', 'rotateX', (None,) * 4, 'source-uuid')
        system = OriginalDrivingFitSystem('Fingers_L', (row,), 3)
        with patch('adv_py.adapters.maya_driving_registration.refresh_registered_sdks'):
            host.restore_original_driving_from_fit((system,))
        removed = [(node, flags['remove']) for node, flags in events if isinstance(flags, dict) and 'remove' in flags]
        self.assertEqual(removed, [('stage:SDKFKCup_L_rotateX1', 'old:AllSet'),
                                   ('stage:SDKFKCup_L_rotateX1', 'UserSDKSet')])
        self.assertIn(('disconnect', ('stage:SDKFKCup_L_rotateX1.drivingSystemOut',
                                      'old:FitSkeleton.drivingSystem[57]')), events)

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
