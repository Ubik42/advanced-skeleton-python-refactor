"""Whole Sam scans in the same native UI, with observation-only scan records."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/auto-place-full-trace'
if os.environ.get('ADV_SAM_REST_INPUT')=='1':
    OUT=ROOT/'validation/results/auto-place-rest-full-trace'
INPUT_KIND='original_Sam_skin_input' if os.environ.get('ADV_SAM_REST_INPUT')=='1' else 'exported_Sam_deformed_mesh'
MODE = ''
SCANS = {'native': [], 'python': []}


def record(axis, index, hits, four, failed):
    from maya import cmds as c
    SCANS[MODE].append(dict(axis=axis, index=index, hits=hits,
        four=bool(four), failed=bool(failed), x=c.getAttr('asFitScanCurve.translateX')))
    if len(SCANS[MODE])%25==0:
        # Retain actual observations if a whole source scan exceeds the
        # runner's resource limit; a live process is never inferred from this.
        (OUT/'scan-progress.json').write_text(json.dumps(dict(
            pid=os.getpid(),mode=MODE,scans=SCANS)),encoding='utf-8')


def capture_native():
    from maya import mel
    def read(kind, variable):
        return mel.eval(f'global {kind} ${variable};${variable}=${variable};')
    record(read('string', 'advProbeAxis'), read('int', 'advProbeIndex'),
           read('int', 'advProbeHits'), read('int', 'advProbeFour'), read('int', 'advProbeFail'))


def rest_fixture():
    """Read Sam's actual skin input, without changing pose or source topology."""
    from maya import cmds as c
    c.file('D:/3D/_tools/_DCC/MayaCraft/files/Rigged/sam/sam.mb',
           open=True,force=True,executeScriptNodes=False)
    shapes=c.skinCluster('skinCluster21',query=True,geometry=True)
    assert len(shapes)==1,shapes
    source=c.listConnections('skinCluster21.input[0].inputGeometry',
                             source=True,destination=False,plugs=True)
    assert len(source or [])==1,source
    transform=c.listRelatives(shapes[0],parent=True,fullPath=True)[0]
    matrix=c.xform(transform,query=True,worldSpace=True,matrix=True)
    bridge=c.createNode('mesh',name='RestInputBridgeShape')
    bridge_transform=c.listRelatives(bridge,parent=True)[0]
    c.connectAttr(source[0],bridge+'.inMesh')
    c.polyEvaluate(bridge,vertex=True)
    mesh=c.duplicate(bridge_transform,name='AutoPlaceRestSam',returnRootsOnly=True)[0]
    c.xform(mesh,worldSpace=True,matrix=matrix)
    c.makeIdentity(mesh,apply=True,translate=True,rotate=True,scale=True)
    c.delete(bridge_transform)
    assert not any(c.nodeType(node)=='skinCluster' for node in c.listHistory(mesh) or [])
    c.select(mesh,replace=True)
    model=OUT/'rest-model.ma'
    c.file(str(model),exportSelected=True,type='mayaAscii',force=True)
    c.file(new=True,force=True)
    c.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),i=True,executeScriptNodes=False)
    c.file(str(model),i=True,executeScriptNodes=False)
    if not c.objExists('FitSkeleton.fitSkeletonTemplate'):
        c.addAttr('FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
    c.setAttr('FitSkeleton.fitSkeletonTemplate','biped',type='string')
    return (mesh,)


def main(*, standalone=False, quit_on_finish=True):
    global MODE
    from maya import cmds as c, mel
    from PySide2 import QtWidgets
    from maya_original_fit_auto_place_sample import fixture, snapshot
    from adv_migration.mel_inventory import PROC_HEADER, _matching_brace
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.application.fit_auto_place import AutoPlaceFit
    from adv_py.adapters import maya_fit_auto_place as engine
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), scope='Whole identical input source/Python trace; original default-model success not accepted',input_kind=INPUT_KIND)
    original_detect = engine.detect_fingers
    option_names = ('asHaveRanThisVersion', 'asDock')
    options = {name: c.optionVar(query=name) if c.optionVar(exists=name) else None for name in option_names}
    try:
        source = (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8-sig')
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        # Existing workspace ownership makes AdvancedSkeleton build in Maya,
        # bypassing its floating showWindow branch without changing the MEL.
        if c.workspaceControl('asWorkspaceControl', exists=True):
            c.deleteUI('asWorkspaceControl', control=True)
        c.workspaceControl('asWorkspaceControl', label='ADV reference', dockToControl=('ToolBox', 'left'), retain=False)
        c.optionVar(intValue=('asHaveRanThisVersion', 1))
        c.optionVar(intValue=('asDock', 1))
        mel.eval('AdvancedSkeleton;')
        assert not c.window('AdvancedSkeletonWindow', exists=True)
        source_procedure = next(match for match in PROC_HEADER.finditer(source) if match['name'] == 'asFitAutoPlace')
        end = _matching_brace(source, source_procedure.end() - 1)
        procedure = source[source_procedure.start():end+1].replace('global proc asFitAutoPlace ()', 'global proc advPyReferenceFullAutoPlace ()', 1)
        marker = '//$fourFingerHit (double-checking first)'
        assert procedure.count(marker) == 1
        observer = '''global string $advProbeAxis;global int $advProbeIndex,$advProbeHits,$advProbeFour,$advProbeFail;
$advProbeAxis=$zxy[$z];$advProbeIndex=$i;$advProbeHits=$numHits;$advProbeFour=$fourFingerHit;$advProbeFail=$fingerGrowFail;
python("import maya_auto_place_full_trace as p;p.capture_native()");
'''
        mel.eval(procedure.replace(marker, observer + marker))
        skin = rest_fixture() if os.environ.get('ADV_SAM_REST_INPUT')=='1' else fixture()
        c.file(rename=str(OUT / 'input.mb'))
        c.file(save=True, type='mayaBinary', force=True)
        constraint_state = c.polySelectConstraint(query=True, stateString=True)
        for MODE in ('native', 'python'):
            c.file(str(OUT / 'input.mb'), open=True, force=True, executeScriptNodes=False)
            QtWidgets.QApplication.processEvents()
            mel.eval(constraint_state)
            c.selectMode(object=True)
            c.select(clear=True)
            for field, value in (('Skin', ' '.join(skin)), ('All', ''), ('RightEye', ''), ('LeftEye', '')):
                c.textField('asBody' + field + 'TextField', edit=True, text=value)
            row = dict(input=snapshot(), selection_constraints=constraint_state)
            report[MODE] = row
            (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            try:
                if MODE == 'native':
                    mel.eval('advPyReferenceFullAutoPlace;')
                else:
                    def observed(state):
                        record(state.axis, state.index, state.hits, state.four_fingers, state.finger_grow_failed)
                        return original_detect(state)
                    engine.detect_fingers = observed
                    host = MayaFitJointHost()
                    host._fit_auto_place_interactive = False
                    result = AutoPlaceFit(host).apply(skin=skin)
                    row['result'] = dict(axes=result.axes_completed, four=result.finger_detected, guides=result.guides_active)
                row['returned'] = True
            except Exception:
                row.update(returned=False, error=traceback.format_exc())
            finally:
                engine.detect_fingers = original_detect
            row['output'] = snapshot()
            c.file(rename=str(OUT / (MODE + '-output.mb')))
            c.file(save=True, type='mayaBinary', force=True)
            report['scans'] = SCANS
            (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        assert report['native']['input'] == report['python']['input'], 'Initial Fit states differ'
        assert SCANS['native'] == SCANS['python'], 'Whole source scan decisions differ'
        native=report['native']['output'];python=report['python']['output']
        assert native['guides']==python['guides'], 'Guide completion states differ'
        assert native['joints'].keys()==python['joints'].keys()
        error=max(abs(a-b) for name,row in native['joints'].items()
                  for a,b in zip(row['matrix'],python['joints'][name]['matrix']))
        fat_error=max(abs(row['fat']-python['joints'][name]['fat'])
                      for name,row in native['joints'].items() if row['fat'] is not None)
        assert error<=1e-4 and fat_error<=1e-4,(error,fat_error)
        assert report['native']['returned'] and report['python']['returned']
        report['comparison']=dict(scan_records=len(SCANS['native']),scan_differences=0,
            maximum_joint_matrix_error=error,maximum_fat_error=fat_error,
            whole_success_accepted=False)
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc(), scans=SCANS)
    finally:
        engine.detect_fingers = original_detect
        if c.workspaceControl('asWorkspaceControl', exists=True):
            c.deleteUI('asWorkspaceControl', control=True)
        for name, value in options.items():
            if value is None:
                c.optionVar(remove=name)
            else:
                c.optionVar(intValue=(name, int(value)))
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1
