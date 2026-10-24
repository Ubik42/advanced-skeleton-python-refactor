"""Allow Maya's normal idle loop to execute source/Python camera restore.

Each observer is queued after the tested restore and runs after main returns;
the harness never tries to drain a MEL queue inside the active Python command.
"""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/auto-place-camera-idle'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_projection import defer_camera_restore
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[],
        scope='Actual native Maya idle dispatch of source/Python camera T/R restoration, root and character namespace; saved guides, no rescanning')
    text=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8')
    start=text.index('$tra=`xform -q -ws -t persp`;',text.index('global proc asFitAutoPlace ('))
    body=text[start:text.index('\n\n',start)]
    cases=(('', 'native'),('', 'python'),('OtherRig','native'),('OtherRig','python'))
    reference={}

    def write():
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

    def complete(error=None):
        report['status']='failed' if error else 'passed'
        if error:report['error']=error
        write()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred('quit -force')

    def observe(index,namespace,mode,scale):
        try:
            translation=c.xform('persp',query=True,worldSpace=True,translation=True)
            expected=[float(format(v,'.10g')) for v in (12.3456789123,-23.4567891234,34.5678912345)]
            error=max(abs(a-b) for a,b in zip(translation,expected))
            assert error<=1e-8,(mode,translation,expected)
            assert c.getAttr('persp.scale')[0]==scale
            matrix=c.xform('persp',query=True,worldSpace=True,matrix=True)
            row=dict(namespace=namespace or ':',mode=mode,translation_error=error,
                     camera_scale_preserved=True,actual_idle_dispatch=True,status='passed')
            if mode=='native':reference[namespace]=matrix
            else:
                row['native_matrix_error']=max(abs(a-b) for a,b in zip(reference[namespace],matrix))
                assert row['native_matrix_error']<=1e-8,row
            report['cases'].append(row);write()
            if index+1==len(cases):complete()
            else:c.evalDeferred(lambda:advance(index+1))
        except Exception:complete(traceback.format_exc())

    def advance(index):
        try:
            namespace,mode=cases[index]
            directory='auto-place-namespace-full' if namespace else 'auto-place-proxy-full'
            filename='guides.mb' if namespace else 'native-output.mb'
            c.file(str(ROOT/'validation/results'/directory/filename),open=True,force=True,executeScriptNodes=False)
            c.xform('persp',worldSpace=True,translation=(12.3456789123,-23.4567891234,34.5678912345),
                    rotation=(17.1234567891,-23.2345678912,31.3456789123))
            c.setAttr('persp.scale',1.2,.9,1.1,type='double3');scale=c.getAttr('persp.scale')[0]
            if mode=='native':
                local=body.replace('asFitOrbitB',('OtherRig:' if namespace else '')+'asFitOrbitB')
                mel.eval('global proc advReferenceIdleRestore(){float $tra[],$rot[];'+local+';}')
                mel.eval('advReferenceIdleRestore;')
            else:defer_camera_restore(MayaFitJointHost(namespace=namespace or None))
            c.xform('persp',worldSpace=True,translation=(50,60,70),rotation=(40,50,60))
            assert c.xform('persp',query=True,worldSpace=True,translation=True)==[50.,60.,70.]
            c.evalDeferred(lambda:observe(index,namespace,mode,scale))
        except Exception:complete(traceback.format_exc())

    write()
    c.evalDeferred(lambda:advance(0))
    # Completion is written by the final idle observer, never on this return.
    return None
