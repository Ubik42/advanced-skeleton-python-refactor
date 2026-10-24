"""Source BS controllers rebuild before external weight/curve handoff."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adv_py.adapters.maya_name_matcher_blend_rebuild import capture,restore
from adv_py.core.character_registry import CharacterChannel,CharacterNode,CharacterRegistryError
from test_character_registry import registration_fixture


class BlendRebuildTests(unittest.TestCase):
    def fixture(self):
        reg=registration_fixture()
        tip=reg.body[-1]
        head=tip.parent+'|Head_M'
        reg=replace(reg,body=reg.body[:-1]+(replace(tip,path=head),),
            nodes=tuple(replace(node,path=head) if node.path==tip.path else node for node in reg.nodes))
        path='|ExpressionsCtrl'
        channel=CharacterChannel('nameMatcher.blendShape.ExpressionsCtrl.Smile',path,'Smile')
        node=CharacterNode(path,'original-control-id','transform',None,())
        return reg,replace(reg,nodes=reg.nodes+(node,),channels=reg.channels+(channel,)),path

    def commands(self,head,path,*,created=True,head_uuid='head-id'):
        matrix=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,5.,8.,3.,1.)
        class Commands:
            exists=created
            writes=[]
            parent_name=path+'|ExpressionsCtrl_parentConstraint1'
            scale_name=path+'|ExpressionsCtrl_scaleConstraint1'
            def ls(self,node,**flags):
                if node in ('Head_M',head):return [head_uuid] if flags.get('uuid') else [head]
                if node in (path,path.lstrip('|')):
                    if not self.exists:return []
                    return ['original-control-id'] if flags.get('uuid') else [path]
                if node in (self.parent_name,self.scale_name):
                    return [node+'-id'] if flags.get('uuid') else [node]
                return []
            def nodeType(self,node):
                return 'parentConstraint' if node==self.parent_name else (
                    'scaleConstraint' if node==self.scale_name else 'transform')
            def listRelatives(self,node,**flags):
                if flags.get('parent'):return []
                if flags.get('shapes'):return [path+'|ExpressionsCtrlShape']
                return [self.parent_name,self.scale_name]
            def objExists(self,plug):
                if plug in ('Head_M',head):return True
                if plug==path.lstrip('|'):return self.exists
                return plug.endswith('.target[0].targetOffsetTranslate')
            def getAttr(self,plug,**flags):
                return 'double3' if flags.get('type') else [(2.,0.,-4.)]
            def connectionInfo(self,*args,**flags):return ''
            def xform(self,node,**flags):
                if flags.get('query'):return matrix
                self.writes.append(('matrix',flags['matrix']))
            def parentConstraint(self,*args,**flags):
                if flags.get('query'):return [head]
                self.writes.append(('parent',args,flags))
                return [self.parent_name]
            def scaleConstraint(self,*args,**flags):
                if flags.get('query'):return [head]
                self.writes.append(('scale',args,flags))
                return [self.scale_name]
            def circle(self,**flags):
                self.exists=True
                self.writes.append(('circle',flags))
                return [path]
            def setAttr(self,*args,**flags):self.writes.append(('attribute',args,flags))
            def addAttr(self,*args,**flags):self.writes.append(('new-attribute',args,flags))
            def connectAttr(self,*args,**flags):
                raise AssertionError('Staging must not connect external blendShape weights')
        return Commands()

    def test_native_nodes_constraints_offsets_and_channels_recreated_without_external_writes(self):
        base,original,path=self.fixture()
        head=next(row.path for row in base.body if row.path.rsplit('|',1)[-1]=='Head_M')
        head_uuid=next(row.uuid for row in base.nodes if row.path==head)
        raw=self.commands(head,path,head_uuid=head_uuid)
        rows=capture(SimpleNamespace(_cmds=raw),original)
        self.assertEqual(len(rows),1)
        self.assertEqual(tuple(row.kind for row in rows[0].constraints),('parentConstraint','scaleConstraint'))
        staged=self.commands(head,path,created=False)
        host=SimpleNamespace(_cmds=staged,_require_transaction=lambda:None,
            capture_character_registration_node=lambda node:CharacterNode(node,'stage-control-id','transform',None,()))
        with patch('adv_py.adapters.maya_name_matcher_blend_rebuild.scene_ids',return_value=frozenset()), \
             patch('adv_py.adapters.maya_name_matcher_blend_rebuild.remember_generated_nodes'), \
             patch('adv_py.adapters.maya_name_matcher_blend_rebuild._write_members'), \
             patch('adv_py.adapters.maya_name_matcher_blend_rebuild._write_string'):
            result=restore(host,rows,base)
        self.assertEqual(result.channels,original.channels)
        self.assertEqual(result.nodes[-1].uuid,'stage-control-id')
        circle=next(row[1] for row in staged.writes if row[0]=='circle')
        self.assertEqual((circle['radius'],circle['degree'],circle['sections']),(1,3,8))
        self.assertTrue(any(row[0]=='attribute' and row[1][0].endswith('targetOffsetTranslate')
                            and row[1][1:]==(2.,0.,-4.) for row in staged.writes))

    def test_control_identity_changes_are_rejected_before_staging(self):
        base,original,path=self.fixture()
        head=next(row.path for row in base.body if row.path.rsplit('|',1)[-1]=='Head_M')
        head_uuid=next(row.uuid for row in base.nodes if row.path==head)
        raw=self.commands(head,path,head_uuid=head_uuid)
        wrong=replace(original,nodes=original.nodes[:-1]+(replace(original.nodes[-1],uuid='replacement'),))
        with self.assertRaisesRegex(CharacterRegistryError,'身份改变'):
            capture(SimpleNamespace(_cmds=raw),wrong)

    def test_same_name_head_replacement_cannot_be_adopted_as_original_target(self):
        base,original,path=self.fixture()
        head=next(row.path for row in base.body if row.path.rsplit('|',1)[-1]=='Head_M')
        raw=self.commands(head,path,head_uuid='replacement-head-id')
        with self.assertRaisesRegex(CharacterRegistryError,'Head 身份改变'):
            capture(SimpleNamespace(_cmds=raw),original)


if __name__=='__main__':unittest.main()
