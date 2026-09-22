from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from adv_py.core.character_animation import *
from adv_py.core.character_registry import CharacterRegistryError, digest
from adv_py.application.character_animation import save_character_animation, load_character_animation, verify_character_animation_write
from test_character_registry import registration_fixture
from test_character_pose import pose_fixture


class CharacterAnimationTests(unittest.TestCase):
    def setUp(self):
        self.reg=registration_fixture();self.pose=pose_fixture(self.reg)
        self.clip=CharacterAnimation('film',((1.,self.pose),(11.,self.pose)))

    def test_portable_roundtrip_and_no_overwrite(self):
        validate_character_animation(self.clip,self.reg)
        text=encode_character_animation(self.clip)
        self.assertNotIn('|',text)
        self.assertEqual(decode_character_animation(text),self.clip)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'animation.json'
            save_character_animation(self.clip,path)
            self.assertEqual(load_character_animation(path),self.clip)
            with self.assertRaises(FileExistsError): save_character_animation(self.clip,path)
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_frame_range_is_bounded_and_exact(self):
        self.assertEqual(character_sample_frames(-1,5,2),(-1.,1.,3.,5.))
        self.assertEqual(character_sample_frames(1,3,1,substeps=4),
                         (1.,1.25,1.5,1.75,2.,2.25,2.5,2.75,3.))
        for substeps in (0,9,True,1.5):
            with self.subTest(substeps=substeps),self.assertRaises(CharacterRegistryError):
                character_sample_frames(1,3,substeps=substeps)
        with self.assertRaises(CharacterRegistryError):
            character_sample_frames(1,1001,substeps=2)
        for args in ((True,3,1),(0,3,2),(1,0,1),(1,3,0),(0,2000,1),(1.,3,1)):
            with self.subTest(args=args),self.assertRaises(CharacterRegistryError): character_sample_frames(*args)

    def test_invalid_timeline_and_inconsistent_pose_layout(self):
        for clip in (replace(self.clip,time_unit='0fps'),replace(self.clip,time_unit='unknown'),
                     replace(self.clip,samples=()),replace(self.clip,samples=((1.,self.pose),(1.,self.pose))),
                     replace(self.clip,samples=((float('nan'),self.pose),)),
                     replace(self.clip,samples=((1.,self.pose),(2.,replace(self.pose,compatibility='0'*64)))),
                     replace(self.clip,samples=((1.,self.pose),(2.,replace(self.pose,spaces=tuple((k,'global' if v=='body' else 'body') for k,v in self.pose.spaces)))))):
            with self.subTest(clip=clip),self.assertRaises(CharacterRegistryError): encode_character_animation(clip)

    def test_tampering_duplicate_keys_and_closed_schema(self):
        for mutation in ({'version':True},{'extra':0},{'digest':'0'*64}):
            raw=json.loads(encode_character_animation(self.clip));raw.update(mutation)
            with self.assertRaises(CharacterRegistryError): decode_character_animation(json.dumps(raw))
        raw=json.loads(encode_character_animation(self.clip));raw['payload']['samples'][1][0]=0
        raw['digest']=digest(raw['payload'])
        with self.assertRaises(CharacterRegistryError): decode_character_animation(json.dumps(raw))
        text=encode_character_animation(self.clip).replace('"version":1','"version":1,"version":1',1)
        with self.assertRaises(CharacterRegistryError): decode_character_animation(text)

    def test_readback_rejects_missing_channel_and_lost_outside_key(self):
        key=self.reg.channels[0].key
        original=(7.,((key,'curve.output',(0.,30.),(2.,3.)),))
        good=(7.,((key,'curve.output',(0.,1.,11.,30.),(2.,0.,0.,3.)),))
        host=SimpleNamespace(sample_character_animation=lambda reg,frames:self.clip.samples,
                             capture_character_key_state=lambda reg:good,
                             read_character_registration=lambda:self.reg)
        verify_character_animation_write(host,self.reg,self.clip,original)
        for bad in ((7.,()),(8.,good[1]),(7.,((key,'curve.output',(0.,1.,11.),(2.,0.,0.)),))):
            host.capture_character_key_state=lambda reg:bad
            with self.assertRaises(RuntimeError): verify_character_animation_write(host,self.reg,self.clip,original)

    def test_body_readback_is_checked_independently_of_key_values(self):
        key=self.reg.channels[0].key
        matrix=list(self.pose.body_frames[0][1]);matrix[12]=1
        bad=replace(self.pose,body_frames=((self.pose.body_frames[0][0],tuple(matrix)),)+self.pose.body_frames[1:])
        host=SimpleNamespace(sample_character_animation=lambda reg,frames:((1.,bad),(11.,self.pose)))
        with self.assertRaises(RuntimeError): verify_character_animation_write(host,self.reg,self.clip,(7.,()))
