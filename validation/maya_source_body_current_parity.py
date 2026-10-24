"""Fresh current multi-Spline/Bendy Body against the saved untouched MEL build."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUTPUT_NAME=os.environ.get('ADV_SOURCE_BODY_OUTPUT','source-body-current-parity')
if not OUTPUT_NAME or any(part in OUTPUT_NAME for part in ('/','\\','..')):
    raise ValueError('ADV_SOURCE_BODY_OUTPUT must be one results directory name')
OUT = ROOT / 'validation/results' / OUTPUT_NAME


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    from maya_original_biped_current_smoke import main as build
    from maya_original_body_pose_compare import main as compare
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid())
    try:
        if os.environ.get('ADV_SOURCE_BODY_USE_SAVED') == '1':
            previous = json.loads((OUT / 'report.json').read_text())
            report['lifecycle'] = previous['lifecycle']
            assert report['lifecycle']['status'] == 'passed'
            report['reused_saved_build'] = True
            c.file(str(OUT / 'original-biped-current.mb'), open=True, force=True, executeScriptNodes=False)
        else:
            report['lifecycle'] = build(ROOT / 'validation/results/source-spline-multi.ma', OUT,
                                        rebuild=True, export=False, opm=False, bendy=True, standalone=False)
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.core.source_limb_root_frame import decode_record
        registration = MayaBodyBuildHost().read_character_registration()
        frames = [decode_record(c.getAttr(node.path + '.advPySourceIkRootFrame'))
                  for node in registration.nodes if c.objExists(node.path + '.advPySourceIkRootFrame')]
        assert frames and all(len(frame.graph.outputs) == 12 for frame in frames)
        report['non_opm_ik_frames'] = len(frames)
        reference = ROOT / 'validation/results/original-spline-multi-nonopm-reference'
        compare(reference / 'original-spline-multi-nonopm-reference.mb',
                OUT / 'original-biped-current.mb',
                reference / 'original-spline-multi-nonopm-reference.json', OUT / 'poses.json',
                extended=True, spline_systems=('Spine_M','SplineTail_R','SplineTail_L','SplineSolo_L'),
                standalone=False)
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (standalone or quit_on_finish):
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred(lambda: c.quit(force=True))
    return 0 if report['status'] == 'passed' else 1
