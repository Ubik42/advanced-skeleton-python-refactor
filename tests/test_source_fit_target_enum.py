"""Portable Fit target labels must remain consumable by original MEL getAttr -asString."""
import unittest
from adv_py.adapters.maya_fit import MayaFitJointHost
from adv_py.core.fit_metadata import FitJointField, FitJointFieldEdit


class TargetCommands:
    def __init__(self):self.definitions={};self.values={}
    def attributeQuery(self,name,*,node,**flags):
        definition=self.definitions.get(node+'.'+name)
        if flags.get('listEnum'):return [definition['enumName']]
        return definition is not None
    def addAttr(self,node,**definition):
        plug=node+'.'+definition['longName'];self.definitions[plug]=definition
        self.values[plug]=definition.get('defaultValue',0)
    def getAttr(self,plug,**flags):
        if flags.get('type'):return self.definitions[plug].get('attributeType','string')
        return self.values[plug]
    def setAttr(self,plug,value,**flags):self.values[plug]=value


class TargetEnumTests(unittest.TestCase):
    def setUp(self):
        self.host=object.__new__(MayaFitJointHost)
        self.host._cmds=TargetCommands()
        self.host._transaction_active=True;self.host._transaction_changed=False
    def test_all_target_fields_create_original_enum_labels(self):
        fields=((FitJointField.FOLLOW,'follow'),(FitJointField.IK_FOLLOW,'ikFollow'),
                (FitJointField.AIM_AT,'aimAt'),(FitJointField.PARENT_CONSTRAINT,'parentConstraint'),
                (FitJointField.POINT_CONSTRAINT,'pointConstraint'),
                (FitJointField.ORIENT_CONSTRAINT,'orientConstraint'),
                (FitJointField.SCALE_CONSTRAINT,'scaleConstraint'))
        for field,attribute in fields:
            with self.subTest(field=field):
                self.host.apply_fit_joint_edit('Joint',FitJointFieldEdit(field,'Root'))
                definitions=self.host._cmds.definitions
                target=definitions['Joint.'+attribute]
                self.assertEqual(target['enumName'],'Root')
                self.assertEqual(target['attributeType'],'enum')
                self.assertNotIn('dataType',target)
                self.assertEqual(self.host._cmds.values['Joint.'+target['longName']],0)
    def test_attachment_namespaces_use_original_encoding(self):
        for field in (FitJointField.GEO_ATTACH,FitJointField.PROXIMITY_PIN,FitJointField.CURVE_GUIDE):
            self.host.apply_fit_joint_edit('Joint',FitJointFieldEdit(field,'Character:mesh'))
        targets=[value for value in self.host._cmds.definitions.values() if value.get('enumName')=='Character__mesh']
        self.assertEqual(len(targets),3)
        self.assertTrue(all(value['attributeType']=='enum' for value in targets))
    def test_follow_and_orient_companion_defaults(self):
        self.host.apply_fit_joint_edit('Joint',FitJointFieldEdit(FitJointField.FOLLOW,'Root'))
        self.host.apply_fit_joint_edit('Joint',FitJointFieldEdit(FitJointField.ORIENT_CONSTRAINT,'Root'))
        for attribute in ('followLeftRight','followWorld','orientConstraintMaintainOffset'):
            definition=self.host._cmds.definitions['Joint.'+attribute]
            self.assertEqual(definition['attributeType'],'bool')
            self.assertFalse(definition['defaultValue'])


if __name__=='__main__':unittest.main()
