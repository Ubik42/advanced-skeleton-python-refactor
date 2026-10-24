"""Source retained-animation order, subframes and absent original skeleton."""
from types import SimpleNamespace
import unittest

from adv_py.core.character_registry import CharacterChannel
from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules
from adv_py.adapters.maya_source_name_matcher_animation import bake,keep


class KeptCommands:
    root='|NameMatcherKeepAnimation:hips'
    child=root+'|NameMatcherKeepAnimation:hand'
    def __init__(self):
        self.nodes={self.root:('copy-root','joint',None),self.child:('copy-hand','joint',self.root),
            '|DeformationSystem':('deformation','transform',None),
            '|DeformationSystem|Root_M':('body-root','joint','|DeformationSystem'),
            '|DeformationSystem|Root_M|Wrist_R':('body-hand','joint','|DeformationSystem|Root_M'),
            '|FKRoot_M':('fk-root','transform',None),'|FKWrist_R':('fk-hand','transform',None),
            'FKIKArm_R':('mode','transform',None),'HipSwinger_M':('hip','transform',None),
            'skin':('skin-id','skinCluster',None),'meshShape':('mesh-id','mesh',None)}
        self.events=[];self.times=(0.,2.75,9.9);self.auto_key=True
    def resolve(self,address):
        return [path for path,(identity,_,_) in self.nodes.items()
            if address in (path,identity,path.rsplit('|',1)[-1])]
    def ls(self,address=None,**flags):
        if flags.get('type')=='skinCluster':return ['skin']
        if address==':NameMatcherKeepAnimation:*':return [path for path in self.nodes if 'NameMatcherKeepAnimation:' in path]
        paths=self.resolve(address)
        return [self.nodes[path][0] for path in paths] if flags.get('uuid') else paths
    def attributeQuery(self,attribute,node,**flags):
        return (attribute=='advPyKeepAnimation' and node==self.root
            or attribute=='FKIKBlend' and node=='FKIKArm_R')
    def getAttr(self,plug,**flags):return plug==self.root+'.advPyKeepAnimation'
    def nodeType(self,node):return self.nodes[self.resolve(node)[0]][1]
    def listRelatives(self,address,**flags):
        paths=self.resolve(address)
        if flags.get('parent'):
            parent=self.nodes[paths[0]][2]
            return [parent] if parent else []
        if address=='DeformationSystem':
            return ['|DeformationSystem|Root_M|Wrist_R','|DeformationSystem|Root_M']
        return [path for path in self.nodes if path.startswith(paths[0]+'|')]
    def objExists(self,address):
        return bool(self.resolve(address)) or address=='HipSwinger_M.stabilize'
    def skinCluster(self,node,**flags):
        return ['|DeformationSystem|Root_M'] if flags.get('influence') else ['meshShape']
    def parentConstraint(self,target,control,**flags):
        self.events.append(('constraint',target,control,flags));return ['parentConstraint1']
    def select(self,*args,**flags):self.events.append(('select',args,flags))
    def keyframe(self,**flags):return self.times
    def playbackOptions(self,**flags):self.events.append(('playback',flags))
    def sets(self,*args,**flags):return ['FKIKArm_R']
    def setAttr(self,plug,*values,**flags):self.events.append(('set',plug,values))
    def bakeResults(self,controls,**flags):self.events.append(('bake',controls,flags))
    def currentTime(self,time):self.events.append(('time',time))
    def delete(self,nodes,**flags):
        self.events.append(('delete',nodes,flags))
        if not flags.get('staticChannels'):
            for path in nodes:self.nodes.pop(path,None)
    def namespace(self,**flags):self.events.append(('namespace',flags))
    def autoKeyframe(self,**flags):
        if flags.get('query'):return self.auto_key
        self.auto_key=flags['state']


class SourceKeptAnimationBakeTests(unittest.TestCase):
    def fixture(self):
        c=KeptCommands()
        channels=(CharacterChannel('generic.fk.Root_MFK.rotateX','|FKRoot_M','rotateX'),
            CharacterChannel('generic.fk.Wrist_RFK.rotateX','|FKWrist_R','rotateX'))
        registration=SimpleNamespace(channels=channels,source_limbs=(),spine=None,additional_spines=())
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            read_character_registration=lambda:registration,scene_address=lambda value:value)
        rows=(NameMatcherRow('Root','hips'),NameMatcherRow('Wrist','hand'))
        return host,c,rows

    def test_native_bake_uses_kept_skeleton_after_original_source_is_gone(self):
        host,c,rows=self.fixture()
        result=bake(host,'|deletedOriginal',rows,NameMatcherRules('','',''))
        self.assertEqual((result.controls,result.first_frame,result.last_frame),(2,-1.,9.))
        self.assertTrue(c.auto_key)
        events=[event[0] for event in c.events]
        self.assertLess(events.index('constraint'),events.index('playback'))
        self.assertLess(events.index('playback'),events.index('set'))
        self.assertLess(events.index('set'),events.index('bake'))
        native=next(event for event in c.events if event[0]=='bake')
        self.assertEqual(native[2]['time'],(-1.,9.))
        self.assertEqual(native[2]['sampleBy'],1)
        self.assertEqual(native[2]['preserveOutsideKeys'],False)
        self.assertFalse(c.ls(':NameMatcherKeepAnimation:*'))
        self.assertIn(('time',-1),c.events)
        self.assertFalse(result.missing)

    def test_no_keys_leaves_kept_skeleton_and_native_constraints_as_source_does(self):
        host,c,rows=self.fixture();c.times=()
        result=bake(host,None,rows,NameMatcherRules('','',''))
        self.assertEqual(result.controls,0)
        self.assertTrue(c.ls(':NameMatcherKeepAnimation:*'))
        self.assertTrue(any(event[0]=='constraint' for event in c.events))
        self.assertFalse(any(event[0] in ('bake','delete','namespace') for event in c.events))

    def test_absent_kept_namespace_is_original_noop(self):
        host,c,rows=self.fixture();c.nodes.pop(c.root);c.nodes.pop(c.child)
        self.assertEqual(bake(host,None,rows,NameMatcherRules()).controls,0)
        self.assertFalse(any(event[0]=='bake' for event in c.events))

    def test_shared_skin_output_to_copied_mesh_does_not_block_native_cleanup(self):
        host,c,rows=self.fixture()
        copied_mesh=c.root+'|NameMatcherKeepAnimation:bodyShape'
        c.nodes[copied_mesh]=('copy-mesh','mesh',c.root)
        def skin(node,**flags):
            if flags.get('influence'):return ['|DeformationSystem|Root_M']
            return ['meshShape']+([copied_mesh] if copied_mesh in c.nodes else [])
        c.skinCluster=skin
        self.assertEqual(bake(host,None,rows,NameMatcherRules('','','')).controls,2)
        self.assertTrue(c.objExists('meshShape'))
        self.assertFalse(c.objExists(copied_mesh))

    def test_production_skin_endpoint_change_is_still_rejected(self):
        host,c,rows=self.fixture()
        original=c.bakeResults
        def change(controls,**flags):
            original(controls,**flags)
            c.nodes['meshShape']=('replaced-production-mesh','mesh',None)
        c.bakeResults=change
        with self.assertRaisesRegex(RuntimeError,'模型身份'):
            bake(host,None,rows,NameMatcherRules('','',''))


class KeepCommands:
    source='|sourceGroup'
    clone='|NameMatcherKeepAnimation:sourceGroup'
    def __init__(self,choice='Yes'):
        self.choice=choice;self.events=[];self.attrs={};self.active=':character'
        self.nodes={self.source:('source-id','transform'),
            self.source+'|meshShape':('source-mesh','mesh')}
        self.inputs=((self.source+'.rotateX','sourceCurve.output'),)
    def ls(self,address=None,**flags):
        if flags.get('selection'):return ['|previousSelection']
        paths=[path for path,(identity,_) in self.nodes.items() if address in (path,identity)]
        return [self.nodes[path][0] for path in paths] if flags.get('uuid') else paths
    def nodeType(self,node):return self.nodes[node][1]
    def select(self,*args,**flags):self.events.append(('select',args,flags))
    def confirmDialog(self,**flags):self.events.append(('dialog',flags));return self.choice
    def namespace(self,**flags):
        if flags.get('exists'):return False
        self.events.append(('namespace',flags))
        if 'setNamespace' in flags:self.active=flags['setNamespace']
    def duplicate(self,root,**flags):
        self.events.append(('duplicate',root,flags,self.active))
        self.nodes[self.clone]=('copy-id','transform')
        self.nodes[self.clone+'|NameMatcherKeepAnimation:meshShape']=('copy-mesh','mesh')
        return [self.clone]
    def addAttr(self,node,**flags):
        self.attrs[node+'.'+flags['longName']]=flags.get('defaultValue')
        self.events.append(('add',node,flags))
    def setAttr(self,plug,*values,**flags):
        if values:self.attrs[plug]=values[0]
        self.events.append(('set',plug,values,flags))
    def delete(self,**flags):self.events.append(('delete-channels',flags))


class SourceKeepAnimationTests(unittest.TestCase):
    def fixture(self,choice='Yes'):
        c=KeepCommands(choice)
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            capture_name_matcher_source_animation=lambda root:c.inputs)
        return host,c

    def test_transform_with_model_duplicates_shared_inputs_in_native_namespace(self):
        host,c=self.fixture()
        clone,count=keep(host,c.source,c.inputs)
        self.assertEqual((clone,count),(c.clone,1))
        duplicate=next(event for event in c.events if event[0]=='duplicate')
        self.assertEqual(duplicate[2],{'inputConnections':True})
        self.assertEqual(duplicate[3],':NameMatcherKeepAnimation')
        self.assertEqual(c.active,':')
        self.assertEqual(c.attrs[clone+'.advPySourceUUID'],'source-id')
        self.assertTrue(c.attrs[clone+'.advPyKeepAnimation'])
        names=[event[0] for event in c.events]
        self.assertLess(names.index('duplicate'),names.index('delete-channels'))
        self.assertEqual(c.events[-1],('select',(('|previousSelection',),),{'replace':True}))

    def test_no_branch_clears_time_channels_without_duplicate_or_selection_restore(self):
        host,c=self.fixture('No')
        self.assertEqual(keep(host,c.source,c.inputs),('',0))
        self.assertFalse(any(event[0] in ('namespace','duplicate','add') for event in c.events))
        self.assertEqual(c.events[-1][0],'delete-channels')
        self.assertFalse(c.events[-1][1]['unitlessAnimationCurves'])

    def test_no_animation_keeps_original_hierarchy_selection_without_dialog_or_dag_changes(self):
        host,c=self.fixture();c.inputs=()
        self.assertEqual(keep(host,c.source,()),('',0))
        self.assertEqual(c.events,[('select',(c.source,),{'hierarchy':True,'replace':True})])


if __name__=='__main__':unittest.main()
