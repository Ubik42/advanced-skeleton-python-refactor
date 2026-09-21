import json
from dataclasses import replace
import unittest

from adv_py.core import (MocapClip,MocapClipJoint,MocapClipChannel,
                         encode_mocap_clip,decode_mocap_clip,validate_mocap_clip)
from adv_py.core.mocap_source import MocapSourceValidationError


IDENTITY=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)


class MocapClipTests(unittest.TestCase):
    def fixture(self):
        joint=MocapClipJoint('Hips',None,(0.,0.,0.),(0.,0.,0.),(0.,0.,0.),(1.,1.,1.),0,
                            (MocapClipChannel('translateX',((1.,0.),(5.,4.))),))
        moved=IDENTITY[:12]+(4.,0.,0.,1.)
        return MocapClip('y','cm','film',(joint,),((1.,(IDENTITY,)),(5.,(moved,))))

    def test_round_trip_and_digest(self):
        clip=self.fixture()
        self.assertEqual(decode_mocap_clip(encode_mocap_clip(clip)),clip)
        raw=json.loads(encode_mocap_clip(clip))
        raw['joints'][0]['channels'][0]['keys'][1][1]=5.
        with self.assertRaisesRegex(MocapSourceValidationError,'摘要'):
            decode_mocap_clip(json.dumps(raw))

    def test_rejects_invalid_topology_keys_and_matrices(self):
        clip=self.fixture()
        invalid=(replace(clip,joints=(replace(clip.joints[0],parent_name='Missing'),)),
                 replace(clip,joints=(replace(clip.joints[0],channels=(MocapClipChannel('translateX',((5.,4.),(1.,0.))),)),)),
                 replace(clip,samples=((1.,((1.,),)),)))
        for item in invalid:
            with self.assertRaises(MocapSourceValidationError):validate_mocap_clip(item)
