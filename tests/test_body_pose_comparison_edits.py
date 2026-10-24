from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as Row
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'validation'))
from maya_original_body_pose_compare import set_edit
from adv_py.core.character_registry import canonical
import test_source_limb_mode as limb_tests


class BodyPoseComparisonEditTests(unittest.TestCase):
    def test_normalized_alias_uses_declared_source_driver_units(self):
        plan = limb_tests.SourceLimbModeTests().plan()
        writes = []
        def attr(plug, **flags):
            if flags.get('settable'):
                return False
            if flags.get('lock'):
                return True
            if plug.endswith('.conversionFactor'):
                return .1
            return canonical(asdict(plan))
        cmds = Row(getAttr=attr, objExists=lambda plug: True,
                   ls=lambda name, **flags: [plan.source_mode.control if name == 'FKIKArm_R' else '|AdvPy_ArmSettings'],
                   isConnected=lambda *args: True,
                   setAttr=lambda *args: writes.append(args))
        set_edit(cmds, ('FKIKArm_R.FKIKBlend', 'AdvPy_ArmSettings.armIkFk_R', 5., .5), 1)
        self.assertEqual(writes, [(plan.mode_plug, 5.)])

    def test_writable_input_keeps_requested_value(self):
        writes = []
        cmds = Row(getAttr=lambda *args, **flags: True, setAttr=lambda *args: writes.append(args))
        set_edit(cmds, ('IKArm_L.translateZ', 'AdvPy_ArmIK_L.translateZ', .7), 1)
        self.assertEqual(writes, [('AdvPy_ArmIK_L.translateZ', .7)])
