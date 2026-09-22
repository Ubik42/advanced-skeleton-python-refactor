import json
from hashlib import sha256
from dataclasses import replace
import unittest

from adv_py.core import (MocapClip,MocapClipJoint,MocapClipChannel,
                         encode_mocap_clip,decode_mocap_clip,validate_mocap_clip)
from adv_py.core.mocap_clip import mocap_verification_times
from adv_py.core.mocap_source import MocapSourceValidationError


IDENTITY=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)


class MocapClipTests(unittest.TestCase):
    def test_long_clip_samples_both_ends_and_intervals(self):
        keyed=tuple(float(frame) for frame in range(1,1202))
        selected=mocap_verification_times(keyed)
        self.assertEqual(len(selected),2000)
        self.assertEqual((selected[0],selected[-1]),(1.,1201.))
        self.assertTrue(any(time!=int(time) for time in selected))
        self.assertEqual(selected,tuple(sorted(set(selected))))
        self.assertEqual(mocap_verification_times((1.,5.,10.)),(1.,3.,5.,7.5,10.))
        self.assertEqual(mocap_verification_times((1.,5.,10.),include_exterior=True),
                         (-1.,1.,3.,5.,7.5,10.,12.5))
        exterior=mocap_verification_times(keyed,include_exterior=True)
        self.assertEqual(len(exterior),2000)
        self.assertEqual((exterior[0],exterior[-1]),(.5,1201.5))
        self.assertIn(1.,exterior)
        self.assertIn(1201.,exterior)

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

    def test_tangent_round_trip_and_rejects_malformed_arrays(self):
        clip=self.fixture()
        channel=replace(clip.joints[0].channels[0],
            in_tangents=('fixed','linear'),out_tangents=('linear','fixed'),
            in_angles=(0.,1.),out_angles=(1.,0.),
            in_weights=(1.,1.),out_weights=(1.,1.),weighted=True,post_infinity=3,
            tangent_locks=(True,False),weight_locks=(False,True),
            breakdown_times=(5.,))
        clip=replace(clip,joints=(replace(clip.joints[0],channels=(channel,)),))
        self.assertEqual(decode_mocap_clip(encode_mocap_clip(clip)),clip)
        with self.assertRaisesRegex(MocapSourceValidationError,'切线数量'):
            validate_mocap_clip(replace(clip,joints=(replace(clip.joints[0],
                channels=(replace(channel,out_angles=(0.,)),)),)))
        malformed=json.loads(encode_mocap_clip(clip))
        malformed['joints'][0]['channels'][0]['in_angles']=None
        with self.assertRaisesRegex(MocapSourceValidationError,'切线结构'):
            decode_mocap_clip(json.dumps(malformed))
        with self.assertRaisesRegex(MocapSourceValidationError,'切线数量'):
            validate_mocap_clip(replace(clip,joints=(replace(clip.joints[0],
                channels=(replace(channel,tangent_locks=(True,)),)),)))
        with self.assertRaisesRegex(MocapSourceValidationError,'切线或循环设置'):
            validate_mocap_clip(replace(clip,joints=(replace(clip.joints[0],
                channels=(replace(channel,breakdown_times=(3.,)),)),)))

    def test_schema_one_clip_remains_readable(self):
        clip=self.fixture()
        raw=json.loads(encode_mocap_clip(clip))
        raw['schema_version']=1
        for channel in raw['joints'][0]['channels']:
            for field in ('tangent_locks','weight_locks','breakdown_times'):
                del channel[field]
        payload={key:value for key,value in raw.items() if key!='content_sha256'}
        raw['content_sha256']=sha256(json.dumps(payload,ensure_ascii=False,
            sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()
        self.assertEqual(decode_mocap_clip(json.dumps(raw)),clip)
