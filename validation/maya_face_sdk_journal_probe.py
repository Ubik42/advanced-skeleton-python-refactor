"""Record exact SDK graphs before/after one operation's native undo and redo."""
from pathlib import Path
import json
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUTPUT = ROOT / 'validation/results/face-sdk-journal'


def snapshot():
    from maya import cmds as c
    result = {'nodes': {}, 'values': {}}
    for node in c.ls(type=('animCurve', 'blendWeighted', 'unitConversion')):
        row = {'uuid': c.ls(node, uuid=True)[0], 'type': c.nodeType(node),
               'connections': c.listConnections(node, plugs=True, connections=True) or []}
        if c.nodeType(node).startswith('animCurve'):
            row['keys'] = {'inputs': c.keyframe(node, query=True, floatChange=True),
                           'values': c.keyframe(node, query=True, valueChange=True)}
        result['nodes'][node] = row
    for plug in ('ctrlEye_L.ty', 'ctrlEye_R.ty', 'SDKEye_L.rx', 'SDKEye_R.rx', 'ctrlMouth_M.ty',
                 'ctrlARKit_M.eyeBlinkRight'):
        if c.objExists(plug):
            result['values'][plug] = {'value': c.getAttr(plug),
                'input': c.listConnections(plug, source=True, destination=False, plugs=True) or []}
    return result


def main():
    from maya import cmds as c
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.core.face_arkit import ARKIT_SHAPES
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    try:
        for observed in (False, True):
            name = 'sampled' if observed else 'unsampled'
            c.file(str(ROOT / 'validation/results/face-complete-shell-fix-live/face-completed.mb'),
                   open=True, force=True, executeScriptNodes=False)
            c.undoInfo(state=True); c.autoKeyframe(state=False); c.currentTime(0)
            c.createNode('transform', name='ExternalARKit')
            for attr in ARKIT_SHAPES:
                c.addAttr('ExternalARKit', longName=attr, attributeType='double', keyable=True)
            host = MayaOriginalFaceBuildHost()
            row = {'before': snapshot()}
            with host.transaction('Quick 图记录'):
                host.connect_original_face_arkit('ExternalARKit')
            row['built'] = snapshot()
            if observed:
                c.undoInfo(stateWithoutFlush=False)
                for attr in ARKIT_SHAPES:
                    c.setAttr('ExternalARKit.' + attr, 1); c.getAttr('SDKEye_L.rx')
                    c.setAttr('ExternalARKit.' + attr, 0)
                c.undoInfo(stateWithoutFlush=True)
            row['undo_name'] = c.undoInfo(query=True, undoName=True)
            c.undo(); row['undone'] = snapshot()
            c.redo(); row['redone'] = snapshot()
            c.undoInfo(stateWithoutFlush=False)
            c.setAttr('ExternalARKit.eyeLookDownLeft', 1)
            row['redone_pose'] = snapshot()
            c.undoInfo(stateWithoutFlush=True)
            report['cases'][name] = row
            (OUTPUT / 'report.json').write_text(json.dumps(report), encoding='utf8')
        report['status'] = 'captured'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report), encoding='utf8')
        from maya import utils
        utils.executeDeferred(c.quit, force=True)
