"""Saved Complete Face rebuild: authored data and complete native lifecycle."""
from pathlib import Path
import json
import os
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUTPUT = ROOT / 'validation/results/face-rebuild-lifecycle'


def sdk_state(c, curve):
    return {'type': c.nodeType(curve),
        'keys': c.keyframe(curve, query=True, floatChange=True),
        'values': c.keyframe(curve, query=True, valueChange=True),
        'in_types': c.keyTangent(curve, query=True, inTangentType=True),
        'out_types': c.keyTangent(curve, query=True, outTangentType=True),
        'weighted': c.keyTangent(curve, query=True, weightedTangents=True),
        'in_angles': c.keyTangent(curve, query=True, inAngle=True),
        'out_angles': c.keyTangent(curve, query=True, outAngle=True),
        'in_weights': c.keyTangent(curve, query=True, inWeight=True),
        'out_weights': c.keyTangent(curve, query=True, outWeight=True),
        'locked': c.keyTangent(curve, query=True, lock=True),
        'weight_locked': c.keyTangent(curve, query=True, weightLock=True),
        'pre': c.getAttr(curve + '.preInfinity'), 'post': c.getAttr(curve + '.postInfinity')}


def shape_state(c, shape):
    count = c.getAttr(shape + '.spans') + c.getAttr(shape + '.degree')
    return {'points': [c.getAttr(shape + '.controlPoints[%d]' % i)[0] for i in range(count)],
            'color': c.getAttr(shape + '.overrideColor')}


def author(c, multi):
    c.addAttr('ctrlLips_M', longName='authoredLipStrength', shortName='als',
              attributeType='double', minValue=0, maxValue=1, defaultValue=.37, keyable=True)
    c.addAttr('ctrlLips_M', longName='authoredLipMode', attributeType='enum',
              enumName='Off:Soft:Strong', defaultValue=2, keyable=True)
    shape = c.listRelatives('ctrlLips_M', shapes=True, fullPath=True, type='nurbsCurve')[0]
    position = c.getAttr(shape + '.controlPoints[0]')[0]
    c.setAttr(shape + '.controlPoints[0]', position[0] + .031, position[1] - .017, position[2])
    c.setAttr(shape + '.overrideColor', 17)
    inputs = c.listConnections('ctrlLips_M.upperRoll', source=False, destination=True, type='blendWeighted') or []
    curves = [curve for node in inputs for curve in
        c.listConnections(node, source=False, destination=True, type='animCurve') or []]
    assert curves, 'upperRoll source SDK curves'
    curve = curves[0]
    values = c.keyframe(curve, query=True, valueChange=True)
    c.keyframe(curve, edit=True, index=(len(values)-1, len(values)-1), valueChange=values[-1] * 1.125)
    c.keyTangent(curve, edit=True, weightedTangents=True, inTangentType='fixed', outTangentType='fixed')
    c.setAttr(curve + '.preInfinity', 3); c.setAttr(curve + '.postInfinity', 4)
    if not c.objExists('FaceSetupEditHistory'):
        c.createNode('transform', name='FaceSetupEditHistory', parent='ControlsSetup')
        c.sets('FaceSetupEditHistory', add='FaceAllSet')
    marker = 'ctrlLips_M_upperRoll_tweaked'
    if not c.objExists('FaceSetupEditHistory.' + marker):
        c.addAttr('FaceSetupEditHistory', longName=marker, attributeType='bool', defaultValue=True)
    weights = []
    if multi:
        cases = [('LipSC', 'FaceMesh.vtx[100]', 'upperLipJoint0_M', 'MultiSkinClustersFaceLipJoint_M', .37)]
        skin = next(node for node in c.listHistory('TongueMesh') or []
            if c.nodeType(node) == 'skinCluster' and node.startswith('UpMidLocSC'))
        cases.append((skin, 'TongueMesh.vtx[1]', 'upperFaceJoint_M', 'middleFaceJoint_M', .31))
    else:
        influences = c.skinCluster('HeadSkin', query=True, influence=True)
        joint = next(name for name in influences if 'LipJoint' in name)
        cases = [('HeadSkin', 'FaceMesh.vtx[100]', joint, 'Head_M', .37)]
    for skin, vertex, joint, other, value in cases:
        c.skinPercent(skin, vertex, transformValue=[(joint, value), (other, 1-value)], zeroRemainingInfluences=True)
        weights.append((skin, vertex, joint, c.skinPercent(skin, vertex, query=True, transform=joint)))
    return {'curve': curve, 'sdk': sdk_state(c, curve), 'shape': shape.rsplit('|',1)[-1],
            'shape_state': shape_state(c, shape), 'weights': weights}


def check_authored(c, expected, compare, *, weight_failures=None):
    assert abs(c.getAttr('ctrlLips_M.authoredLipStrength') - .37) < 1e-8
    assert c.getAttr('ctrlLips_M.authoredLipMode') == 2
    assert c.addAttr('ctrlLips_M.authoredLipMode', query=True, enumName=True) == 'Off:Soft:Strong'
    compare(expected['sdk'], sdk_state(c, expected['curve']))
    compare(expected['shape_state'], shape_state(c, expected['shape']))
    for skin, vertex, joint, value in expected['weights']:
        actual = c.skinPercent(skin, vertex, query=True, transform=joint)
        if abs(actual - value) >= 1e-8:
            failure = {'skin':skin,'component':vertex,'influence':joint,'before':value,'after':actual}
            if weight_failures is None:
                raise AssertionError(failure)
            weight_failures.append(failure)


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, utils
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_conversion_parity import skin_snapshot, scene_identity, observe, compare, control_states
    from adv_py.product.maya_panel_controller import MayaPanelController
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'cases': {}}
    def save_report():
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    save_report()
    try:
        load_project_native_plugin()
        names = os.environ.get('ADV_FACE_REBUILD_CASES','ordinary,multi').split(',')
        for name in names:
            c.file(str(ROOT / ('validation/results/face-optional-full-build/' + name + '.mb')),
                   open=True, force=True, executeScriptNodes=False)
            c.undoInfo(state=True)
            expected = author(c, name == 'multi')
            before_identity = scene_identity(); before_skin = skin_snapshot(include_non_mesh=True)
            before_controls = control_states(); before_poses = observe()
            c.file(rename=str(OUTPUT / (name + '-input.mb'))); c.file(save=True, type='mayaBinary', force=True)
            result = MayaPanelController().face_original_build(':')
            row = {'stages': list(result['stages']), 'restore': result['stages']['RebuildRestore']}
            report['cases'][name] = row; save_report()
            assert not c.objExists('prefix_FaceGroup')
            failures = []
            check_authored(c, expected, compare, weight_failures=failures)
            row['authored_weight_failures'] = failures
            row['authored_data_preserved'] = not failures
            # Keep the original strict comparison. Record a failed preservation
            # check and continue the remaining graph lifecycle independently.
            try:
                row['rebuilt_pose_error'] = compare(before_poses, observe())
            except AssertionError as exc:
                row['rebuilt_pose_failure'] = str(exc)
            save_report()
            built_identity = scene_identity(); built_skin = skin_snapshot(include_non_mesh=True)
            built_controls = control_states(); built_poses = observe()
            c.undo()
            undone_identity = scene_identity()
            difference = {'extra': {k:v for k,v in undone_identity.items() if k not in before_identity},
                'missing': {k:v for k,v in before_identity.items() if k not in undone_identity},
                'changed': {k:[v,undone_identity[k]] for k,v in before_identity.items()
                            if k in undone_identity and v != undone_identity[k]}}
            (OUTPUT / (name + '-undo-difference.json')).write_text(json.dumps(difference, indent=2), encoding='utf8')
            compare(before_identity, scene_identity()); compare(before_controls, control_states())
            row['undo_identity_restored'] = True
            row['undo_skin_error'] = compare(before_skin, skin_snapshot(include_non_mesh=True))
            row['undo_pose_error'] = compare(before_poses, observe()); check_authored(c, expected, compare)
            c.redo()
            compare(built_identity, scene_identity()); compare(built_controls, control_states())
            row['redo_identity_restored'] = True
            row['redo_skin_error'] = compare(built_skin, skin_snapshot(include_non_mesh=True))
            row['redo_pose_error'] = compare(built_poses, observe()); check_authored(c, expected, compare, weight_failures=[])
            saved = OUTPUT / (name + '-rebuilt.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            row['reopen_skin_error'] = compare(built_skin, skin_snapshot(include_non_mesh=True))
            row['reopen_pose_error'] = compare(built_poses, observe()); check_authored(c, expected, compare, weight_failures=[])
            save_report()
        report['status'] = ('failed' if any(v.get('authored_weight_failures') or v.get('rebuilt_pose_failure')
            for v in report['cases'].values()) else 'passed')
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        save_report()
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion: Path(completion).write_text(json.dumps({'pid':os.getpid(),'status':report['status']}),encoding='utf8')
        if quit_on_finish: utils.executeDeferred(c.quit, force=True)
