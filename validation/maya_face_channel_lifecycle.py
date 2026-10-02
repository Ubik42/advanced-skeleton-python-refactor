"""Fresh-process channel lifecycle, external namespace isolation and disconnect."""
from pathlib import Path
import json
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
from maya_face_channel_parity import SCENE, observe, compare
OUTPUT = ROOT / 'validation/results/face-channel-lifecycle'


def main(kind='arkit_quick', native=False):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from maya_face_channel_parity import fixture
    OUTPUT.mkdir(parents=True, exist_ok=True)
    name = kind + ('-native' if native else '-python')
    report = {'status': 'running', 'kind': kind, 'native': native}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 0)); mel.eval('AdvancedSkeleton;')
        driver = fixture(kind, True)
        report['before_time'] = c.currentTime(query=True)
        # Inspect the source under the same one-chunk lifecycle as Python.
        if native:
            c.undoInfo(openChunk=True, chunkName='原版 ARKit 单次撤销')
            try:
                mel.eval('asConnectARKit "";')
            finally:
                c.undoInfo(closeChunk=True)
        else:
            host = MayaOriginalFaceBuildHost()
            with host.transaction('ARKit 单次撤销'):
                host.connect_original_face_arkit(driver)
        before = observe(driver, 1)
        report['poses'] = len(before)
        report['status'] = 'before_undo'
        (OUTPUT / (name + '.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
        c.undo(); c.redo()
        report['undo_redo'] = compare(before, observe(driver, 1))
        if native:
            mel.eval('asDisconnectARKit "";')
        else:
            with host.transaction('断开 ARKit'):
                host.disconnect_original_face_arkit()
        report['disconnected'] = observe(driver, 1)
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / (name + '.json')).write_text(json.dumps(report), encoding='utf8')
        c.quit(force=True)
