"""Build and verify a replacement rig before transferring any original data."""
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import (
    CharacterRegistration, CharacterRegistryError,
)
from adv_py.core.character_preservation import (
    CharacterPreservation, RebuildOwnership, character_transfer_error,
)
from .character_preservation import CaptureBodyCharacterPreservation
from .fit_skeleton_io import ExportFitSkeleton,CreateAndImportFitSkeleton
from .registered_body_build import BuildRegisteredBodyCharacter
from .body_selection_sets import finalize_body_character_sets
from .character_limb_animation import EnableBodyCharacterLimbAnimation
from .character_stretch_matching import EnableBodyCharacterStretchMatching
from .character_spaces import EnableBodyCharacterSpaceAnimation


@dataclass(frozen=True)
class StagedCharacterRebuild:
    original: CharacterPreservation
    namespace: str
    registration: CharacterRegistration
    custom_properties: tuple = ()
    ownership: RebuildOwnership | None = None


def _rebuild_axial_description(
    registration: CharacterRegistration,
) -> BodyAxialDescription | None:
    if not isinstance(registration.spine, BodySplinePlan):
        return None
    by_path = {joint.path: joint for joint in registration.body}
    heads = [joint for joint in registration.body
             if joint.path.rsplit("|", 1)[-1] == "Head_M"]
    if len(heads) != 1:
        raise CharacterRegistryError(
            "可变身体重建需要明确的 Head_M 颈头终点")
    neck = []
    joint = heads[0]
    chest = registration.spine.body_joints[-1]
    visited = set()
    while joint.path != chest:
        if joint.path in visited:
            raise CharacterRegistryError("重建颈头链存在父级循环")
        visited.add(joint.path)
        neck.append(joint.path.rsplit("|", 1)[-1])
        if joint.parent not in by_path:
            raise CharacterRegistryError("重建颈头链没有连接到胸部")
        joint = by_path[joint.parent]
    return BodyAxialDescription(
        spine=tuple(path.rsplit("|", 1)[-1]
                    for path in registration.spine.body_joints),
        neck=tuple(reversed(neck)),
    )


def _transfer_sample_frames(
    original: CharacterPreservation,
) -> tuple[float, ...]:
    keys = sorted({original.current_time,
                   *(time for curve in original.curves for time in curve.times)})
    frames = tuple(sorted({*keys, *((a + b) / 2
                                    for a, b in zip(keys, keys[1:]))}))
    if len(frames) > 2000:
        raise CharacterRegistryError(
            "交接复检采样最多 2000 帧，需要分段验证策略")
    return frames


class StageBodyCharacterRebuild:
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=()):
        host=self._host
        host.preflight_character_rebuild_namespace(namespace)
        original=CaptureBodyCharacterPreservation(host).execute(extensions=extensions)
        selection_mode = host.capture_body_rebuild_selection_mode()
        include_dynamic = host.has_body_dynamic_system()
        with TemporaryDirectory(prefix='adv-py-rebuild-') as directory:
            fit=Path(directory)/'source.fit.json'
            ExportFitSkeleton(host).apply(fit,original.registration.container)
            with host.character_rebuild_transaction('Stage replacement character'):
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('重建暂存前原角色发生变化')
                if (host.capture_body_rebuild_selection_mode() != selection_mode
                        or host.has_body_dynamic_system() != include_dynamic):
                    raise RuntimeError('重建暂存前原角色系统层级或选择集发生变化')
                stage=host.create_character_rebuild_host(namespace)
                CreateAndImportFitSkeleton(stage).apply(fit)
                scene_before = stage.capture_body_scene_nodes()
                keys={channel.key for channel in original.registration.channels}
                description = _rebuild_axial_description(
                    original.registration)
                # Rebuild the same Body/Part/control graph as a fresh
                # character. Selection sets wait until legacy channel
                # compatibility and animation registration are resolved.
                built = BuildRegisteredBodyCharacter(stage).apply(
                    'FitSkeleton',
                    axial_description=description,
                    include_head_aim='head.aim.headAim' in keys,
                    _include_dynamic=include_dynamic,
                    _defer_selection_sets=True,
                    _scene_before=scene_before)
                fit_path = '|Group|FitSkeleton'
                registration = built.registration
                if any('.ikOrientation.' in key for key in keys):registration=EnableBodyCharacterLimbAnimation(stage).apply()
                if any('.ikLengthWeight.' in key for key in keys):registration=EnableBodyCharacterStretchMatching(stage).apply()
                if any(key.startswith('space.') for key in keys):registration=EnableBodyCharacterSpaceAnimation(stage).apply()
                if any(key.startswith('spine.fkMatch.') for key in keys):
                    from .character_spline_animation import EnableBodyCharacterSplineAnimation
                    registration=EnableBodyCharacterSplineAnimation(stage).apply()
                if any(key.startswith('game.rootMotion.') for key in keys):
                    from .body_game_root_motion import SwitchGameRootMotion
                    SwitchGameRootMotion(stage).apply(create=True)
                    registration=stage.read_character_registration()
                host.match_character_rebuild_solver(stage,registration)
                registration=host.preserve_character_rebuild_binding(stage,original.registration,registration)
                if selection_mode != "none":
                    finalize_body_character_sets(
                        stage, registration, built.rig.plan,
                        segments=built.segment_influences,
                        extras=built.selection_extras,
                        scene_before=scene_before, fit_container=fit_path,
                        populate_all=selection_mode == "populated")
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('暂存构建改写了原角色，已回滚')
                properties=host.plan_character_property_transfer(original,namespace)
                staged=StagedCharacterRebuild(original,namespace,registration,properties)
                staged=replace(staged,ownership=host.audit_character_rebuild_ownership(staged))
        return staged


class TransferStagedBodyCharacterData:
    def __init__(self,host):self._host=host

    def apply(self,staged):
        host=self._host
        original=staged.original
        extensions=tuple(row.path for row in original.extensions)
        if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
            raise CharacterRegistryError('原角色与暂存时的保留数据不同，请重新暂存')
        host.preflight_character_transfer(staged)
        if staged.ownership is not None and host.audit_character_rebuild_ownership(staged)!=staged.ownership:
            raise CharacterRegistryError('暂存后的 Rig 归属或连接已变化，请重新暂存')
        frames=_transfer_sample_frames(original)
        before=host.sample_character_transfer(staged,frames)
        with host.character_rebuild_transaction('Transfer preserved data to replacement rig'):
            host.transfer_character_data(staged)
            host.verify_character_retained_data(staged)
            after=host.sample_character_transfer(staged,frames,target=True)
            error=character_transfer_error(before,after)
            if error>1e-4:
                raise RuntimeError('交接改变身体、控制空间、蒙皮或用户附件；最大误差：'+str(error))
        return staged


class RebuildBodyCharacter:
    """Same-layout replacement, including creation and cleanup in one Undo."""
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=()):
        host=self._host
        with host.transaction('Rebuild character preserving user data'):
            staged=StageBodyCharacterRebuild(host).apply(namespace,extensions=extensions)
            TransferStagedBodyCharacterData(host).apply(staged)
            frames=_transfer_sample_frames(staged.original)
            before=host.sample_character_transfer(staged,frames,target=True)
            promoted=host.promote_character_rebuild(staged)
            after=host.sample_character_transfer(promoted,frames,target=True)
            if character_transfer_error(before,after)>1e-4:
                raise RuntimeError('原位替换改变身体、蒙皮或用户数据')
        return promoted
