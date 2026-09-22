"""Verify the saved cross-spine-count product scene in a fresh Maya process."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main(scene):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        cmds.file(str(scene.resolve()), open=True, force=True)
        source_host = MayaBodyBuildHost(namespace='source')
        target_host = MayaBodyBuildHost(namespace='target')
        source = source_host.read_character_registration()
        target = target_host.read_character_registration()
        source_channels = {row.key: row for row in source.channels}
        target_channels = {row.key: row for row in target.channels}
        keys = ('global.translateX', 'torso.TorsoSpine1_MFK.rotateZ',
                'torso.TorsoChest_MFK.rotateZ', 'arm.fk.ShoulderFK_R.rotateZ')
        for key in keys:
            source_row = source_channels[key]
            target_row = target_channels[key]
            source_times = cmds.keyframe(source_host.scene_address(source_row.node)
                + '.' + source_row.attribute, query=True, timeChange=True) or []
            target_times = cmds.keyframe(target_host.scene_address(target_row.node)
                + '.' + target_row.attribute, query=True, timeChange=True) or []
            if tuple(source_times) != (1., 5., 10.) or tuple(target_times) != tuple(range(1, 11)):
                raise RuntimeError('重开后的源／目标控制关键帧不符：' + key)
        if any(value.startswith('AdvPySpineBridge_') for value in
               (cmds.namespaceInfo(listOnlyNamespaces=True) or [])):
            raise RuntimeError('重开场景仍有临时脊柱骨架')
        print('cross-spine product reopen: source keys 3, target keys 10, no bridge')
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(Path(sys.argv[1]))
