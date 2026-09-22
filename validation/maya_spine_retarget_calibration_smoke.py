"""Existing target animation must not be added to a replacement take."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import maya.standalone


def main():
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaOriginalSkinSpineMigrationHost
        from adv_py.application.character_spine_retarget import RetargetCharacterSpineFk

        folder = ROOT / 'validation' / 'results'
        cmds.file(str(folder / 'full-spine-replacement-before.ma'), open=True, force=True)
        cmds.undoInfo(state=True)
        host = MayaOriginalSkinSpineMigrationHost(namespace='target')
        target = host.read_character_registration()
        frames = tuple(range(1, 11))
        _, expected = host.capture_resampled_character_source('source', target, frames)
        global_x = next(ch for ch in target.channels if ch.key == 'global.translateX')
        before = float(host._cmds.getAttr(global_x.node+'.translateX', time=10))
        with host.transaction('Calibrate existing replacement animation'):
            RetargetCharacterSpineFk(host).apply_in_transaction(
                'source', start_frame=1, end_frame=10)
        errors = []
        for frame, pose in expected:
            cmds.currentTime(frame, edit=True)
            for row in target.body:
                name = row.path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
                actual = host._cmds.xform(row.path, query=True, worldSpace=True, matrix=True)
                errors.append((max(abs(a-b) for a,b in zip(actual, pose[name])), frame, name))
        after = float(host._cmds.getAttr(global_x.node+'.translateX', time=10))
        report = dict(before=before, after=after, worst_body=max(errors),
                      worst_spine=max(row for row in errors if row[2].startswith(('Spine','Chest'))),
                      worst_root=max(row for row in errors if row[2] == 'Root_M'))
        print('CALIBRATION', json.dumps(report), flush=True)
        if (abs(before-6.) > 1e-6 or abs(after-6.) > 1e-6
                or report['worst_root'][0] > 1e-4):
            raise RuntimeError(report)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main()
