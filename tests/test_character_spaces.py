from dataclasses import replace
import json
import unittest
from adv_py.core.character_spaces import validate_space_values, space_channels, character_channel_tangent
from adv_py.core.character_animation import CharacterAnimation, encode_character_animation, decode_character_animation
from adv_py.core.character_registry import CharacterRegistryError
from test_character_registry import registration_fixture
from test_character_pose import pose_fixture


class CharacterSpaceTests(unittest.TestCase):
    def test_dynamic_clip_roundtrip_and_mode_consistency(self):
        reg=registration_fixture();pose=pose_fixture(reg)
        def mode_pose(mode):
            return replace(pose, spaces=tuple((k,mode) for k,_ in pose.spaces),
                channels=pose.channels+tuple((f'space.{k}.mode',0. if mode=='body' else 1.) for k,_ in pose.spaces))
        clip=CharacterAnimation('film',((1.,mode_pose('body')),(10.,mode_pose('global'))))
        text=encode_character_animation(clip)
        self.assertEqual(json.loads(text)['version'],2)
        self.assertEqual(decode_character_animation(text),clip)
        # Explicitly force mismatching modes regardless of fixture defaults.
        bad_pose=replace(mode_pose('global'),spaces=tuple((k,'body') for k,_ in pose.spaces))
        with self.assertRaises(CharacterRegistryError):encode_character_animation(replace(clip,samples=((1.,bad_pose),)))

    def test_discrete_values_and_semantic_tangents(self):
        for values in ((('space.head.mode',.5),),(('space.head.mode',1.),)):
            with self.assertRaises(CharacterRegistryError):validate_space_values(values,(('head','body'),('hand_R','global')))
        self.assertEqual(character_channel_tangent('space.hand_R.0.body.rotateX'),'step')
        self.assertEqual(character_channel_tangent('global.rotateX'),'linear')
        reg=registration_fixture()
        for spec in reg.spaces.spaces:
            channels=space_channels(spec)
            self.assertEqual(len(channels),1+len(spec.targets)*2*len(spec.attributes))
            self.assertEqual(len({ch.key for ch in channels}),len(channels))
