"""Native AutoRig keeps the original transform-top-node/template route."""
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adv_py.application.name_matcher_character import BuildNameMatchedCharacter
from adv_py.application.name_matcher_fit import NameMatcherFitResult
from adv_py.core.name_matcher_fit import NameMatcherRules
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.adapters.maya_source_skeleton_fit import MayaSourceSkeletonFitHost


@dataclass(frozen=True)
class Built:
    registration: str


class NativeCharacterTests(unittest.TestCase):
    def host(self):
        class Host:
            calls=[]
            changed=False
            @contextmanager
            def transaction(self,label):yield
            def capture_source_skeleton(self,root):
                raise AssertionError('Native AutoRig must not read a synthetic joint description')
            def capture_source_name_matcher_character_boundary(self,root):
                self.calls.append('boundary')
                return ('transform-top-id',self.changed)
            def capture_name_matcher_skin_boundary(self,root):return ('skin-id',)
            def capture_name_matcher_source_animation(self,root):return ()
            def create_source_name_matched_fit(self,*args,**kwargs):pass
            def capture_body_scene_nodes(self):return ()
            def create_source_name_matcher_blend_controls(self):self.calls.append('blend-controls')
            def attach_source_name_matcher_skeleton(self,*args):
                self.calls.append('attach')
                return SimpleNamespace(constraints=3)
            def auto_scale_source_name_matcher_fk_curves(self):self.calls.append('scale-controls')
            def read_character_registration(self):return 'actual-final-registration'
        return Host()

    def test_transform_top_node_runs_full_native_build_and_attachment(self):
        host=self.host()
        fit=NameMatcherFitResult(32,(),1.,'|sourceTop')
        with patch('adv_py.application.name_matcher_character.BuildNameMatchedFit') as fit_builder, \
             patch('adv_py.application.name_matcher_character.BuildRegisteredBodyCharacter') as body_builder:
            fit_builder.return_value.apply.return_value=fit
            body_builder.return_value.apply.return_value=Built('before-attachment')
            result=BuildNameMatchedCharacter(host).apply('|sourceTop',(),NameMatcherRules())
        self.assertEqual(result.fit,fit)
        self.assertEqual(result.body.registration,'actual-final-registration')
        self.assertIsNone(result.animation)
        self.assertEqual(result.skins_preserved,1)
        self.assertEqual(host.calls,['boundary','boundary','blend-controls','attach','scale-controls'])

    def test_source_changes_before_native_build_are_rejected(self):
        host=self.host()
        original=host.capture_source_name_matcher_character_boundary
        def changed(root):
            value=original(root)
            host.changed=True
            return value
        host.capture_source_name_matcher_character_boundary=changed
        with self.assertRaisesRegex(FitSkeletonValidationError,'构建前变化'):
            BuildNameMatchedCharacter(host).apply('|sourceTop',(),NameMatcherRules())

    def test_skin_boundary_includes_joints_below_a_transform_top(self):
        class Commands:
            def ls(self,address=None,**flags):
                if flags.get('type')=='skinCluster':return ['model:skin']
                if flags.get('uuid'):
                    return {'|sourceTop|hip':['hip-id'],'model:skin':['skin-id'],
                            '|model|bodyShape':['mesh-id']}.get(address,[])
                return ['|sourceTop'] if address=='sourceTop' else []
            def nodeType(self,address):return 'transform' if address=='|sourceTop' else 'joint'
            def listRelatives(self,*args,**flags):return ['|sourceTop|hip']
            def skinCluster(self,node,**flags):
                return ['|sourceTop|hip'] if flags.get('influence') else ['|model|bodyShape']
        host=MayaSourceSkeletonFitHost.__new__(MayaSourceSkeletonFitHost)
        host._cmds=Commands()
        self.assertEqual(host.capture_name_matcher_skin_boundary('sourceTop'),
                         (('skin-id',('hip-id',),('mesh-id',)),))


if __name__=='__main__':unittest.main()
