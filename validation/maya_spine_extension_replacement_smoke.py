"""Keep an explicitly declared user attachment on a replaced control."""
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
        from adv_py.adapters import MayaOriginalSkinSpineMigrationHost, MayaBodyBuildHost
        from adv_py.application import ReplaceRegisteredSpineCharacter
        skins = (('source:SourceSkin', '|source:SourceMesh'),
                 ('source:SecondSkin', '|source:SecondMesh'))
        if mode == 'inspect':
            scene = sys.argv[3] if len(sys.argv) > 3 else 'spine-extension-replaced.ma'
            cmds.file(str(folder / scene), open=True, force=True)
            MayaBodyBuildHost(namespace='source').read_character_registration()
            accessory = cmds.ls('source:Accessory', long=True) or []
            if (cmds.namespace(exists='target') or len(accessory) != 1
                    or cmds.getAttr(accessory[0] + '.assetCode') != 'rig-prop-A'):
                raise RuntimeError('重开后附件未保留')
            expected = json.loads((folder / 'spine-extension-replacement.json')
                                  .read_text(encoding='utf8'))['original_world']
            for frame, matrix in zip((1,10),expected):
                cmds.currentTime(frame, edit=True)
                actual = cmds.xform(accessory[0], query=True,
                                    worldSpace=True, matrix=True)
                if max(abs(a-b) for a,b in zip(actual,matrix)) > 1e-4:
                    raise RuntimeError('重开后附件世界轨迹改变')
            curves = cmds.listConnections(accessory[0], source=True,
                destination=False, type='animCurve') or []
            if len(set(curves)) != 9 or any(not curve.startswith('source:')
                                           for curve in curves):
                raise RuntimeError('附件动画曲线未归属原角色命名空间')
            print('REOPEN_OK', accessory[0], flush=True)
            return
        cmds.file(str(folder / 'multi-skin-spine-before.ma'),
                  open=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentTime(1, edit=True)
        source_parent = (cmds.ls('source:AdvPy_WristFK_R', long=True) or [None])[0]
        target_parent = (cmds.ls('target:AdvPy_WristFK_R', long=True) or [None])[0]
        if not source_parent or not target_parent:
            raise RuntimeError('手腕控制节点缺失')
        accessory = cmds.createNode('transform', name='source:Accessory',
                                    parent=source_parent)
        cmds.createNode('locator', name='source:AccessoryShape', parent=accessory)
        cmds.addAttr(accessory, longName='assetCode', dataType='string')
        cmds.setAttr(accessory + '.assetCode', 'rig-prop-A', type='string')
        accessory = (cmds.ls(accessory, long=True) or [None])[0]
        uuid = cmds.ls(accessory, uuid=True)[0]
        local = tuple(cmds.xform(accessory, query=True,
                                  objectSpace=True, matrix=True))
        def world(path, frame):
            cmds.currentTime(frame, edit=True)
            return tuple(cmds.xform(path, query=True,
                                    worldSpace=True, matrix=True))
        original_world = tuple(world(accessory, frame) for frame in (1, 10))
        cmds.currentTime(1, edit=True)
        cmds.file(rename=str(folder / 'spine-extension-before.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        class FailedPromotionHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_extensions(self, moves):
                super().apply_original_spine_extensions(moves)
                raise RuntimeError('Injected extension transfer failure')
        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                return FailedPromotionHost()
        try:
            ReplaceRegisteredSpineCharacter(
                FailedHost(namespace='target')).apply_many(
                    'source', 'target', skins, start_frame=1, end_frame=10,
                    extensions=(accessory,))
        except RuntimeError as exc:
            if 'Injected extension transfer failure' not in str(exc):
                raise
            rollback = ((cmds.ls(uuid, long=True) or [None])[0] == accessory
                        and cmds.namespace(exists='target'))
        else:
            rollback = False
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target')).apply_many(
                'source', 'target', skins, start_frame=1, end_frame=10,
                extensions=(accessory,))
        moved = (cmds.ls(uuid, long=True) or [None])[0]
        attached = (moved and moved.startswith('|source:')
            and '|source:AdvPy_WristFK_R|source:Accessory' in moved
            and tuple(cmds.xform(moved, query=True,
                                 objectSpace=True, matrix=True)) == local
            and cmds.getAttr(moved + '.assetCode') == 'rig-prop-A')
        cmds.undo()
        undone = ((cmds.ls(uuid, long=True) or [None])[0] == accessory
                  and cmds.namespace(exists='target'))
        cmds.redo()
        redone = ((cmds.ls(uuid, long=True) or [None])[0] == moved
                  and not cmds.namespace(exists='target'))
        moved_world = tuple(world(moved, frame) for frame in (1, 10))
        trajectory_error = max(abs(a-b) for before, after in
            zip(original_world, moved_world) for a,b in zip(before,after))
        cmds.currentTime(1, edit=True)
        report = dict(skins=result.skin_count, attached=bool(attached),
                      trajectory_error=trajectory_error,
                      original_world=original_world,
                      rollback=rollback, undo=undone, redo=redone)
        (folder / 'spine-extension-replacement.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        if not all((result.skin_count == 2, attached,
                    trajectory_error < 1e-4, rollback,
                    undone, redone)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder / 'spine-extension-replaced.ma'))
        cmds.file(save=True, type='mayaAscii', force=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]).resolve())
