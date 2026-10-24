"""Rebuild pre-owner-marker Body data and retain authored native SDK curves."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/body-legacy-sdk-current'


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    from maya_body_sdk_lifecycle import capture_scene
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), cases={})
    try:
        source = ROOT / 'validation/results/body-lifecycle-current/traditional/original-biped-current.mb'
        labels = ('pre-owner-marker', 'authored-sdk')
        requested = tuple(filter(None, os.environ.get('ADV_LEGACY_SDK_CASES', ','.join(labels)).split(',')))
        if not requested or len(set(requested)) != len(requested) or set(requested) - set(labels):
            raise ValueError('ADV_LEGACY_SDK_CASES must select pre-owner-marker/authored-sdk')
        report['requested_cases'] = requested
        for label in requested:
            authored = label == 'authored-sdk'
            report['active_case'] = label
            c.file(str(source), open=True, force=True, executeScriptNodes=False)
            c.undoInfo(state=True)
            assert not c.objExists('FKIKArm_R.advPySourceRpModeReverse')
            if authored:
                c.addAttr('Fingers_L.cup', edit=True, minValue=-15., maxValue=20.,
                          softMinValue=-12., softMaxValue=18.)
                c.setAttr('Fingers_L.cup', 3.)
                curve = 'SDKFKCup_L_rotateX1'
                c.keyTangent(curve, edit=True, weightedTangents=True)
                c.keyTangent(curve, edit=True, lock=False, weightLock=False,
                             inTangentType='fixed', outTangentType='fixed',
                             inAngle=15., outAngle=-30., inWeight=2., outWeight=3.)
            before_file = OUT / (label + '-before.mb')
            c.file(rename=str(before_file)); c.file(save=True, type='mayaBinary', force=True)
            poses, targets, curves, samples, count = capture_scene(before_file)
            host = MayaBodyBuildHost()
            original = CaptureBodyCharacterPreservation(host).execute()
            MayaPanelController().body_rebuild(':', 'LegacyReplacement')
            retained = CaptureBodyCharacterPreservation(MayaBodyBuildHost()).execute()
            for skin in original.skins:
                actual = next(row for row in retained.skins if row.uuid == skin.uuid)
                assert actual.weights == skin.weights
                assert actual.blend_weights == skin.blend_weights
                assert actual.component_memberships == skin.component_memberships
            assert {row.uuid for row in original.curves} == {row.uuid for row in retained.curves}
            c.undo()
            assert MayaBodyBuildHost().read_character_registration() == original.registration
            c.redo()
            assert MayaBodyBuildHost().read_character_registration() == retained.registration
            after_file = OUT / (label + '-after.mb')
            c.file(rename=str(after_file)); c.file(save=True, type='mayaBinary', force=True)
            _, actual_targets, actual_curves, actual_samples, actual_count = capture_scene(after_file, poses)
            assert targets == actual_targets and count == actual_count
            assert curves == actual_curves, 'Authored native SDK interpolation changed'
            assert all(len(a) == len(b) for a, b in zip(samples, actual_samples))
            error = max(abs(x-y) for a, b in zip(samples, actual_samples) for x, y in zip(a, b))
            assert error <= 1e-4, (label, error)
            if authored:
                driver = MayaBodyBuildHost().plan_body_driving_fit_sync('|Group|FitSkeleton')
                cup = next(attribute for control in driver.controls if control.path.endswith('|Fingers_L')
                           for attribute in control.attributes if attribute.name == 'cup')
                assert (cup.minimum, cup.maximum, cup.soft_minimum, cup.soft_maximum) == (-15.,20.,-12.,18.)
            report['cases'][label] = dict(poses=len(poses), sdk_layers=count,
                curves=len(curves), maximum_error=error, native_curve_data_identical=True,
                retained_skin_animation=True, undo_redo=True, reopened=True,
                authored_driver_limits_preserved=authored)
        report.pop('active_case', None)
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (quit_on_finish or standalone):
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(standalone=True))
