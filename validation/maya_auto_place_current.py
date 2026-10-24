"""Current AutoPlace source phase parity, retries and Sam failure rollback.

The controlled success chain is not a complete biped AutoPlace acceptance.
Sam's original failure is preserved, not converted into a successful scan.
"""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/auto-place-current'


def retry_parity(c, mel):
    from maya_fit_auto_place_finger_detection_parity import fixture, snapshot, native_procedure
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_state import FitAutoPlaceScanState
    from adv_py.adapters.maya_fit_auto_place_fingers import detect_fingers
    source = (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8-sig')
    mel.eval(native_procedure(source))
    rows = []
    for collision in ('curve', 'pivot'):
        def seed():
            fixture()
            if collision == 'curve':
                curve = c.curve(degree=1, name='FingerCurveIndex', point=((0, 0, 0), (1, 0, 0)))
                c.parent(curve, 'asFitPivotsFingers')
            else:
                c.createNode('transform', name='asFitPivotIndexFinger4', parent='asFitPivotsFingers')
            c.select(clear=True)
        seed()
        scene = OUT / (collision + '-retry-input.mb')
        c.file(rename=str(scene))
        c.file(save=True, type='mayaBinary', force=True)
        native_error = None
        try:
            mel.eval('advPyReferenceDetectFingers;')
        except (RuntimeError, ValueError) as error:
            native_error = str(error)
        native = snapshot()
        c.file(str(scene), open=True, force=True, executeScriptNodes=False)
        host = MayaFitJointHost()
        state = FitAutoPlaceScanState(host, host._cmds, 0., -8., -2., 2., 10., 'biped',
            axis='y', hits=4, step_z=-.16, direction=(0, 1, 0), project_on='CombinedSkinUpper_M')
        baseline = snapshot()
        uuids = set(c.ls(uuid=True))
        python_error = None
        try:
            with host.transaction('Source retry detection'):
                detect_fingers(state)
        except (RuntimeError, ValueError) as error:
            python_error = str(error)
        if collision == 'curve':
            assert native_error and 'FingerCurveIndex' in native_error, native_error
            assert python_error and 'FingerCurveIndex' in python_error, python_error
            assert snapshot() == baseline, 'Retry exception did not roll back the input'
            assert set(c.ls(uuid=True)) == uuids
            rows.append(dict(case=collision, status='passed', source_failure='FingerCurveIndex ambiguity',
                             python_same_failure=True, rollback=True))
        else:
            assert native_error is None and python_error is None, (native_error, python_error)
            from maya_fit_auto_place_finger_detection_parity import compare
            maximum = compare(native, snapshot())
            assert maximum <= 1e-6, maximum
            rows.append(dict(case=collision, status='passed', maximum_error=maximum,
                             source_requested_name_preserved=True))
    return rows


def sam_scan(c):
    from maya_original_fit_auto_place_sample import fixture, snapshot
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.application.fit_auto_place import AutoPlaceFit
    skin = fixture()
    baseline = snapshot()
    uuids = set(c.ls(uuid=True))
    display = c.jointDisplayScale(query=True)
    host = MayaFitJointHost()
    host._fit_auto_place_interactive = False
    failure = None
    result = None
    try:
        result = AutoPlaceFit(host).apply(skin=skin)
    except (RuntimeError, ValueError) as error:
        failure = str(error)
    if result is not None:
        if result.guides_active:
            c.file(rename=str(OUT / 'sam-guides.mb'))
            c.file(save=True, type='mayaBinary', force=True)
        return dict(status='guides_active' if result.guides_active else 'not_detected',
                    axes=result.axes_completed, finger_detected=result.finger_detected,
                    guides_active=result.guides_active,
                    scope='Current Python full Sam input; original full success not confirmed')
    assert failure and 'FingerCurveIndex' in failure, failure
    assert snapshot() == baseline, 'Sam failure did not restore Fit matrices and fat'
    assert set(c.ls(uuid=True)) == uuids, 'Sam failure left scan nodes'
    assert c.jointDisplayScale(query=True) == display
    return dict(status='expected_source_failure', error=failure, rollback=True,
                scope='Python full Sam input preserves the recorded original ambiguity; no complete success claim')


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        raise ValueError('Use one owned Maya GUI session')
    from maya import cmds as c, mel
    from maya_fit_auto_place_phases import main as phases
    from maya_fit_auto_place_finger_detection_parity import main as fingers
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(),
                  scope='Current native phase parity and retry semantics; complete biped AutoPlace not accepted')
    try:
        if os.environ.get('ADV_SAM_ONLY') == '1':
            report['sam'] = sam_scan(c)
            report['status'] = 'incomplete'
            return 1
        from adv_py.core.fit_auto_place import source_fit_finger_force
        math_rows=[]
        for degrees in (-360.,-180.,-90.,-63.43494882292201,-33.6900675259798,
                        0.,33.6900675259798,63.43494882292201,90.,180.,360.):
            expected=[]
            for expression in ('-98*(1-$advFactor)','0','98*$advFactor'):
                expected.append(mel.eval(f'float $advDegrees={degrees!r};float $advFactor=sin(deg_to_rad($advDegrees));float $advValue={expression};$advValue=$advValue;'))
            maximum=max(abs(a-b) for a,b in zip(expected,source_fit_finger_force(degrees)))
            assert maximum<=1e-12,(degrees,maximum)
            math_rows.append(dict(degrees=degrees,maximum_error=maximum))
        report['force_math']=math_rows
        phase_status = phases(OUT / 'phases', initialize=False)
        report['phases'] = json.loads((OUT / 'phases/phases.json').read_text())
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        result = fingers(OUT / 'fingers', initialize=False)
        report['fingers'] = result
        report['retries'] = retry_parity(c, mel)
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if os.environ.get('ADV_PHASES_ONLY') != '1':
            report['sam'] = sam_scan(c)
        report['status'] = 'passed' if phase_status == 0 and result['status'] == 'passed' else 'failed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1
