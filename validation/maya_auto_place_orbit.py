"""Source Ctrl orbit channel semantics, without repeating body scanning."""
from pathlib import Path
import json, os, sys, traceback
from unittest.mock import patch
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/auto-place-orbit'


def snapshot(namespace):
    from maya import cmds as c
    prefix=namespace+':' if namespace else ''
    return {name:c.xform(address,query=True,worldSpace=True,matrix=True)
            for name,address in (('camera','persp'),('orbit',prefix+'asFitOrbitA'))}


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_projection import auto_orbit,defer_camera_restore
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[],
                scope='Exact asFitAutoOrbit executed body with deterministic modifier input; root and character namespace, nonunit camera/guide scale')
    try:
        text=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8')
        start=text.index('global proc asFitAutoOrbit (')
        end=text.index('global proc asFitAutoPlaceFromScanCurves',start)
        procedure=text[start:end].replace('asFitAutoOrbit (float $camOrbitStep)',
                'advReferenceOrbit (float $camOrbitStep, int $modifier)')
        procedure=procedure.replace('int $modifier=`getModifiers`;','')
        camera_start=text.index('$tra=`xform -q -ws -t persp`;',text.index('global proc asFitAutoPlace ('))
        camera_end=text.index('\n\n',camera_start)
        camera_body=text[camera_start:camera_end]
        # Only the input modifier command is supplied deterministically. The
        # source branch, rotate and joint camera xform stay unchanged.
        for namespace in ('','OtherRig'):
            directory='auto-place-namespace-full' if namespace else 'auto-place-proxy-full'
            filename='guides.mb' if namespace else 'native-output.mb'
            path=ROOT/'validation/results'/directory/filename
            prefix=namespace+':' if namespace else ''
            source=procedure
            if namespace:
                source=source.replace('asFitOrbitA',prefix+'asFitOrbitA').replace('asFitOrbitB',prefix+'asFitOrbitB')
            mel.eval(source)
            for modifier in (() if os.environ.get('ADV_CAMERA_ONLY')=='1' else (0,4,5)):
                reference=None
                for mode in ('native','python'):
                    c.file(str(path),open=True,force=True,executeScriptNodes=False)
                    c.setAttr('persp.scale',1.2,.9,1.1,type='double3')
                    c.setAttr(prefix+'asFitOrbitA.scale',.8,1.25,1.1,type='double3')
                    c.setAttr(prefix+'asFitOrbitB.rotate',17.,-23.,31.,type='double3')
                    before=snapshot(namespace);scale=c.getAttr('persp.scale')[0]
                    states=[]
                    for step in (1.8,-3.6,90.):
                        if mode=='native':mel.eval('advReferenceOrbit '+str(step)+' '+str(modifier)+';')
                        else:
                            with patch.object(c,'getModifiers',return_value=modifier):
                                auto_orbit(MayaFitJointHost(namespace=namespace or None),step)
                        assert c.getAttr('persp.scale')[0]==scale
                        state=snapshot(namespace);states.append(state)
                        if modifier!=4:assert state==before
                    if reference is None:reference=states
                    else:
                        errors=[max(abs(x-y) for name in a for x,y in zip(a[name],b[name]))
                                for a,b in zip(reference,states)]
                        assert max(errors)<=1e-8,errors
                        if modifier==4:assert states[-1]!=before
                        report['cases'].append(dict(namespace=namespace or ':',modifier=modifier,
                            steps=(1.8,-3.6,90.),maximum_matrix_errors=errors,camera_scale_preserved=True,status='passed'))
            reference=None
            for mode in ('native','python'):
                import maya.utils
                c.file(str(path),open=True,force=True,executeScriptNodes=False)
                maya.utils.processIdleEvents()
                c.xform('persp',worldSpace=True,translation=(12.3456789123,-23.4567891234,34.5678912345),
                        rotation=(17.1234567891,-23.2345678912,31.3456789123))
                c.setAttr('persp.scale',1.2,.9,1.1,type='double3')
                before=snapshot(namespace);scale=c.getAttr('persp.scale')[0]
                pending=Counter(c.evalDeferred(list=True) or [])
                if mode=='native':
                    body=camera_body.replace('asFitOrbitB',prefix+'asFitOrbitB')
                    mel.eval('global proc advReferenceCameraRestore(){float $tra[],$rot[];'+body+';}')
                    mel.eval('advReferenceCameraRestore;')
                else:defer_camera_restore(MayaFitJointHost(namespace=namespace or None))
                queued=[command for command in (Counter(c.evalDeferred(list=True) or [])-pending).elements()
                        if command.startswith('xform -ws -t ') and command.endswith(' persp')]
                assert len(queued)==1,queued
                # Restoration must be queued rather than immediately executed.
                c.xform('persp',worldSpace=True,translation=(50,60,70),rotation=(40,50,60))
                assert snapshot(namespace)!=before
                # Maya does not drain this MEL queue reentrantly while the
                # current Python command runs. Verify actual queued text, then
                # execute that exact source/Python command to compare channels.
                mel.eval(queued[0])
                state=snapshot(namespace)
                assert c.getAttr('persp.scale')[0]==scale
                expected=tuple(float(format(v,'.10g')) for v in (12.3456789123,-23.4567891234,34.5678912345))
                assert max(abs(a-b) for a,b in zip(c.xform('persp',query=True,worldSpace=True,translation=True),expected))<=1e-8
                if reference is None:reference=(state,queued[0])
                else:
                    assert reference[1]==queued[0],(reference[1],queued[0])
                    error=max(abs(a-b) for name in state for a,b in zip(reference[0][name],state[name]))
                    assert error<=1e-8,error
                    report['cases'].append(dict(namespace=namespace or ':',operation='deferred-camera-restore',
                        maximum_matrix_error=error,camera_scale_preserved=True,queued_command=queued[0],
                        source_python_queue_text_identical=True,queued_command_executed_explicitly=True,
                        actual_idle_dispatch_not_accepted=True,status='passed'))
        report['status']='passed'
    except Exception:report.update(status='failed',error=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
