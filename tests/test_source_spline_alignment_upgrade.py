"""Migration changes only the missing native reference-frame feature."""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_spline_alignment_upgrade import (
    source_spline_alignment_upgrade_systems,
    upgrade_source_spline_alignment_layouts,
    audit_source_spline_alignment_upgrade,
)
from adv_py.application.source_spline_alignment_upgrade import UpgradeSourceSplineAlignment
from test_source_spline_alignment import fixture


def registration(layouts):
    return NS(spine=layouts[0] if layouts else None, additional_spines=tuple(layouts[1:]),
        channels=(NS(key='generic.fk.Root_MFK.rotateX'),), body=(NS(path='|Root_M'),),
        nodes=())


class AlignmentUpgradeTests(unittest.TestCase):
    def layouts(self):
        plan, _, _, _ = fixture()
        return (replace(plan, source_alignment_frames=False),
                replace(plan, system_name='Tail_M', source_alignment_frames=False),
                replace(plan, system_name='Neck_M'))

    def test_default_upgrade_finds_only_legacy_source_systems(self):
        self.assertEqual(source_spline_alignment_upgrade_systems(registration(self.layouts())),
                         ('', 'Tail_M'))

    def test_selected_layout_preserves_all_other_saved_fields(self):
        before = self.layouts()
        after = upgrade_source_spline_alignment_layouts(before, ('Tail_M',))
        self.assertIs(before[0], after[0])
        self.assertIs(before[2], after[2])
        self.assertEqual(before[1], replace(after[1], source_alignment_frames=False))
        self.assertFalse(before[1].source_alignment_frames)

    def test_invalid_selection_and_non_source_are_rejected(self):
        before = registration(self.layouts())
        for systems in ('Tail_M', ('Unknown',), ('Tail_M', 'Tail_M'), (None,)):
            with self.subTest(systems=systems), self.assertRaises(CharacterRegistryError):
                source_spline_alignment_upgrade_systems(before, systems)
        generic = registration((replace(self.layouts()[0], source_curve_points=()),))
        with self.assertRaises(CharacterRegistryError):
            source_spline_alignment_upgrade_systems(generic, ('',))

    def test_audit_rejects_implicit_count_or_solver_changes(self):
        layouts = self.layouts()
        upgraded = upgrade_source_spline_alignment_layouts(layouts, ('',))
        before, after = registration(layouts), registration(upgraded)
        with patch('adv_py.core.character_preservation.validate_rebuild_layout') as gate:
            audit_source_spline_alignment_upgrade(before, after, ('',))
            gate.assert_called_once_with(before, after)
            for field, value in (('source_world_controls', not upgraded[0].source_world_controls),
                                 ('source_hybrid_graph', not upgraded[0].source_hybrid_graph),
                                 ('targets', ('|Changed', '|ChangedEnd'))):
                changed = registration((replace(upgraded[0], **{field:value}), *upgraded[1:]))
                with self.subTest(field=field), self.assertRaises(CharacterRegistryError):
                    audit_source_spline_alignment_upgrade(before, changed, ('',))

    def test_application_uses_complete_rebuild_and_explicit_selection(self):
        before = registration(self.layouts())
        host = NS(read_character_registration=lambda: before)
        with patch('adv_py.application.source_spline_alignment_upgrade.RebuildBodyCharacter') as rebuild:
            rebuild.return_value.apply.return_value = 'promoted'
            result = UpgradeSourceSplineAlignment(host).apply('Stage', ('Tail_M',),
                                                            extensions=('|UserAttachment',))
            rebuild.return_value.apply.assert_called_once_with('Stage',
                extensions=('|UserAttachment',), spline_alignment_systems=('Tail_M',))
            self.assertEqual(result.rebuild, 'promoted')

    def test_current_layout_does_not_touch_a_scene_or_stage(self):
        layouts = tuple(replace(plan, source_alignment_frames=True) for plan in self.layouts())
        host = NS(read_character_registration=lambda: registration(layouts))
        with patch('adv_py.application.source_spline_alignment_upgrade.RebuildBodyCharacter') as rebuild:
            result = UpgradeSourceSplineAlignment(host).apply('Unused')
            self.assertEqual(result.systems, ())
            self.assertIsNone(result.rebuild)
            rebuild.assert_not_called()


if __name__ == '__main__':
    unittest.main()
