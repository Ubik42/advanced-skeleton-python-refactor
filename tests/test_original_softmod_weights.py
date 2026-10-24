"""Offline checks of the source weight writes, locks and cleanup ordering."""
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_face_softmod_weights import MayaFaceSoftModWeightsMixin


class Commands:
    def __init__(self):
        self.selection = ['originalControl']; self.moved = False
        self.events = []; self.writes = []; self.nodes = {'joint_R','mesh','skin','lipArea'}
    def ls(self, **flags):
        return ['tempMesh.vtx[0]','tempMesh.vtx[1]'] if flags.get('flatten') else list(self.selection)
    def nodeType(self, node): return 'skinCluster'
    def objExists(self, plug): return plug in self.nodes
    def xform(self, node, **flags):
        if not flags.get('query'):return None
        if node == 'joint_R':return [0.,0.,0.]
        return [0., (2. if node.endswith('[1]') else 0.) + (.25 if self.moved else 0.), 0.]
    def duplicate(self, geometry, **flags): self.nodes.add(flags['name']); return [flags['name']]
    def softMod(self, node): return ['tempSoft','tempHandle']
    def rename(self, node, name):self.nodes.add(name);return name
    def setAttr(self, plug, *values, **flags):
        if plug == 'TempSoftModHandle.ty':self.moved = bool(values[0])
        self.events.append(('set',plug,values))
    def select(self, *nodes, **flags):self.selection = list(nodes)
    def polySelectConstraint(self, **flags):pass
    def sets(self, vertex, **flags):return vertex.endswith('[1]')
    def about(self, **flags):return False
    def progressBar(self, progress, **flags):
        if flags.get('query'):return False
        self.events.append(('end' if flags.get('endProgress') else 'progress',))
    def skinPercent(self, skin, geometry, **flags):
        self.writes.append((skin,geometry,flags))
    def delete(self, node):self.nodes.discard(node);self.events.append(('delete',node))


class Host(MayaFaceSoftModWeightsMixin):
    def __init__(self, commands):self._cmds = commands;self._transaction_changed = False
    def _require_transaction(self):pass
    def scene_address(self, node):return node
    def _original_restore_leaf(self, node):return node
    def _original_softmod_influence_index(self, skin, joint):return 7
    def _original_face_softmod_sets(self):return nullcontext()


class OriginalSoftModTests(unittest.TestCase):
    def test_sparse_source_weights_keep_logical_index_and_two_normalizes(self):
        c=Commands();host=Host(c)
        host.set_original_face_joint_weights('joint_R','mesh','skin',(4,9),(.2,.8))
        self.assertEqual(c.events[:2], [('set','skin.weightList[4].weights[7]',(.2,)),
                                      ('set','skin.weightList[9].weights[7]',(.8,))])
        self.assertEqual([row for row in c.events if row[1:2]==('joint_R.lockInfluenceWeights',)],
                         [('set','joint_R.lockInfluenceWeights',(True,)),
                          ('set','joint_R.lockInfluenceWeights',(False,))])
        self.assertEqual(c.writes, [('skin','mesh',dict(normalize=True)),
                                   ('skin','mesh',dict(normalize=True))])

    def test_short_source_weight_array_is_not_silently_truncated(self):
        c=Commands();host=Host(c)
        with self.assertRaises(IndexError):
            host.set_original_face_joint_weights('joint_R','mesh','skin',(4,9),(.2,))
        self.assertTrue(host._transaction_changed)

    def test_delta_branch_writes_skipped_initial_vertex_and_ends_after_cleanup(self):
        c=Commands();host=Host(c)
        maya=ModuleType('maya');maya.mel=SimpleNamespace(eval=lambda text:'progress')
        with patch.dict('sys.modules',{'maya':maya}):
            count=host._weight_original_face_by_softmod_delta('joint_R','mesh','skin',2.,.5)
        self.assertEqual(count,2)
        self.assertEqual(c.writes, [('skin','mesh.vtx[0]',dict(transformValue=(('joint_R',.125),))),
                                   ('skin','mesh.vtx[1]',dict(transformValue=(('joint_R',1),)))])
        self.assertLess(c.events.index(('delete','tempMesh')),c.events.index(('end',)))
        self.assertFalse(c.moved)
        self.assertTrue(host._transaction_changed)


if __name__=='__main__':unittest.main()
