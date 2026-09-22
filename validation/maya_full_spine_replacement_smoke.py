"""One-Undo variable-spine replacement on the original mesh and Skin."""
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
        from adv_py.adapters import MayaBodyBuildHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        from adv_py.application import ReplaceRegisteredSpineCharacter
        skin, mesh = 'source:SourceSkin', '|source:SourceMesh'
        if mode == 'inspect':
            scene_name = sys.argv[3] if len(sys.argv) > 3 else 'full-spine-replaced.ma'
            cmds.file(str(folder / scene_name), open=True, force=True)
            registration = MayaBodyBuildHost(namespace='source').read_character_registration()
            state = MayaOriginalSpinePromotionHost().capture_all_skin_weights(skin, mesh)
            if (cmds.namespace(exists='target') or len(registration.spine.body_joints) != 7
                    or len(state.influence_paths) != 8
                    or any('|source:' not in path for path in state.influence_paths)):
                raise RuntimeError('完整角色替换重开后无效')
            print('REOPEN_OK', state.vertex_count, flush=True)
            return
        cmds.file(str(folder / 'registered-spine-skin-before.ma'),
                  open=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentTime(1, edit=True)
        cmds.deltaMush(mesh, name='source:SourceDeltaMush',
                       smoothingIterations=2)
        cmds.delete('target:TargetSkin')
        cmds.delete('target:TargetMesh')
        cmds.file(rename=str(folder / 'full-spine-replacement-before.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
        skin_host = MayaOriginalSpinePromotionHost()
        before = skin_host.capture_all_skin_weights(skin, mesh)
        boundary = skin_host.capture_skin_handoff_boundary(skin, mesh)
        class FailedPromotionHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_promotion(self, plan):
                super().apply_original_spine_promotion(plan)
                raise RuntimeError('Injected failure after complete replacement')
        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                return FailedPromotionHost()
        try:
            ReplaceRegisteredSpineCharacter(
                FailedHost(namespace='target')).apply(
                    'source', 'target', skin, mesh,
                    start_frame=1, end_frame=10)
        except RuntimeError as exc:
            if 'Injected failure after complete replacement' not in str(exc):
                raise
            rollback = (cmds.namespace(exists='target')
                and skin_host.capture_all_skin_weights(skin, mesh) == before
                and skin_host.capture_skin_handoff_boundary(skin, mesh) == boundary
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints) == 5)
        else:
            rollback = False
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target')).apply(
                'source', 'target', skin, mesh, start_frame=1, end_frame=10)
        def promoted():
            return (not cmds.namespace(exists='target')
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints) == 7
                and len(skin_host.capture_all_skin_weights(skin, mesh)
                        .influence_paths) == 8
                and skin_host.capture_skin_handoff_boundary(skin, mesh) == boundary)
        takeover = promoted()
        cmds.undo()
        undo = (cmds.namespace(exists='target')
                and skin_host.capture_all_skin_weights(skin, mesh) == before
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints) == 5)
        cmds.redo()
        redo = promoted()
        def vertex(frame):
            cmds.currentTime(frame, edit=True)
            return tuple(cmds.xform(mesh + '.vtx[0]', query=True,
                                    worldSpace=True, translation=True))
        moved = max(abs(a-b) for a,b in zip(vertex(1), vertex(10))) > 1e-4
        report = dict(frames=result.frames, groups=result.fk_groups,
            vertices=result.vertices, old_nodes_removed=result.old_nodes_removed,
            rollback=rollback, takeover=takeover, undo=undo, redo=redo,
            moved=moved)
        (folder / 'full-spine-replacement.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        if not all((result.frames == 10, result.fk_groups == 7,
                    result.vertices == 4, rollback, takeover, undo, redo,
                    moved)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder / 'full-spine-replaced.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]).resolve())
