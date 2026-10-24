"""Observe native/Python nCloth inputs and native replay, without tuning physics."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/auto-place-cloth-inputs'
TAG = ''
INPUTS = {}


def capture():
    from maya import cmds as c
    meshes = {}
    for name in ('CombinedSkinUpper_M', 'CombinedSkinIndex_R', 'CombinedSkinMiddle_R',
                 'CombinedSkinRing_R', 'CombinedSkinPinky_R'):
        meshes[name] = c.xform(name + '.vtx[*]', query=True, worldSpace=True, translation=True)
    attrs = {}
    for node in c.ls(type='nCloth') + c.ls(type='nucleus'):
        values = {}
        for attr in ('localForce', 'collide', 'selfCollide', 'stretchResistance',
                     'compressionResistance', 'bendResistance', 'bendAngleDropoff',
                     'pointMass', 'tangentialDrag', 'damp', 'ignoreSolverGravity',
                     'spaceScale', 'subSteps', 'maxCollisionIterations', 'gravity',
                     'gravityDirection', 'windSpeed', 'windDirection', 'airDensity',
                     'timeScale', 'startFrame', 'thickness', 'bounce', 'friction',
                     'selfCollideWidthScale', 'restLengthScale', 'drag', 'lift'):
            if c.attributeQuery(attr, node=node, exists=True):
                values[attr] = c.getAttr(node + '.' + attr)
        attrs[node] = values
    INPUTS[TAG] = dict(meshes=meshes, attrs=attrs)


def difference(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), (a.keys(), b.keys())
        return max((difference(a[key], b[key]) for key in a), default=0.)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        assert len(a) == len(b)
        return max((difference(x, y) for x, y in zip(a, b)), default=0.)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b)
    assert a == b, (a, b)
    return 0.


def main(*, standalone=False, quit_on_finish=True):
    global TAG
    from maya import cmds as c, mel
    from maya_fit_auto_place_phases import hand_fixture, native_finger_procedure, mesh_snapshot
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_state import FitAutoPlaceScanState
    from adv_py.adapters.maya_fit_auto_place_fingers import straighten_fingers
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), scope='Input and replay diagnosis, not AutoPlace acceptance')
    original_set_attr = c.setAttr
    try:
        source = (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8-sig')
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        procedure = native_finger_procedure(source)
        marker = 'setAttr asFitNCloth.v 0;'
        assert procedure.count(marker) == 1
        mel.eval(procedure.replace(marker, marker + '\npython("import maya_auto_place_cloth_inputs as p;p.capture()");'))
        hand_fixture()
        scene = OUT / 'input.mb'
        c.file(rename=str(scene))
        c.file(save=True, type='mayaBinary', force=True)
        outputs = {}
        for TAG in ('native-1', 'native-2', 'python'):
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            if TAG.startswith('native'):
                mel.eval('advPyReferenceStraightenFingers;')
            else:
                def observe(*args, **kwargs):
                    result = original_set_attr(*args, **kwargs)
                    if args[:2] == ('asFitNCloth.visibility', False):
                        capture()
                    return result
                c.setAttr = observe
                host = MayaFitJointHost()
                with host.transaction('Source nCloth input diagnosis'):
                    state = FitAutoPlaceScanState(host, host._cmds, 0., -8., -2., 2., 10., 'biped', four_fingers=True)
                    straighten_fingers(state)
                c.setAttr = original_set_attr
            outputs[TAG] = mesh_snapshot('CombinedSkinUpper_M')
        report.update(status='passed', inputs=INPUTS, outputs=outputs,
            native_replay_input_error=difference(INPUTS['native-1'], INPUTS['native-2']),
            native_replay_output_error=difference(outputs['native-1'], outputs['native-2']),
            python_input_error=difference(INPUTS['native-1'], INPUTS['python']),
            python_output_error=difference(outputs['native-1'], outputs['python']))
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc(), inputs=INPUTS)
    finally:
        c.setAttr = original_set_attr
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1
