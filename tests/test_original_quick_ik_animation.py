"""Metadata follows native QuickIK key/static edits without editing business DG."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_original_quick_ik_animation import capture,finish
from adv_py.adapters.maya_original_quick_ik_state import remember,audit
from adv_py.adapters.maya_original_quick_ik_rebuild import capture as capture_rebuild,expected,install,verify,sample_frames
from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_quick_ik import ATTRIBUTE,decode_quick_ik,rebase_quick_ik
from test_source_native_animation import NativeCommands


class Commands(NativeCommands):
    def ls(self,address=None,**flags):
        if address is None and flags.get('type')=='animCurve':
            return [name for name,row in self.nodes.items() if row[1].startswith('animCurve')]
        return super().ls(address,**flags)


class QuickAnimationTests(unittest.TestCase):
    def fixture(self,*,weight_curve=False):
        c=Commands()
        # This is a QuickIK scene, not an active NameMatcher/MoCap session.
        c.nodes.pop(c.group)
        c.attrs={plug:value for plug,value in c.attrs.items() if not plug.startswith(c.group+'.')}
        c.locks={plug:value for plug,value in c.locks.items() if not plug.startswith(c.group+'.')}
        c.inputs.pop(c.constraint+'.nodeState')
        c.nodes['|QuickIK']=('quick-root','transform',None)
        group='|QuickIK|QuickGroup'
        joint=group+'|QuickJoint'
        c.nodes[group]=('quick-group','transform','|QuickIK')
        c.nodes[joint]=('quick-joint','joint',group)
        c.inputs[c.constraint+'.target[0].targetParentMatrix']=joint+'.parentMatrix[0]'
        if weight_curve:
            c.nodes['weightCurve']=('weight-curve','animCurveTU',None)
            c.inputs[c.blend+'.weight']='weightCurve.output'
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,scene_address=lambda node:node)
        remember(host,group,(c.control,),(c.constraint,))
        ports=frozenset(('control-id','rotate'+axis) for axis in 'XYZ')
        return host,c,group,joint,ports

    def test_native_key_replaces_only_covered_axis_and_refreshes_cached_values(self):
        host,c,group,_,ports=self.fixture()
        boundary=capture(host)
        c.nodes['newX']=('new-x','animCurveTA',None)
        c.inputs[c.blend+'.inRotateX1']='newX.output'
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        finish(host,boundary,ports)
        self.assertEqual((c.nodes,c.inputs),before)
        value=decode_quick_ik(c.attrs[group+'.'+ATTRIBUTE])
        self.assertTrue(any(edge['source_uuid']=='new-x' for node in value['nodes'] for edge in node['inputs']))
        self.assertEqual(len(audit(host)),3)

    def shared_axis_fixture(self, *, cached=False):
        host,c,group,joint,ports=self.fixture()
        other='|OtherFK'
        c.nodes[other]=('other-control','transform',None)
        c.inputs[other+'.rotateZ']=c.blend+'.outRotateZ'
        if cached:
            # Maya cannot set a driven plug directly. Model editable cached
            # Z inputs, still shared through the real pairBlend output.
            for index in ('1','2'):c.inputs.pop(c.blend+'.inRotateZ'+index)
        remember(host,group,(c.control,other),(c.constraint,))
        return host,c,group,ports

    def test_partial_native_edit_cannot_change_axis_shared_with_another_receiver(self):
        host,c,_,ports=self.shared_axis_fixture()
        boundary=capture(host)
        c.nodes['newZ']=('new-z','animCurveTA',None)
        c.inputs[c.blend+'.inRotateZ1']='newZ.output'
        with self.assertRaisesRegex(CharacterRegistryError,'未覆盖'):
            finish(host,boundary,ports)

    def test_partial_native_edit_keeps_shared_weight_and_uncovered_cache(self):
        for attr in ('weight','inRotateZ1','inRotateZ2'):
            with self.subTest(attribute=attr):
                host,c,_,ports=self.shared_axis_fixture(cached=True)
                boundary=capture(host)
                c.attrs[c.blend+'.'+attr]=.7
                with self.assertRaisesRegex(CharacterRegistryError,'未覆盖'):
                    finish(host,boundary,ports)

    def test_partial_native_edit_accepts_new_key_on_exclusively_covered_axis(self):
        host,c,group,ports=self.shared_axis_fixture()
        boundary=capture(host)
        c.nodes['newX']=('new-x','animCurveTA',None)
        c.inputs[c.blend+'.inRotateX1']='newX.output'
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        finish(host,boundary,ports)
        self.assertEqual((c.nodes,c.inputs),before)
        document=decode_quick_ik(c.attrs[group+'.'+ATTRIBUTE])
        self.assertEqual(document['receivers'][1]['inputs'][0]['source'],c.blend+'.outRotateZ')

    def test_other_existing_curve_or_uncovered_cache_cannot_be_adopted(self):
        for mode in ('other-axis','cache'):
            with self.subTest(mode=mode):
                host,c,_,_,ports=self.fixture()
                boundary=capture(host)
                if mode=='other-axis':c.inputs[c.blend+'.inRotateX1']='animY.output'
                else:c.attrs[c.blend+'.rotInterpolation']=1.
                with self.assertRaises(CharacterRegistryError):finish(host,boundary,ports)

    def test_static_collapse_retains_exact_original_same_axis_constraint(self):
        host,c,_,_,ports=self.fixture()
        boundary=capture(host)
        c.nodes.pop(c.blend)
        c.inputs={destination:source for destination,source in c.inputs.items()
            if destination.split('.',1)[0]!=c.blend and source.split('.',1)[0]!=c.blend}
        for axis in 'XYZ':c.inputs[c.control+'.rotate'+axis]=c.constraint+'.constraintRotate'+axis
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        finish(host,boundary,ports,static=True)
        self.assertEqual((c.nodes,c.inputs),before)
        self.assertEqual(len(audit(host)),3)

    def test_static_cleanup_freezes_new_quick_control_keys_added_after_creation(self):
        host,c,_,joint,ports=self.fixture()
        c.nodes['quickX']=('quick-x','animCurveTL',None)
        c.inputs[joint+'.translateX']='quickX.output'
        boundary=capture(host)
        c.nodes.pop('quickX')
        c.inputs.pop(joint+'.translateX')
        finish(host,boundary,ports,static=True)
        self.assertEqual(len(audit(host)),3)

    def test_static_weight_curve_deletion_preserves_native_cache_and_graph(self):
        host,c,_,_,ports=self.fixture(weight_curve=True)
        boundary=capture(host)
        c.nodes.pop('weightCurve')
        c.inputs.pop(c.blend+'.weight')
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        finish(host,boundary,ports,static=True)
        self.assertEqual((c.nodes,c.inputs),before)
        self.assertEqual(len(audit(host)),3)

    def test_metadata_change_or_unlock_cannot_be_hidden_by_animation_refresh(self):
        for kind in ('unlock','replace'):
            with self.subTest(kind=kind):
                host,c,group,_,ports=self.fixture()
                boundary=capture(host)
                plug=group+'.'+ATTRIBUTE
                if kind=='unlock':c.locks[plug]=False
                else:
                    doc=decode_quick_ik(c.attrs[plug])
                    doc['receivers'][0]['inputs'].pop()
                    c.attrs[plug]=canonical(doc)
                with self.assertRaises(CharacterRegistryError):finish(host,boundary,ports)

    def test_same_axis_native_curve_can_move_between_pairblend_inputs(self):
        host,c,_,_,ports=self.fixture()
        # Keep the original Quick constraint on compound rotation, so this
        # axis's opposite input is free for Maya's native curve handoff.
        source=c.inputs[c.blend+'.inRotateX2']
        for axis in 'XYZ':c.inputs.pop(c.blend+'.inRotate'+axis+'2')
        c.inputs[c.blend+'.inRotate2']=source.removesuffix('X')
        value=decode_quick_ik(c.attrs['|QuickIK|QuickGroup.'+ATTRIBUTE])
        row=next(row for row in value['nodes'] if row['uuid']=='blend-id')
        edge=next(edge for edge in row['inputs'] if edge['destination']=='inRotateX2')
        row['inputs']=[edge for edge in row['inputs'] if edge['destination'] not in
                       ('inRotateX2','inRotateY2','inRotateZ2')]
        row['inputs'].append({**edge,'destination':'inRotate2','source':source.removesuffix('X')})
        row['inputs'].sort(key=lambda edge:edge['destination'])
        from adv_py.adapters.maya_source_native_animation import _settings
        value['blend_settings'][0]['settings']=_settings(c,c.blend)
        c.attrs['|QuickIK|QuickGroup.'+ATTRIBUTE]=canonical(value)
        boundary=capture(host)
        c.inputs[c.blend+'.inRotateX2']=c.inputs.pop(c.blend+'.inRotateX1')
        finish(host,boundary,ports)
        self.assertEqual(len(audit(host)),3)

    def test_rebuild_samples_quick_root_and_external_target_parent_keys(self):
        host,c,_,_,_=self.fixture()
        documents=capture_rebuild(host)
        c.nodes['|QuickIK']=('quick-root','transform','|external')
        c.keyframe=lambda node,**flags: {'|QuickIK':(7.,),c.control:(3.,),'|external':(9.,)}.get(node,())
        c.playbackOptions=lambda **flags:1. if flags.get('minTime') else 24.
        self.assertEqual(sample_frames(host,documents),(1.,3.,7.,9.,24.))

    def test_original_animation_to_extra_moves_only_quick_receiver_metadata(self):
        from adv_py.adapters.maya_animation_port_move import capture as capture_move,finish as finish_move
        host,c,group,_,_=self.fixture()
        extra='|controls|FKExtra'
        c.nodes[extra]=('extra-id','transform','|controls')
        boundary=capture_move(host,((c.control+'.rotateX',extra+'.rotateX'),))
        c.inputs[extra+'.rotateX']=c.inputs.pop(c.control+'.rotateX')
        graph=deepcopy(c.nodes),deepcopy(c.inputs)
        finish_move(host,boundary)
        self.assertEqual((c.nodes,c.inputs),graph)
        value=decode_quick_ik(c.attrs[group+'.'+ATTRIBUTE])
        self.assertEqual({row['uuid']:tuple(edge['destination'] for edge in row['inputs'])
            for row in value['receivers']},{'extra-id':('rotateX',),'control-id':('rotateY','rotateZ')})
        self.assertEqual(len(audit(host)),3)

    def test_rebuild_reuses_quick_graph_and_rebinds_receiver_uuid_only(self):
        host,c,group,_,_=self.fixture()
        documents=capture_rebuild(host)
        parent='|stage:Controls'
        control=parent+'|stage:FK'
        c.nodes[parent]=('stage-parent','transform',None)
        c.nodes[control]=('stage-control','transform',parent)
        for axis in 'XYZ':
            c.inputs[control+'.rotate'+axis]=c.inputs.pop(c.control+'.rotate'+axis)
        # The ordinary extension handoff reparents the retained constraint and
        # moves its original controller parent-inverse-matrix input as well.
        old_constraint=c.constraint
        c.constraint=control+'|FK_orientConstraint1'
        identity,kind,_=c.nodes.pop(old_constraint)
        c.nodes[c.constraint]=(identity,kind,control)
        c.inputs={destination.replace(old_constraint,c.constraint,1):
            source.replace(old_constraint,c.constraint,1).replace(c.control+'.',control+'.',1)
            for destination,source in c.inputs.items()}
        staged=SimpleNamespace(original=SimpleNamespace(quick_ik=documents),
            ownership=SimpleNamespace(nodes=(('control','control-id','stage-control','transform'),),removed_nodes=()))
        before=deepcopy(c.nodes),deepcopy(c.inputs)
        install(host,staged)
        self.assertEqual((c.nodes,c.inputs),before)
        wanted=expected(host,staged)[0]
        self.assertEqual(wanted['receivers'][0]['uuid'],'stage-control')
        self.assertEqual(decode_quick_ik(c.attrs[group+'.'+ATTRIBUTE]),wanted)
        verify(host,staged)

    def test_closed_handoff_preserves_original_blend_settings(self):
        host,c,group,_,_=self.fixture()
        value=decode_quick_ik(c.attrs[group+'.'+ATTRIBUTE])
        identities={node['uuid']:(node['path'],node['uuid']) for node in value['nodes']}
        identities.update({row['uuid']:(row['path'],row['uuid']) for row in value['receivers']})
        for node in value['nodes']:
            if node['parent'] is not None:
                identities[node['parent']]=(c.ls(node['parent'],long=True)[0],node['parent'])
            for edge in node['inputs']:
                identities[edge['source_uuid']]=(edge['source'].split('.',1)[0],edge['source_uuid'])
        rebased=rebase_quick_ik(value,identities)
        self.assertEqual(decode_quick_ik(canonical(rebased))['blend_settings'],value['blend_settings'])
