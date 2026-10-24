"""Rebuild a completed Face after changing each original Include setting."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUT = ROOT / 'validation/results/face-include-rebuild-current'
INPUT = ROOT / 'validation/results/face-optional-full-build/ordinary.mb'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, utils
    from adv_py.core.face_build_requirements import FaceInclude
    from adv_py.product.maya_panel_controller import MayaPanelController
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_conversion_parity import scene_identity, skin_snapshot, compare

    OUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'input': str(INPUT), 'cases': {}}
    def save():
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    save()
    try:
        load_project_native_plugin()
        for include in (FaceInclude.SKIP_ABOVE, FaceInclude.SKIP_BELOW,
                        FaceInclude.EYES_ONLY):
            name = include.name.lower()
            row = {'include': include.value, 'status': 'running'}
            report['cases'][name] = row
            save()
            try:
                c.file(str(INPUT), open=True, force=True, executeScriptNodes=False)
                c.undoInfo(state=True)
                controller = MayaPanelController()
                assert controller.face_build_set_include(':', include.value) == include.value
                before = scene_identity()
                before_skin = skin_snapshot(include_non_mesh=True)
                built = controller.face_original_build(':')
                assert c.getAttr('FaceFitSkeleton.buildCompleted')
                assert not c.objExists('prefix_FaceGroup')
                assert len(built['stages']) == 30
                after = scene_identity()
                after_skin = skin_snapshot(include_non_mesh=True)
                c.undo()
                compare(before, scene_identity())
                row['undo_skin_error'] = compare(before_skin, skin_snapshot(include_non_mesh=True))
                c.redo()
                compare(after, scene_identity())
                row['redo_skin_error'] = compare(after_skin, skin_snapshot(include_non_mesh=True))
                output = OUT / (name + '.mb')
                c.file(rename=str(output)); c.file(save=True, type='mayaBinary', force=True)
                c.file(str(output), open=True, force=True, executeScriptNodes=False)
                row['reopened_skin_error'] = compare(after_skin, skin_snapshot(include_non_mesh=True))
                row['stages'] = len(built['stages'])
                row['skin_nodes'] = len(after_skin)
                row['status'] = 'passed'
            except Exception:
                row['status'] = 'failed'
                row['error'] = traceback.format_exc()
            save()
        report['status'] = ('passed' if all(row['status'] == 'passed'
            for row in report['cases'].values()) else 'failed')
    except Exception:
        report['status'] = 'failed'
        report['error'] = traceback.format_exc()
    finally:
        save()
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:
            Path(completion).write_text(json.dumps(
                {'pid': os.getpid(), 'status': report['status']}), encoding='utf8')
        if quit_on_finish:
            utils.executeDeferred(c.quit, force=True)
