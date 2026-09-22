"""Audit and replace a four-spine Rig with its six-spine successor."""
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
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        if mode == 'inspect':
            scene_name = (sys.argv[3] if len(sys.argv) > 3
                          else 'spine-original-promoted.ma')
            cmds.file(str(folder / scene_name), open=True,
                      force=True)
            host = MayaOriginalSpinePromotionHost()
            from adv_py.adapters import MayaBodyBuildHost
            registration = MayaBodyBuildHost(namespace='source').read_character_registration()
            state = host.capture_all_skin_weights('source:SourceSkin',
                                                 '|source:SourceMesh')
            if (cmds.namespace(exists='target') or len(registration.spine.body_joints) != 7
                    or len(state.influence_paths) != 8
                    or any(not path.startswith('|source:')
                           for path in state.influence_paths)):
                raise RuntimeError('重开后原位角色接管无效')
            print('REOPEN_OK', state.vertex_count, flush=True)
            return
        cmds.file(str(folder / 'spine-skin-handoff.ma'), open=True, force=True)
        cmds.undoInfo(state=True)
        cmds.delete('target:TargetSkin')
        cmds.delete('target:TargetMesh')
        cmds.file(rename=str(folder / 'spine-original-promotion-before.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
        host = MayaOriginalSpinePromotionHost()
        plan = host.plan_original_spine_promotion('source', 'target',
            'source:SourceSkin', '|source:SourceMesh')
        class FailedHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_promotion(self, plan):
                super().apply_original_spine_promotion(plan)
                raise RuntimeError('Injected post-promotion failure')
        try:
            failed = FailedHost()
            with failed.transaction('Failed original spine promotion'):
                failed.apply_original_spine_promotion(plan)
        except RuntimeError as exc:
            if 'Injected post-promotion failure' not in str(exc):
                raise
            rollback = (host.plan_original_spine_promotion('source', 'target',
                'source:SourceSkin', '|source:SourceMesh') == plan)
        else:
            rollback = False
        with host.transaction('Promote replacement spine Rig'):
            host.apply_original_spine_promotion(plan)
        from adv_py.adapters import MayaBodyBuildHost
        def promoted():
            registration = MayaBodyBuildHost(namespace='source').read_character_registration()
            state = host.capture_all_skin_weights('source:SourceSkin',
                '|source:SourceMesh')
            return (not cmds.namespace(exists='target')
                and registration == plan.target_registration
                and len(state.influence_paths) == 8
                and all('|source:' in path for path in state.influence_paths)
                and host.capture_skin_handoff_boundary('source:SourceSkin',
                    '|source:SourceMesh') == plan.boundary)
        takeover = promoted()
        cmds.undo()
        undo = (host.plan_original_spine_promotion('source', 'target',
            'source:SourceSkin', '|source:SourceMesh') == plan)
        cmds.redo()
        redo = promoted()
        def vertex(frame):
            cmds.currentTime(frame, edit=True)
            return tuple(cmds.xform('|source:SourceMesh.vtx[0]', query=True,
                                    worldSpace=True, translation=True))
        moved = max(abs(a-b) for a,b in zip(vertex(1), vertex(10))) > 1e-4
        report = dict(deleted=len(plan.deletion_uuids),
            retained=len(plan.retained_uuids), replacement=len(plan.target_uuids),
            rollback=rollback, takeover=takeover, undo=undo, redo=redo,
            moved=moved)
        (folder / 'spine-original-promotion.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        if not all((rollback, takeover, undo, redo, moved)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder / 'spine-original-promoted.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]).resolve())
