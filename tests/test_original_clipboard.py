"""Clipboard keeps native merge flags and cleans its exact reference/helper."""
from unittest.mock import patch
import unittest
from adv_py.adapters.maya_original_clipboard import MayaOriginalClipboardMixin


class Commands:
    def __init__(self):
        self.events=[];self.auto=True;self.names={'FKWrist_R.tx','Main.tx'}
        self.command='setAttr Main.tx 9;connectAttr WristCurve.output FKWrist_R.tx;'
    def getModifiers(self):return 5
    def ls(self,**flags):return ['FKWrist_R']
    def currentTime(self,**flags):return 12.5
    def autoKeyframe(self,**flags):
        if flags.get('query'):return self.auto
        self.auto=flags['state'];self.events.append(('auto',self.auto))
    def objExists(self,node):return node in self.names
    def sets(self,*args,**flags):return ['FKWrist_R','Main']
    def file(self,*args,**flags):
        self.events.append(('file',args,flags))
        if flags.get('exists'):return True
        if flags.get('reference'):return ['Selector2:poserAnimationInfo','Selector2:WristCurve']
    def referenceQuery(self,node,**flags):return 'Selector2RN'
    def getAttr(self,node,**flags):return self.command
    def createNode(self,kind,**flags):
        node=flags['name'].lstrip(':');self.names.add(node);return node
    def addAttr(self,node,**flags):self.names.add(node+'.'+flags['longName'])
    def attributeQuery(self,*args,**flags):return False
    def connectAttr(self,*args,**flags):self.events.append(('connect',args,flags))
    def copyKey(self,*args,**flags):self.events.append(('copy',args,flags))
    def pasteKey(self,*args,**flags):self.events.append(('paste',args,flags))
    def setAttr(self,*args,**flags):self.events.append(('set',args,flags))
    def delete(self,node):self.names.remove(node);self.events.append(('delete',node))
    def select(self,*args,**flags):self.events.append(('select',args,flags))
    def warning(self,message):self.events.append(('warning',message))


class Host(MayaOriginalClipboardMixin):
    def __init__(self):self._cmds=Commands()
    def _require_transaction(self):pass
    def scene_address(self,node):return node
    def original_control_sets(self,*args,**flags):return ('ControlSet',)


class OriginalClipboardTests(unittest.TestCase):
    def test_animation_shift_offsets_native_merge_and_control_preserves_main(self):
        host=Host();c=host._cmds
        with patch('adv_py.adapters.maya_native_animation_bake_boundary.capture',return_value='before'), \
             patch('adv_py.adapters.maya_native_animation_bake_boundary.finish') as finish, \
             patch('adv_py.adapters.maya_original_clipboard.source_control_from_role',side_effect=lambda h,n:n):
            self.assertEqual(host.paste_original_control_clipboard(True,source='clip.ma'),())
        self.assertIn(('paste',('FKWrist_R.tx',),dict(option='merge',copies=1,connect=False,
            timeOffset=12.5,floatOffset=0,valueOffset=0)),c.events)
        self.assertIn(('connect',('Selector2:WristCurve.output','tempXform.tx'),{'force':True}),c.events)
        self.assertFalse(any(row[0]=='set' for row in c.events))
        finish.assert_called_once_with(host,'before',mark_baked=False)
        self.assertIn(('file',(),{'removeReference':True,'referenceNode':'Selector2RN'}),c.events)
        self.assertNotIn('tempXform',c.names)
        self.assertTrue(c.auto)

    def test_missing_carrier_still_removes_the_new_exact_reference_and_restores_auto(self):
        host=Host();c=host._cmds;original=c.file
        def file(*args,**flags):
            result=original(*args,**flags)
            return ['Selector2:WristCurve'] if flags.get('reference') else result
        c.file=file
        with patch('adv_py.adapters.maya_native_animation_bake_boundary.capture',return_value='before'):
            with self.assertRaisesRegex(ValueError,'poserAnimationInfo'):
                host.paste_original_control_clipboard(True,source='clip.ma')
        self.assertIn(('file',(),{'removeReference':True,'referenceNode':'Selector2RN'}),c.events)
        self.assertTrue(c.auto)
