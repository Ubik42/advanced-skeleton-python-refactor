"""Concentrated source Pin/AimAt comparisons for receivers ignoring parents."""
from pathlib import Path
import json,os,traceback
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/results/source-attachment-no-inherit-current'

def main(standalone=False,quit_on_finish=True):
    from maya import cmds as c
    import maya_source_pin_matrix as pin
    import maya_source_fit_aim_alignment as aim
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid())
    previous=os.environ.get('ADV_ATTACHMENT_NO_INHERIT')
    os.environ['ADV_ATTACHMENT_NO_INHERIT']='1'
    try:
        for name,suite in (('pin',pin),('aim',aim)):
            saved=suite.OUT;suite.OUT=OUT/name
            try:result=suite.main(standalone=False,quit_on_finish=False)
            finally:suite.OUT=saved
            report[name]=json.loads((OUT/name/'report.json').read_text(encoding='utf-8'))
            assert result==0,report[name]
        report['status']='passed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        if previous is None:os.environ.pop('ADV_ATTACHMENT_NO_INHERIT',None)
        else:os.environ['ADV_ATTACHMENT_NO_INHERIT']=previous
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
