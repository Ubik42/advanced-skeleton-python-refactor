"""Full ordinary/multi Face after restoring native paint smoothing callbacks."""
from pathlib import Path
import json
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUTPUT = ROOT / 'validation/results/face-optional-full-build'


def main():
    from maya import cmds as c
    from maya.api import OpenMaya as om
    from adv_py.product.maya_panel_controller import MayaPanelController
    from maya_original_face_lower_smoke import fit_input, validate_lower_motion
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    try:
        for multi in (False, True):
            name = 'multi' if multi else 'ordinary'
            c.file(new=True, force=True); c.undoInfo(state=True)
            controller = MayaPanelController()
            fit_input(c, om, controller, multi=multi, opm=True, complete=True, attachments=True)
            # Use the public default flood counts, not a reduced proxy count.
            result = controller.face_original_build(':')
            assert c.getAttr('FaceFitSkeleton.buildCompleted')
            state = c.undoInfo(query=True, state=True)
            c.undoInfo(stateWithoutFlush=False)
            try:
                motion = validate_lower_motion(c, complete=True, attachments=True)
            finally:
                c.undoInfo(stateWithoutFlush=state)
            c.undo(); assert not c.objExists('FaceMotionSystem')
            c.redo(); assert c.getAttr('FaceFitSkeleton.buildCompleted')
            saved = OUTPUT / (name + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            reopened = validate_lower_motion(c, complete=True, attachments=True)
            assert max(abs(reopened[k] - v) for k, v in motion.items()) < 1e-5
            report['cases'][name] = {'stages': list(result['stages']), 'motion': motion,
                'undo_redo': True, 'saved_reopened': True, 'public_default_smoothing': True}
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        c.quit(force=True)
