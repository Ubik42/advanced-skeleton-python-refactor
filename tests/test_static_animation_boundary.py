"""Static cleanup follows actual native DG changes, without replacing drivers."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_static_animation_boundary import capture,finish
from adv_py.adapters.maya_source_name_matcher_session import remember,audit
from adv_py.adapters.maya_source_native_animation import observe_disconnect,capture as native_capture
from adv_py.adapters.maya_source_mocap_rebuild import expected,sample_frames
from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_name_matcher_session import ATTRIBUTE,decode_session,rebase_session
from adv_py.core.source_native_animation import ATTRIBUTE as NATIVE_ATTRIBUTE,decode_native_animation
from test_source_native_animation import NativeCommands


class StaticAnimationTests(unittest.TestCase):
    def fixture(self,*,detached=False):
        c=NativeCommands()
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            scene_address=lambda name:c.group if name=='MoCapConstraints' else name)
        saved=remember(host,((c.control,None,c.constraint),))
        if detached:
            c.native_disconnect();observe_disconnect(host,saved)
        return host,c

    def remove_curve(self,c,axis):
        name='anim'+axis
        c.nodes.pop(name)
        c.inputs={dest:source for dest,source in c.inputs.items() if source!=name+'.output'}

    def test_detached_native_record_forgets_only_genuinely_deleted_time_curve(self):
        host,c=self.fixture(detached=True)
        boundary=capture(host)
        self.remove_curve(c,'X')
        graph=deepcopy(c.nodes),deepcopy(c.inputs)
        finish(host,boundary)
        self.assertEqual((c.nodes,c.inputs),graph)
        current=decode_native_animation(c.attrs[c.blend+'.'+NATIVE_ATTRIBUTE])
        self.assertFalse(any(edge['source_uuid']=='animX-id' for edge in current['node']['inputs']))
        self.assertIn({'attribute':'inRotateX1','value':0.},current['settings'])
        self.assertEqual(len(native_capture(host)),1)

    def test_active_static_cleanup_preserves_unbaked_session_and_closed_rebuild_document(self):
        host,c=self.fixture()
        boundary=capture(host)
        self.remove_curve(c,'X')
        finish(host,boundary)
        current=decode_session(c.attrs[c.group+'.'+ATTRIBUTE])
        self.assertEqual(current['version'],3)
        self.assertTrue(current['static_cleaned'])
        self.assertFalse(current['baked'])
        self.assertEqual(len(audit(host)),3)
        changed=rebase_session(current,{'control-id':('|staged|FK','staged-control-id')})
        self.assertEqual(changed['receivers'][0]['uuid'],'staged-control-id')
        self.assertFalse(changed['baked'])

    def test_static_cleanup_cannot_authorize_rewire_or_disconnection_of_live_curve(self):
        for mode in ('rewire','detach-live','cache'):
            with self.subTest(mode=mode):
                host,c=self.fixture(detached=True)
                boundary=capture(host)
                if mode=='rewire':c.inputs[c.blend+'.inRotateX1']='animY.output'
                elif mode=='detach-live':c.inputs.pop(c.blend+'.inRotateX1')
                else:
                    self.remove_curve(c,'X');c.attrs[c.blend+'.inRotateX1']=4.
                with self.assertRaises(CharacterRegistryError):finish(host,boundary)

    def test_deleted_native_blend_may_collapse_to_its_same_axis_original_inputs(self):
        host,c=self.fixture(detached=True)
        boundary=capture(host)
        c.nodes.pop(c.blend)
        c.inputs={dest:source for dest,source in c.inputs.items()
            if dest.split('.',1)[0]!=c.blend and source.split('.',1)[0]!=c.blend}
        c.attrs={plug:value for plug,value in c.attrs.items() if plug.split('.',1)[0]!=c.blend}
        for axis in 'XYZ':c.inputs[c.control+'.rotate'+axis]='anim'+axis+'.output'
        graph=deepcopy(c.nodes),deepcopy(c.inputs)
        finish(host,boundary)
        self.assertEqual((c.nodes,c.inputs),graph)
        self.assertEqual(native_capture(host),())

    def test_deleted_blend_cannot_collapse_to_wrong_axis_or_new_node(self):
        host,c=self.fixture(detached=True)
        boundary=capture(host)
        c.nodes.pop(c.blend)
        c.inputs={dest:source for dest,source in c.inputs.items()
            if dest.split('.',1)[0]!=c.blend and source.split('.',1)[0]!=c.blend}
        c.inputs[c.control+'.rotateX']='animY.output'
        with self.assertRaisesRegex(CharacterRegistryError,'非原输入'):finish(host,boundary)

    def test_active_native_blend_deletion_does_not_fabricate_a_bake(self):
        host,c=self.fixture()
        boundary=capture(host)
        c.nodes.pop(c.blend)
        c.inputs={dest:source for dest,source in c.inputs.items()
            if dest.split('.',1)[0]!=c.blend and source.split('.',1)[0]!=c.blend}
        for axis in 'XYZ':
            c.inputs[c.control+'.rotate'+axis]=c.constraint+'.constraintRotate'+axis
        finish(host,boundary)
        current=decode_session(c.attrs[c.group+'.'+ATTRIBUTE])
        self.assertFalse(current['baked'])
        self.assertEqual(current['removed_blends'],['blend-id'])
        self.assertTrue(current['static_cleaned'])
        invalid={**current,'static_cleaned':False}
        with self.assertRaises(CharacterRegistryError):decode_session(canonical(invalid))

    def test_rebuild_does_not_resurrect_inputs_of_natively_deleted_blend(self):
        host,c=self.fixture()
        boundary=capture(host)
        c.nodes.pop(c.blend)
        self.remove_curve(c,'X')
        c.inputs={dest:source for dest,source in c.inputs.items()
            if dest.split('.',1)[0]!=c.blend and source.split('.',1)[0]!=c.blend}
        for axis in 'XYZ':c.inputs[c.control+'.rotate'+axis]=c.constraint+'.constraintRotate'+axis
        finish(host,boundary)
        document=c.attrs[c.group+'.'+ATTRIBUTE]
        staged=SimpleNamespace(original=SimpleNamespace(mocap_session=document),
            ownership=SimpleNamespace(nodes=(),removed_nodes=()))
        self.assertEqual(expected(host,staged),decode_session(document))
        node_type=c.nodeType
        c.nodeType=lambda node,**flags: (['dagNode',node_type(node)]
            if flags.get('inherited') and node_type(node) in ('joint','transform') else node_type(node))
        c.keyframe=lambda node,**flags: [1.,6.5,12.] if node==c.target else []
        c.playbackOptions=lambda **flags: 1. if flags.get('minTime') else 12.
        self.assertEqual(sample_frames(host,document),(1.,6.5,12.))


if __name__=='__main__':unittest.main()
