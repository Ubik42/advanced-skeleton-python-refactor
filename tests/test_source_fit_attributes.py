"""Original grouped defaults, selection targets and legacy attribute removal."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adv_py.adapters.maya_source_fit_attributes import add, remove
from adv_py.adapters.maya_fit import MayaFitJointHost
from adv_py.core.fit_metadata import FitJointValidationError


class Commands:
    def __init__(self):
        self.selected = ['Root', 'Hip']
        self.types = dict(Root='joint', Hip='joint', Knee='joint', geo='transform',
                          geoShape='mesh', guide='transform', guideShape='nurbsCurve')
        self.attrs = {}
        self.definitions = {}
        self.events = []
        self.version = '2026'

    def ls(self, **flags):
        return [node for node in self.selected
                if not flags.get('type') or self.types[node] == flags['type']]

    def objectType(self, node):
        return self.types[node]

    def attributeQuery(self, name, *, node, **flags):
        return node+'.'+name in self.attrs

    def addAttr(self, node, **flags):
        plug = node+'.'+flags['longName']
        if plug in self.attrs:
            raise RuntimeError('Attribute already exists: '+plug)
        self.attrs[plug] = flags['defaultValue']
        self.definitions[plug] = flags
        self.events.append(('add', plug))

    def deleteAttr(self, plug):
        del self.attrs[plug]
        self.events.append(('remove', plug))

    def listAttr(self, node, **flags):
        return [plug.split('.', 1)[1] for plug in self.attrs if plug.startswith(node+'.')]

    def listRelatives(self, node, **flags):
        return {'geo': ['geoShape'], 'guide': ['guideShape']}.get(node, [])

    def select(self, node, **flags):
        self.selected = [node]

    def warning(self, message):
        self.events.append(('warning', message))

    def about(self, **flags):
        return self.version


class Host:
    namespace = None
    def __init__(self):
        self._cmds = Commands()
        self._transaction_active = False
        self._transaction_changed = False

    @contextmanager
    def transaction(self, label):
        if self._transaction_active:
            raise AssertionError('Nested transaction')
        before = dict(self._cmds.attrs)
        self._transaction_active = True
        self._transaction_changed = False
        try:
            yield
        except Exception:
            self._cmds.attrs = before
            raise
        finally:
            self._transaction_active = False


class SourceFitAttributeTests(unittest.TestCase):
    def setUp(self):
        self.host = Host()
        self.c = self.host._cmds

    def test_twist_group_source_defaults_skip_existing_and_update_geometry_after_commit(self):
        self.c.attrs['Hip.twistJoints'] = 7
        events = []
        def geometry(host):
            self.assertFalse(host._transaction_active)
            events.append(dict(self.c.attrs))
        with patch('adv_py.adapters.maya_source_fit_attributes._refresh_twist_geometry', geometry):
            self.assertEqual(add(self.host, 'twist/bendy'), ('Root',))
        self.assertEqual(self.c.attrs['Root.twistJoints'], 2)
        self.assertEqual(self.c.attrs['Root.bendyCtrls'], 0)
        self.assertEqual(self.c.attrs['Hip.twistJoints'], 7)
        self.assertNotIn('Hip.bendyCtrls', self.c.attrs)
        self.assertEqual(len(events), 1)

    def test_inbetween_conflict_keeps_prior_joint_and_undoes_only_failing_joint(self):
        self.c.attrs['Hip.twistJoints'] = 0
        with self.assertRaises(FitJointValidationError):
            add(self.host, 'inbetween')
        self.assertEqual(self.c.attrs['Root.inbetweenJoints'], 2)
        self.assertEqual(self.c.attrs['Root.unTwister'], 0)
        self.assertNotIn('Hip.inbetweenJoints', self.c.attrs)

    def test_aim_target_is_first_selected_and_all_receivers_keep_original_companions(self):
        self.c.selected = ['Root', 'Hip', 'Knee']
        self.assertEqual(add(self.host, 'aimAt'), ('Hip', 'Knee'))
        self.assertNotIn('Root.aimAt', self.c.attrs)
        for joint in ('Hip', 'Knee'):
            self.assertEqual(self.c.definitions[joint+'.aimAt']['enumName'], 'Root')
            self.assertEqual(self.c.attrs[joint+'.aimAxis'], 0)
            self.assertEqual(self.c.attrs[joint+'.aimUpAxis'], 1)
            self.assertEqual(self.c.attrs[joint+'.aimUpObject'], 0)
        self.assertEqual(self.c.selected, ['Knee'])

    def test_non_joint_in_constraint_selection_is_rejected_before_attribute_write(self):
        self.c.selected = ['Root', 'geo', 'Hip']
        with self.assertRaises(FitJointValidationError):
            add(self.host, 'parentConstraint')
        self.assertEqual(self.c.attrs, {})

    def test_geo_and_curve_guides_use_native_enum_modes_and_select_affected_joint(self):
        self.c.selected = ['Hip', 'geo']
        self.assertEqual(add(self.host, 'geoAttach'), ('Hip',))
        self.assertEqual(self.c.definitions['Hip.geoAttach']['enumName'], 'geo')
        self.assertEqual(self.c.attrs['Hip.geoAttachMode'], 2)
        self.c.selected = ['Knee', 'guide']
        self.assertEqual(add(self.host, 'curveGuide'), ('Knee',))
        self.assertEqual(self.c.attrs['Knee.curveGuideMode'], 1)
        self.assertEqual(self.c.selected, ['Knee'])

    def test_proximity_pin_version_gate_preserves_scene(self):
        self.c.version = '2019.3'
        self.c.selected = ['Hip', 'geo']
        with self.assertRaises(FitJointValidationError):
            add(self.host, 'proximityPin')
        self.assertEqual(self.c.attrs, {})

    def test_root_options_preserve_authored_zero_and_remove_both_legacy_spellings(self):
        self.c.selected = ['Root']
        self.c.attrs['Root.legLock'] = 0
        add(self.host, 'rootOptions')
        self.assertEqual(self.c.attrs, {'Root.legLock': 0, 'Root.numMainExtras': 0,
                                       'Root.centerBetweenFeet': 0})
        self.c.attrs['Root.centerBtwFeet'] = 1
        self.assertEqual(remove(self.host, 'rootOptions'), ('Root',))
        self.assertEqual(self.c.attrs, {})

    def test_follow_star_removal_is_original_wildcard_including_related_options(self):
        self.c.selected = ['Hip']
        self.c.attrs = {'Hip.followRoot': 10, 'Hip.follow': 0,
                        'Hip.followLeftRight': 0, 'Hip.followSpaces': 1, 'Hip.aim': 1}
        remove(self.host, 'follow*')
        self.assertEqual(self.c.attrs, {'Hip.aim': 1})

    def test_twist_removal_includes_old_bendy_and_part_controllers(self):
        self.c.selected = ['Hip']
        self.c.attrs = {'Hip.'+name: value for name, value in (
            ('twistJoints', 4), ('bendyJoints', 1), ('bendyCtrls', 2),
            ('partControllers', 1), ('control', 1))}
        remove(self.host, 'twist/bendy')
        self.assertEqual(self.c.attrs, {'Hip.control': 1})

    def test_no_mirror_existing_false_skips_companion_and_tweaker_requires_opm(self):
        self.c.selected = ['Hip']
        self.c.attrs['Hip.noMirror'] = 0
        self.assertEqual(add(self.host, 'noMirror'), ())
        self.assertNotIn('Hip.noMirrorLeft', self.c.attrs)
        self.assertEqual(add(self.host, 'tweakerControl', use_opm=False), ())
        self.assertEqual(add(self.host, 'tweakerControl', use_opm=True), ('Hip',))

    def test_world_orientation_and_child_of_part_keep_source_enum_defaults_and_bounds(self):
        self.c.selected = ['Hip']
        add(self.host, 'worldOrient')
        add(self.host, 'childOfPart')
        self.assertEqual(self.c.attrs['Hip.worldOrientForward'], 6)
        self.assertEqual(self.c.definitions['Hip.worldOrientForward']['enumName'],
            'xForward:yForward:zForward:xBackward:yBackward:zBackward:free:')
        self.assertEqual(self.c.attrs['Hip.childOfPart'], 2)
        self.assertEqual(self.c.definitions['Hip.childOfPart']['minValue'], 1)
        self.assertEqual(self.c.definitions['Hip.childOfPart']['maxValue'], 10)

    def test_mesh_target_keeps_existing_literal_and_decodes_only_first_separator(self):
        existing=set()
        host=SimpleNamespace(_cmds=SimpleNamespace(objExists=lambda node:node in existing),
            _optional_constraint_target=lambda *_:'a__b__mesh')
        read=lambda:MayaFitJointHost._optional_mesh_target(host,'Hip','geoAttach')
        existing.update(('a__b__mesh','a:b__mesh','a:b:mesh'))
        self.assertEqual(read(),'a__b__mesh')
        existing.remove('a__b__mesh')
        self.assertEqual(read(),'a:b__mesh')
        existing.remove('a:b__mesh')
        self.assertEqual(read(),'a__b__mesh')


if __name__ == '__main__':
    unittest.main()
