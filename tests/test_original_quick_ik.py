"""Source QuickIK chain inference and the complete temporary graph commands."""
import unittest
from unittest.mock import patch
from adv_py.adapters.maya_original_quick_ik import create


class Commands:
    def __init__(self):
        self.parents={'Rig':None,'IndexFinger1_R':'Rig','IndexFinger2_R':'IndexFinger1_R',
                      'IndexFinger3_R':'IndexFinger2_R','IndexFingerEnd_R':'IndexFinger3_R',
                      'FKIndexFinger1_R':'Rig','FKIndexFinger2_R':'Rig','FKIndexFinger3_R':'Rig'}
        self.kinds={name:'joint' if name.startswith('Index') else 'transform' for name in self.parents}
        self.events=[];self.selected=[];self.values={};self.temporary=0
    def objExists(self,name):return name.split('.',1)[0] in self.parents
    def path(self,name):
        parts=[name]
        while self.parents.get(parts[-1]):parts.append(self.parents[parts[-1]])
        return '|'+ '|'.join(reversed(parts))
    def ls(self,name=None,**flags):
        if flags.get('selection'):return self.selected
        if name and name.split('|')[-1] in self.parents:
            name=name.split('|')[-1];return [self.path(name) if flags.get('long') else name]
        return []
    def listRelatives(self,name,**flags):
        if flags.get('parent'):return [self.parents[name]] if self.parents[name] else []
        return [node for node in reversed(tuple(self.parents)) if node!=name
                and self.path(node).startswith(self.path(name)+'|') and self.kinds[node]=='joint']
    def select(self,name):self.selected=[name];self.events.append(('select',name))
    def createNode(self,kind,**flags):
        name=flags.get('name')
        if not name:
            self.temporary+=1;parent='annotation'+str(self.temporary)
            self.parents[parent]=None;self.kinds[parent]='transform';name=parent+'Shape'
            flags['parent']=parent
        self.parents[name]=flags.get('parent');self.kinds[name]=kind
        self.events.append(('create',name,kind,dict(flags)));return name
    def joint(self,**flags):return self.createNode('joint',parent=self.selected[0],**flags)
    def parent(self,name,parent=None,**flags):
        self.events.append(('parent',name,parent,flags));self.parents[name]=parent;return [name]
    def setAttr(self,plug,*values,**flags):self.values[plug]=values;self.events.append(('set',plug,values,flags))
    def getAttr(self,plug):return 3 if plug.endswith('.rotateOrder') else 8
    def xform(self,name,**flags):
        self.events.append(('xform',name,flags))
        if flags.get('query'):return (0,0,0) if name.endswith('1_R') else (8,0,0)
    def spaceLocator(self,**flags):return [self.createNode('transform',**flags)]
    def duplicate(self,source,**flags):return [self.createNode('transform',parent=self.parents[source],**flags)]
    def ikHandle(self,**flags):self.events.append(('ik',flags));return [self.createNode('ikHandle',**flags),'effector']
    def parentConstraint(self,*args,**flags):self.events.append(('root_follow',args,flags));return ['parentConstraint']
    def poleVectorConstraint(self,*args):self.events.append(('pole',args));return ['poleConstraint']
    def orientConstraint(self,*args):self.events.append(('orient',args));return ['orientConstraint']
    def rename(self,name,target):self.parents[target]=self.parents.pop(name);self.kinds[target]=self.kinds.pop(name);return target
    def connectAttr(self,*args):self.events.append(('connect',args))
    def warning(self,message):self.events.append(('warning',message))


class Host:
    def __init__(self):self._cmds=Commands()
    def _require_transaction(self):pass


class OriginalQuickIKTests(unittest.TestCase):
    def test_reversed_selection_assumes_one_end_and_keeps_source_finger_graph(self):
        host=Host();c=host._cmds
        with patch('adv_py.adapters.maya_original_quick_ik.registration',return_value=None):
            result=create(host,('FKIndexFinger3_R','FKIndexFinger1_R'))
        self.assertEqual((result.start_joint,result.end_joint,result.assumed_end),('IndexFinger1_R','IndexFingerEnd_R',True))
        self.assertEqual(result.constrained_controls,('FKIndexFinger1_R','FKIndexFinger2_R','FKIndexFinger3_R'))
        self.assertEqual(len(result.joints),4)
        self.assertEqual(c.parents[result.control],'QuickIKOffset_IndexFinger1_R')
        self.assertEqual(c.parents[result.pole],'QuickPoleVectorOffset_IndexFinger1_R')
        self.assertEqual(c.parents['QuickPoleVectorOffset_IndexFinger1_R'],result.control)
        self.assertEqual(c.values[result.pole+'.tz'],(8.0,))
        self.assertNotIn(result.pole+'.ty',c.values)
        self.assertTrue(all(c.values[node+'.preferredAngle']==(0,10,0) for node in result.joints))
        self.assertIn(('ik',dict(name=result.handle,numSpans=2,solver='ikRPsolver',
            startJoint=result.joints[0],endEffector=result.joints[-1])),c.events)
        self.assertEqual(c.selected,[result.control])

    def test_unrelated_controls_fail_before_creating_any_graph(self):
        host=Host()
        host._cmds.parents['Other_R']=None
        host._cmds.kinds['Other_R']='joint'
        host._cmds.parents['FKOther_R']=None
        host._cmds.kinds['FKOther_R']='transform'
        with patch('adv_py.adapters.maya_original_quick_ik.registration',return_value=None):
            with self.assertRaisesRegex(ValueError,'same hierarchy'):
                create(host,('FKIndexFinger1_R','FKOther_R'))
        self.assertEqual(host._cmds.events,[])
