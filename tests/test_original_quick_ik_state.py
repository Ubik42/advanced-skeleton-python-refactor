"""QuickIK accepts native time keys, while keeping original UUID inputs exact."""
from types import SimpleNamespace
import unittest
from adv_py.adapters.maya_original_quick_ik_state import remember, audit
from adv_py.core.character_registry import CharacterRegistryError
from test_source_native_animation import NativeCommands


class OriginalQuickIKStateTests(unittest.TestCase):
    def fixture(self):
        c=NativeCommands()
        c.nodes['|QuickIK']=('quick-root-id','transform',None)
        group='|QuickIK|QuickIK_Hip_RGroup'
        joint=group+'|QuickIKjoint_Hip_R'
        c.nodes[group]=('quick-group-id','transform','|QuickIK')
        c.nodes[joint]=('quick-joint-id','joint',group)
        c.inputs[c.constraint+'.target[0].targetParentMatrix']=joint+'.parentMatrix[0]'
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,scene_address=lambda node:node)
        remember(host,group,(c.control,),(c.constraint,))
        return host,c,joint

    def test_new_native_quick_control_time_keys_do_not_invalidate_the_original_graph(self):
        host,c,joint=self.fixture()
        self.assertEqual(len(audit(host)),3)
        c.nodes['quickKey']=('quick-key-id','animCurveTL',None)
        c.inputs[joint+'.translateX']='quickKey.output'
        self.assertEqual(len(audit(host)),3)

    def test_same_name_joint_replacement_and_receiver_axis_rewire_are_rejected(self):
        host,c,joint=self.fixture()
        c.nodes[joint]=('replacement-joint-id','joint',c.nodes[joint][2])
        with self.assertRaises(CharacterRegistryError):audit(host)
        host,c,_=self.fixture()
        c.inputs[c.control+'.rotateX']=c.blend+'.outRotateY'
        with self.assertRaises(CharacterRegistryError):audit(host)
