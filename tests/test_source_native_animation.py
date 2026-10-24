"""Native Disconnect survivors stay UUID-proven, with untouched animation DG."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_native_animation import (
    ATTRIBUTE,decode_native_animation,encode_native_animation,rebase_native_animation)
from adv_py.adapters.maya_source_name_matcher_session import remember
from adv_py.adapters.maya_source_native_animation import (
    observe_disconnect,capture,audit,reconnect_records)
from adv_py.adapters.maya_source_mocap_rebuild import install,verify
from adv_py.core.name_matcher_mocap import NameMatcherMocapPlan,NameMatcherMocapLink
from test_source_name_matcher_session import SessionCommands


class NativeCommands(SessionCommands):
    identity=CharacterIdentity('')
    blend='pairBlend1'
    def __init__(self):
        super().__init__()
        self.nodes[self.blend]=('blend-id','pairBlend',None)
        for axis in 'XYZ':
            curve='anim'+axis
            self.nodes[curve]=(curve+'-id','animCurveTA',None)
            self.inputs[self.blend+'.inRotate'+axis+'1']=curve+'.output'
            self.inputs[self.blend+'.inRotate'+axis+'2']=self.constraint+'.constraintRotate'+axis
            self.inputs[self.control+'.rotate'+axis]=self.blend+'.outRotate'+axis
        names=tuple('in'+kind+axis+index for kind in ('Translate','Rotate')
            for index in ('1','2') for axis in 'XYZ')
        names+=('weight','rotInterpolation','rotateMode','translateXMode','translateYMode','translateZMode')
        self.attrs.update({self.blend+'.'+name:0. for name in names})
    def objExists(self,address):
        return address in self.attrs or address in self.inputs or bool(self.name(address))
    def ls(self,address,**flags):
        if address.startswith('*.'):
            suffix=address[1:]
            return [plug.rsplit('.',1)[0] for plug in self.attrs if plug.endswith(suffix)]
        return super().ls(address,**flags)
    def deleteAttr(self,plug):
        self.attrs.pop(plug);self.locks.pop(plug,None)
    def native_disconnect(self):
        removed=(self.constraint,self.group)
        for node in removed:self.nodes.pop(node)
        self.inputs={destination:source for destination,source in self.inputs.items()
            if destination.split('.',1)[0] not in removed and source.split('.',1)[0] not in removed}
        self.attrs={plug:value for plug,value in self.attrs.items() if plug.split('.',1)[0] not in removed}


class SourceNativeAnimationTests(unittest.TestCase):
    def fixture(self):
        c=NativeCommands()
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            scene_address=lambda name:c.group if name=='MoCapConstraints' else name)
        saved=remember(host,((c.control,None,c.constraint),))
        c.native_disconnect()
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        observe_disconnect(host,saved)
        self.assertEqual((c.nodes,c.inputs),before)
        return host,c,decode_native_animation(c.attrs[c.blend+'.'+ATTRIBUTE])

    def test_disconnect_only_records_actual_native_survivor(self):
        host,c,value=self.fixture()
        self.assertEqual(value['origin'],'group-id')
        self.assertEqual(value['node']['uuid'],'blend-id')
        self.assertEqual(len(audit(host)),3)
        self.assertEqual(capture(host),(encode_native_animation(value),))
        self.assertEqual(c.inputs[c.blend+'.inRotateX1'],'animX.output')

    def test_animation_rewire_or_cached_native_input_edit_is_rejected(self):
        host,c,_=self.fixture()
        c.inputs[c.blend+'.inRotateX1']='animY.output'
        with self.assertRaisesRegex(CharacterRegistryError,'缓存值变化'):audit(host)
        host,c,_=self.fixture()
        c.attrs[c.blend+'.inRotateX2']=7.
        with self.assertRaisesRegex(CharacterRegistryError,'缓存值变化'):audit(host)

    def test_replacement_and_undeclared_output_are_rejected(self):
        host,c,_=self.fixture()
        c.nodes[c.blend]=('replacement-id','pairBlend',None)
        with self.assertRaises(CharacterRegistryError):audit(host)
        host,c,_=self.fixture()
        c.inputs[c.target+'.rotateX']=c.blend+'.outRotateX'
        with self.assertRaisesRegex(CharacterRegistryError,'未登记'):audit(host)

    def test_reconnect_retires_metadata_without_deleting_animation_objects(self):
        host,c,_=self.fixture()
        plan=NameMatcherMocapPlan((NameMatcherMocapLink(c.target,c.control,False,True),),(),
            None,None,False,())
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        self.assertEqual(reconnect_records(host,plan),(c.blend+'.'+ATTRIBUTE,))
        reconnect_records(host,plan,remove=True)
        self.assertEqual((c.nodes,c.inputs),before)
        self.assertNotIn(c.blend+'.'+ATTRIBUTE,c.attrs)

    def test_native_animation_rebuild_retains_blend_and_original_animation(self):
        host,c,value=self.fixture()
        old_document=encode_native_animation(value)
        parent='|stage:controls';control=parent+'|stage:FK'
        c.nodes[parent]=('new-parent','transform',None)
        c.nodes[control]=('new-control','transform',parent)
        for axis in 'XYZ':
            source=c.inputs.pop(c.control+'.rotate'+axis)
            c.inputs[control+'.rotate'+axis]=source
        staged=SimpleNamespace(original=SimpleNamespace(mocap_session=None,native_animation=(old_document,)),
            ownership=SimpleNamespace(nodes=(('control','control-id','new-control','transform'),),removed_nodes=()))
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        install(host,staged)
        self.assertEqual((c.nodes,c.inputs),before)
        wanted=decode_native_animation(c.attrs[c.blend+'.'+ATTRIBUTE])
        self.assertEqual(wanted['receivers'][0]['uuid'],'new-control')
        self.assertEqual(wanted['receivers'][0]['path'],control)
        verify(host,staged)

    def test_closed_record_cannot_reassign_blend_or_accept_wrong_output_axis(self):
        _,c,value=self.fixture()
        with self.assertRaisesRegex(CharacterRegistryError,'不能替换'):
            rebase_native_animation(value,{'blend-id':(c.blend,'replacement')})
        wrong=deepcopy(value)
        wrong['receivers'][0]['inputs'][0]['source']=c.blend+'.outRotateY'
        with self.assertRaisesRegex(CharacterRegistryError,'输出轴向'):
            decode_native_animation(canonical(wrong))


if __name__=='__main__':unittest.main()
