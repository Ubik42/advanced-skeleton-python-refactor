"""Full ordinary/multi Face after restoring native paint smoothing callbacks."""
from pathlib import Path
import json
import os
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUTPUT = ROOT / 'validation/results/face-optional-full-build'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, utils
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_conversion_parity import skin_snapshot, scene_identity, observe, compare
    load_project_native_plugin()
    from maya.api import OpenMaya as om
    from adv_py.product.maya_panel_controller import MayaPanelController
    from maya_original_face_lower_smoke import fit_input, validate_lower_motion
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'cases': {}}
    (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    try:
        for multi in (False, True):
            name = 'multi' if multi else 'ordinary'
            c.file(new=True, force=True); c.undoInfo(state=True)
            controller = MayaPanelController()
            fit_input(c, om, controller, multi=multi, opm=True, complete=True, attachments=True)
            before_identity = scene_identity()
            before_skin = skin_snapshot(include_non_mesh=True)
            # Use the public default flood counts, not a reduced proxy count.
            result = controller.face_original_build(':')
            assert c.getAttr('FaceFitSkeleton.buildCompleted')
            built_identity = scene_identity()
            built_skin = skin_snapshot(include_non_mesh=True)
            built_poses = observe()
            state = c.undoInfo(query=True, state=True)
            c.undoInfo(stateWithoutFlush=False)
            try:
                motion = validate_lower_motion(c, complete=True, attachments=True)
            finally:
                c.undoInfo(stateWithoutFlush=state)
            report['cases'][name] = {'stages': list(result['stages']), 'skin_nodes': len(built_skin), 'poses': len(built_poses)}
            c.undo(); assert not c.objExists('FaceMotionSystem')
            undone_identity = scene_identity()
            (OUTPUT / (name + '-undo-difference.json')).write_text(json.dumps({
                'extra': {key: value for key, value in undone_identity.items() if key not in before_identity},
                'missing': {key: value for key, value in before_identity.items() if key not in undone_identity},
                'changed': {key: [value, undone_identity[key]] for key, value in before_identity.items() if key in undone_identity and value != undone_identity[key]}}, indent=2), encoding='utf8')
            report['cases'][name]['undo_skin_error'] = compare(before_skin, skin_snapshot(include_non_mesh=True))
            compare(before_identity, undone_identity)
            undo_skin_error = compare(before_skin, skin_snapshot(include_non_mesh=True))
            c.redo(); assert c.getAttr('FaceFitSkeleton.buildCompleted')
            compare(built_identity, scene_identity())
            redo_skin_error = compare(built_skin, skin_snapshot(include_non_mesh=True))
            redo_pose_error = compare(built_poses, observe())
            saved = OUTPUT / (name + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            reopen_skin_error = compare(built_skin, skin_snapshot(include_non_mesh=True))
            reopen_pose_error = compare(built_poses, observe())
            reopened = validate_lower_motion(c, complete=True, attachments=True)
            assert max(abs(reopened[k] - v) for k, v in motion.items()) < 1e-5
            report['cases'][name] = {'stages': list(result['stages']), 'motion': motion,
                'undo_redo': True, 'saved_reopened': True, 'public_default_smoothing': True,
                'skin_nodes': len(built_skin), 'undo_skin_error': undo_skin_error,
                'redo_skin_error': redo_skin_error, 'redo_pose_error': redo_pose_error,
                'reopen_skin_error': reopen_skin_error, 'reopen_pose_error': reopen_pose_error}
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion: Path(completion).write_text(json.dumps({'pid': os.getpid(), 'status': report['status']}), encoding='utf8')
        if quit_on_finish: utils.executeDeferred(c.quit, force=True)
