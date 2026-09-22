"""Replace one registered Rig while retaining two original skinClusters."""
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
        skins = (('source:SourceSkin', '|source:SourceMesh'),
                 ('source:SecondSkin', '|source:SecondMesh'))
        if mode == 'inspect':
            scene = sys.argv[3] if len(sys.argv) > 3 else 'multi-skin-spine-replaced.ma'
            cmds.file(str(folder / scene), open=True, force=True)
            if cmds.namespace(exists='target'):
                raise RuntimeError('重开后目标命名空间仍在')
            registration = MayaBodyBuildHost(namespace='source').read_character_registration()
            states = [MayaOriginalSpinePromotionHost().capture_all_skin_weights(*item)
                      for item in skins]
            if (len(registration.spine.body_joints) != 7
                    or [state.vertex_count for state in states] != [4, 4]
                    or any(any('|source:' not in path for path in state.influence_paths)
                           for state in states)):
                raise RuntimeError('多 Skin 重开后绑定无效')
            print('REOPEN_OK', len(states), flush=True)
            return
        cmds.file(str(folder / 'registered-spine-skin-before.ma'),
                  open=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentTime(1, edit=True)
        cmds.deltaMush('|source:SourceMesh', name='source:SourceDeltaMush',
                       smoothingIterations=2)
        second = cmds.polyPlane(name='source:SecondMesh', width=1.5,
                                height=1.5, subdivisionsX=1,
                                subdivisionsY=1)[0]
        cmds.skinCluster(
            '|source:Root_M|source:Spine1_M',
            '|source:Root_M|source:Spine1_M|source:Spine2_M|source:Spine3_M|source:Chest_M|source:Scapula_R|source:Shoulder_R',
            second, toSelectedBones=True, bindMethod=0,
            normalizeWeights=1, maximumInfluences=2,
            name='source:SecondSkin')
        cmds.delete('target:TargetSkin')
        cmds.delete('target:TargetMesh')
        cmds.file(rename=str(folder / 'multi-skin-spine-before.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
        poses = tuple(tuple(cmds.listConnections(skin + '.bindPose',
            source=True, destination=False, type='dagPose') or ())
            for skin, _ in skins)
        skin_host = MayaOriginalSpinePromotionHost()
        before = tuple(skin_host.capture_all_skin_weights(*item) for item in skins)
        boundaries = tuple(skin_host.capture_skin_handoff_boundary(*item)
                           for item in skins)
        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                class FailAfterSecond(MayaOriginalSpinePromotionHost):
                    calls = 0
                    def remove_skin_handoff_influences(self, *args):
                        super().remove_skin_handoff_influences(*args)
                        self.calls += 1
                        if self.calls == 2:
                            raise RuntimeError('Injected second Skin failure')
                return FailAfterSecond()
        try:
            ReplaceRegisteredSpineCharacter(
                FailedHost(namespace='target')).apply_many(
                    'source', 'target', skins, start_frame=1, end_frame=10)
        except RuntimeError as exc:
            if 'Injected second Skin failure' not in str(exc):
                raise
            rollback = tuple(skin_host.capture_all_skin_weights(*item)
                             for item in skins) == before
        else:
            rollback = False
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target')).apply_many(
                'source', 'target', skins, start_frame=1, end_frame=10)
        def promoted():
            return (not cmds.namespace(exists='target')
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints) == 7
                and all(skin_host.capture_skin_handoff_boundary(*item) == boundary
                        for item, boundary in zip(skins, boundaries))
                and all(all('|source:' in p for p in
                    skin_host.capture_all_skin_weights(*item).influence_paths)
                    for item in skins))
        takeover = promoted()
        cmds.undo()
        undo = (cmds.namespace(exists='target')
            and tuple(skin_host.capture_all_skin_weights(*item)
                      for item in skins) == before)
        cmds.redo()
        redo = promoted()
        report = dict(skins=result.skin_count, vertices=result.vertices,
            bind_poses=poses, shared_bind_pose=bool(poses[0] and poses[0] == poses[1]),
            rollback=rollback, takeover=takeover, undo=undo, redo=redo)
        (folder / 'multi-skin-spine-replacement.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        if not all((result.skin_count == 2, result.vertices == 8,
                    rollback, takeover, undo, redo)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder / 'multi-skin-spine-replaced.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]).resolve())
