"""Build and verify a replacement rig before transferring any original data."""
from dataclasses import dataclass, replace
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory, TemporaryFile

from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.body_skeleton import plan_body_non_deform_markers
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
    authored_geometry: tuple | None = None


def _rebuild_axial_description(
    registration: CharacterRegistration,
) -> BodyAxialDescription | None:
    if not isinstance(registration.spine, BodySplinePlan):
        return None
    def leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    by_path = {joint.path: joint for joint in registration.body}
    heads = [joint for joint in registration.body
             if leaf(joint.path) == "Head_M"]
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
        neck.append(leaf(joint.path))
        # A rebuilt Body can place Fit Part joints between the registered
        # neck/head joints. Follow the physical DAG until the next Body joint.
        parent = joint.parent
        while parent is not None and parent not in by_path:
            parent = parent.rsplit("|", 1)[0] or None
        if parent is None:
            raise CharacterRegistryError("重建颈头链没有连接到胸部")
        joint = by_path[parent]
    return BodyAxialDescription(
        spine=tuple(leaf(path)
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
    return frames


_TRANSFER_SAMPLE_BATCH_SIZE = 8


def _rebuild_segment_mode(host, body_root: str) -> str:
    capture = getattr(host, 'capture_body_rebuild_segment_mode', None)
    return capture(body_root) if capture is not None else 'fit_part'


def _write_transfer_samples(host, staged, frames, stream, *, target):
    """Spool animation and mesh samples without retaining every frame in RAM."""
    for offset in range(0, len(frames), _TRANSFER_SAMPLE_BATCH_SIZE):
        batch = frames[offset:offset + _TRANSFER_SAMPLE_BATCH_SIZE]
        pickle.dump(host.sample_character_transfer(staged, batch,
                    target=target), stream, protocol=pickle.HIGHEST_PROTOCOL)
    stream.flush()
    stream.seek(0)


def _compare_transfer_samples(host, staged, frames, stream, *, target):
    stream.seek(0)
    greatest = 0.0
    for offset in range(0, len(frames), _TRANSFER_SAMPLE_BATCH_SIZE):
        batch = frames[offset:offset + _TRANSFER_SAMPLE_BATCH_SIZE]
        before = pickle.load(stream)
        after = host.sample_character_transfer(staged, batch,
                                               target=target)
        greatest = max(greatest, character_transfer_error(before, after))
    return greatest


class StageBodyCharacterRebuild:
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=()):
        host=self._host
        host.preflight_character_rebuild_namespace(namespace)
        original=CaptureBodyCharacterPreservation(host).execute(extensions=extensions)
        authored_geometry = host.capture_body_geometry_contents()
        # Older Python builds retained MEL's temporary Foot pivot markers in
        # the registered Body. Preserve that saved topology during a rebuild;
        # new characters remove those joints before Skin and registration.
        retained_markers = plan_body_non_deform_markers(
            host.capture_body_skeleton(original.registration.body_root),
            require_leaf=False)
        selection_mode = host.capture_body_rebuild_selection_mode()
        generic_fk_policy = host.capture_body_generic_fk_feature_policy(
            original.registration)
        segment_mode = _rebuild_segment_mode(host,
            original.registration.body_root)
        include_dynamic = host.has_body_dynamic_system()
        with TemporaryDirectory(prefix='adv-py-rebuild-') as directory:
            fit=Path(directory)/'source.fit.json'
            ExportFitSkeleton(host).apply(fit,original.registration.container)
            with host.character_rebuild_transaction('Stage replacement character'):
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('重建暂存前原角色发生变化')
                if (host.capture_body_rebuild_selection_mode() != selection_mode
                        or _rebuild_segment_mode(host,
                            original.registration.body_root) != segment_mode
                        or host.has_body_dynamic_system() != include_dynamic
                        or host.capture_body_geometry_contents() != authored_geometry):
                    raise RuntimeError('重建暂存前原角色系统层级、分段或选择集发生变化')
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
                    use_fit_part_hierarchy=segment_mode == 'fit_part',
                    _include_dynamic=include_dynamic,
                    _retain_non_deform_markers=bool(retained_markers),
                    _generic_fk_policy=generic_fk_policy,
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
                if host.capture_body_geometry_contents() != authored_geometry:
                    raise RuntimeError('暂存构建改写了 Geometry 模型层级')
                stage_geometry_roots = {
                    row[0] for row in stage.capture_body_geometry_contents()}
                # A feature generated in both rigs belongs to the replacement;
                # only old-only Geometry children are handed across intact.
                preserved_geometry = tuple(
                    row for row in authored_geometry
                    if row[0] not in stage_geometry_roots)
                properties=host.plan_character_property_transfer(original,namespace)
                staged=StagedCharacterRebuild(original,namespace,registration,
                                              properties,
                                              authored_geometry=preserved_geometry)
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
        geometry_roots = {row[0] for row in staged.authored_geometry or ()}
        if host.capture_body_geometry_contents(geometry_roots) != staged.authored_geometry:
            raise CharacterRegistryError('Geometry 模型层级在暂存后发生变化')
        host.preflight_character_transfer(staged)
        if staged.ownership is not None and host.audit_character_rebuild_ownership(staged)!=staged.ownership:
            raise CharacterRegistryError('暂存后的 Rig 归属或连接已变化，请重新暂存')
        frames=_transfer_sample_frames(original)
        with TemporaryFile(mode='w+b') as baseline:
            _write_transfer_samples(host,staged,frames,baseline,target=False)
            with host.character_rebuild_transaction('Transfer preserved data to replacement rig'):
                host.transfer_character_data(staged)
                host.verify_character_retained_data(staged)
                if host.capture_body_geometry_contents(geometry_roots) != staged.authored_geometry:
                    raise RuntimeError('交接改变了 Geometry 模型层级')
                error=_compare_transfer_samples(host,staged,frames,baseline,
                                                target=True)
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
            with TemporaryFile(mode='w+b') as baseline:
                _write_transfer_samples(host,staged,frames,baseline,target=True)
                promoted=host.promote_character_rebuild(staged)
                geometry_roots = {row[0] for row in staged.authored_geometry or ()}
                if host.capture_body_geometry_contents(geometry_roots) != staged.authored_geometry:
                    raise RuntimeError('重建后 Geometry 模型层级身份或姿态变化')
                if _compare_transfer_samples(host,promoted,frames,baseline,
                                             target=True)>1e-4:
                    raise RuntimeError('原位替换改变身体、蒙皮或用户数据')
        return promoted
