"""Mode schedules consume the saved public control, not its solver input."""
from types import SimpleNamespace
import unittest

from adv_py.core.character_registry import CharacterChannel,CharacterRegistryError
from adv_py.adapters.maya_mocap_control import MayaMocapControlHost


class SourceMocapModeBoundaryTests(unittest.TestCase):
    def fixture(self,attribute,value):
        host=MayaMocapControlHost.__new__(MayaMocapControlHost)
        host.scene_address=lambda node:node
        host._cmds=SimpleNamespace(getAttr=lambda *args,**flags:value,
            keyframe=lambda *args,**flags:(),keyTangent=lambda *args,**flags:())
        channel=CharacterChannel('arm.settings.armIkFk_R','|mode',attribute,0.,
            10. if attribute=='FKIKBlend' else 1.)
        return host,SimpleNamespace(channels=(channel,)),channel.key

    def test_source_ten_is_an_ik_endpoint_and_boundary_value_stays_ten(self):
        host,saved,key=self.fixture('FKIKBlend',10.)
        boundary=host.preflight_mocap_mode_schedule(saved,(key,),(1.,2.),replace_existing_modes=True)
        self.assertEqual(boundary[0][-2:],(10.,10.))

    def test_source_one_is_a_blended_pose_and_is_not_an_ik_endpoint(self):
        host,saved,key=self.fixture('FKIKBlend',1.)
        with self.assertRaises(CharacterRegistryError):
            host.preflight_mocap_mode_schedule(saved,(key,),(1.,2.),replace_existing_modes=True)

    def test_historical_solver_channel_still_uses_one(self):
        host,saved,key=self.fixture('armIkFk_R',1.)
        self.assertEqual(host.preflight_mocap_mode_schedule(saved,(key,),(1.,2.),
            replace_existing_modes=True)[0][-2:],(1.,1.))

    def test_non_replacement_schedule_requires_fk_for_both_control_layouts(self):
        for attribute,ik in (('FKIKBlend',10.),('armIkFk_R',1.)):
            host,saved,key=self.fixture(attribute,ik)
            with self.subTest(attribute=attribute),self.assertRaises(CharacterRegistryError):
                host.preflight_mocap_mode_schedule(saved,(key,),(1.,2.))
            host._cmds.getAttr=lambda *args,**flags:0.
            self.assertEqual(host.preflight_mocap_mode_schedule(saved,(key,),(1.,2.))[0][-2:],(0.,0.))


if __name__=='__main__':unittest.main()
