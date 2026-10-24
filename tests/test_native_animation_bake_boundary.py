"""Native bake adoption is limited to selected ports and new time curves."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from adv_py.adapters.maya_native_animation_bake_boundary import capture, finish
from adv_py.adapters.maya_source_name_matcher_session import remember, audit
from adv_py.adapters.maya_source_native_animation import observe_disconnect, capture as capture_native
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_native_animation import ATTRIBUTE as NATIVE_ATTRIBUTE, decode_native_animation
from test_source_native_animation import NativeCommands


class BakeCommands(NativeCommands):
    def ls(self, address=None, **flags):
        if address is None and flags.get('type') == 'animCurve':
            return [path for path, (_, kind, _) in self.nodes.items() if kind.startswith('animCurve')]
        return super().ls(address, **flags)


class NativeBakeBoundaryTests(unittest.TestCase):
    def fixture(self, detached=True):
        c = BakeCommands()
        host = SimpleNamespace(_cmds=c, _require_transaction=lambda: None,
            scene_address=lambda node:c.group if node == 'MoCapConstraints' else node)
        saved = remember(host, ((c.control, None, c.constraint),))
        if detached:
            c.native_disconnect(); observe_disconnect(host, saved)
        return host, c

    def new_curve(self, c, axis):
        name = 'baked' + axis
        c.nodes[name] = (name + '-id', 'animCurveTA', None)
        c.inputs[c.control + '.rotate' + axis] = name + '.output'

    def test_native_bake_retires_metadata_when_all_outputs_become_new_time_curves(self):
        host, c = self.fixture()
        boundary = capture(host, (c.control,))
        for axis in 'XYZ': self.new_curve(c, axis)
        graph = deepcopy(c.nodes), deepcopy(c.inputs)
        finish(host, boundary)
        self.assertEqual((c.nodes,c.inputs), graph)
        self.assertNotIn(c.blend + '.' + NATIVE_ATTRIBUTE, c.attrs)
        self.assertEqual(capture_native(host), ())

    def test_partial_native_bake_retains_other_actual_receiver_edges(self):
        host, c = self.fixture()
        boundary = capture(host, (c.control,))
        self.new_curve(c, 'X')
        finish(host, boundary)
        saved = decode_native_animation(c.attrs[c.blend + '.' + NATIVE_ATTRIBUTE])
        self.assertEqual([edge['destination'] for edge in saved['receivers'][0]['inputs']], ['rotateY','rotateZ'])
        self.assertEqual(len(capture_native(host)), 1)

    def test_other_preexisting_curve_or_unselected_receiver_cannot_be_adopted(self):
        for mode in ('wrong_axis','unselected','sdk'):
            with self.subTest(mode=mode):
                host, c = self.fixture()
                if mode == 'sdk': c.nodes['sdk'] = ('sdk-id','animCurveUU',None)
                boundary = capture(host, () if mode == 'unselected' else (c.control,))
                if mode == 'wrong_axis': c.inputs[c.control + '.rotateX'] = 'animY.output'
                elif mode == 'sdk': c.inputs[c.control + '.rotateX'] = 'sdk.output'
                else: self.new_curve(c, 'X')
                with self.assertRaises(CharacterRegistryError): finish(host, boundary)

    def test_same_axis_original_curve_can_survive_a_native_blend_collapse(self):
        host, c = self.fixture()
        boundary = capture(host, (c.control,))
        for axis in 'XYZ': c.inputs[c.control + '.rotate' + axis] = 'anim' + axis + '.output'
        c.nodes.pop(c.blend)
        c.inputs = {plug: source for plug, source in c.inputs.items() if plug.split('.',1)[0] != c.blend}
        finish(host, boundary)

    def test_active_already_baked_receiver_snapshot_is_accepted_if_unchanged(self):
        host, c = self.fixture(detached=False)
        self.new_curve(c, 'X')
        # The original session intentionally keeps the historical output edge.
        from adv_py.adapters.maya_source_name_matcher_session import remember_native_bake
        remember_native_bake(host)
        boundary = capture(host, ())
        finish(host, boundary)
        self.assertEqual(len(audit(host)), 2)

    def test_existing_other_curve_cannot_be_added_to_retained_blend_input(self):
        host, c = self.fixture()
        boundary = capture(host, (c.control,))
        c.inputs[c.blend + '.inRotateX1'] = 'animY.output'
        with self.assertRaisesRegex(CharacterRegistryError,'其他原有'): finish(host, boundary)

    def test_unlocked_preexisting_document_cannot_be_revalidated_by_native_bake(self):
        from adv_py.core.source_name_matcher_session import ATTRIBUTE
        for detached in (False,True):
            with self.subTest(detached=detached):
                host,c=self.fixture(detached=detached)
                boundary=capture(host,(c.control,))
                plug=(c.blend+'.'+NATIVE_ATTRIBUTE if detached else c.group+'.'+ATTRIBUTE)
                c.locks[plug]=False
                before=deepcopy(c.attrs)
                with self.assertRaisesRegex(CharacterRegistryError,'锁'):finish(host,boundary)
                self.assertEqual(c.attrs,before)

    def split_receivers(self):
        host,c=self.fixture()
        plug=c.blend+'.'+NATIVE_ATTRIBUTE
        saved=decode_native_animation(c.attrs[plug])
        c.nodes['|controls|Other']=('other-control-id','transform','|controls')
        moved=saved['receivers'][0]['inputs'].pop()
        c.inputs.pop(c.control+'.'+moved['destination'])
        c.inputs['|controls|Other.'+moved['destination']]=moved['source']
        saved['receivers'].append(dict(path='|controls|Other',uuid='other-control-id',inputs=[moved]))
        from adv_py.core.source_native_animation import encode_native_animation
        c.attrs[plug]=encode_native_animation(saved)
        return host,c

    def test_shared_blend_cannot_adopt_curve_on_other_controller_axis(self):
        host,c=self.split_receivers()
        boundary=capture(host,(c.control,))
        c.nodes['bakedZ']=('bakedZ-id','animCurveTA',None)
        c.inputs[c.blend+'.inRotateZ1']='bakedZ.output'
        with self.assertRaisesRegex(CharacterRegistryError,'未覆盖'):finish(host,boundary)

    def test_shared_blend_preserves_other_axis_cached_values_and_shared_weight(self):
        for attribute in ('inRotateZ2','weight','rotInterpolation'):
            with self.subTest(attribute=attribute):
                host,c=self.split_receivers()
                boundary=capture(host,(c.control,))
                c.attrs[c.blend+'.'+attribute]=9.
                with self.assertRaisesRegex(CharacterRegistryError,'未覆盖'):finish(host,boundary)

    def test_shared_blend_can_bake_selected_axis_without_touching_other_receiver(self):
        host,c=self.split_receivers()
        boundary=capture(host,(c.control,))
        c.nodes['bakedX']=('bakedX-id','animCurveTA',None)
        c.inputs[c.blend+'.inRotateX1']='bakedX.output'
        c.attrs[c.blend+'.inRotateX2']=12.
        other=c.inputs['|controls|Other.rotateZ']
        finish(host,boundary)
        self.assertEqual(c.inputs['|controls|Other.rotateZ'],other)
        self.assertEqual(len(capture_native(host)),1)


if __name__ == '__main__': unittest.main()
