"""One owned Maya process for related export-retirement and Spline migration."""
from pathlib import Path
import json
import os
import traceback


def main(*,standalone=False,quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds
    import maya_export_retirement_lifecycle as retirement
    import maya_source_spline_alignment_lifecycle as alignment
    out=Path(__file__).resolve().parent/'results/export-alignment-current'
    out.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases={})
    try:
        suites=dict(retirement=retirement,alignment=alignment)
        selected=tuple(filter(None,os.environ.get('ADV_EXPORT_ALIGNMENT_CASES','retirement,alignment').split(',')))
        if not selected or len(set(selected))!=len(selected) or set(selected)-suites.keys():
            raise ValueError('ADV_EXPORT_ALIGNMENT_CASES must select retirement/alignment')
        report['requested_cases']=selected
        for name in selected:
            suite=suites[name]
            report['stage']=name
            (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            result=suite.main(standalone=False,quit_on_finish=False)
            report['cases'][name]=dict(status='passed' if result==0 else 'failed',
                                      report=str(suite.OUT/'report.json'))
        report.update(status='passed' if all(row['status']=='passed' for row in report['cases'].values())
                      else 'failed',stage='complete')
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (standalone or quit_on_finish):
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if standalone:maya.standalone.uninitialize()
        elif quit_on_finish:cmds.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
