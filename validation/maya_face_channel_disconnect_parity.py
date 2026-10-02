"""Original disconnect and build-pose reset after an external ARKit connection."""
from pathlib import Path
import json
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUTPUT = ROOT / 'validation/results/face-channel-disconnect-parity'


def main():
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from maya_face_channel_parity import fixture, observe, compare
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 0))
        mel.eval('AdvancedSkeleton;')
        for kind in ('arkit_connect', 'arkit_quick'):
            driver = fixture(kind, True)
            mel.eval('asConnectARKit "";')
            c.setAttr(driver + '.eyeBlink_R', .75)
            c.setAttr(driver + '.jawOpen', .5)
            mel.eval('asDisconnectARKit "";')
            native = observe(driver, 1)
            driver = fixture(kind, True)
            host = MayaOriginalFaceBuildHost()
            with host.transaction('连接 ARKit'):
                host.connect_original_face_arkit(driver)
            c.setAttr(driver + '.eyeBlink_R', .75)
            c.setAttr(driver + '.jawOpen', .5)
            with host.transaction('断开 ARKit 并恢复构建姿态'):
                host.disconnect_original_face_arkit()
            data = observe(driver, 1)
            row = compare(native, data)
            report['cases'][kind] = row
            c.undo(); c.redo()
            row['undo_redo'] = compare(data, observe(driver, 1))
            saved = OUTPUT / (kind + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            row['reopened'] = compare(data, observe(driver, 1))
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        from maya import utils
        utils.executeDeferred(c.quit, force=True)
