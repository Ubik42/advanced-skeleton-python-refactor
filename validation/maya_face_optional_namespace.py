"""Optional Face chains with another editor namespace active and external data."""
from pathlib import Path
import json
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))
OUTPUT = ROOT / 'validation/results/face-optional-namespace'


def main(kinds=None):
    from maya import cmds as c
    from adv_py.adapters.maya_namespace import MayaCharacterCommands
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.core.face_arkit import ARKIT_SHAPES
    from maya_face_channel_parity import SCENE, observe, compare, node_ids
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    try:
        for kind in ('arkit_create', 'arkit_connect', 'roblox', 'arkit_quick'):
            if kinds is not None and kind not in kinds:
                continue
            c.file(new=True, force=True); c.undoInfo(state=True)
            c.file(str(SCENE), i=True, namespace='FaceActor', executeScriptNodes=False)
            c.namespace(add='OtherEditor')
            cube = c.polyCube(name='ForeignGeometry', constructionHistory=False)[0]
            foreign_uuid = c.ls(cube, uuid=True)[0]
            c.createNode('transform', name='ExternalARKit')
            for name in ARKIT_SHAPES:
                c.addAttr('ExternalARKit', longName=name.replace('Left', '_L').replace('Right', '_R'),
                          attributeType='double', keyable=True)
            external_uuid = c.ls('ExternalARKit', uuid=True)[0]
            c.currentTime(0); c.autoKeyframe(state=False)
            commands = MayaCharacterCommands(c, 'FaceActor')
            driver = 'ctrlRobloxHead_M' if kind == 'roblox' else 'ctrlARKit_M'
            if kind != 'arkit_quick':
                commands.createNode('transform', name=driver)
                commands.sets(driver, add='FaceControlSet')
                if kind == 'arkit_connect':
                    for name in ARKIT_SHAPES:
                        commands.addAttr(driver, longName=name, attributeType='double', keyable=True)
            else:
                driver = ':ExternalARKit'
            before = node_ids()
            c.namespace(set='OtherEditor')
            previous_namespace = c.namespaceInfo(currentNamespace=True, absoluteName=True)
            host = MayaOriginalFaceBuildHost(namespace='FaceActor')
            with host.transaction('独立角色可选 Face 驱动'):
                if kind == 'roblox':
                    host.create_original_face_roblox_head()
                else:
                    host.connect_original_face_arkit(':ExternalARKit' if kind in ('arkit_quick', 'arkit_connect') else None)
            physical = ':ExternalARKit' if kind in ('arkit_quick', 'arkit_connect') else ':FaceActor:' + driver
            # Canonical root reference keys use ExternalARKit without a colon.
            maximum = 1 if kind in ('arkit_quick', 'arkit_connect') else 10
            data = observe(physical.lstrip(':'), maximum, 'FaceActor')
            generated = node_ids() - before
            actual_namespace = c.namespaceInfo(currentNamespace=True, absoluteName=True)
            assert actual_namespace == previous_namespace, (previous_namespace, actual_namespace)
            assert c.ls(':ForeignGeometry', uuid=True)[0] == foreign_uuid
            assert c.ls(':ExternalARKit', uuid=True)[0] == external_uuid
            c.undo()
            remaining = generated.intersection(node_ids())
            report['cases'][kind] = {'undo_remaining_nodes': {uid: c.ls(uid, long=True) for uid in remaining}}
            c.redo()
            assert compare(data, observe(physical.lstrip(':'), maximum, 'FaceActor'))['maximum_error'] == 0
            saved = OUTPUT / (kind + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            assert compare(data, observe(physical.lstrip(':'), maximum, 'FaceActor'))['maximum_error'] == 0
            report['cases'][kind] = {'poses': len(data), 'undo_redo': True, 'saved_reopened': True,
                                     'foreign_objects_preserved': True, 'active_namespace_restored': True,
                                     'undo_clean': not bool(remaining),
                                     'undo_remaining_nodes': {uid: c.ls(uid, long=True) for uid in remaining}}
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        from maya_face_pupil_parity import OUTPUT as PUPIL_OUTPUT, observe as pupil_observe, compare as pupil_compare
        c.file(new=True, force=True); c.undoInfo(state=True)
        c.file(str(PUPIL_OUTPUT / 'ordinary-separated-input.mb'), i=True,
               namespace='FaceActor', executeScriptNodes=False)
        c.namespace(add='OtherEditor')
        cube = c.polyCube(name='ForeignGeometry', constructionHistory=False)[0]
        foreign_uuid = c.ls(cube, uuid=True)[0]
        c.namespace(set='OtherEditor')
        host = MayaOriginalFaceBuildHost(namespace='FaceActor')
        source = host.capture_original_face_pupil_input()
        with host.transaction('独立角色瞳孔虹膜'):
            host.create_original_face_pupil_iris(source)
        commands = MayaCharacterCommands(c, 'FaceActor')
        data = pupil_observe(commands)
        native = json.loads((PUPIL_OUTPUT / 'ordinary-separated-native.json').read_text(encoding='utf8'))
        error = pupil_compare(native, data)
        c.undo(); assert not c.objExists(':FaceActor:PupilJoint_R')
        c.redo(); assert c.objExists(':FaceActor:PupilJoint_R')
        assert pupil_compare(data, pupil_observe(commands)) == 0
        assert c.namespaceInfo(currentNamespace=True, absoluteName=True) == ':OtherEditor'
        assert c.ls(':ForeignGeometry', uuid=True)[0] == foreign_uuid
        saved = OUTPUT / 'pupil.mb'
        c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
        c.file(str(saved), open=True, force=True, executeScriptNodes=False)
        assert pupil_compare(data, pupil_observe(commands)) == 0
        report['cases']['pupil_iris'] = {'poses': len(data), 'source_error': error, 'undo_redo': True,
            'saved_reopened': True, 'foreign_objects_preserved': True, 'active_namespace_restored': True}
        report['status'] = 'passed' if all(row.get('undo_clean', True) for row in report['cases'].values()) else 'failed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        from maya import utils
        utils.executeDeferred(c.quit, force=True)
