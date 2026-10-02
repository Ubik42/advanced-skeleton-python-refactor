"""Native Pupil/Iris topology, Skin, SDK and lifecycle parity.

Uses untouched asFacePupilIris on the exact same saved EyeBall stage input.
"""
from pathlib import Path
from collections import defaultdict
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUTPUT = ROOT / 'validation/results/face-pupil-parity'
INPUT = ROOT / 'validation/results/face-original-full-final-20261001/face-fit-input.mb'


def fit_fixture(multi=False, adjacent=False):
    from maya import cmds as c
    from maya.api import OpenMaya as om
    from adv_py.product.maya_panel_controller import MayaPanelController
    c.file(str(INPUT), open=True, force=True, executeScriptNodes=False)
    c.undoInfo(state=True)
    c.autoKeyframe(state=False)
    c.selectMode(object=True)
    c.softSelect(softSelectEnabled=False)
    c.select(clear=True)
    for side, x in (('Right', -.8), ('Left', .8)):
        c.delete('Eye' + side)
        mesh = c.polySphere(name='Eye' + side, radius=.31, axis=(0, 0, 1),
                            subdivisionsX=24, subdivisionsY=24, constructionHistory=False)[0]
        c.xform(mesh, worldSpace=True, translation=(x, 3.1, 1.1))
        c.makeIdentity(mesh, apply=True, translate=True, rotate=True, scale=True)
        c.skinCluster('Head_M', mesh, toSelectedBones=True, name=mesh + 'HeadSkin')
    for attr, value in (('MultiSkinClusters', multi), ('useOffsetParentMatrix', multi)):
        if not c.objExists('FaceFitSkeleton.' + attr):
            c.addAttr('FaceFitSkeleton', longName=attr, attributeType='bool')
        c.setAttr('FaceFitSkeleton.' + attr, value)
    if multi:
        c.createNode('transform', name='DeformationSystem')
        # Source asGetOpm reads FitSkeleton, even for an independent Face.
        c.createNode('transform', name='FitSkeleton')
        c.addAttr('FitSkeleton', longName='useOffsetParentMatrix', attributeType='bool', defaultValue=True)
    controller = MayaPanelController()
    # Create source fit loops through public entry before Prep mirrors them.
    selection = om.MSelectionList(); selection.add('EyeRight')
    fn = om.MFnMesh(selection.getDagPath(0))
    by_z = defaultdict(set)
    for i in range(fn.numVertices):
        p = fn.getPoint(i, om.MSpace.kWorld)
        if p.z > 1.1:
            by_z[round(p.z, 6)].add(i)
    rings = []
    for z, indices in sorted(by_z.items(), reverse=True):
        edges = [f'EyeRight.e[{i}]' for i in range(fn.numEdges)
                 if set(fn.getEdgeVertices(i)).issubset(indices)]
        if len(edges) == 24:
            rings.append(edges)
    assert len(rings) >= 7
    for role, edges in (('Pupil', rings[1]), ('Iris', rings[2] if adjacent else rings[5])):
        c.select(edges, replace=True)
        controller.face_fit_marker(':', role)
    # EyeBall includes the optional Pupil procedure. Hide only its dispatch
    # markers while constructing the common stage checkpoint, then restore.
    for role in ('Pupil', 'Iris'):
        c.rename('FaceFit' + role, 'ParityPending' + role)
    for step in (1, 2, 3):
        controller.face_original_build(':', step=step)
    for role in ('Pupil', 'Iris'):
        c.rename('ParityPending' + role, 'FaceFit' + role)
    # Prep has already duplicated these holders and their curve children.
    for role in ('Pupil', 'Iris'):
        c.rename('ParityPending' + role + 'Left', 'FaceFit' + role + 'Left')
    c.select(clear=True)
    return controller


def snapshot(commands=None):
    from maya import cmds as raw
    c = commands or raw
    result = {'joints': {}, 'weights': {}, 'controls': {}, 'meshes': {}}
    for side in ('_R', '_L'):
        for stem in ('Pupil', 'Iris'):
            name = stem + side
            result['controls'][name] = c.xform(name + '.cv[*]', query=True, worldSpace=True, translation=True)
            result['joints'][stem + 'Joint' + side] = c.xform(stem + 'Joint' + side, query=True, worldSpace=True, matrix=True)
        eye = 'EyeRight' if side == '_R' else 'EyeLeft'
        result['meshes'][eye] = c.xform(eye + '.vtx[*]', query=True, worldSpace=True, translation=True)
        skin = next(n for n in reversed(c.listHistory(eye) or []) if c.nodeType(n) == 'skinCluster' and n != 'squashIKSC')
        inf = c.skinCluster(skin, query=True, influence=True)
        result['weights'][eye] = {'influences': [i.replace('FaceActor:', '') for i in inf], 'values': [c.skinPercent(skin, eye + f'.vtx[{i}]', query=True, value=True)
            for i in range(c.polyEvaluate(eye, vertex=True))]}
    return result


def observe(commands=None):
    from maya import cmds as c
    state = c.undoInfo(query=True, state=True)
    c.undoInfo(stateWithoutFlush=False)
    try:
        return poses(commands)
    finally:
        c.undoInfo(stateWithoutFlush=state)


def poses(commands=None):
    from maya import cmds as raw
    c = commands or raw
    result = {'neutral': snapshot(commands)}
    for side in ('_R', '_L'):
        for attr in ('pupil', 'iris'):
            for value in (-10, -5, 5, 10):
                plug = 'ctrlEye' + side + '.' + attr
                c.setAttr(plug, value)
                result[plug + '=' + str(value)] = snapshot(commands)
                c.setAttr(plug, 0)
    return result


def compare(a, b):
    def errors(x, y):
        if isinstance(x, dict):
            assert x.keys() == y.keys()
            for key in x:
                yield from errors(x[key], y[key])
        elif isinstance(x, (list, tuple)):
            assert len(x) == len(y)
            for first, second in zip(x, y):
                yield from errors(first, second)
        elif isinstance(x, (int, float)):
            yield abs(x - y)
        else:
            assert x == y, (x, y)
    maximum = max(errors(a, b), default=0.)
    assert maximum <= 1e-4, maximum
    return maximum


def main():
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 0))
        mel.eval('AdvancedSkeleton;')
        for multi, adjacent in ((False, False), (False, True), (True, False)):
            name = ('multi' if multi else 'ordinary') + ('-adjacent' if adjacent else '-separated')
            print('PUPIL CASE', name, flush=True)
            fit_fixture(multi, adjacent)
            scene = OUTPUT / (name + '-input.mb')
            c.file(rename=str(scene)); c.file(save=True, type='mayaBinary', force=True)
            for field, value in (('HeadJoint', 'Head_M'), ('RightEye', 'EyeRight'), ('LeftEye', 'EyeLeft')):
                c.textField('asFace' + field + 'TextField', edit=True, text=value)
            c.checkBox('asFaceMultiSkinClustersCheckBox', edit=True, value=multi)
            c.checkBox('asBodyOffsetParentMatrixCheckBox', edit=True, value=multi)
            mel.eval('asFacePupilIris;')
            native = observe()
            (OUTPUT / (name + '-native.json')).write_text(json.dumps(native), encoding='utf8')
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            host = MayaOriginalFaceBuildHost()
            source = host.capture_original_face_pupil_input()
            with host.transaction('原版瞳孔虹膜对照'):
                result = host.create_original_face_pupil_iris(source)
            python = observe()
            report['cases'][name] = {'maximum_error': compare(native, python), 'poses': len(native), 'controls': result['controls']}
            c.undo(); assert not c.objExists('PupilJoint_R')
            c.redo(); assert c.objExists('PupilJoint_R')
            report['cases'][name]['undo_redo_error'] = compare(python, observe())
            saved = OUTPUT / (name + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            report['cases'][name]['reopened_error'] = compare(python, observe())
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        c.quit(force=True)
