"""Unedited MEL channel procedures versus Python on the same complete Face.

This is channel/mesh parity on a procedural Face, not default model appearance.
Run in graphical Maya so the source uses its actual UI and native commands.
"""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUTPUT = ROOT / 'validation/results/face-channel-parity'
SCENE = ROOT / 'validation/results/face-complete-shell-fix-live/face-completed.mb'


def node_ids():
    from maya import cmds as c
    # With no objects Maya ignores uuid=True and returns node names. Names
    # can be reused by setDrivenKeyframe during undo; query explicit objects.
    return set(c.ls(c.ls(long=True) or [], uuid=True) or [])


def fixture(kind, alternate=False):
    from maya import cmds as c
    from adv_py.core.face_arkit import ARKIT_SHAPES
    c.file(str(SCENE), open=True, force=True, executeScriptNodes=False)
    c.undoInfo(state=True)
    c.autoKeyframe(state=False)
    c.currentTime(0)
    if not c.objExists('FaceFitSkeleton.SnapChat'):
        c.addAttr('FaceFitSkeleton', longName='SnapChat', attributeType='bool')
    c.setAttr('FaceFitSkeleton.SnapChat', kind == 'snapchat')
    if kind in ('arkit_create', 'snapchat'):
        node = c.createNode('transform', name='ctrlSnapChat_M' if kind == 'snapchat' else 'ctrlARKit_M')
        c.sets(node, add='FaceControlSet')
    elif kind == 'arkit_connect':
        node = c.createNode('transform', name='ctrlARKit_M')
        c.sets(node, add='FaceControlSet')
        for name in ARKIT_SHAPES:
            c.addAttr(node, longName=name, attributeType='double', keyable=True)
    elif kind == 'roblox':
        node = c.createNode('transform', name='ctrlRobloxHead_M')
        c.sets(node, add='FaceControlSet')
    if kind in ('arkit_quick', 'arkit_connect'):
        source = c.createNode('transform', name='ExternalARKit')
        for name in ARKIT_SHAPES:
            attr = name.replace('Right', '_R').replace('Left', '_L') if alternate else name
            c.addAttr(source, longName=attr, attributeType='double', keyable=True)
        # The source reads the option menu even for a transform attribute source.
        if c.optionMenu('asConnectARKitBSOptionMenu', exists=True):
            c.deleteUI('asConnectARKitBSOptionMenu')
        c.optionMenu('asConnectARKitBSOptionMenu')
        c.menuItem(label=source)
        return source
    return node


def sample(driver, maximum, namespace=''):
    from maya import cmds as c
    attrs = c.listAttr(driver, userDefined=True, keyable=True) or []
    prefix = namespace + ':' if namespace else ''
    controls = c.sets(prefix + 'FaceControlSet', query=True) or []
    controls += c.ls(prefix + 'SDK*', type='transform') or []
    plugs = sorted({node + '.' + attr for node in controls if node != driver
                    for attr in (c.listAttr(node, keyable=True) or [])
                    if c.getAttr(node + '.' + attr, type=True) in ('double', 'doubleLinear', 'doubleAngle', 'float', 'long', 'bool', 'enum')})
    meshes = [prefix + mesh for mesh in ('FaceMesh', 'EyeRight', 'EyeLeft', 'TongueMesh', 'UpperTeethMesh', 'LowerTeethMesh') if c.objExists(prefix + mesh)]
    result = {}
    for attr in attrs:
        plug = driver + '.' + attr
        for value in (0., maximum / 2., maximum):
            c.setAttr(plug, value)
            result[plug.removeprefix(prefix) + '=' + str(value)] = {
                'plugs': {p.removeprefix(prefix): c.getAttr(p) for p in plugs},
                'meshes': {m.removeprefix(prefix): c.xform(m + '.vtx[*]', query=True, worldSpace=True, translation=True) for m in meshes}}
        c.setAttr(plug, 0)
    return result


def observe(driver, maximum, namespace=''):
    # Sampling drives attributes but must not put those edits above the build
    # chunk. Otherwise undo/redo would only test the last sampled attribute.
    from maya import cmds as c
    state = c.undoInfo(query=True, state=True)
    c.undoInfo(stateWithoutFlush=False)
    try:
        return sample(driver, maximum, namespace)
    finally:
        c.undoInfo(stateWithoutFlush=state)


def compare(native, python):
    assert native.keys() == python.keys(), (native.keys() - python.keys(), python.keys() - native.keys())
    maximum = 0.
    worst = None
    for pose, row in native.items():
        other = python[pose]
        assert row['plugs'].keys() == other['plugs'].keys(), pose
        errors = [(abs(value - other['plugs'][plug]), plug) for plug, value in row['plugs'].items()]
        for mesh, points in row['meshes'].items():
            assert len(points) == len(other['meshes'][mesh])
            errors.append((max(abs(a - b) for a, b in zip(points, other['meshes'][mesh])), mesh))
        error, item = max(errors)
        if error > maximum:
            maximum, worst = error, (pose, item)
    assert maximum <= 1e-4, (maximum, worst)
    return {'poses': len(native), 'maximum_error': maximum, 'worst': worst}


def main(kinds=None):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1))
        c.optionVar(intValue=('asDock', 0))
        mel.eval('AdvancedSkeleton;')
        for kind, alternate in (('arkit_create', False), ('snapchat', False),
                                ('arkit_connect', True), ('roblox', False), ('arkit_quick', True)):
            if kinds is not None and kind not in kinds:
                continue
            print('CHANNEL CASE', kind, flush=True)
            driver = fixture(kind, alternate)
            if kind == 'roblox':
                mel.eval('asFaceRobloxHead;')
            else:
                mel.eval('asConnectARKit "";')
            maximum = 1 if kind in ('arkit_quick', 'arkit_connect') else 10
            native = observe(driver, maximum)
            (OUTPUT / (kind + '-native.json')).write_text(json.dumps(native), encoding='utf8')
            driver = fixture(kind, alternate)
            host = MayaOriginalFaceBuildHost()
            previous = node_ids()
            with host.transaction('Face 来源通道对照'):
                if kind == 'roblox':
                    host.create_original_face_roblox_head()
                else:
                    host.connect_original_face_arkit(driver if kind in ('arkit_quick', 'arkit_connect') else None)
            generated = node_ids() - previous
            python = observe(driver, maximum)
            report['cases'][kind] = compare(native, python)
            c.file(rename=str(OUTPUT / (kind + '.mb')))
            c.file(save=True, type='mayaBinary', force=True)
            c.undo()
            remaining = generated.intersection(node_ids())
            report['cases'][kind]['undo_remaining_nodes'] = {uid: c.ls(uid, long=True) for uid in remaining}
            report['cases'][kind]['undo_clean'] = not bool(remaining)
            c.redo()
            # Native SDK redo can recreate implicit nodes with new UUIDs;
            # verify every driven value and production point after redo.
            report['cases'][kind]['undo_redo'] = compare(python, observe(driver, maximum))
            c.file(str(OUTPUT / (kind + '.mb')), open=True, force=True, executeScriptNodes=False)
            report['cases'][kind]['reopened'] = compare(python, observe(driver, maximum))
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed' if all(row['undo_clean'] for row in report['cases'].values()) else 'failed'
    except Exception:
        report['status'] = 'failed'
        report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        c.quit(force=True)
