"""Source role branches must not depend on Python implementation spelling."""
from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

from adv_py.core.character_registry import CharacterChannel
from adv_py.adapters.maya_original_control_identity import (
    fk_bindings, source_control_name, source_fk_joint, source_fk_control,
    source_mirror_control, source_control_from_role, original_character_height,
)


def fixture():
    channels=[]
    for side in ('R','L'):
        primary='|Group|AdvPy_Finger1_'+side+'FK'
        key='generic.fk.Finger1_'+side+'FK'
        channels += [CharacterChannel(key+'.rotateX',primary,'rotateX'),
                     CharacterChannel(key+'.sub.rotateX',primary+'|AdvPy_Finger1_'+side+'FKSub','rotateX'),
                     CharacterChannel(key+'.extra.rotateX','|Extra_'+side,'rotateX')]
        channels.append(CharacterChannel('arm.'+side+'.blend','|Mode_'+side,'FKIKBlend'))
    limbs=tuple(Row(label='Arm',side=side,blend_key='arm.'+side+'.blend',ik_control='|AdvPy_Arm_'+side+'_IKControl',
        pole_control='|AdvPy_Arm_'+side+'_Pole',reset_controls=(),joints=(
            Row(body='|Shoulder_'+side,control='|AdvPy_Shoulder_'+side+'FK',fk_driver='|FKX_'+side),
            Row(body='|Hidden_'+side,control='|HiddenFKX_'+side,fk_driver='|HiddenFKX_'+side)))
        for side in ('R','L'))
    return Row(channels=tuple(channels),source_limbs=limbs,spine=None,additional_spines=())


class OriginalControlIdentityTests(unittest.TestCase):
    def setUp(self):
        self.saved=fixture()
        self.host=Row(_cmds=Row(objExists=lambda _:False))
        scope=patch('adv_py.adapters.maya_original_control_identity.registration',return_value=self.saved)
        scope.start();self.addCleanup(scope.stop)

    def test_sub_and_extra_do_not_replace_primary_fk(self):
        bindings=fk_bindings(self.saved)
        self.assertEqual(bindings['Finger1_R'],'AdvPy_Finger1_RFK')
        self.assertNotIn('Hidden_R',bindings)

    def test_native_saved_sdk_roles_resolve_existing_python_controls(self):
        for source, actual in (('FKShoulder_R','AdvPy_Shoulder_RFK'),
                               ('IKArm_L','AdvPy_Arm_L_IKControl'),
                               ('PoleArm_R','AdvPy_Arm_R_Pole'),
                               ('FKIKArm_R','Mode_R')):
            self.assertEqual(source_control_from_role(self.host,source),actual)
        self.assertEqual(source_control_from_role(self.host,'DrivingSystem1_R'),'DrivingSystem1_R')

    def test_source_role_and_deformation_joint_survive_full_namespace_paths(self):
        control='|hero:Group|hero:AdvPy_Shoulder_RFK'
        self.assertEqual(source_control_name(self.host,control),'FKShoulder_R')
        self.assertEqual(source_fk_joint(self.host,control),'Shoulder_R')
        self.assertEqual(source_fk_control(self.host,'Shoulder_R'),'AdvPy_Shoulder_RFK')

    def test_fk_ik_and_pole_mirror_actual_objects_by_role(self):
        for source,expected in (('AdvPy_Shoulder_RFK','AdvPy_Shoulder_LFK'),
                ('AdvPy_Arm_R_IKControl','AdvPy_Arm_L_IKControl'),
                ('AdvPy_Arm_R_Pole','AdvPy_Arm_L_Pole')):
            self.assertEqual(source_mirror_control(self.host,source,'L'),expected)
        self.assertEqual(source_mirror_control(self.host,'ctrlCustom_R','L'),'ctrlCustom_L')
        self.assertEqual(source_mirror_control(self.host,'ctrlLips_M','L'),'ctrlLips_M')

    def test_source_extra_sub_and_mode_branches_use_registered_roles(self):
        self.assertEqual(source_control_name(self.host,'Extra_R'),'FKExtraFinger1_R')
        self.assertEqual(source_control_name(self.host,'AdvPy_Finger1_LFKSub'),'FKSubFinger1_L')
        self.assertEqual(source_control_name(self.host,'Mode_R'),'FKIKArm_R')
        self.assertEqual(source_mirror_control(self.host,'Mode_R','L'),'Mode_L')
        self.assertEqual(source_mirror_control(self.host,'ctrl_R_custom','L'),'ctrl_L_custom')

    def test_character_height_preserves_native_precedence_and_zero(self):
        values={'hero:AdvPy_Global':True,'hero:AdvPy_Global.height':200.}
        c=Row(objExists=lambda node:node in values,getAttr=lambda node:values[node])
        self.assertEqual(original_character_height(c,'hero'),200.)
        values.update({'hero:Main':True,'hero:Main.height':180.})
        self.assertEqual(original_character_height(c,'hero'),180.)
        del values['hero:Main.height']
        with self.assertRaises(KeyError):original_character_height(c,'hero')
        self.assertEqual(original_character_height(c,'other'),0.)

    def test_source_scene_without_python_registration_keeps_literal_names(self):
        with patch('adv_py.adapters.maya_original_control_identity.registration',return_value=None):
            self.assertEqual(source_control_name(self.host,'FKElbow_R'),'FKElbow_R')
            self.assertEqual(source_fk_joint(self.host,'FKElbow_R'),'Elbow_R')
            self.assertEqual(source_mirror_control(self.host,'FKElbow_R','L'),'FKElbow_L')
