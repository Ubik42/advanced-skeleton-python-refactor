"""Native Connect must not impose the legacy single-root source reader."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest

from adv_py.application.name_matcher_mocap import ConnectNameMatchedMocap
from adv_py.core.name_matcher_fit import NameMatcherConstraintPair,NameMatcherConstraintPlan,NameMatcherRules
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.adapters.maya_source_mocap_connect import connect
from test_source_mocap_order import SourceMocapOrderTests


class NativeHost:
    def __init__(self,pairs=None):
        self.registration=SourceMocapOrderTests().registration()
        self.mapping=NameMatcherConstraintPlan(tuple(pairs if pairs is not None else (
            NameMatcherConstraintPair('|Root_M','|takeA:hips'),
            NameMatcherConstraintPair('|Wrist_R','|otherRoot|takeA:hand'))),('takeA:missingFoot',))
        self.boundary=(('actual-target-identities',),('actual-production-skin-identities',))
        self.calls=[];self.applied=[]
    def transaction(self,label):return nullcontext()
    def capture_source_skeleton(self,*args):raise AssertionError('Native mapping has no single source-root requirement')
    def capture_name_matcher_skin_boundary(self,*args):raise AssertionError('Skin must be read from actual mapped targets')
    def capture_name_matcher_advanced_joints(self):return ('|Root_M','|Wrist_R')
    def read_character_registration(self):return self.registration
    def plan_source_name_matcher_mocap_mapping(self,root,rows,rules,**flags):
        self.calls.append((root,flags));return self.mapping
    def capture_source_name_matcher_mocap_boundary(self,mapping):return self.boundary
    def preflight_name_matcher_mocap(self,plan):pass
    def apply_name_matcher_mocap(self,plan):
        self.applied.append(plan)
        return tuple((link.control,'point' if link.point else None,'orient') for link in plan.links)
    def verify_name_matcher_mocap(self,plan,created):pass


class SourceLiveMocapMappingTests(unittest.TestCase):
    def test_separate_source_roots_use_explicit_namespace_without_legacy_reader(self):
        host=NativeHost()
        result=ConnectNameMatchedMocap(host).apply(None,(),NameMatcherRules(),source_namespace='takeA')
        self.assertEqual(result.connected_controls,3)
        self.assertEqual(result.missing,('takeA:missingFoot',))
        self.assertTrue(all(root is None and flags=={'source_namespace':'takeA'} for root,flags in host.calls))
        self.assertEqual(tuple(link.external_joint for link in host.applied[0].links),
            ('|takeA:hips','|otherRoot|takeA:hand','|otherRoot|takeA:hand'))

    def test_no_matching_controls_leaves_native_connect_a_noop(self):
        host=NativeHost(pairs=())
        result=ConnectNameMatchedMocap(host).apply(None,(),NameMatcherRules(),source_namespace='takeA')
        self.assertEqual(result.connected_controls,0)
        plan=host.applied[0]
        commands=[]
        native=SimpleNamespace(_require_transaction=lambda:None,
            preflight_name_matcher_mocap=lambda value:commands.append('preflight'))
        self.assertEqual(connect(native,plan),())
        self.assertEqual(commands,['preflight'])

    def test_source_identity_change_before_mutation_is_rejected(self):
        host=NativeHost()
        def changed(plan):host.boundary=(('replacement-target',),host.boundary[1])
        host.preflight_name_matcher_mocap=changed
        with self.assertRaisesRegex(FitSkeletonValidationError,'实际来源'):
            ConnectNameMatchedMocap(host).apply(None,(),NameMatcherRules(),source_namespace='takeA')
        self.assertEqual(host.applied,[])

    def test_skin_endpoint_change_during_connect_is_rejected(self):
        host=NativeHost();native=host.apply_name_matcher_mocap
        def changed(plan):
            result=native(plan)
            host.boundary=(host.boundary[0],('replaced-skin',))
            return result
        host.apply_name_matcher_mocap=changed
        with self.assertRaisesRegex(RuntimeError,'生产 Skin'):
            ConnectNameMatchedMocap(host).apply(None,(),NameMatcherRules(),source_namespace='takeA')


if __name__=='__main__':unittest.main()
