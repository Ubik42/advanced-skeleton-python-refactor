"""Native motion receivers can move to Extra without adopting new drivers."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_animation_port_move import capture, finish
from adv_py.adapters.maya_source_name_matcher_session import remember, audit
from adv_py.adapters.maya_source_native_animation import observe_disconnect, capture as capture_native
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_name_matcher_session import ATTRIBUTE, decode_session
from adv_py.core.source_native_animation import ATTRIBUTE as NATIVE_ATTRIBUTE, decode_native_animation
from test_source_native_animation import NativeCommands


class AnimationPortMoveTests(unittest.TestCase):
    extra = '|controls|FKExtra'
    def fixture(self, detached=False):
        c = NativeCommands()
        c.nodes[self.extra] = ('extra-id', 'transform', '|controls')
        host = SimpleNamespace(_cmds=c, _require_transaction=lambda: None,
            scene_address=lambda node: c.group if node == 'MoCapConstraints' else node)
        saved = remember(host, ((c.control, None, c.constraint),))
        if detached:
            c.native_disconnect(); observe_disconnect(host, saved)
        return host, c

    def ports(self, c):
        return tuple((c.control + '.rotate' + axis, self.extra + '.rotate' + axis) for axis in 'XYZ')

    def perform(self, c, boundary):
        for move in boundary.moves:
            c.inputs[move.destination] = c.inputs.pop(move.source)

    def test_active_session_preserves_constraint_identity_and_moves_actual_receivers(self):
        host, c = self.fixture()
        boundary = capture(host, self.ports(c))
        self.perform(c, boundary)
        graph = deepcopy(c.nodes), deepcopy(c.inputs)
        finish(host, boundary)
        self.assertEqual((c.nodes, c.inputs), graph)
        saved = decode_session(c.attrs[c.group + '.' + ATTRIBUTE])
        self.assertEqual(saved['receivers'][0]['uuid'], 'extra-id')
        self.assertEqual(len(audit(host)), 3)
        self.assertFalse(saved['baked'])

    def test_detached_blend_retains_inputs_and_exact_output_uuid_after_move(self):
        host, c = self.fixture(detached=True)
        before_inputs = deepcopy(c.inputs)
        boundary = capture(host, self.ports(c))
        self.perform(c, boundary); finish(host, boundary)
        saved = decode_native_animation(c.attrs[c.blend + '.' + NATIVE_ATTRIBUTE])
        self.assertEqual(saved['receivers'][0]['path'], self.extra)
        self.assertEqual(len(capture_native(host)), 1)
        for axis in 'XYZ':
            self.assertEqual(c.inputs[c.blend + '.inRotate' + axis + '1'],
                             before_inputs[c.blend + '.inRotate' + axis + '1'])

    def test_partial_axis_transfer_splits_receiver_rows_and_keeps_untouched_axes(self):
        host, c = self.fixture(detached=True)
        boundary = capture(host, self.ports(c)[:1])
        self.perform(c, boundary); finish(host, boundary)
        saved = decode_native_animation(c.attrs[c.blend + '.' + NATIVE_ATTRIBUTE])
        ports = {row['uuid']: [edge['destination'] for edge in row['inputs']] for row in saved['receivers']}
        self.assertEqual(ports, {'extra-id': ['rotateX'], 'control-id': ['rotateY', 'rotateZ']})

    def test_replacement_receiver_driver_or_retained_connection_is_rejected(self):
        for change in ('receiver', 'driver', 'old_connection', 'blend_input'):
            with self.subTest(change=change):
                host, c = self.fixture(detached=True)
                boundary = capture(host, self.ports(c))
                self.perform(c, boundary)
                if change == 'receiver': c.nodes[self.extra] = ('other-extra-id', 'transform', '|controls')
                elif change == 'driver': c.inputs[self.extra + '.rotateX'] = 'animX.output'
                elif change == 'old_connection': c.inputs[c.control + '.rotateX'] = c.blend + '.outRotateX'
                else: c.inputs[c.blend + '.inRotateX1'] = 'animY.output'
                with self.assertRaises(CharacterRegistryError): finish(host, boundary)

    def test_occupied_extra_or_wrong_axis_is_rejected_before_business_move(self):
        host, c = self.fixture()
        c.inputs[self.extra + '.rotateX'] = 'animX.output'
        with self.assertRaisesRegex(CharacterRegistryError, '占用'): capture(host, self.ports(c))
        with self.assertRaisesRegex(CharacterRegistryError, '轴向'):
            capture(host, ((c.control + '.rotateX', self.extra + '.rotateY'),))

    def test_unlocked_document_is_not_legitimized_by_an_exact_driver_move(self):
        for detached in (False,True):
            with self.subTest(detached=detached):
                host,c=self.fixture(detached=detached)
                boundary=capture(host,self.ports(c))
                self.perform(c,boundary)
                plug=(c.blend+'.'+NATIVE_ATTRIBUTE if detached else c.group+'.'+ATTRIBUTE)
                c.locks[plug]=False
                before=deepcopy(c.attrs)
                with self.assertRaisesRegex(CharacterRegistryError,'锁'):finish(host,boundary)
                self.assertEqual(c.attrs,before)


if __name__ == '__main__': unittest.main()
