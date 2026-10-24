"""Native imported influence subtrees stay separate from generated Body."""
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_name_matcher_retained import retained_roots,KIND
from adv_py.core.character_registry import CharacterRegistryError


class Commands:
    body='|Group|DeformationSystem|Root_M'
    wrist=body+'|Wrist_R'
    branch=wrist+'|src:Extra'
    child=branch+'|src:End'
    ordinary=wrist+'|Other'
    def __init__(self):
        self.marked={self.branch:KIND,self.child:KIND}
        self.parents={self.branch:self.wrist,self.child:self.branch,self.ordinary:self.wrist}
        self.unlocked=set()
    def listRelatives(self,address,**flags):
        if flags.get('parent'):return [self.parents[address]]
        return [self.wrist,*self.parents]
    def attributeQuery(self,name,*,node,**flags):return node in self.marked
    def getAttr(self,address,**flags):
        node=address.split('.',1)[0]
        if flags.get('type'):return 'string'
        if flags.get('lock'):return node not in self.unlocked
        return self.marked[node]


class MatcherRetainedTests(unittest.TestCase):
    def fixture(self):
        c=Commands()
        saved=SimpleNamespace(body_root=c.body,
            body=tuple(SimpleNamespace(path=node) for node in (c.body,c.wrist)),
            nodes=tuple(SimpleNamespace(path=node) for node in (c.body,c.wrist)))
        return SimpleNamespace(_cmds=c),saved

    def test_marked_subtree_is_kept_once_without_claiming_other_joint_children(self):
        host,saved=self.fixture()
        self.assertEqual(retained_roots(host,saved),(host._cmds.branch,))
        host._cmds.marked[host._cmds.ordinary]='custom-skin-v1'
        self.assertEqual(retained_roots(host,saved),(host._cmds.branch,))

    def test_unlocked_or_generated_markers_cannot_authorize_retained_foreign_subtrees(self):
        host,saved=self.fixture()
        host._cmds.unlocked.add(host._cmds.child)
        with self.assertRaisesRegex(CharacterRegistryError,'标记无效'):retained_roots(host,saved)
        host,saved=self.fixture()
        saved.nodes+=(SimpleNamespace(path=host._cmds.branch),)
        with self.assertRaisesRegex(CharacterRegistryError,'标记无效'):retained_roots(host,saved)

    def test_branch_must_still_be_attached_to_the_actual_body_correspondence(self):
        host,saved=self.fixture()
        host._cmds.parents[host._cmds.branch]='|otherRig|joint'
        with self.assertRaisesRegex(CharacterRegistryError,'Body 父级'):retained_roots(host,saved)


if __name__=='__main__':unittest.main()
