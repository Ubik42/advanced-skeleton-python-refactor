"""Regression for native axis-restricted FK roles, including default Jaw."""
import unittest
from types import SimpleNamespace as NS
from adv_py.core.source_control_identity import source_fk_bindings, source_control_roles


def saved(channels):
    return NS(channels=channels, source_limbs=(), spine=None, additional_spines=(), nodes=())


class SourceControlIdentityTests(unittest.TestCase):
    def test_jaw_without_rotate_x_keeps_native_role(self):
        control = '|Group|JawOffset|JawControl'
        rows = tuple(NS(key='generic.fk.Jaw_MFK.' + attr, attribute=attr, node=control)
                     for attr in ('translateY', 'translateZ', 'rotateZ', 'scaleX', 'scaleY', 'scaleZ'))
        self.assertEqual(source_fk_bindings(saved(rows)), (('Jaw_M', control),))
        self.assertEqual(source_control_roles(saved(rows)), {'JawControl': 'FKJaw_M'})

    def test_extra_sub_and_custom_channels_do_not_replace_primary(self):
        rows = [NS(key='generic.fk.Jaw_MFK.rotateZ', attribute='rotateZ', node='|Jaw')]
        rows += [NS(key='generic.fk.Jaw_MFK.' + layer + '.rotateX', attribute='rotateX', node='|' + layer)
                 for layer in ('extra', 'sub')]
        rows.append(NS(key='generic.fk.Jaw_MFK.custom', attribute='custom', node='|Custom'))
        self.assertEqual(source_fk_bindings(saved(rows)), (('Jaw_M', '|Jaw'),))

    def test_conflicting_registered_controls_remain_visible(self):
        rows = [NS(key='generic.fk.Jaw_MFK.rotateZ', attribute='rotateZ', node=path)
                for path in ('|First', '|Second')]
        self.assertEqual(source_fk_bindings(saved(rows)), (('Jaw_M', '|First'), ('Jaw_M', '|Second')))
