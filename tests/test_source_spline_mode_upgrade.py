import unittest
from dataclasses import replace

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterChannel, CharacterRegistryError
from adv_py.core.fit_hierarchy import FitHierarchyNode, FitHierarchySnapshot
from adv_py.core.joint_labels import JointLabel
from adv_py.core.source_spline_mode_upgrade import (
    plan_source_spline_mode_upgrade, upgrade_mode_channels,
)


def fixture(side='M', part=False, suffix=''):
    container = '|FitSkeleton'
    paths = [container + '|Root' + suffix]
    paths += [paths[0] + '|Spine' + suffix]
    paths += [paths[1] + '|Chest' + suffix]
    joints = tuple(FitHierarchyNode(path, name + suffix,
        container if index == 0 else paths[index - 1], (0., 10., 0.),
        (0., float(index * 10), 0.))
        for index, (path, name) in enumerate(zip(paths, ('Root', 'Spine', 'Chest'))))
    hierarchy = FitHierarchySnapshot(container, joints)
    labels = {paths[0]: JointLabel.parse('Root'), paths[1]: None,
              paths[2]: JointLabel.parse('Chest')}
    base = '|Group|DeformationSystem|Root_M' + ('|RootPart1_M' if part else '')
    body = (base + '|Root_' + side, base + '|Root_' + side + '|Spine_' + side,
            base + '|Root_' + side + '|Spine_' + side + '|Chest_' + side)
    spline = BodySplinePlan('|Group|Spline', (), body, (), '|Pelvis', '|Chest',
        ('|IK0', '|IK1', '|IK2'), (), (), (10., 10.), source_curve_points=((0., 0., 0.),) * 3)
    return spline, hierarchy, labels


class SourceSplineModeUpgradeTests(unittest.TestCase):
    def test_original_fit_chain_parent_and_units(self):
        spline, hierarchy, labels = fixture()
        upgraded = plan_source_spline_mode_upgrade(spline, hierarchy, labels)
        self.assertEqual(upgraded.source_mode.name, 'FKIKSpine_M')
        self.assertEqual(upgraded.source_mode.parent_source,
                         '|Group|MotionSystem|RootSystem|AdvPy_LegLockConstrained')
        self.assertEqual(upgraded.source_fit_control_count, 2)
        self.assertEqual(upgraded.mode_maximum, 10.)
        self.assertEqual(upgraded.mode_weight, upgraded.source_mode.weight_unit + '.output')
        self.assertIs(plan_source_spline_mode_upgrade(upgraded, hierarchy, labels), upgraded)

    def test_physical_part_parent_and_authored_count_are_retained(self):
        spline, hierarchy, labels = fixture(part=True)
        spline = replace(spline, source_fit_control_count=5)
        result = plan_source_spline_mode_upgrade(spline, hierarchy, labels)
        self.assertEqual(result.source_mode.parent_source,
                         '|Group|DeformationSystem|Root_M|RootPart1_M')
        self.assertEqual(result.source_fit_control_count, 5)

    def test_left_and_nonsymmetry_preserve_original_sign(self):
        for side, suffix in (('L', ''), ('R', '_NonSymmetry')):
            spline, hierarchy, labels = fixture(side, suffix=suffix)
            result = plan_source_spline_mode_upgrade(spline, hierarchy, labels)
            self.assertEqual(result.source_mode.side_sign, -1)

    def test_unrelated_chain_and_mixed_sides_are_rejected(self):
        spline, hierarchy, labels = fixture()
        for changed in (replace(spline, body_joints=(*spline.body_joints[:-1], '|Wrong_M')),
                        replace(spline, body_joints=(*spline.body_joints[:-1], '|Chest_L')),
                        replace(spline, source_curve_points=())):
            with self.assertRaises(CharacterRegistryError):
                plan_source_spline_mode_upgrade(changed, hierarchy, labels)

    def test_fresh_build_channel_identity_without_other_channel_changes(self):
        spline, hierarchy, labels = fixture()
        result = plan_source_spline_mode_upgrade(spline, hierarchy, labels)
        channels = (CharacterChannel('source.spline.spineIkFk', spline.mode_control,
                                     'spineIkFk', 0., 1.),
                    CharacterChannel('source.spline.FKVis', spline.visibility_settings,
                                     'FKVis', 0., 1.),
                    CharacterChannel('arm.rotateX', '|Arm', 'rotateX'))
        changed = upgrade_mode_channels(channels, spline, result)
        self.assertEqual(changed[0], CharacterChannel('source.spline.FKIKBlend',
            result.mode_control, 'FKIKBlend', 0., 10.))
        self.assertEqual(changed[1].node, result.visibility_settings)
        self.assertEqual(changed[2], channels[2])


if __name__ == '__main__':
    unittest.main()
