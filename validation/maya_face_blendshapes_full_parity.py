"""Full original MEL versus Python Face rebuild in BlendShapes RigType."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUT = ROOT / 'validation/results/face-blendshapes-full-current'
INPUT = ROOT / 'validation/results/face-optional-full-build/ordinary.mb'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, mel, utils
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_rebuild_source_parity import prepare_source_ui
    from maya_face_conversion_parity import skin_snapshot, observe, snapshot, compare
    from adv_py.product.maya_panel_controller import MayaPanelController

    OUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'input': str(INPUT),
              'native_stages': []}
    def save():
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    save()
    try:
        load_project_native_plugin()
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1))
        c.optionVar(intValue=('asDock', 1))
        mel.eval('AdvancedSkeleton;')
        reuse = os.environ.get('ADV_FACE_BS_REUSE_NATIVE') == '1'
        if reuse:
            c.file(str(OUT / 'native.mb'), open=True, force=True,
                   executeScriptNodes=False)
            report['native_stages'] = ['saved_original_complete_build']
        else:
            c.file(str(INPUT), open=True, force=True, executeScriptNodes=False)
            prepare_source_ui(c)
            c.optionMenu('asFaceRigTypeOptionMenu', edit=True, value='BlendShapes')
            mel.eval('asFaceUpdateInfo 0;')
            assert c.getAttr('FaceFitSkeleton.RigType') == 1
            for step in range(1, 31):
                label = c.text('stepBuild%dText' % step, query=True, label=True)
                procedure = 'asFace' + label.split(':', 1)[1].strip()
                mel.eval(procedure + ';')
                mel.eval('asStepBuildComplete %d;' % step)
                report['native_stages'].append(procedure)
                save()
        native_skin = skin_snapshot(include_non_mesh=True)
        native_poses = observe()
        native_snapshot = snapshot()
        native_joints = {joint: c.xform(joint, query=True, worldSpace=True,
                                        matrix=True) for joint in c.ls(type='joint')}
        report['native_blendshapes'] = len(c.ls('asFaceBS*', type='blendShape') or [])
        if not reuse:
            c.file(rename=str(OUT / 'native.mb'))
            c.file(save=True, type='mayaBinary', force=True)
        c.file(str(INPUT), open=True, force=True, executeScriptNodes=False)
        c.undoInfo(state=True)
        if not c.objExists('FaceFitSkeleton.RigType'):
            c.addAttr('FaceFitSkeleton', longName='RigType',
                      attributeType='enum', enumName='Joints:BlendShapes:Mixed')
        c.setAttr('FaceFitSkeleton.RigType', 1)
        built = MayaPanelController().face_original_build(':')
        report['python_stages'] = len(built['stages'])
        report['python_blendshapes'] = len(c.ls('asFaceBS*', type='blendShape') or [])
        c.file(rename=str(OUT / 'python-diagnostic.mb'))
        c.file(save=True, type='mayaBinary', force=True)
        python_snapshot = snapshot()
        (OUT / 'target-summary.json').write_text(json.dumps({
            side: {node: {target: len(data['points']) for target, data in targets.items()}
                   for node, targets in state['blendshapes'].items()}
            for side, state in (('native', native_snapshot), ('python', python_snapshot))},
            indent=2), encoding='utf8')
        report['skin_error'] = compare(native_skin, skin_snapshot(include_non_mesh=True))
        report['pose_error'] = compare(native_poses, observe())
        report['snapshot_error'] = compare(native_snapshot, python_snapshot)
        python_joints = {joint: c.xform(joint, query=True, worldSpace=True,
                                        matrix=True) for joint in c.ls(type='joint')}
        report['joint_error'] = compare(native_joints, python_joints)
        c.file(rename=str(OUT / 'python.mb'))
        c.file(save=True, type='mayaBinary', force=True)
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'
        report['error'] = traceback.format_exc()
    finally:
        save()
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:
            Path(completion).write_text(json.dumps(
                {'pid': os.getpid(), 'status': report['status']}), encoding='utf8')
        if quit_on_finish:
            utils.executeDeferred(c.quit, force=True)
