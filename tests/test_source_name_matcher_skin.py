"""Native skin transfer command order and scene-wide freeze semantics."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_source_name_matcher_skin import transfer_source_skin
from adv_py.adapters.maya_source_name_matcher_context import mapping_action
from adv_py.adapters.maya_source_name_matcher_controls import MayaSourceNameMatcherControlsMixin
from adv_py.application.name_matcher_constraints import TransferNameMatchedSkinInfluences
from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules
from adv_py.core.source_name_matcher import source_name_matcher_targets

MATRIX = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)


class SkinCommands:
    def __init__(self):
        self.nodes = {
            'group':('imported',None,'transform'),
            'root':('src:pelvis','group','joint'),
            'hand':('src:hand','root','joint'),
            'extra':('src:extra','hand','joint'),
            'tip':('src:tip','extra','joint'),
            'dud':('src:dud','hand','joint'),
            'rig':('DeformationSystem',None,'transform'),
            'body':('Root_M','rig','joint'),
            'wrist':('Wrist_R','body','joint'),
            'bodytip':('HeadEnd_M','body','joint')}
        self.advanced = ('|DeformationSystem|Root_M',
                         '|DeformationSystem|Root_M|Wrist_R',
                         '|DeformationSystem|Root_M|HeadEnd_M')
        self.events = []
        self.edges = {
            'skin.matrix[2]':'src:hand.worldMatrix[0]',
            'branchSkin.matrix[5]':'src:extra.worldMatrix[0]',
            'unrelated.matrix[9]':'unrelatedJoint.worldMatrix[0]'}
        self.frozen = {}
    def path(self,identity):
        leaf,parent,_ = self.nodes[identity]
        return (self.path(parent) if parent else '')+'|'+leaf
    def ids(self,address):
        if address in self.nodes:return [address]
        return [identity for identity,(name,_,_) in self.nodes.items()
                if address in (name,self.path(identity))]
    def ls(self,address=None,**flags):
        if flags.get('type')=='skinCluster':return ['skin','branchSkin','unrelated']
        ids = self.ids(address)
        if flags.get('uuid'):return ids
        return [self.path(identity) for identity in ids]
    def objExists(self,address):
        node = address.split('.',1)[0]
        return bool(self.ids(node)) or node in ('skin','branchSkin','unrelated','unrelatedJoint')
    def attributeQuery(self,*args,**kwargs):return False
    def addAttr(self,*args,**kwargs):pass
    def nodeType(self,address):return self.nodes[self.ids(address)[0]][2]
    def listRelatives(self,address,**flags):
        ids = self.ids(address)
        if not ids:return []
        identity = ids[0]
        if flags.get('parent'):
            parent = self.nodes[identity][1]
            return [self.path(parent)] if parent else []
        if flags.get('allDescendents') and address=='DeformationSystem':return self.advanced
        return [self.path(child) for child,(_,parent,kind) in self.nodes.items()
                if parent==identity and (not flags.get('type') or kind==flags['type'])]
    def listConnections(self,address,**flags):
        if address.endswith('.matrix'):
            return [item for destination,source in self.edges.items()
                    if destination.startswith(address+'[') for item in (destination,source)]
        node = address.split('.',1)[0]
        names = [node]
        ids = self.ids(node)
        if ids:names.extend(self.nodes[identity][0] for identity in ids)
        return [destination for destination,source in self.edges.items()
                if source.split('.',1)[0] in names]
    def connectAttr(self,source,destination,**flags):
        self.events.append(('connect',source,destination,flags))
        self.edges[destination] = source
    def parent(self,child,parent):
        identity = self.ids(child)[0]
        name,_,kind = self.nodes[identity]
        self.nodes[identity] = name,self.ids(parent)[0],kind
        self.events.append(('parent',identity,self.ids(parent)[0]))
        return [self.path(identity)]
    def delete(self,address):
        identity = self.ids(address)[0]
        descendants = [item for item in self.nodes if self.path(item).startswith(self.path(identity)+'|')]
        self.events.append(('delete',identity))
        for item in (*descendants,identity):self.nodes.pop(item)
    def getAttr(self,address,**flags):return [MATRIX]
    def setAttr(self,address,*values,**flags):
        self.events.append(('set',address,values))
        if '.bindPreMatrix[' in address:self.frozen[address] = values
    def confirmDialog(self,**flags):self.events.append(('note',flags['message']));return 'Ok'
    def dgdirty(self,**flags):self.events.append(('dirty',flags))
    def listHistory(self,address,**flags):return [address+'Mesh','unusedTransform']
    def objectType(self,address):return 'mesh' if address.endswith('Mesh') else 'transform'
    def skinPercent(self,skin,node,**flags):self.events.append(('normalize',skin,node,flags))


class NativeSkinTests(unittest.TestCase):
    def host(self,commands):
        return SimpleNamespace(_cmds=commands,_require_transaction=lambda:None,
                               scene_address=lambda address:address)
    def test_source_targets_keep_absent_final_target_and_exact_duplicate_rows(self):
        result = source_name_matcher_targets(('|rig|Root_M','|rig|IndexFinger4_R'),
            (NameMatcherRow('Root','old'),NameMatcherRow('Root','pelvis'),
             NameMatcherRow('IndexFinger4','missing')),NameMatcherRules('r','l','',True,True),namespace='src')
        self.assertEqual(result,(('|rig|Root_M','src:pelvis'),('|rig|IndexFinger4_R','src:r_missing')))

    def test_native_handoff_rewires_then_retains_live_branch_deletes_dud_freezes_every_skin(self):
        commands = SkinCommands()
        # Tip maps to an ADV end, so it returns to its previous source parent
        # instead of being dragged along inside the retained extra branch.
        result = transfer_source_skin(self.host(commands),'src:pelvis',
            (NameMatcherRow('Root','pelvis'),NameMatcherRow('Wrist','hand'),
             NameMatcherRow('HeadEnd','tip')),NameMatcherRules('','',''))
        self.assertEqual((result.skins,result.matrix_links,result.retained_branches),(3,1,1))
        self.assertEqual(commands.nodes['extra'][1],'wrist')
        self.assertNotIn('tip',commands.nodes)
        self.assertNotIn('dud',commands.nodes)
        self.assertNotIn('group',commands.nodes)
        self.assertEqual(commands.edges['skin.matrix[2]'],commands.advanced[1]+'.worldMatrix[0]')
        self.assertEqual(set(commands.frozen),{'skin.bindPreMatrix[2]',
            'branchSkin.bindPreMatrix[5]','unrelated.bindPreMatrix[9]'})
        delete_index = next(i for i,event in enumerate(commands.events) if event==('delete','group'))
        dirty_index = next(i for i,event in enumerate(commands.events) if event[0]=='dirty')
        self.assertLess(delete_index,dirty_index)
        self.assertEqual([event[1] for event in commands.events if event[0]=='normalize'],
                         ['skin','branchSkin','unrelated'])
        self.assertIn(('parent','tip','hand'),commands.events)

    def test_absent_last_target_does_not_delete_ancestor_of_a_different_pair(self):
        commands = SkinCommands()
        result = transfer_source_skin(self.host(commands),'src:pelvis',
            (NameMatcherRow('Root','pelvis'),NameMatcherRow('Wrist','hand'),
             NameMatcherRow('HeadEnd','missing')),NameMatcherRules('','',''))
        self.assertIn('group',commands.nodes)
        self.assertEqual(result.missing,('src:missing',))

    def test_application_uses_native_action_without_legacy_matrix_compensation(self):
        class Host:
            @contextmanager
            def transaction(self,label):yield
            def transfer_source_name_matcher_skin(self,*args):return 'native'
            def capture_source_skeleton(self,*args):raise AssertionError('legacy route')
        self.assertEqual(TransferNameMatchedSkinInfluences(Host()).apply('root',(),NameMatcherRules()),'native')

    def test_mapping_action_restores_auto_key_on_failure(self):
        commands = SimpleNamespace(autoKeyframe=lambda **kwargs:
            True if kwargs.get('query') else events.append(kwargs['state']),
            select=lambda **kwargs:events.append('selection'))
        events = []
        @mapping_action
        def fail(host):raise RuntimeError('native failure')
        with self.assertRaisesRegex(RuntimeError,'native failure'):fail(self.host(commands))
        self.assertEqual(events,[False,True])

    def test_zero_out_skips_locked_rotation_without_unlocking_or_aborting(self):
        commands = SkinCommands()
        events = []
        commands.autoKeyframe = lambda **kwargs: True if kwargs.get('query') else events.append(kwargs['state'])
        commands.select = lambda **kwargs:events.append('selection')
        def set_attr(plug,*values,**kwargs):
            events.append(plug)
            if plug=='src:hand.rotate':raise RuntimeError('locked')
        commands.setAttr = set_attr
        host = self.host(commands)
        result = MayaSourceNameMatcherControlsMixin.zero_out_source_name_matcher_joints(host,'src:pelvis',
            (NameMatcherRow('Root','pelvis'),NameMatcherRow('Wrist','hand')),
            NameMatcherRules('','',''))
        self.assertEqual(result.joints,2)
        self.assertEqual(events,[False,'src:pelvis.rotate','src:hand.rotate',True,'selection'])


if __name__=='__main__':unittest.main()
