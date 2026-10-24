"""Rebuild a saved Body/Complete Face character and retain its native data."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OPM_BODY = os.environ.get('ADV_BODY_FACE_OPM') == '1'
OUT = ROOT / ('validation/results/body-face-opm-rebuild-current' if OPM_BODY
              else 'validation/results/body-face-rebuild-current')
INPUT = ROOT / ('validation/results/body-face-opm-lifecycle-current/body-face-built.mb'
                if OPM_BODY else 'validation/results/body-face-lifecycle-current/body-face-built.mb')


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, utils
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    from maya_face_conversion_parity import skin_snapshot, compare

    OUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'input': str(INPUT)}
    def save():
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    def body():
        return MayaBodyBuildHost().read_character_registration()
    def roots():
        return {name: c.ls(name, uuid=True)[0]
                for name in ('FaceGroup', 'FaceJoint_M', 'FaceAllSet', 'FaceControlSet')}
    def face_members():
        return {c.ls(member, uuid=True)[0]
                for member in c.sets('FaceAllSet', query=True) or []}
    def face_skins():
        return {name: data for name, data in skin_snapshot(
            include_non_mesh=True).items() if name != 'AdvPy_BodySkin'}
    def poses():
        state = c.undoInfo(query=True, state=True)
        c.undoInfo(stateWithoutFlush=False)
        try:
            result = {}
            for name, changes in (
                ('neutral', ()),
                ('head_turn', (('AdvPy_Head_MFK.rotateZ', 15),)),
                ('mouth', (('ctrlMouth_M.ty', -1),)),
                ('head_and_mouth', (('AdvPy_Head_MFK.rotateZ', 15),
                                    ('ctrlMouth_M.ty', -1))),
                ('main_scale', (('AdvPy_Global.scaleX', 1.1),
                                ('AdvPy_Global.scaleY', 1.2),
                                ('AdvPy_Global.scaleZ', .9))),
            ):
                old = [(plug, c.getAttr(plug)) for plug, _ in changes]
                try:
                    for plug, value in changes:
                        c.setAttr(plug, value)
                    result[name] = {mesh: list(c.xform(mesh + '.vtx[*]',
                        query=True, worldSpace=True, translation=True))
                        for mesh in ('FaceMesh', 'BipedBindProxy')}
                finally:
                    for plug, value in old:
                        c.setAttr(plug, value)
            current = c.currentTime(query=True)
            try:
                for frame in (1, 3, 5):
                    c.currentTime(frame)
                    result['frame_' + str(frame)] = {
                        mesh: list(c.xform(mesh + '.vtx[*]', query=True,
                                         worldSpace=True, translation=True))
                        for mesh in ('FaceMesh', 'BipedBindProxy')}
            finally:
                c.currentTime(current)
            return result
        finally:
            c.undoInfo(stateWithoutFlush=state)
    try:
        c.file(str(INPUT), open=True, force=True, executeScriptNodes=False)
        c.undoInfo(state=True)
        c.currentTime(1)
        original = body()
        original_roots = roots()
        original_members = face_members()
        original_skins = face_skins()
        original_poses = poses()
        original_curves = set(c.ls(type='animCurve', uuid=True) or [])
        report.update(body_joints=len(original.body), face_joints=len(
            c.ls('FaceJoint_M', dag=True, type='joint') or []),
            face_members=len(original_members), face_skins=len(original_skins))
        report['stage'] = 'body_rebuild'; save()
        MayaPanelController().body_rebuild(':', 'advBodyFaceStage')
        assert not c.namespace(exists='advBodyFaceStage')
        rebuilt = body()
        assert len(rebuilt.body) == len(original.body)
        assert roots() == original_roots
        assert face_members() == original_members
        assert original_curves <= set(c.ls(type='animCurve', uuid=True) or [])
        report['skin_error'] = compare(original_skins, face_skins())
        report['pose_error'] = compare(original_poses, poses())
        report['stage'] = 'undo_redo'; save()
        c.undo()
        assert body() == original
        assert roots() == original_roots
        assert face_members() == original_members
        compare(original_skins, face_skins())
        compare(original_poses, poses())
        c.redo()
        assert body() == rebuilt
        assert roots() == original_roots
        assert face_members() == original_members
        compare(original_skins, face_skins())
        compare(original_poses, poses())
        report['undo_redo'] = True
        report['stage'] = 'save_reopen'; save()
        output = OUT / 'body-face-body-rebuilt.mb'
        c.file(rename=str(output)); c.file(save=True, type='mayaBinary', force=True)
        c.file(str(output), open=True, force=True, executeScriptNodes=False)
        assert body() == rebuilt
        assert roots() == original_roots
        assert face_members() == original_members
        report['reopened_skin_error'] = compare(original_skins, face_skins())
        report['reopened_pose_error'] = compare(original_poses, poses())
        report.update(status='passed', stage='complete', output=str(output))
    except Exception:
        report.update(status='failed', error=traceback.format_exc())
    finally:
        save()
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:
            Path(completion).write_text(json.dumps(
                {'pid': os.getpid(), 'status': report['status']}), encoding='utf-8')
        if quit_on_finish:
            utils.executeDeferred(c.quit, force=True)
