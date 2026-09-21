"""Explicit shape-matching extension for previously registered limb animation."""
from dataclasses import dataclass
from adv_py.core.character_registry import CharacterRegistration, encode_registration, CharacterRegistryError
from adv_py.core.body_control_spaces import control_space_pose_error


@dataclass(frozen=True)
class StretchMatchingPlan:
    before: CharacterRegistration
    after: CharacterRegistration


class EnableBodyCharacterStretchMatching:
    def __init__(self,host):self._host=host

    def plan(self):
        # The adapter supplies all Maya graph inspection; no Maya import here.
        before=self._host.read_character_registration()
        if not any('.ikOrientation.' in ch.key for ch in before.channels):
            raise CharacterRegistryError('先启用四肢动画登记')
        self._host.preflight_character_keyframe(before)
        after=self._host.describe_character_stretch_matching(before)
        encode_registration(after)
        return StretchMatchingPlan(before,after)

    def apply(self):
        plan=self.plan()
        if plan.before==plan.after:return plan.after
        with self._host.transaction('Enable limb stretch matching'):
            if self.plan()!=plan:raise RuntimeError('拉伸匹配提交前场景变化')
            world=self._host.capture_character_stretch_world(plan.before)
            control_space_pose_error(world,world)
            self._host.install_character_stretch_matching(plan.before,plan.after)
            if self._host.read_character_registration()!=plan.after:
                raise RuntimeError('拉伸匹配登记读回不一致')
            if control_space_pose_error(world,self._host.capture_character_stretch_world(plan.after))>1e-4:
                raise RuntimeError('拉伸匹配安装改变了机制或辅助骨骼的世界姿态')
        return plan.after
