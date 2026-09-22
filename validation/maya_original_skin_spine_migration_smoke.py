"""Original mesh/Skin and FK migration share one Maya Undo chunk."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main(mode, folder):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaOriginalSkinSpineMigrationHost
        from adv_py.application import MigrateRegisteredSpineOnOriginalSkin
        from adv_py.adapters.maya_body import MayaBodyBuildHost

        skin = 'source:SourceSkin'
        mesh = '|source:SourceMesh'
        if mode == 'exercise':
            cmds.file(str(folder / 'registered-spine-skin-before.ma'),
                      open=True, force=True)
            cmds.undoInfo(state=True)
            cmds.currentTime(1, edit=True)
            cmds.deltaMush(mesh, name='source:SourceDeltaMush',
                           smoothingIterations=2)
            host = MayaOriginalSkinSpineMigrationHost(namespace='target')
            skin_host = host.original_skin_handoff_host()
            before = skin_host.capture_all_skin_weights(skin, mesh)
            boundary = skin_host.capture_skin_handoff_boundary(skin, mesh)
            class FailedHost(MayaOriginalSkinSpineMigrationHost):
                def write_mocap_fk_group_keys(self, group):
                    super().write_mocap_fk_group_keys(group)
                    raise RuntimeError('Injected FK failure after original Skin handoff')
            try:
                MigrateRegisteredSpineOnOriginalSkin(
                    FailedHost(namespace='target')).apply(
                        'source', 'target', skin, mesh,
                        start_frame=1, end_frame=10)
            except RuntimeError as exc:
                if 'Injected FK failure' not in str(exc):
                    raise
                rollback = (skin_host.capture_all_skin_weights(skin, mesh) == before
                            and skin_host.capture_skin_handoff_boundary(skin, mesh)
                            == boundary)
            else:
                rollback = False
            result = MigrateRegisteredSpineOnOriginalSkin(host).apply(
                'source', 'target', skin, mesh,
                start_frame=1, end_frame=10)
            after = skin_host.capture_all_skin_weights(skin, mesh)
            unchanged_boundary = skin_host.capture_skin_handoff_boundary(skin, mesh) == boundary
            cmds.undo()
            undo = skin_host.capture_all_skin_weights(skin, mesh) == before
            cmds.redo()
            redo = skin_host.capture_all_skin_weights(skin, mesh) == after
            def position(frame):
                cmds.currentTime(frame, edit=True)
                return tuple(cmds.xform(mesh + '.vtx[0]', query=True,
                                        worldSpace=True, translation=True))
            moved = max(abs(a-b) for a, b in zip(position(1), position(10))) > 1e-4
            report = dict(frames=result.frames, groups=result.fk_groups,
                vertices=result.vertices, rollback=rollback, undo=undo,
                redo=redo, unchanged_boundary=unchanged_boundary, moved=moved)
            (folder / 'original-skin-spine-migration.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            if not all((result.frames == 10, result.fk_groups == 7,
                        result.vertices == 4, rollback, undo, redo,
                        unchanged_boundary, moved)):
                raise RuntimeError(report)
            cmds.file(rename=str(folder / 'original-skin-spine-migration.ma'))
            cmds.file(save=True, type='mayaAscii', force=True)
        else:
            scene_name = (sys.argv[3] if len(sys.argv) > 3
                          else 'original-skin-spine-migration.ma')
            cmds.file(str(folder / scene_name),
                      open=True, force=True)
            host = MayaOriginalSkinSpineMigrationHost(namespace='target')
            state = host.original_skin_handoff_host().capture_all_skin_weights(skin, mesh)
            MayaBodyBuildHost(namespace='source').read_character_registration()
            host.read_character_registration()
            if not (len(state.influence_paths) == 8
                    and all('|target:' in p for p in state.influence_paths)):
                raise RuntimeError('重开后原 Skin 交接无效')
            cmds.currentTime(10, edit=True)
            print('REOPEN_OK', state.vertex_count, flush=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]).resolve())
