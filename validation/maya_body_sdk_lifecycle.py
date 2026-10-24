"""Compare actual SDK poses in the saved pre/post Body rebuild scenes.

This is preservation evidence, not a substitute for MEL solver parity.
No build is repeated: the full lifecycle suite supplies both native scenes.
"""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/body-sdk-current'


def capture_scene(path, poses=None):
    from maya import cmds as c
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_driving_registration import SDK_MARKER
    c.file(str(path), open=True, force=True, executeScriptNodes=False)
    # The lifecycle intentionally saves the input at frame 1 and the rebuilt
    # scene at frame 5. Compare SDK poses at the same animation time.
    c.currentTime(1)
    host = MayaBodyBuildHost()
    registration = host.read_character_registration()
    plan = host.plan_body_driving_fit_sync(registration.container)
    assert plan and plan.controls
    drivers = tuple((control.path + '.' + attribute.name, attribute)
                    for control in plan.controls for attribute in control.attributes
                    if attribute.curves)
    baseline = {plug: c.getAttr(plug) for plug, _ in drivers}
    if poses is None:
        poses = [('neutral', {})]
        for plug, attribute in drivers:
            limits = (attribute.minimum, attribute.maximum)
            for label, value in zip(('minimum', 'maximum'), limits):
                if value is None:
                    value = baseline[plug] + (-1. if label == 'minimum' else 1.)
                poses.append((plug + ':' + label, {plug: value}))
    sdk = tuple(node.path for node in registration.nodes
                if c.objExists(node.path + '.' + SDK_MARKER))
    assert sdk
    targets = tuple(sorted(set(sdk) | {joint.path for joint in registration.body}))
    curve_data = {}
    for _, attribute in drivers:
        for curve in attribute.curves:
            key = curve.rsplit(':', 1)[-1]
            data = dict(
                type=c.nodeType(curve),
                inputs=tuple(c.keyframe(curve, query=True, floatChange=True) or []),
                values=tuple(c.keyframe(curve, query=True, valueChange=True) or []),
                weighted=c.getAttr(curve + '.weightedTangents'),
                pre=c.getAttr(curve + '.preInfinity'),
                post=c.getAttr(curve + '.postInfinity'))
            for flag in ('inTangentType', 'outTangentType', 'inAngle', 'outAngle',
                         'inWeight', 'outWeight', 'lock', 'weightLock'):
                data[flag] = tuple(c.keyTangent(curve, query=True, **{flag: True}) or [])
            curve_data[key] = data
    samples = []
    try:
        for _, values in poses:
            for plug, value in baseline.items():
                c.setAttr(plug, value)
            for plug, value in values.items():
                c.setAttr(plug, value)
            c.dgdirty(allPlugs=True)
            values = []
            for target in targets:
                values.extend(c.xform(target, query=True, worldSpace=True, matrix=True))
                if target in sdk:
                    for attribute in ('translate', 'rotate', 'scale'):
                        values.extend(c.getAttr(target + '.' + attribute)[0])
            samples.append(tuple(values))
    finally:
        for plug, value in baseline.items():
            c.setAttr(plug, value)
    return poses, targets, curve_data, samples, len(sdk)


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), sample_frame=1, cases={})
    try:
        for mode in ('traditional', 'opm', 'bendy'):
            report['active_case'] = mode
            base = ROOT / 'validation/results/body-lifecycle-current' / mode
            poses, targets, curves, before, count = capture_scene(base / 'original-biped-current.mb')
            _, actual_targets, actual_curves, after, actual_count = capture_scene(
                base / 'original-biped-rebuilt.mb', poses)
            assert targets == actual_targets
            assert count == actual_count
            assert curves == actual_curves, 'SDK native keys/tangents/infinity changed'
            assert len(before) == len(after)
            assert all(len(a) == len(b) for a, b in zip(before, after))
            error = max(abs(x-y) for a, b in zip(before, after) for x, y in zip(a, b))
            assert error <= 1e-4, (mode, error)
            report['cases'][mode] = dict(poses=len(poses), sdk_layers=count,
                native_curves=len(curves), native_curve_data_identical=True,
                body_and_sdk_max_error=error)
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
