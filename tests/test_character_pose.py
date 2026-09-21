import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adv_py.core.character_pose import *
from adv_py.core.character_registry import CharacterRegistryError,digest
from adv_py.application.character_pose import save_character_pose,load_character_pose
from test_character_registry import registration_fixture


def pose_fixture(registration):
    matrix=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
    return CharacterPose(registration.compatibility_digest,tuple((c.key,0.) for c in registration.channels),
        tuple((s.key,s.initial_mode) for s in registration.spaces.spaces),
        tuple((s.key+'.'+str(i),matrix) for s in registration.spaces.spaces for i,_ in enumerate(s.targets)),
        tuple((j.path.rsplit('|',1)[-1],matrix) for j in registration.body))


class CharacterPoseTests(unittest.TestCase):
    def setUp(self):
        self.registry=registration_fixture();self.pose=pose_fixture(self.registry)

    def test_roundtrip_has_no_scene_paths(self):
        text=encode_character_pose(self.pose)
        self.assertNotIn('|',text)
        self.assertEqual(decode_character_pose(text),self.pose)
        validate_character_pose(self.pose,self.registry)
        self.assertEqual(character_pose_error(self.pose,self.pose),0)

    def test_invalid_documents_and_full_contract(self):
        for mutation in ({'version':True},{'version':2},{'digest':'bad'},{'unknown':0}):
            raw=json.loads(encode_character_pose(self.pose));raw.update(mutation)
            with self.assertRaises(CharacterRegistryError): decode_character_pose(json.dumps(raw))
        for pose in (replace(self.pose,compatibility='0'*64),replace(self.pose,channels=()),
                     replace(self.pose,spaces=self.pose.spaces[:-1]),replace(self.pose,body_frames=self.pose.body_frames[:-1]),
                     replace(self.pose,channels=((self.pose.channels[0][0],float('nan')),))):
            with self.assertRaises((CharacterRegistryError,ValueError)): validate_character_pose(pose,self.registry)
        limited=replace(self.registry,channels=(replace(self.registry.channels[0],minimum=0,maximum=1),))
        excessive=replace(pose_fixture(limited),channels=((limited.channels[0].key,2.),))
        with self.assertRaises(CharacterRegistryError): validate_character_pose(excessive,limited)
        raw=json.loads(encode_character_pose(self.pose));raw['payload']['channels']*=2;raw['digest']=digest(raw['payload'])
        with self.assertRaises(CharacterRegistryError): decode_character_pose(json.dumps(raw))

    def test_atomic_file_no_overwrite_or_leftover_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'完整姿态.json'
            save_character_pose(self.pose,target)
            self.assertEqual(load_character_pose(target),self.pose)
            old=target.read_bytes()
            with self.assertRaises(FileExistsError): save_character_pose(self.pose,target)
            self.assertEqual(target.read_bytes(),old)
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])

    def test_publication_race_preserves_other_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'pose.json'
            def race(source,destination):
                Path(destination).write_text('other writer',encoding='utf-8')
                raise FileExistsError(destination)
            with patch('adv_py.application.character_pose.os.link',side_effect=race):
                with self.assertRaises(FileExistsError): save_character_pose(self.pose,target)
            self.assertEqual(target.read_text(encoding='utf-8'),'other writer')
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])
