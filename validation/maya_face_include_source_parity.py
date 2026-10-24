"""Compare original MEL and Python Face rebuild for Include variants."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUT = ROOT / 'validation/results/face-include-source-current'
INPUT = ROOT / 'validation/results/face-optional-full-build/ordinary.mb'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, mel, utils
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_rebuild_source_parity import prepare_source_ui
    from maya_face_conversion_parity import skin_snapshot, observe, compare
    from adv_py.core.face_build_requirements import FaceInclude

    OUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'cases': {}}
    def save():
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    save()
    try:
        load_project_native_plugin()
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1))
        c.optionVar(intValue=('asDock', 1))
        mel.eval('AdvancedSkeleton;')
        for include in (FaceInclude.SKIP_ABOVE, FaceInclude.SKIP_BELOW,
                        FaceInclude.EYES_ONLY):
            name = include.name.lower()
            row = {'include': include.value, 'status': 'running', 'stages': []}
            report['cases'][name] = row
            save()
            try:
                c.file(str(INPUT), open=True, force=True, executeScriptNodes=False)
                prepare_source_ui(c)
                c.optionMenu('asFaceIncludeOptionMenu', edit=True, value=include.value)
                mel.eval('asFaceUpdateInfo 0;')
                row['source_include'] = c.getAttr('FaceFitSkeleton.Include', asString=True)
                row['ui_include'] = c.optionMenu('asFaceIncludeOptionMenu', query=True, value=True)
                assert row['source_include'] == include.value
                for step in range(1, 31):
                    label = c.text('stepBuild%dText' % step, query=True, label=True)
                    procedure = 'asFace' + label.split(':', 1)[1].strip()
                    mel.eval(procedure + ';')
                    mel.eval('asStepBuildComplete %d;' % step)
                    row['stages'].append(procedure)
                    save()
                native_skin = skin_snapshot(include_non_mesh=True)
                native_poses = observe()
                c.file(rename=str(OUT / (name + '-native.mb')))
                c.file(save=True, type='mayaBinary', force=True)
                c.file(str(ROOT / ('validation/results/face-include-rebuild-current/'
                                   + name + '.mb')), open=True, force=True,
                       executeScriptNodes=False)
                row['skin_error'] = compare(native_skin,
                                             skin_snapshot(include_non_mesh=True))
                row['pose_error'] = compare(native_poses, observe())
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
