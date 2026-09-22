"""Transfer a registered variable-spine character take to another topology."""
from contextlib import nullcontext
from math import isfinite
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.mocap_mapping import MocapJointMapping
from adv_py.core.mocap_preset import MocapMappingPreset

from .mocap_control_retarget import character_sample_frames
from .mocap_variable_retarget import RetargetMocapVariableFullFkToCharacter


class RetargetCharacterSpineFk:
    """Sample a source character and write editable FK curves on a target."""

    def __init__(self, host):
        self._host = host

    def apply(self, source_namespace, *, start_frame, end_frame, sample_by=1,
              reference_frame=None, fk_substeps=1):
        return self._apply(source_namespace, start_frame=start_frame,
            end_frame=end_frame, sample_by=sample_by,
            reference_frame=reference_frame, fk_substeps=fk_substeps,
            own_transaction=True)

    def apply_in_transaction(self, source_namespace, *, start_frame, end_frame,
                             sample_by=1, reference_frame=None, fk_substeps=1):
        """Write inside the caller's transaction for combined animation/Skin edits."""
        return self._apply(source_namespace, start_frame=start_frame,
            end_frame=end_frame, sample_by=sample_by,
            reference_frame=reference_frame, fk_substeps=fk_substeps,
            own_transaction=False)

    def _apply(self, source_namespace, *, start_frame, end_frame, sample_by,
               reference_frame, fk_substeps, own_transaction):
        frames = character_sample_frames(start_frame, end_frame, sample_by,
                                         substeps=fk_substeps)
        if (reference_frame is not None and
                (isinstance(reference_frame, bool) or
                 not isinstance(reference_frame, (int, float)) or
                 not isfinite(reference_frame))):
            raise CharacterRegistryError('脊柱迁移校准帧须为有限数值')
        reference = frames[0] if reference_frame is None else float(reference_frame)
        if reference < frames[0] or reference > frames[-1]:
            raise CharacterRegistryError('脊柱迁移校准帧必须位于写入区间')
        target = self._host.read_character_registration()
        if not isinstance(target.spine, BodySplinePlan):
            raise CharacterRegistryError('脊柱迁移目标必须是已登记的可变脊柱角色')
        source, samples = self._host.capture_resampled_character_source(
            source_namespace, target, tuple(sorted(set((*frames, reference)))))
        short = lambda path: path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        if not isinstance(source.spine, BodySplinePlan):
            raise CharacterRegistryError('脊柱迁移来源必须是已登记的可变脊柱角色')
        if len(source.spine.body_joints) == len(target.spine.body_joints):
            raise CharacterRegistryError('此入口要求来源与目标脊柱段数不同')
        boundary = (self._host.transaction('Retarget character across spine counts')
                    if own_transaction else nullcontext())
        with boundary:
            # Mocap writers apply source deltas to the target pose at each
            # sampled frame. A prebuilt replacement may already be animated;
            # establish one calibration pose first so those deltas are not
            # added to its old motion.
            self._host.prepare_resampled_character_target(target, frames, reference)
            bridge_root = self._host.create_resampled_character_source(target, samples)
            body_names = {short(joint.path) for joint in target.body}
            required = {short(target.body_root),
                        *(short(path) for path in target.spine.body_joints[1:]),
                        'Neck_M', 'Head_M', 'Scapula_R', 'Scapula_L'}
            required.update(part + '_' + side for side in ('R', 'L')
                            for part in ('Shoulder', 'Elbow', 'Wrist',
                                         'Hip', 'Knee', 'Ankle', 'Toes'))
            if any(name.startswith('Thumb1_') for name in body_names):
                required.update(f'{digit}{segment}_{side}' for side in ('R', 'L')
                                for digit in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
                                for segment in (1, 2, 3))
            if not required.issubset(body_names):
                raise CharacterRegistryError('目标角色缺少完整 FK Body 关节')
            names = tuple(sorted(required))
            preset = MocapMappingPreset('Resampled character spine FK',
                tuple(MocapJointMapping(name, name, name == short(target.body_root), True)
                      for name in names), len(target.body))
            service = RetargetMocapVariableFullFkToCharacter(self._host)
            options = dict(start_frame=start_frame, end_frame=end_frame,
                           sample_by=sample_by, reference_frame=reference,
                           substeps=fk_substeps)
            plan = service.plan_with_preset(bridge_root, preset, **options)
            root_samples = self._host.write_mocap_root_control_keys(plan.root)
            group_samples = tuple(self._host.write_mocap_fk_group_keys(group)
                                  for group in plan.groups)
            if any(tuple(sample.frame for sample in group) != frames
                   for group in (root_samples, *group_samples)):
                raise RuntimeError('跨段数 FK 动画采样不完整')
            self._host.match_resampled_character_fk_positions(target, samples, frames)
            self._host.delete_resampled_character_source(bridge_root)
        return root_samples, group_samples
