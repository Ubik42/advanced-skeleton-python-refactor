"""Only the actual owned MoCap graph may occupy registered control inputs."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_name_matcher_session import ATTRIBUTE,decode_session,encode_session
from adv_py.adapters.maya_source_name_matcher_session import remember,audit,allowed_input,remember_native_bake


class SessionCommands:
    group = '|MoCapConstraints'
    control = '|controls|FK'
    target = '|external|hand'
    constraint = '|controls|FK|FK_orientConstraint1'
    def __init__(self):
        self.nodes = {
            self.group:('group-id','transform',None),
            self.control:('control-id','transform','|controls'),
            '|controls':('controls-id','transform',None),
            self.target:('target-id','joint','|external'),
            '|external':('external-id','transform',None),
            self.constraint:('constraint-id','orientConstraint',self.control)}
        self.inputs = {
            self.constraint+'.constraintParentInverseMatrix':self.control+'.parentInverseMatrix[0]',
            self.constraint+'.target[0].targetParentMatrix':self.target+'.worldMatrix[0]',
            self.constraint+'.nodeState':self.group+'.disableConstraints',
            **{self.control+'.rotate'+axis:self.constraint+'.constraintRotate'+axis for axis in 'XYZ'}}
        self.attrs = {self.group+'.advPyNameMatcher':True,self.group+'.disableConstraints':False}
        self.locks = {self.group+'.advPyNameMatcher':True}
    def name(self,address):
        if address in self.nodes:return address
        values = [path for path,(identity,_,_) in self.nodes.items()
                  if address in (identity,path.rsplit('|',1)[-1])]
        return values[0] if len(values)==1 else None
    def ls(self,address,**flags):
        name = self.name(address)
        if not name:return []
        return [self.nodes[name][0] if flags.get('uuid') else name]
    def objExists(self,address):
        if address in self.attrs:return True
        node,separator,attribute = address.partition('.')
        return bool(self.name(node)) and (not separator or attribute!=ATTRIBUTE)
    def nodeType(self,address):return self.nodes[self.name(address)][1]
    def listRelatives(self,address,**flags):
        node = self.name(address)
        if flags.get('parent'):
            parent = self.nodes[node][2]
            return [parent] if parent else []
        return [path for path in self.nodes if path.startswith(node+'|')]
    def listConnections(self,address,**flags):
        if flags.get('source'):
            matches = [(dest,source) for dest,source in self.inputs.items()
                       if dest.split('.',1)[0]==address]
            return [value for edge in matches for value in edge]
        return [dest for dest,source in self.inputs.items() if source==address]
    def connectionInfo(self,address,**flags):return self.inputs.get(address,'')
    def addAttr(self,node,**flags):self.attrs[node+'.'+flags['longName']] = ''
    def getAttr(self,address,**flags):
        return self.locks.get(address,False) if flags.get('lock') else self.attrs[address]
    def setAttr(self,address,*values,**flags):
        if 'lock' in flags:self.locks[address] = flags['lock']
        if values:self.attrs[address] = values[0]


class SourceSessionTests(unittest.TestCase):
    def setup_session(self):
        commands = SessionCommands()
        host = SimpleNamespace(_cmds=commands,_require_transaction=lambda:None,
                               scene_address=lambda name:'|MoCapConstraints' if name=='MoCapConstraints' else name)
        value = remember(host,((commands.control,None,commands.constraint),))
        return host,commands,value

    def test_record_roundtrip_and_live_receivers_are_exact_uuid_edges(self):
        host,commands,value = self.setup_session()
        self.assertEqual(decode_session(encode_session(value)),value)
        edges = audit(host)
        self.assertEqual(len(edges),3)
        self.assertTrue(allowed_input(host,edges,'control-id','rotateX',commands.constraint+'.constraintRotateX'))
        self.assertFalse(allowed_input(host,edges,'control-id','rotateY',commands.constraint+'.constraintRotateX'))
        self.assertTrue(commands.locks[commands.group+'.'+ATTRIBUTE])

    def test_native_bake_may_detach_outputs_without_changing_target_topology(self):
        host,commands,_ = self.setup_session()
        for axis in 'XYZ':commands.inputs.pop(commands.control+'.rotate'+axis)
        self.assertFalse(audit(host))
        commands.nodes['|animCurve'] = 'anim-curve-id','animCurveTA',None
        commands.inputs[commands.control+'.rotateX'] = 'animCurve.output'
        self.assertFalse(audit(host))

    def test_same_name_constraint_or_external_target_replacement_is_rejected(self):
        for node in ('constraint','target','control'):
            with self.subTest(node=node):
                host,commands,_ = self.setup_session()
                path = getattr(commands,node)
                _,kind,parent = commands.nodes[path]
                commands.nodes[path] = 'replacement-id',kind,parent
                with self.assertRaises(CharacterRegistryError):audit(host)

    def test_target_rewire_and_disable_switch_passenger_are_rejected(self):
        host,commands,_ = self.setup_session()
        commands.inputs[commands.constraint+'.target[0].targetParentMatrix'] = commands.control+'.worldMatrix[0]'
        with self.assertRaisesRegex(CharacterRegistryError,'接线变化'):audit(host)
        host,commands,_ = self.setup_session()
        commands.inputs[commands.control+'.visibility'] = commands.group+'.disableConstraints'
        with self.assertRaisesRegex(CharacterRegistryError,'其他属性'):audit(host)

    def test_unknown_descendants_or_outputs_are_not_owned_by_marker_alone(self):
        host,commands,_ = self.setup_session()
        commands.nodes[commands.group+'|unowned'] = 'unowned-id','transform',commands.group
        with self.assertRaisesRegex(CharacterRegistryError,'未登记节点'):audit(host)
        host,commands,_ = self.setup_session()
        commands.inputs[commands.target+'.rotateX'] = commands.constraint+'.constraintRotateX'
        with self.assertRaisesRegex(CharacterRegistryError,'未登记控制器'):audit(host)

    def test_unlocked_document_cannot_authorize_external_drivers(self):
        host,commands,_ = self.setup_session()
        commands.locks[commands.group+'.'+ATTRIBUTE] = False
        with self.assertRaisesRegex(CharacterRegistryError,'锁定'):audit(host)

    def test_closed_schema_rejects_unknown_fields_duplicate_ids_and_wrong_axis(self):
        _,_,value = self.setup_session()
        invalid = []
        changed = deepcopy(value);changed['extra'] = True;invalid.append(changed)
        changed = deepcopy(value);changed['nodes'].append(deepcopy(changed['nodes'][0]));invalid.append(changed)
        changed = deepcopy(value);changed['receivers'][0]['inputs'][0]['destination'] = 'scaleX';invalid.append(changed)
        changed = deepcopy(value);changed['receivers'][0]['inputs'][0]['source_uuid'] = 'other';invalid.append(changed)
        changed = deepcopy(value);changed['receivers'][0]['inputs'][0]['source'] = SessionCommands.constraint+'.constraintRotateY';invalid.append(changed)
        for changed in invalid:
            with self.assertRaises(CharacterRegistryError):decode_session(canonical(changed))


    def setup_animated_session(self):
        commands=SessionCommands()
        blend='pairBlend1'
        commands.nodes[blend]=('blend-id','pairBlend',None)
        for axis in 'XYZ':
            curve='anim'+axis
            commands.nodes[curve]=(curve+'-id','animCurveTA',None)
            commands.inputs[blend+'.inRotate'+axis+'1']=curve+'.output'
            commands.inputs[blend+'.inRotate'+axis+'2']=commands.constraint+'.constraintRotate'+axis
            commands.inputs[commands.control+'.rotate'+axis]=blend+'.outRotate'+axis
        host=SimpleNamespace(_cmds=commands,_require_transaction=lambda:None,
            scene_address=lambda name:commands.group if name=='MoCapConstraints' else name)
        value=remember(host,((commands.control,None,commands.constraint),))
        return host,commands,value,blend

    def test_native_pair_blend_preserves_animation_and_proves_constraint_route(self):
        host,c,value,blend=self.setup_animated_session()
        self.assertEqual(value['version'],2)
        self.assertEqual(value['output_constraints'],['constraint-id'])
        self.assertEqual(len(audit(host)),3)
        self.assertTrue(allowed_input(host,audit(host),'control-id','rotateX',blend+'.outRotateX'))
        self.assertEqual(c.inputs[blend+'.inRotateX1'],'animX.output')
        wrong=deepcopy(value)
        row=next(node for node in wrong['nodes'] if node['kind']=='pairBlend')
        row['inputs']=[edge for edge in row['inputs'] if edge['destination']!='inRotateX2']
        with self.assertRaisesRegex(CharacterRegistryError,'pairBlend'):
            decode_session(canonical(wrong))

    def test_pair_blend_replacement_or_internal_animation_rewire_is_rejected(self):
        host,c,_,blend=self.setup_animated_session()
        c.nodes[blend]=('replacement','pairBlend',None)
        with self.assertRaises(CharacterRegistryError):audit(host)
        host,c,_,blend=self.setup_animated_session()
        c.inputs[blend+'.inRotateX1']='animY.output'
        with self.assertRaisesRegex(CharacterRegistryError,'接线变化'):audit(host)

    def test_native_bake_records_actual_blend_deletion_and_keeps_constraints(self):
        host,c,_,blend=self.setup_animated_session()
        c.nodes.pop(blend)
        c.inputs={target:source for target,source in c.inputs.items() if not target.startswith(blend+'.')}
        for axis in 'XYZ':c.inputs[c.control+'.rotate'+axis]='anim'+axis+'.output'
        remember_native_bake(host)
        saved=decode_session(c.attrs[c.group+'.'+ATTRIBUTE])
        self.assertTrue(saved['baked']);self.assertEqual(saved['removed_blends'],['blend-id'])
        self.assertFalse(audit(host))
        c.nodes[blend]=('replacement','pairBlend',None)
        with self.assertRaisesRegex(CharacterRegistryError,'重新出现'):audit(host)

    def test_bake_cannot_refresh_foreign_nodes_or_arbitrary_new_blend_inputs(self):
        host,c,_,blend=self.setup_animated_session()
        c.inputs[blend+'.weight']=c.target+'.visibility'
        with self.assertRaisesRegex(CharacterRegistryError,'非动画'):remember_native_bake(host)
        host,c,_,blend=self.setup_animated_session()
        c.inputs[c.constraint+'.target[0].targetParentMatrix']=c.control+'.worldMatrix[0]'
        with self.assertRaisesRegex(CharacterRegistryError,'原约束'):remember_native_bake(host)

    def test_version_one_direct_constraint_documents_remain_readable(self):
        _,_,value=self.setup_session()
        for field in ('output_constraints','baked','removed_blends'):value.pop(field)
        value['version']=1
        for receiver in value['receivers']:
            for edge in receiver['inputs']:edge.pop('constraint_uuid')
        self.assertEqual(decode_session(encode_session(value)),value)


if __name__=='__main__':unittest.main()
