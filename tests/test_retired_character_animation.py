"""Export preparation cannot invalidate unchanged animator control clips."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from adv_py.core.character_body_retirement import CharacterRetiredBodyJoint,retire_body_correspondence
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_pose import validate_character_pose,normalize_character_pose_compatibility
from adv_py.core.character_animation import CharacterAnimation,validate_character_animation
from adv_py.application.character_animation import ApplyBodyCharacterAnimation
from adv_py.application.character_pose import ApplyBodyCharacterPose
from test_character_registry import registration_fixture
from test_character_pose import pose_fixture


class RetiredAnimationTests(unittest.TestCase):
    def fixture(self):
        before=registration_fixture()
        tip=before.body[-1]
        identity=next(row.uuid for row in before.nodes if row.path==tip.path)
        retired=CharacterRetiredBodyJoint(tip.path,identity,tip.parent,tip.matrix,0,len(before.body)-1)
        after=retire_body_correspondence(before,(retired,),
            tuple(row for row in before.nodes if row.path!=tip.path),before.channels)
        return before,after,pose_fixture(before)

    def test_old_clip_controls_and_timing_survive_native_tip_deletion(self):
        before,after,pose=self.fixture()
        validate_character_pose(pose,after)
        normalized=normalize_character_pose_compatibility(pose,after)
        self.assertEqual(normalized.channels,pose.channels)
        self.assertEqual(normalized.spaces,pose.spaces)
        self.assertEqual(normalized.space_frames,pose.space_frames)
        self.assertEqual(normalized.body_frames,pose.body_frames[:-1])
        clip=CharacterAnimation('film',((1.,pose),(3.5,pose)))
        validate_character_animation(clip,after)
        host=SimpleNamespace(read_character_registration=lambda:after,
            preflight_character_keyframe=lambda reg:None,
            capture_character_key_state=lambda reg:(),
            capture_character_pose=lambda reg:pose_fixture(reg),
            character_time_unit=lambda:'film')
        plan=ApplyBodyCharacterAnimation(host).plan(clip)
        self.assertEqual(tuple(frame for frame,_ in plan.animation.samples),(1.,3.5))
        self.assertTrue(all(current.channels==pose.channels for _,current in plan.animation.samples))
        self.assertTrue(all(current.body_frames==normalized.body_frames for _,current in plan.animation.samples))

    def test_live_body_references_cannot_be_removed_reordered_or_replaced(self):
        _,after,pose=self.fixture()
        invalid=(replace(pose,body_frames=pose.body_frames[1:]),
                 replace(pose,body_frames=tuple(reversed(pose.body_frames))),
                 replace(pose,body_frames=pose.body_frames[:-1]+(('UnrecordedEnd',pose.body_frames[-1][1]),)))
        for value in invalid:
            with self.subTest(pose=value),self.assertRaises(CharacterRegistryError):
                normalize_character_pose_compatibility(value,after)

    def test_pose_application_uses_live_reference_validation_and_unchanged_controls(self):
        _,after,pose=self.fixture()
        host=SimpleNamespace(read_character_registration=lambda:after,
            preflight_character_pose=lambda reg:None,
            capture_character_pose=lambda reg:pose_fixture(reg))
        plan=ApplyBodyCharacterPose(host).plan(pose)
        self.assertEqual(plan.target.channels,pose.channels)
        self.assertEqual(plan.target.body_frames,plan.before.body_frames)


if __name__=='__main__':unittest.main()
