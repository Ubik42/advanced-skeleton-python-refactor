"""Restore the native optional Game Engine operations during Body rebuild."""
from dataclasses import dataclass

from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from adv_py.core.character_registry import CharacterRegistryError
from .maya_original_control_identity import leaf


@dataclass(frozen=True)
class OriginalGameRebuildState:
    root_name: str | None = None
    scaling: bool | None = None
    unreal_twist: bool = False
    unreal_joints: bool = False
    scaling_after_unreal_joints: bool = False
    root_names: tuple[str, ...] = ()
    root_channel_keys: tuple[tuple[str, str, str], ...] = ()
    unreal_before_root: str | None = None
    scaling_record: str | None = None
    legacy_root_renamed: bool = False
    unreal_legacy_root: bool = False
    controller_tags: bool = False
    decomposed_opm: bool = False

    def __bool__(self):
        return (self.root_name is not None or self.scaling is not None or self.unreal_twist
                or self.unreal_joints or self.controller_tags or self.decomposed_opm)


def capture(host, registration):
    c = host._cmds
    root_names = []
    root_keys = []
    legacy_root_renamed = False
    for channel in registration.channels:
        if not channel.key.startswith('game.rootMotion.'):
            continue
        role = leaf(channel.node)
        name = role.removeprefix('FKExtra') if role.startswith('FKExtra') else role.removeprefix('FK')
        actual = name
        if (name == 'root' and not c.objExists('root.advPyGameRootMotionOwner')
                and c.objExists('rootUserCreated.advPyGameRootMotionOwner')):
            actual = 'rootUserCreated'
            legacy_root_renamed = True
        if name not in ('RootMotion_M', 'root') or not c.objExists(actual + '.advPyGameRootMotionOwner'):
            raise CharacterRegistryError('已登记 Root Motion 的原关节缺失')
        if name not in root_names:
            root_names.append(name)
        root_keys.append((role, channel.attribute, channel.key))
    root_name = root_names[0] if root_names else None
    scaling = None
    unreal = False
    for node in registration.nodes:
        if node.node_type != 'joint':
            continue
        if c.objExists(node.path + '.GameEngineScalingSSC'):
            scaling = bool(scaling or not c.getAttr(node.path + '.segmentScaleCompensate'))
        if c.objExists(node.path + '.originalParent'):
            unreal = True
    from .maya_unreal_joints import NAMES
    deformation = c.ls('DeformationSystem', long=True) or []
    markers = []
    for name in NAMES[1:]:
        paths = c.ls(name, long=True, type='joint') or []
        if (len(paths) == 1 and len(deformation) == 1
                and paths[0].startswith(deformation[0] + '|')):
            markers.append(paths[0])
    unreal_joints = len(markers) == len(NAMES) - 1
    scaling_after_markers = unreal_joints and any(
        c.objExists(path + '.GameEngineScalingSSC') for path in markers)
    unreal_before_root = None
    unreal_roots = c.ls('UnrealRoot', long=True, type='joint') or []
    if unreal_joints and len(unreal_roots) == 1:
        for name in root_names:
            actual = 'rootUserCreated' if name == 'root' and legacy_root_renamed else name
            paths = c.ls(actual, long=True, type='joint') or []
            if len(paths) == 1 and unreal_roots[0].startswith(paths[0] + '|'):
                unreal_before_root = name
                break
    unreal_legacy_root = False
    hand_root = c.ls('ik_hand_root', long=True, type='joint') or []
    if unreal_joints and len(hand_root) == 1:
        parent = (c.listRelatives(hand_root[0], parent=True, fullPath=True) or [None])[0]
        unreal_legacy_root = parent is not None and leaf(parent) in ('root', 'rootUserCreated')
    from .maya_game_scaling_state import MARKER, load, retained_record
    scaling_record = None
    if c.objExists('DeformationSystem.' + MARKER):
        _, scale_plan = load(host)
        scaling = scale_plan.enable
        scaling_record = retained_record(host)
    from .maya_original_optimize import has_original_controller_tags
    controller_tags = has_original_controller_tags(host)
    from .maya_original_opm_decomposition import has_original_opm_decomposition
    decomposed_opm = has_original_opm_decomposition(host)
    return OriginalGameRebuildState(root_name, scaling, unreal,
        unreal_joints, scaling_after_markers, tuple(root_names), tuple(root_keys), unreal_before_root, scaling_record, legacy_root_renamed, unreal_legacy_root, controller_tags, decomposed_opm)


def _rebase_rig(before, after, rig):
    current = {node.uuid: node for node in after.nodes}
    rewrites = []
    for node in before.nodes:
        actual = current.get(node.uuid)
        if actual is None or actual.node_type != node.node_type:
            raise CharacterRegistryError('Game Engine 重建替换了 Body 原对象')
        if node.path != actual.path:
            rewrites.append((node.path, actual.path))
    return rebase_plan_paths_after_parts(rig, FitPartFinalPaths((), (), tuple(rewrites)))


def restore_root(host, state, registration, rig):
    if state.root_name is None:
        return registration, rig
    from adv_py.application.body_game_root_motion import SwitchGameRootMotion
    for name in state.root_names or (state.root_name,):
        if state.unreal_before_root == name:
            _restore_unreal_markers(host)
        if name == 'root':
            with host.transaction('Restore original legacy Root Motion option'):
                host._transaction_changed = True
                option = host._cmds.createNode('transform', name='asCreateGameEngineRootMotionOptions')
                host._cmds.addAttr(option, longName='useOldRootName', attributeType='bool')
        SwitchGameRootMotion(host).apply(create=True)
        if name == 'root' and state.unreal_legacy_root:
            _restore_unreal_markers(host)
        if name == 'root' and state.legacy_root_renamed:
            from .maya_game_registration import source_registration, refresh_hierarchy
            with host.transaction('Restore native Mannequin legacy root name'):
                host._transaction_changed = True
                before = source_registration(host)
                host._cmds.rename('root', 'rootUserCreated')
                refresh_hierarchy(host, before)
    updated = host.read_character_registration()
    if state.root_channel_keys:
        from dataclasses import replace
        from adv_py.core.character_registry import REGISTRY_NAME, encode_registration
        from .maya_driving_registration import _write_string
        keys = {(role, attribute): key for role, attribute, key in state.root_channel_keys}
        updated = replace(updated, channels=tuple(replace(channel,
            key=keys.get((leaf(channel.node), channel.attribute), channel.key))
            for channel in updated.channels))
        with host.transaction('Restore original Root Motion channel identities'):
            host._transaction_changed = True
            _write_string(host._cmds, REGISTRY_NAME + '.advPyRegistryDocument', encode_registration(updated))
            updated = host.read_character_registration()
    return updated, _rebase_rig(registration, updated, rig)


def _restore_unreal_markers(host):
    from .maya_unreal_joints import MayaUnrealJointsHost
    from adv_py.application.unreal_joints import CreateUnrealJoints
    boundary = _operation_boundary(host, MayaUnrealJointsHost)
    CreateUnrealJoints(boundary).apply()


def restore_modes(host, state, registration, rig):
    if state.decomposed_opm:
        from .maya_original_opm_decomposition import MayaOriginalOpmDecompositionHost
        boundary = _operation_boundary(host, MayaOriginalOpmDecompositionHost)
        with boundary.transaction('Restore original OPM decomposition'):
            boundary.decompose_original_offset_parent_matrices()
    if state.controller_tags:
        from .maya_original_optimize import MayaOriginalOptimizeHost
        boundary = _operation_boundary(host, MayaOriginalOptimizeHost)
        with boundary.transaction('Restore original Controller tags'):
            boundary.tag_original_controllers()
    if state.scaling_record is not None:
        # Build the final native hierarchy first, then replay the exact saved
        # graph. Scaling-before-Twist and Scaling-before-Root preserve their
        # source calculation, instead of recalculating it against new parents.
        if state.unreal_joints and state.unreal_before_root is None and not state.unreal_legacy_root:
            _restore_unreal_markers(host)
        if state.unreal_twist:
            _restore_twist(host)
        from .maya_game_scaling_rebuild import restore
        with host.transaction('Restore original Game Scaling graph'):
            restore(host, state.scaling_record)
    else:
        # Original MEL scenes without our snapshot retain the native switches.
        if state.unreal_joints and state.scaling_after_unreal_joints and state.unreal_before_root is None and not state.unreal_legacy_root:
            _restore_unreal_markers(host)
        if state.scaling is not None:
            from adv_py.application.body_game_scaling import SwitchBodyGameScaling
            SwitchBodyGameScaling(host).apply(enable=True)
            if not state.scaling:
                SwitchBodyGameScaling(host).apply(enable=False)
        if state.unreal_joints and not state.scaling_after_unreal_joints and state.unreal_before_root is None and not state.unreal_legacy_root:
            _restore_unreal_markers(host)
        if state.unreal_twist:
            _restore_twist(host)
    if not (state.scaling is not None or state.unreal_twist or state.unreal_joints
            or state.controller_tags or state.decomposed_opm):
        return registration, rig
    updated = host.read_character_registration()
    return updated, _rebase_rig(registration, updated, rig)


def _restore_twist(host):
    from .maya_unreal_twist import MayaUnrealTwistHost
    from adv_py.application.unreal_twist import SetUnrealTwistHierarchy
    boundary = _operation_boundary(host, MayaUnrealTwistHost)
    SetUnrealTwistHierarchy(boundary).apply(True)


def _operation_boundary(host, operation_type):
    """Keep the rebuild owner's transaction while exposing operation methods.

    A staged Body delegates Undo to its original character. Copying only its
    instance data into a normal operation host loses that delegation and opens
    another native chunk. The adapter must retain the actual owner's method,
    together with the shared state used by mutation guards and checkpoints.
    """
    class RebuildOperation(operation_type):
        def transaction(self, label):
            return host.transaction(label)

    boundary = object.__new__(RebuildOperation)
    boundary.__dict__ = host.__dict__
    return boundary
