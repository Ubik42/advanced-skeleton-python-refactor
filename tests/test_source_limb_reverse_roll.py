from types import SimpleNamespace as Row
import unittest

from adv_py.adapters.maya_source_limb_reverse_roll import align_original_reverse_roll
from adv_py.core.character_registry import CharacterRegistryError


class ReverseCommands:
    def __init__(self, fail_aim=False, handle=True):
        self.nodes = {}; self.calls = []; self.fail_aim = fail_aim; self.handle = handle
    def listRelatives(self, node, **flags):
        return ['|Motion|Roll|LocalOrient|NativeHandle'] if flags.get('allDescendents') and self.handle else (
            ['|Motion|RollOffset'] if flags.get('parent') else [])
    def createNode(self, kind, **flags):
        identity = 'uuid-' + flags['name']
        path = flags['parent'] + '|' + flags['name']
        self.nodes[identity] = path
        self.calls.append(('create', identity, path))
        return path
    def ls(self, node, **flags):
        if flags.get('uuid'):
            return [key for key, value in self.nodes.items() if value == node]
        return [self.nodes[node]] if node in self.nodes else []
    def parent(self, node, parent, **flags):
        new = parent + '|' + node.rsplit('|', 1)[-1]
        for key, path in list(self.nodes.items()):
            if path == node or path.startswith(node + '|'):
                self.nodes[key] = new + path[len(node):]
        self.calls.append(('parent', node, parent, flags))
        return [new]
    def aimConstraint(self, target, node, **flags):
        self.calls.append(('aim', target, node, flags))
        if self.fail_aim: raise RuntimeError('native aim failed')
        return ['aimConstraint1']
    def xform(self, node, **flags):
        self.calls.append(('xform', node, flags))
        if flags.get('query'):
            if node != self.nodes['uuid-tempXform2']:
                raise RuntimeError('stale temporary DAG path')
            return (12., 34., 56.)
    def delete(self, nodes):
        for node in nodes:
            for key, path in list(self.nodes.items()):
                if path == node or path.startswith(node + '|'): del self.nodes[key]


def binding(side):
    return Row(reverse_roll='|Motion|Roll', primary_count=3, side=side,
               joints=tuple(Row(control='FK' + name, fk_driver='FKX' + name)
                            for name in ('Hip', 'Knee', 'Ankle')))


class SourceReverseRollTests(unittest.TestCase):
    def test_source_uses_descendant_local_handle_actual_fk_and_world_euler(self):
        for side, sign in (('R', 1.), ('L', -1.)):
            commands = ReverseCommands()
            host = Row(_cmds=commands, _require_transaction=lambda: None, _transaction_changed=False)
            align_original_reverse_roll(host, binding(side))
            aim = next(row for row in commands.calls if row[0] == 'aim')
            self.assertEqual(aim[1], 'FKAnkle')
            self.assertEqual(aim[3]['aimVector'], (-sign, 0., 0.))
            self.assertEqual(aim[3]['upVector'], (0., sign, 0.))
            self.assertEqual(aim[3]['worldUpObject'], 'FKAnkle')
            self.assertEqual(commands.calls[-1], ('xform', '|Motion|Roll',
                {'worldSpace': True, 'rotation': (12., 34., 56.)}))
            self.assertFalse(commands.nodes)
            self.assertTrue(host._transaction_changed)

    def test_failure_cleans_reparented_temporaries_by_identity(self):
        commands = ReverseCommands(fail_aim=True)
        host = Row(_cmds=commands, _require_transaction=lambda: None, _transaction_changed=False)
        with self.assertRaisesRegex(RuntimeError, 'native aim failed'):
            align_original_reverse_roll(host, binding('L'))
        self.assertFalse(commands.nodes)

    def test_missing_source_handle_does_not_create_temporary_nodes(self):
        commands = ReverseCommands(handle=False)
        host = Row(_cmds=commands, _require_transaction=lambda: None, _transaction_changed=False)
        with self.assertRaises(CharacterRegistryError):
            align_original_reverse_roll(host, binding('R'))
        self.assertFalse(commands.calls)
