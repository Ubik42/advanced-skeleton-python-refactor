"""Build and verify a replacement rig before transferring any original data."""
from dataclasses import dataclass, replace
from contextlib import nullcontext
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory, TemporaryFile

from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.body_skeleton import plan_body_non_deform_markers
from adv_py.core.character_registry import (
    CharacterRegistration, CharacterRegistryError, is_source_body_registration,
)
from adv_py.core.character_preservation import (
    CharacterPreservation, RebuildOwnership, character_transfer_error,
)
from .character_preservation import CaptureBodyCharacterPreservation
from .fit_skeleton_io import CreateAndImportFitSkeleton
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
    geometry_container_state: tuple | None = None
    geometry_container_drivers: tuple = ()
    geometry_container_conversions: tuple = ()
    geometry_container_outputs: tuple = ()
    geometry_output_conversions: tuple = ()
    deformer_input_conversions: tuple = ()
    deformer_output_conversions: tuple = ()
    deformer_sample_frames: tuple[float, ...] = ()
    deformer_animation_state: tuple = ()
    segment_influences: tuple[str, ...] = ()
    spline_change: object | None = None
    spline_alignment_systems: tuple[str, ...] = ()


def _rebuild_axial_description(
    registration: CharacterRegistration,
) -> BodyAxialDescription | None:
    if not isinstance(registration.spine, BodySplinePlan):
        return None
    def leaf(path: str) -> str:
        return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    # Optional export cleanup removes scene joints, not their authored Fit
    # correspondence. Recover the complete neck chain before building and
    # reapplying that same native deletion to the replacement.
    from adv_py.core.character_body_retirement import complete_body_bindings
    complete_body=complete_body_bindings(registration)
    by_path = {joint.path: joint for joint in complete_body}
    heads = [joint for joint in complete_body
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
    extra_frames: tuple[float, ...] = (),
) -> tuple[float, ...]:
    keys = sorted({original.current_time,
                   *original.mocap_sample_frames,
                   *original.quick_ik_sample_frames,
                   *(time for curve in original.curves for time in curve.times),
                   *extra_frames})
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


def _compare_transfer_samples(host, staged, frames, stream, *, target,
                              exclude_unattached_face=False):
    stream.seek(0)
    greatest = 0.0
    face_meshes = frozenset(
        uuid for skin in staged.original.skins
        if any(source == 'FaceJoint_M' or '|FaceJoint_M' in source
               for _, source, _, _ in skin.influences)
        for _, uuid, _ in skin.meshes) if exclude_unattached_face else frozenset()
    def staged_body_samples(samples):
        if not face_meshes:
            return samples
        return tuple((frame, body, spaces,
            tuple((uuid, points) for uuid, points in meshes
                  if uuid not in face_meshes), attachments)
            for frame, body, spaces, meshes, attachments in samples)
    for offset in range(0, len(frames), _TRANSFER_SAMPLE_BATCH_SIZE):
        batch = frames[offset:offset + _TRANSFER_SAMPLE_BATCH_SIZE]
        before = staged_body_samples(pickle.load(stream))
        after = staged_body_samples(host.sample_character_transfer(
            staged, batch, target=target))
        greatest = max(greatest, character_transfer_error(before, after))
    return greatest


def _transfer_sample_differences(host, staged, frames, stream):
    """Name the largest remaining full-character errors after promotion."""
    from adv_py.core.body_control_spaces import control_space_pose_error
    stream.seek(0)
    rows=[]
    for offset in range(0,len(frames),_TRANSFER_SAMPLE_BATCH_SIZE):
        before=pickle.load(stream)
        after=host.sample_character_transfer(
            staged,frames[offset:offset+_TRANSFER_SAMPLE_BATCH_SIZE],target=True)
        for left,right in zip(before,after):
            frame=left[0]
            for label,index in (('body',1),('spaces',2)):
                if left[index] or right[index]:
                    rows.append((control_space_pose_error(
                        tuple(left[index]),tuple(right[index])),frame,label))
            for label,index in (('mesh',3),('attachment',4)):
                for (key,a),(_,b) in zip(left[index],right[index]):
                    if len(a)==len(b):
                        delta=max((range(len(a))),
                                  key=lambda i:abs(a[i]-b[i]),default=None)
                        if delta is not None:
                            rows.append((abs(a[delta]-b[delta]),frame,
                                         label+':'+key,delta,a[delta],b[delta]))
    return tuple(sorted(rows,reverse=True)[:12])


class StageBodyCharacterRebuild:
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=(),spline_counts=(),spline_alignment_systems=()):
        host=self._host
        host.preflight_character_rebuild_namespace(namespace)
        original=CaptureBodyCharacterPreservation(host).execute(extensions=extensions)
        authored_geometry = host.capture_body_geometry_contents()
        geometry_container_state = host.capture_body_geometry_container_state()
        geometry_container_drivers = host.capture_body_geometry_container_drivers()
        geometry_container_conversions = host.capture_body_geometry_container_conversions()
        geometry_container_outputs = host.capture_body_geometry_container_outputs()
        geometry_output_conversions = host.capture_body_geometry_output_conversions()
        deformer_input_conversions = host.capture_character_deformer_conversions(
            original.deformers)
        deformer_output_conversions = host.capture_character_deformer_output_conversions(
            original.deformers)
        deformer_animation_state = host.capture_character_deformer_animation_state(
            original.deformers,original.skins)
        deformer_sample_frames = tuple(sorted({time
            for row in deformer_animation_state for time in row.times}))
        # Older Python builds retained MEL's temporary Foot pivot markers in
        # the registered Body. Preserve that saved topology during a rebuild;
        # new characters remove those joints before Skin and registration.
        retained_markers = plan_body_non_deform_markers(
            host.capture_body_skeleton(original.registration.body_root),
            require_leaf=False)
        selection_mode = host.capture_body_rebuild_selection_mode()
        selection_members=host.capture_body_rebuild_selection_members()
        generic_fk_policy = host.capture_body_generic_fk_feature_policy(
            original.registration)
        explicit_alignment_upgrade = bool(spline_alignment_systems)
        if spline_alignment_systems:
            from adv_py.core.source_spline_alignment_upgrade import (
                source_spline_alignment_upgrade_systems, upgrade_source_spline_alignment_layouts)
            spline_alignment_systems = source_spline_alignment_upgrade_systems(
                original.registration, spline_alignment_systems)
            if spline_counts:
                raise CharacterRegistryError('AlignIKTo 参考节点升级与控制数量修改需要分别执行')
            generic_fk_policy = replace(generic_fk_policy,
                source_spline_layouts=upgrade_source_spline_alignment_layouts(
                    generic_fk_policy.source_spline_layouts, spline_alignment_systems))
        if (is_source_body_registration(original.registration) and not spline_counts
                and not explicit_alignment_upgrade):
            from adv_py.adapters.maya_spline_control_rebuild import authored_fit_count_changes
            spline_counts=authored_fit_count_changes(host,original.registration)
        if spline_counts:
            from adv_py.core.spline_control_rebuild import splines,control_count
            available={plan.system_name:control_count(plan) for plan in splines(original.registration)}
            requested=dict(spline_counts)
            if (len(requested)!=len(spline_counts) or requested.keys()-available
                    or any(type(count) is not int or count<2 for count in requested.values())):
                raise CharacterRegistryError('请指定现有 Spline 系统及至少 2 的控制数量')
            spline_counts=tuple((system,count) for system,count in spline_counts
                                if count!=available[system])
            generic_fk_policy=replace(generic_fk_policy,source_spline_counts=spline_counts)
        segment_mode = _rebuild_segment_mode(host,
            original.registration.body_root)
        include_dynamic = host.has_body_dynamic_system()
        fit_channels=host.capture_character_rebuild_fit_channels(original.registration.container)
        fit_values=host.read_fit_skeleton_settings(original.registration.container)
        fit_curve=host.capture_control_curves((original.registration.container,),strict=True)[0]
        capture_terminal=getattr(host,'capture_source_fit_terminal_state',None)
        terminal_state=(capture_terminal(original.registration.container)
                        if capture_terminal is not None else None)
        capture_driving = getattr(host, 'capture_body_driving_rebuild', None)
        driving_state = capture_driving(original.registration) if capture_driving else None
        capture_orient = getattr(host, 'capture_body_control_orient_rebuild', None)
        orient_state = capture_orient(original.registration) if capture_orient else ()
        capture_game = getattr(host, 'capture_body_game_rebuild', None)
        game_state = capture_game(original.registration) if capture_game else None
        capture_matcher_blends=getattr(host,'capture_name_matcher_blend_rebuild',None)
        matcher_blends=capture_matcher_blends(original.registration) if capture_matcher_blends else ()
        with TemporaryDirectory(prefix='adv-py-rebuild-') as directory:
            fit=Path(directory)/'source.fit.json'
            # Built ADV keeps Fit beneath Group. Export its authored data
            # through the existing nested-Fit contract without detaching it.
            from .external_fit_export import ExportExternalFitSkeleton
            # Portable user exports reject scene paths/scripts. Internal
            # rebuilding retains the live original Fit and carries these
            # literal values separately; do not weaken that export contract.
            from adv_py.core.fit_skeleton_io import FIT_SKELETON_NONPORTABLE_SETTING_FIELDS
            class PortableRebuildFitHost:
                def __getattr__(self,name):return getattr(host,name)
                def read_fit_skeleton_settings(self,container):
                    settings=host.read_fit_skeleton_settings(container)
                    return replace(settings,settings=tuple(
                        replace(item,value='') if item.field in FIT_SKELETON_NONPORTABLE_SETTING_FIELDS
                        else item for item in settings.settings))
            ExportExternalFitSkeleton(PortableRebuildFitHost()).apply(fit,original.registration.container)
            with host.character_rebuild_transaction('Stage replacement character'):
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('重建暂存前原角色发生变化')
                if (host.capture_body_rebuild_selection_mode() != selection_mode
                        or _rebuild_segment_mode(host,
                            original.registration.body_root) != segment_mode
                        or host.has_body_dynamic_system() != include_dynamic
                        or host.capture_body_geometry_contents() != authored_geometry
                        or host.capture_body_geometry_container_state() != geometry_container_state
                        or host.capture_body_geometry_container_drivers() != geometry_container_drivers
                        or host.capture_body_geometry_container_conversions() != geometry_container_conversions
                        or host.capture_body_geometry_container_outputs() != geometry_container_outputs
                        or host.capture_body_geometry_output_conversions() != geometry_output_conversions
                        or host.capture_character_deformer_conversions(
                            original.deformers) != deformer_input_conversions
                        or host.capture_character_deformer_output_conversions(
                            original.deformers) != deformer_output_conversions
                        or host.capture_character_deformer_animation_state(
                            original.deformers,original.skins)
                            != deformer_animation_state):
                    raise RuntimeError('重建暂存前原角色系统层级、分段或选择集发生变化')
                if (capture_terminal is not None and
                        capture_terminal(original.registration.container)!=terminal_state):
                    raise CharacterRegistryError('重建暂存前非对称 previousParent 末端判定发生变化')
                if capture_matcher_blends and capture_matcher_blends(original.registration)!=matcher_blends:
                    raise CharacterRegistryError('重建暂存前 NameMatcher BlendShape 控制器状态变化')
                stage=host.create_character_rebuild_host(namespace)
                CreateAndImportFitSkeleton(stage).apply(fit)
                with stage.transaction('Restore original Fit channel state'):
                    stage.restore_character_rebuild_fit_channels(fit_channels)
                    if terminal_state is not None:
                        stage.install_source_fit_terminal_state(terminal_state)
                    for setting in fit_values.settings:
                        if setting.field in FIT_SKELETON_NONPORTABLE_SETTING_FIELDS:
                            stage.set_fit_skeleton_setting('FitSkeleton',setting)
                    current_curve=stage.capture_control_curves(('FitSkeleton',),strict=True)[0]
                    if (len(current_curve.shapes)!=len(fit_curve.shapes) or any(
                        (source.degree,source.form,len(source.points))!=
                        (target.degree,target.form,len(target.points))
                        for source,target in zip(fit_curve.shapes,current_curve.shapes))):
                        raise CharacterRegistryError('重建 Fit 容器曲线拓扑不一致')
                    for source,target in zip(fit_curve.shapes,current_curve.shapes):
                        stage.set_control_curve_points(target.path,source.points)
                scene_before = stage.capture_body_scene_nodes()
                keys={channel.key for channel in original.registration.channels}
                source_build = is_source_body_registration(original.registration)
                source_labels = (tuple(
                    (node.short_name.rsplit(":", 1)[-1], label.text)
                    for node in stage.capture_fit_hierarchy("FitSkeleton").joints
                    if (label := stage.read_joint_label(node.path)) is not None)
                    if source_build else None)
                description = (None if source_build else
                    _rebuild_axial_description(original.registration))
                # Rebuild the same Body/Part/control graph as a fresh
                # character. Selection sets wait until legacy channel
                # compatibility and animation registration are resolved.
                built = BuildRegisteredBodyCharacter(stage).apply(
                    'FitSkeleton',
                    axial_description=description,
                    _source_limb_labels=source_labels,
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
                host.match_character_rebuild_solver(stage,registration)
                driving_sets_created = False
                root_motion_saved = any(key.startswith('game.rootMotion.') for key in keys)
                if driving_state is not None or orient_state or game_state or root_motion_saved:
                    if selection_mode == 'none':
                        raise CharacterRegistryError('原版朝向、SDK 和 Game Engine 重建需要 ControlSet 和构建姿态')
                    # SDK construction uses the native source sets/pose. Create
                    # them now, then populate the complete AllSet after SDK
                    # restoration has added the final graph nodes.
                    registration = finalize_body_character_sets(stage, registration, built.rig.plan,
                        segments=built.segment_influences, extras=built.selection_extras,
                        scene_before=scene_before, fit_container=fit_path, populate_all=False)
                    driving_sets_created = True
                if game_state:
                    registration, rig = stage.restore_body_game_rebuild_root(
                        game_state, registration, built.rig)
                    built = replace(built, registration=registration, rig=rig)
                elif root_motion_saved:
                    from .body_game_root_motion import SwitchGameRootMotion
                    SwitchGameRootMotion(stage).apply(create=True)
                    registration=stage.read_character_registration()
                if orient_state:
                    with stage.transaction('Restore original controller orientations'):
                        registration, rig = stage.restore_body_control_orient_rebuild(
                            orient_state, registration, built.rig)
                    built = replace(built, registration=registration, rig=rig)
                if driving_state is not None:
                    with stage.transaction('Restore original Fit Driving Systems'):
                        registration, rig = stage.restore_body_driving_rebuild(
                            driving_state, registration, built.rig, fit=fit_path)
                    built = replace(built, registration=registration, rig=rig)
                if game_state:
                    registration, rig = stage.restore_body_game_rebuild_modes(
                        game_state, registration, built.rig)
                    built = replace(built, registration=registration, rig=rig)
                if matcher_blends:
                    with stage.transaction('Restore original NameMatcher BlendShape controls'):
                        registration=stage.restore_name_matcher_blend_rebuild(matcher_blends,registration)
                    built=replace(built,registration=registration)
                if original.registration.retired_body:
                    # Native export deletion happens after ADV has enrolled
                    # its constructed graph in AllSet. Deferring ownership
                    # until after deletion lets Maya also delete now-orphaned
                    # Spline scale utilities which the original rig retains.
                    if selection_mode != 'none':
                        registration = finalize_body_character_sets(
                            stage, registration, built.rig.plan,
                            segments=built.segment_influences,
                            extras=built.selection_extras,
                            scene_before=scene_before, fit_container=fit_path,
                            create_sets=not driving_sets_created,
                            populate_all=selection_mode == 'populated')
                        driving_sets_created = True
                        built = replace(built,registration=registration)
                    with stage.transaction('Restore original export end-joint deletion'):
                        registration = stage.restore_body_retirement_rebuild(
                            original.registration, preservation=original)
                    built = replace(built,registration=registration)
                spline_change=None
                if spline_counts:
                    from adv_py.core.spline_control_rebuild import plan_spline_control_rebuild
                    spline_change=plan_spline_control_rebuild(original.registration,registration,spline_counts)
                    registration=host.preserve_character_rebuild_binding(stage,original.registration,
                        registration,spline_change=spline_change)
                else:
                    registration=host.preserve_character_rebuild_binding(stage,original.registration,registration)
                if spline_alignment_systems:
                    from adv_py.core.source_spline_alignment_upgrade import audit_source_spline_alignment_upgrade
                    audit_source_spline_alignment_upgrade(original.registration, registration,
                                                         spline_alignment_systems)
                if selection_mode != "none":
                    registration = finalize_body_character_sets(
                        stage, registration, built.rig.plan,
                        segments=built.segment_influences,
                        extras=built.selection_extras,
                        scene_before=scene_before, fit_container=fit_path,
                        create_sets=not driving_sets_created,
                        populate_all=selection_mode == "populated")
                    if driving_state is not None:
                        with stage.transaction('Restore original SDK AllSet membership'):
                            stage.restore_body_driving_rebuild_membership(driving_state)
                    if spline_change is None or not spline_change.systems:
                        with stage.transaction('Preserve original selection membership'):
                            stage.restore_body_rebuild_selection_members(selection_members)
                if host.capture_body_rebuild_selection_members()!=selection_members:
                    raise RuntimeError('暂存构建改写了原角色选择集成员')
                if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
                    raise RuntimeError('暂存构建改写了原角色，已回滚')
                if host.capture_body_geometry_contents() != authored_geometry:
                    raise RuntimeError('暂存构建改写了 Geometry 模型层级')
                if host.capture_body_geometry_container_state() != geometry_container_state:
                    raise RuntimeError('暂存构建改写了 Geometry 容器状态')
                if host.capture_body_geometry_container_drivers() != geometry_container_drivers:
                    raise RuntimeError('暂存构建改写了 Geometry 驱动连接')
                if host.capture_body_geometry_container_conversions() != geometry_container_conversions:
                    raise RuntimeError('暂存构建改写了 Geometry 单位转换输入')
                if host.capture_body_geometry_container_outputs() != geometry_container_outputs:
                    raise RuntimeError('暂存构建改写了 Geometry 输出连接')
                if host.capture_body_geometry_output_conversions() != geometry_output_conversions:
                    raise RuntimeError('暂存构建改写了 Geometry 输出单位转换')
                if host.capture_character_deformer_conversions(
                        original.deformers) != deformer_input_conversions:
                    raise RuntimeError('暂存构建改写了生产变形器单位转换')
                if host.capture_character_deformer_output_conversions(
                        original.deformers) != deformer_output_conversions:
                    raise RuntimeError('暂存构建改写了生产变形器输出单位转换')
                if (host.capture_character_deformer_animation_state(
                        original.deformers,original.skins)
                        != deformer_animation_state):
                    raise RuntimeError('暂存构建改写了生产变形器动画曲线')
                host.apply_body_geometry_container_state(
                    namespace, geometry_container_state)
                stage_geometry = stage.capture_body_geometry_contents()
                stage_geometry_roots = {row[0] for row in stage_geometry}
                existing_roots = {row[0] for row in authored_geometry}
                overlapping_roots = existing_roots & stage_geometry_roots
                old_owned = (set(host.capture_body_all_set_members())
                             if selection_mode == 'populated' else set())
                if overlapping_roots - old_owned:
                    raise RuntimeError(
                        'Geometry 用户模型与新构建节点同名，不能静默覆盖：'
                        + repr(sorted(overlapping_roots - old_owned)))
                # A feature generated in both rigs belongs to the replacement;
                # only old-only Geometry children are handed across intact.
                preserved_direct = tuple(
                    row for row in authored_geometry
                    if row[0] not in stage_geometry_roots)
                old_members = {
                    root + suffix: kind
                    for root, identities, _, _ in authored_geometry
                    for suffix, _, kind in identities}
                stage_members = {
                    root + suffix
                    for root, identities, _, _ in stage_geometry
                    for suffix, _, _ in identities}
                old_owned.update(node.path for node in original.registration.nodes)
                ambiguous_descendants = {
                    path for path in set(old_members) & stage_members
                    if path not in old_owned and path not in overlapping_roots
                    and any(path.startswith(root + '|')
                            for root in overlapping_roots)}
                if ambiguous_descendants:
                    raise RuntimeError(
                        'Geometry 用户子节点与新构建同名，不能静默覆盖：'
                        + repr(sorted(ambiguous_descendants)))
                old_only = {
                    path for path in old_members
                    if path not in stage_members and path not in old_owned
                    and any(path.startswith(root + '|')
                            for root in overlapping_roots)}
                nested_roots = tuple(sorted(path for path in old_only
                    if not any(path.startswith(parent + '|')
                               for parent in old_only if parent != path)))
                nested = host.capture_body_geometry_contents(
                    set(nested_roots)) if nested_roots else ()
                preserved_geometry = tuple(sorted(
                    (*preserved_direct, *nested), key=lambda row: row[0]))
                host.capture_body_geometry_contents(
                    {row[0] for row in preserved_geometry})
                from adv_py.adapters.maya_driving_rebuild import derived_property_plugs
                derived_plugs = derived_property_plugs(driving_state, original.registration)
                if source_build:
                    from adv_py.adapters.maya_source_body_rebuild import derived_properties
                    derived_plugs |= derived_properties(stage,registration)
                property_options = {'derived_plugs': derived_plugs} if derived_plugs else {}
                if spline_change is not None and spline_change.systems:
                    from adv_py.adapters.maya_spline_control_rebuild import plan_properties
                    properties=plan_properties(host,stage,original,registration,spline_change,**property_options)
                else:
                    properties=host.plan_character_property_transfer(original,namespace,**property_options)
                staged=StagedCharacterRebuild(original,namespace,registration,
                                              properties,
                                              authored_geometry=preserved_geometry,
                                              geometry_container_state=geometry_container_state,
                                              geometry_container_drivers=geometry_container_drivers,
                                              geometry_container_conversions=geometry_container_conversions,
                                              geometry_container_outputs=geometry_container_outputs,
                                              geometry_output_conversions=geometry_output_conversions,
                                              deformer_input_conversions=deformer_input_conversions,
                                              deformer_output_conversions=deformer_output_conversions,
                                              deformer_sample_frames=deformer_sample_frames,
                                              deformer_animation_state=deformer_animation_state,
                                              segment_influences=built.segment_influences,
                                              spline_change=spline_change,
                                              spline_alignment_systems=spline_alignment_systems)
                staged=replace(staged,ownership=host.audit_character_rebuild_ownership(staged))
        return staged


class TransferStagedBodyCharacterData:
    def __init__(self,host):self._host=host

    def apply(self,staged,*,baseline=None):
        host=self._host
        original=staged.original
        extensions=tuple(row.path for row in original.extensions)
        if CaptureBodyCharacterPreservation(host).execute(extensions=extensions)!=original:
            raise CharacterRegistryError('原角色与暂存时的保留数据不同，请重新暂存')
        geometry_roots = {row[0] for row in staged.authored_geometry or ()}
        if host.capture_body_geometry_contents(geometry_roots) != staged.authored_geometry:
            raise CharacterRegistryError('Geometry 模型层级在暂存后发生变化')
        if host.capture_body_geometry_container_state() != staged.geometry_container_state:
            raise CharacterRegistryError('Geometry 容器状态在暂存后发生变化')
        if host.capture_body_geometry_container_drivers() != staged.geometry_container_drivers:
            raise CharacterRegistryError('Geometry 驱动连接在暂存后发生变化')
        if host.capture_body_geometry_container_conversions() != staged.geometry_container_conversions:
            raise CharacterRegistryError('Geometry 单位转换在暂存后发生变化')
        if host.capture_body_geometry_container_outputs() != staged.geometry_container_outputs:
            raise CharacterRegistryError('Geometry 输出连接在暂存后发生变化')
        if host.capture_body_geometry_output_conversions() != staged.geometry_output_conversions:
            raise CharacterRegistryError('Geometry 输出单位转换在暂存后发生变化')
        if host.capture_character_deformer_conversions(
                original.deformers) != staged.deformer_input_conversions:
            raise CharacterRegistryError('生产变形器单位转换在暂存后发生变化')
        if host.capture_character_deformer_output_conversions(
                original.deformers) != staged.deformer_output_conversions:
            raise CharacterRegistryError('生产变形器输出单位转换在暂存后发生变化')
        if (host.capture_character_deformer_animation_state(
                original.deformers,original.skins)
                != staged.deformer_animation_state):
            raise CharacterRegistryError('生产变形器动画曲线在暂存后发生变化')
        host.preflight_character_transfer(staged)
        if staged.ownership is not None and host.audit_character_rebuild_ownership(staged)!=staged.ownership:
            raise CharacterRegistryError('暂存后的 Rig 归属或连接已变化，请重新暂存')
        frames=_transfer_sample_frames(original,staged.deformer_sample_frames)
        with (nullcontext(baseline) if baseline is not None
              else TemporaryFile(mode='w+b')) as transfer_baseline:
            if staged.spline_change is None or not staged.spline_change.systems:
                _write_transfer_samples(host,staged,frames,transfer_baseline,
                                        target=False)
            with host.character_rebuild_transaction('Transfer preserved data to replacement rig'):
                host.transfer_character_data(staged)
                host.verify_character_retained_data(staged)
                if host.capture_body_geometry_contents(geometry_roots) != staged.authored_geometry:
                    raise RuntimeError('交接改变了 Geometry 模型层级')
                from adv_py.adapters.maya_body import MayaBodyBuildHost
                target = MayaBodyBuildHost(namespace=staged.namespace)
                if target.capture_body_geometry_container_state() != staged.geometry_container_state:
                    raise RuntimeError('交接改变了 Geometry 容器状态')
                if staged.spline_change is None or not staged.spline_change.systems:
                    error=_compare_transfer_samples(host,staged,frames,transfer_baseline,
                                                    target=True,
                                                    exclude_unattached_face=True)
                    if error>1e-4:
                        raise RuntimeError('交接改变身体、控制空间、蒙皮或用户附件；最大误差：'+str(error))
        return staged


class RebuildBodyCharacter:
    """Original rebuild, including explicit/label-derived Spline count edits."""
    def __init__(self,host):self._host=host

    def apply(self,namespace,*,extensions=(),spline_counts=(),spline_alignment_systems=()):
        host=self._host
        with host.transaction('Rebuild character preserving user data'):
            from adv_py.adapters.maya_source_parent_inverse import repair
            repair(host, host.read_character_registration())
            staged=StageBodyCharacterRebuild(host).apply(namespace,extensions=extensions,
                spline_counts=spline_counts,spline_alignment_systems=spline_alignment_systems)
            frames=_transfer_sample_frames(staged.original,
                staged.deformer_sample_frames)
            from adv_py.adapters.maya_body_face_rebuild import retained_roots
            preserve_face=bool(retained_roots(host,staged.original.registration))
            use_source_baseline=(preserve_face and
                (staged.spline_change is None or not staged.spline_change.systems))
            with TemporaryFile(mode='w+b') as baseline:
                # The Face stays attached to the old Head until promotion.
                # Its mesh at the transfer midpoint is not a valid final
                # baseline once animation has moved to the staged Body.
                TransferStagedBodyCharacterData(host).apply(
                    staged,baseline=baseline if use_source_baseline else None)
                if not use_source_baseline:
                    _write_transfer_samples(host,staged,frames,baseline,target=True)
                promoted=host.promote_character_rebuild(staged)
                # Match MEL's final `dgdirty -a` after the handoff (78540).
                from maya import cmds as cmds
                cmds.dgdirty(allPlugs=True)
                geometry_roots = {row[0] for row in staged.authored_geometry or ()}
                if host.capture_body_geometry_contents(geometry_roots) != staged.authored_geometry:
                    raise RuntimeError('重建后 Geometry 模型层级身份或姿态变化')
                if host.capture_body_geometry_container_state() != staged.geometry_container_state:
                    raise RuntimeError('重建后 Geometry 容器状态变化')
                if host.capture_body_geometry_container_drivers() != staged.geometry_container_drivers:
                    raise RuntimeError('重建后 Geometry 驱动连接变化')
                if host.capture_body_geometry_container_conversions() != staged.geometry_container_conversions:
                    raise RuntimeError('重建后 Geometry 单位转换输入变化')
                if host.capture_body_geometry_container_outputs() != staged.geometry_container_outputs:
                    raise RuntimeError('重建后 Geometry 输出连接变化')
                if host.capture_body_geometry_output_conversions() != staged.geometry_output_conversions:
                    raise RuntimeError('重建后 Geometry 输出单位转换变化')
                final_error=_compare_transfer_samples(host,promoted,frames,baseline,
                                                     target=True)
                if final_error>1e-4:
                    details=_transfer_sample_differences(
                        host,promoted,frames,baseline)
                    raise RuntimeError('原位替换改变身体、蒙皮或用户数据：'
                                       +repr(details))
        return promoted
