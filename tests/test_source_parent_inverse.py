import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from adv_py.adapters.maya_source_parent_inverse import repair
from adv_py.core.character_registry import CharacterRegistryError


class SourceParentInverseTests(unittest.TestCase):
    def fixture(self, *, existing=True, owned=True, foreign_driver=False, locked=False):
        matrix = 'AdvPy_SourceRootFollowMM'
        node = '|Group|MotionSystem|FKSystem|RootOffset'
        c = Mock()
        c.objExists.side_effect = lambda name: existing and name == matrix
        c.connectionInfo.return_value = [node + '.offsetParentMatrix']
        c.isConnected.return_value = not foreign_driver
        c.listRelatives.return_value = [node.rsplit('|', 1)[0]]
        c.nodeType.return_value = 'multMatrix'
        c.referenceQuery.return_value = False
        c.lockNode.return_value = [locked]
        c.getAttr.return_value = False
        host = SimpleNamespace(_cmds=c, _transaction_changed=False,
            _require_transaction=Mock(), _resolve_connected_node=lambda path: path)
        reg = SimpleNamespace(nodes=(SimpleNamespace(path=node),) if owned else (),
                              spine=None, additional_spines=())
        return host, reg, node, matrix

    def test_only_the_exact_registered_self_inverse_is_replaced(self):
        host, reg, node, matrix = self.fixture()
        edits = repair(host, reg)
        self.assertEqual(edits, ((node + '.parentInverseMatrix[0]',
            node.rsplit('|', 1)[0] + '.worldInverseMatrix[0]', matrix + '.matrixIn[2]'),))
        host._cmds.disconnectAttr.assert_called_once_with(edits[0][0], edits[0][2])
        host._cmds.connectAttr.assert_called_once_with(edits[0][1], edits[0][2])
        self.assertTrue(host._transaction_changed)

    def test_foreign_input_is_never_overwritten(self):
        host, reg, _, _ = self.fixture(foreign_driver=True)
        self.assertEqual(repair(host, reg), ())
        host._cmds.disconnectAttr.assert_not_called()

    def test_foreign_output_and_locked_matrix_fail_without_mutation(self):
        for options in ({'owned': False}, {'locked': True}):
            host, reg, _, _ = self.fixture(**options)
            with self.subTest(options=options), self.assertRaises(CharacterRegistryError):
                repair(host, reg)
            host._cmds.disconnectAttr.assert_not_called()

    def test_missing_source_system_is_a_read_only_noop(self):
        host, reg, _, _ = self.fixture(existing=False)
        self.assertEqual(repair(host, reg), ())
        host._require_transaction.assert_not_called()


if __name__ == '__main__':
    unittest.main()
