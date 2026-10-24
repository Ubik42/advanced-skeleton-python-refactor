"""Concentrated current public Body lifecycle in one owned Maya instance.

This checks lifecycle preservation, not numerical parity with the MEL solver.
The Fit input is the untouched original biped asset.
"""
from pathlib import Path
import json
import os
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation/results/body-lifecycle-current'


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds
    from maya_original_biped_current_smoke import main as run_case
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'cases': {}}
    def save_report():
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    source = ROOT / 'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'
    cases = (
        ('traditional', dict()),
        ('opm', dict(opm=True)),
        ('bendy', dict(bendy=True, restricted_skin=True)),
    )
    try:
        requested = os.environ.get('ADV_BODY_LIFECYCLE_MODES', '').split(',')
        requested = tuple(name for name in requested if name)
        if requested:
            assert len(set(requested)) == len(requested)
            assert set(requested) <= {name for name, _ in cases}
            cases = tuple(case for case in cases if case[0] in requested)
        report['requested_cases'] = [name for name, _ in cases]
        for name, options in cases:
            report['active_case'] = name
            save_report()
            print('Body lifecycle case: ' + name, flush=True)
            report['cases'][name] = run_case(
                source, OUT / name, rebuild=True, export=True,
                standalone=False, **options)
            save_report()
        report.pop('active_case', None)
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'
        report['traceback'] = traceback.format_exc()
    finally:
        save_report()
        print(json.dumps(report, indent=2), flush=True)
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:
            Path(completion).write_text(json.dumps({
                'pid': os.getpid(), 'status': report['status']}), encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            cmds.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(standalone=True))
