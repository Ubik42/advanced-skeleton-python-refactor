"""Atomic registered spine FK and Skin transfer with rollback and reopen."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def short(path):
    return path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def main(mode, folder):
    folder = folder.resolve()
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaCharacterSpineMigrationHost, MayaBodyBuildHost
        from adv_py.application import MigrateRegisteredSpineCharacter

        if mode == 'exercise':
            cmds.file(str(folder / 'registered-spine-skin-before.ma'),
                      open=True, force=True)
            cmds.undoInfo(state=True)
            host = MayaCharacterSpineMigrationHost(namespace='target')
            target = host.read_character_registration()
            for channel in target.channels:
                plug = host.scene_address(channel.node + '.' + channel.attribute)
                if cmds.keyframe(plug, query=True, keyframeCount=True):
                    cmds.cutKey(plug, clear=True)
            cmds.currentTime(1, edit=True)
            before_keys = host.capture_character_key_state(target)
            before_skin = host.capture_all_skin_weights('TargetSkin', '|TargetMesh')
            source_skin = host.capture_all_skin_weights('source:SourceSkin',
                                                        '|source:SourceMesh')
            cmds.file(rename=str(folder / 'character-spine-atomic-before.ma'))
            cmds.file(save=True, type='mayaAscii', force=True)
            options = dict(start_frame=1, end_frame=10, sample_by=1,
                           max_distance=1e-6)
            class FailedHost(MayaCharacterSpineMigrationHost):
                calls = 0
                def write_mocap_fk_group_keys(self, plan):
                    result = super().write_mocap_fk_group_keys(plan)
                    self.calls += 1
                    if self.calls == 3:
                        raise RuntimeError('Injected atomic spine failure')
                    return result
            try:
                MigrateRegisteredSpineCharacter(FailedHost(namespace='target')).apply(
                    'source', 'source:SourceSkin', '|source:SourceMesh',
                    'TargetSkin', '|TargetMesh', **options)
            except RuntimeError as exc:
                if 'Injected atomic spine failure' not in str(exc):
                    raise
                rollback = (host.capture_character_key_state(target) == before_keys
                    and host.capture_all_skin_weights('TargetSkin', '|TargetMesh') == before_skin
                    and host.capture_all_skin_weights('source:SourceSkin',
                        '|source:SourceMesh') == source_skin)
            else:
                rollback = False
            result = MigrateRegisteredSpineCharacter(host).apply('source',
                'source:SourceSkin', '|source:SourceMesh',
                'TargetSkin', '|TargetMesh', **options)
            after_keys = host.capture_character_key_state(target)
            after_skin = host.capture_all_skin_weights('TargetSkin', '|TargetMesh')
            first = {short(row.influence_path): row.weight
                     for row in after_skin.vertices[0].weights}
            split = (abs(first.get('Spine1_M', 0.) - .25) < 1e-6
                     and abs(first.get('Spine2_M', 0.) - .25) < 1e-6
                     and abs(first.get('Shoulder_R', 0.) - .5) < 1e-6)
            source_unchanged = (host.capture_all_skin_weights('source:SourceSkin',
                '|source:SourceMesh') == source_skin)
            cmds.undo()
            undo = (host.capture_character_key_state(target) == before_keys
                    and host.capture_all_skin_weights('TargetSkin', '|TargetMesh') == before_skin)
            cmds.redo()
            redo = (host.capture_character_key_state(target) == after_keys
                    and host.capture_all_skin_weights('TargetSkin', '|TargetMesh') == after_skin)
            report = dict(frames=result.frames, groups=result.fk_groups,
                changed_vertices=result.changed_vertices, rollback=rollback,
                split=split, source_unchanged=source_unchanged, undo=undo, redo=redo,
                keys_changed=after_keys != before_keys,
                no_bridge=not any(name.startswith('AdvPySpineBridge_')
                    for name in (cmds.namespaceInfo(listOnlyNamespaces=True) or [])))
            (folder / 'character-spine-atomic.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            if not all((report['frames'] == 10, report['groups'] == 7,
                        report['changed_vertices'] == 4, rollback, split,
                        source_unchanged, undo, redo, report['keys_changed'],
                        report['no_bridge'])):
                raise RuntimeError(report)
        elif mode == 'inspect':
            cmds.file(str(folder / 'character-spine-atomic-product.ma'),
                      open=True, force=True)
            target_host = MayaCharacterSpineMigrationHost(namespace='target')
            source_host = MayaBodyBuildHost(namespace='source')
            target = target_host.read_character_registration()
            source_host.read_character_registration()
            keys = {row.key: row for row in target.channels}
            for key in ('global.translateX', 'torso.TorsoSpine1_MFK.rotateZ',
                        'torso.TorsoChest_MFK.rotateZ'):
                channel = keys[key]
                times = cmds.keyframe(target_host.scene_address(channel.node)
                    + '.' + channel.attribute, query=True, timeChange=True) or []
                if tuple(times) != tuple(range(1, 11)):
                    raise RuntimeError('重开后 FK 控制键缺失：' + key)
            state = target_host.capture_all_skin_weights('TargetSkin', '|TargetMesh')
            first = {short(row.influence_path): row.weight
                     for row in state.vertices[0].weights}
            if not (abs(first.get('Spine1_M', 0.) - .25) < 1e-6
                    and abs(first.get('Spine2_M', 0.) - .25) < 1e-6):
                raise RuntimeError('重开后脊柱 Skin 权重不符')
            print('atomic spine product reopen: FK keys and Skin split preserved')
        else:
            raise ValueError(mode)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]))
