"""Source Fit manual update dispatch, center locks and native scale gates."""
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_fit import MayaFitJointHost
from adv_py.adapters.maya_source_fit_manual_update import MayaSourceFitManualUpdateMixin
from adv_py.core.fit_hierarchy import FitHierarchyNode, FitHierarchySnapshot
from adv_py.core.source_fit_center_locks import source_fit_center_locks
from adv_py.core.source_fit_unique_names import source_fit_unique_labels


IDENTITY = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)


def hierarchy(x=0., parent='|FitSkeleton'):
    return FitHierarchySnapshot('|FitSkeleton', (
        FitHierarchyNode(parent+'|Joint', 'Joint', parent,
                         (x,17.176163,0.), (x,17.176163,0.)),))


class ManualCommands:
    def __init__(self, locked):
        self.locked = locked
        self.selection = ['|FitSkeleton|Root']
        self.calls = []

    def objExists(self, *args):
        return True

    def ls(self, **options):
        return self.selection

    def attributeQuery(self, *args, **options):
        return True

    def getAttr(self, plug):
        return self.locked

    def select(self, nodes=None, **options):
        self.calls.append(('select', nodes))


class ManualHost(MayaSourceFitManualUpdateMixin):
    def __init__(self, locked=True):
        self._cmds = ManualCommands(locked)
        self.calls = []

    def _require_transaction(self):
        pass

    def _resolve_transform(self, *args):
        return '|FitSkeleton'

    def normalize_fit_joint_names(self, *args):
        self.calls.append('names')

    def normalize_fit_ik_labels(self, *args):
        self.calls.append('labels')

    def set_fit_center_joint_lock_state(self, container, enabled):
        self.calls.append(('locks', enabled))
        self._cmds.locked = enabled

    @contextmanager
    def fit_manual_update_channels(self, *args):
        self.calls.append('channels_enter')
        yield
        self.calls.append('channels_exit')

    def bake_fit_container_scale(self, *args):
        self.calls.append('manual_scale')

    def bake_fit_container_scale_for_build(self, *args):
        self.calls.append('build_scale')

    def snap_fit_ik_chain_centers(self, *args):
        self.calls.append('snap')


class SourceFitManualUpdateTests(unittest.TestCase):
    def test_center_locks_use_world_points_including_parent_translation(self):
        frame = list(IDENTITY)
        frame[12] = .6
        locks = source_fit_center_locks(hierarchy(), {'|FitSkeleton': frame}, '-X', 'Z')
        self.assertEqual(locks[0][1], ('tx', 'ty', 'tz', 'rx', 'rz'))

    def test_native_half_unit_sampler_threshold_is_strict(self):
        frame = list(IDENTITY)
        frame[0] = .5
        locks = source_fit_center_locks(hierarchy(), {'|FitSkeleton': frame}, 'Y', '-Z')
        self.assertEqual(locks[0][1], ('ry', 'rz'))

    def test_side_joint_remains_unlocked_and_does_not_require_parent_frame(self):
        self.assertEqual(source_fit_center_locks(hierarchy(.010001), {}, 'X', 'Y')[0][1], ())

    def test_center_threshold_includes_native_exact_boundary(self):
        self.assertEqual(source_fit_center_locks(hierarchy(.01), {'|FitSkeleton': IDENTITY},
                                                'X', 'Y')[0][1], ('tx','rx','ry'))

    def test_manual_update_follows_source_order_and_restores_center_lock_mode(self):
        host = ManualHost()
        with patch('adv_py.application.registered_body_build._refresh_fit_orientations_before_body',
                   side_effect=lambda *args: host.calls.append('aim')):
            host.manual_update_fit()
        self.assertEqual(host.calls, ['names','labels',('locks',False),'channels_enter',
                                     'manual_scale','aim','channels_exit',('locks',True)])
        self.assertTrue(host._cmds.locked)
        self.assertEqual(tuple(host._cmds.calls[0][1]), ('|FitSkeleton|Root',))

    def test_build_dispatch_forces_scale_and_unlocked_centers_stay_unlocked(self):
        host = ManualHost(locked=False)
        with patch('adv_py.application.registered_body_build._refresh_fit_orientations_before_body',
                   side_effect=lambda *args: host.calls.append('aim')):
            host.manual_update_fit(from_body_build=True)
        self.assertIn('build_scale', host.calls)
        self.assertFalse(any(isinstance(call, tuple) and call[0]=='locks' for call in host.calls))

    def test_label_duplicates_keep_the_source_array_and_candidate_order(self):
        rows = (('a','Shoulder'),('b','Shoulder'),('c','Shoulder1'),
                ('d','Neck'),('e','Neck'),('f','0Spine'),('g','0Spine'),('h','0SpineA'))
        self.assertEqual(source_fit_unique_labels(rows),
                         (('a','Shoulder2'),('b','Shoulder3'),('f','0SpineB'),('g','0SpineC')))

    def test_native_label_exhaustion_keeps_last_candidate_instead_of_inventing_a_name(self):
        rows = (('a','0Spine'),('b','0Spine'), *tuple((str(i),'0Spine'+chr(65+i)) for i in range(26)))
        self.assertEqual(source_fit_unique_labels(rows), (('a','0Spine'),('b','0Spine')))

    def test_unit_scale_manual_update_leaves_authored_joint_scales_untouched(self):
        class Commands:
            def getAttr(self, *args): return [(1.,1.,1.)]
            def listRelatives(self, *args, **options):
                if options.get('type') == 'transform': return []
                raise AssertionError('manual unit scale must return before enumerating joint TRS')
        host = MayaFitJointHost.__new__(MayaFitJointHost)
        host._cmds = Commands()
        host._transaction_active = True
        host._resolve_transform = lambda *args: '|FitSkeleton'
        host.bake_fit_container_scale('FitSkeleton')


if __name__ == '__main__':
    unittest.main()
