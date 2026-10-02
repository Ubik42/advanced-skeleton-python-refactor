from types import SimpleNamespace as Row
import unittest

from adv_py.adapters.maya_namespace import MayaCharacterCommands
from adv_py.adapters.maya_body_selection_sets import MayaBodySelectionSetsMixin
from adv_py.core.body_all_set import BodyAllSetPlan


class Commands:
    def __init__(self): self.current=':'; self.calls=[]
    def namespace(self, **flags):
        if flags.get('query'): return False
        if flags.get('exists'): return True
        self.current=flags['setNamespace']
    def namespaceInfo(self, **flags): return self.current
    def autoKeyframe(self, **flags): self.calls.append(('auto',flags)); return True
    def playbackOptions(self, **flags): self.calls.append(('timeline',flags)); return (1.,10.)
    def warning(self, text): self.calls.append(('warning',text))
    def skinPercent(self, *args, **flags): self.calls.append(('skin',args,flags))
    def listSets(self, **flags): self.calls.append(('sets',flags)); return ['hero:AllSet']


class SourceCommandBoundaryTests(unittest.TestCase):
    def test_original_auto_key_timeline_and_warning_are_shared_literal_operations(self):
        raw=Commands(); c=MayaCharacterCommands(raw,'hero')
        self.assertTrue(c.autoKeyframe(query=True,state=True))
        self.assertEqual(c.playbackOptions(query=True,selectionStartTime=True),(1.,10.))
        c.warning('Missing: partner:Control.rotateX')
        self.assertEqual(raw.calls[-1],('warning','Missing: partner:Control.rotateX'))
        self.assertEqual(raw.current,':')

    def test_native_single_and_multiple_influence_pairs_keep_weights(self):
        raw=Commands(); c=MayaCharacterCommands(raw,'hero')
        c.skinPercent('Skin','Mesh.vtx[2]',transformValue=('Elbow_R',.75))
        self.assertEqual(raw.calls[-1][2]['transformValue'],(':hero:Elbow_R',.75))
        c.skinPercent('Skin','Mesh.vtx[2]',transformValue=[('Elbow_R',.75),('Wrist_R',.25)])
        self.assertEqual(raw.calls[-1][2]['transformValue'],[(':hero:Elbow_R',.75),(':hero:Wrist_R',.25)])
        self.assertEqual(c.listSets(object='Skin'),['AllSet'])
        self.assertEqual(raw.calls[-1],('sets',{'object':':hero:Skin'}))

    def set_host(self, members):
        raw=Row(objExists=lambda _:True,nodeType=lambda _:'objectSet',
                referenceQuery=lambda *a,**k:False,sets=lambda *a,**k:None)
        return Row(_cmds=raw,_require_transaction=lambda:None,_transaction_changed=False,
            _body_selection_set_address=lambda name:name,scene_address=lambda name:name,
            capture_body_all_set_members=lambda:tuple(members))

    def test_native_all_set_completion_accepts_source_helpers_partial_membership(self):
        host=self.set_host(('ExistingNode',))
        MayaBodySelectionSetsMixin.populate_body_all_set(host,
            BodyAllSetPlan(('ExistingNode','NewSDKCurve')))
        self.assertTrue(host._transaction_changed)

    def test_all_set_completion_rejects_unrelated_existing_members(self):
        host=self.set_host(('UnrelatedNode',))
        with self.assertRaises(ValueError):
            MayaBodySelectionSetsMixin.populate_body_all_set(host,BodyAllSetPlan(('NewSDKCurve',)))
        self.assertFalse(host._transaction_changed)
