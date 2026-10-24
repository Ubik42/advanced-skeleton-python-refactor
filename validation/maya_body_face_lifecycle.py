"""Public Body-to-Face handoff on the retained complete Python biped.

The face mesh is a procedural deformation fixture, not a presentation asset.
The existing Body eyes are replaced through the source EyeBall Fit entry.
"""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OPM_BODY = os.environ.get('ADV_BODY_FACE_OPM') == '1'
OUT = ROOT / ('validation/results/body-face-opm-lifecycle-current' if OPM_BODY
              else 'validation/results/body-face-lifecycle-current')
BODY = ROOT / ('validation/results/source-fit-aim-opm-order-lifecycle-current/opm/original-biped-current.mb'
               if OPM_BODY else
               'validation/results/source-fit-aim-native-order-lifecycle-current/traditional/original-biped-current.mb')


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, utils
    from maya.api import OpenMaya as om
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_conversion_parity import skin_snapshot, scene_identity, compare
    from maya_original_face_lower_smoke import fit_input
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    load_project_native_plugin()
    OUT.mkdir(parents=True, exist_ok=True)
    reuse = os.environ.get('ADV_BODY_FACE_REUSE') == '1'
    report = dict(status='running', pid=os.getpid(), body_input=str(BODY), reused_complete_build=reuse)
    def save():
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    def body():
        return MayaBodyBuildHost().read_character_registration()
    def mesh_points(name):
        return tuple(c.xform(name + '.vtx[*]', query=True, worldSpace=True, translation=True))
    def poses():
        # These controls address the actual Body and Face systems together.
        result = {}
        for name, changes in (
            ('neutral', ()),
            ('head_turn', (('AdvPy_Head_MFK.rotateZ', 15),)),
            ('mouth', (('ctrlMouth_M.ty', -1),)),
            ('head_and_mouth', (('AdvPy_Head_MFK.rotateZ', 15), ('ctrlMouth_M.ty', -1))),
            ('main_scale', (('AdvPy_Global.scaleX', 1.1), ('AdvPy_Global.scaleY', 1.2), ('AdvPy_Global.scaleZ', .9))),
        ):
            old = [(plug, c.getAttr(plug)) for plug, value in changes]
            try:
                for plug, value in changes:
                    c.setAttr(plug, value)
                result[name] = {mesh: mesh_points(mesh) for mesh in ('FaceMesh', 'BipedBindProxy')}
            finally:
                for plug, value in old:
                    c.setAttr(plug, value)
        for name in ('head_turn', 'mouth', 'head_and_mouth'):
            delta = max(abs(a-b) for a,b in zip(result['neutral']['FaceMesh'], result[name]['FaceMesh']))
            assert delta > 1e-5, (name, 'Face did not deform')
        c.currentTime(1)
        start = mesh_points('FaceMesh')
        c.currentTime(5)
        end = mesh_points('FaceMesh')
        c.currentTime(1)
        error = max(abs((b-a) - (10 if i % 3 == 0 else 0))
                    for i, (a, b) in enumerate(zip(start, end)))
        assert error < 1e-4, ('Body animation does not carry Face', error)
        result['global_animation_error'] = error
        return result
    try:
        c.file(str(BODY), open=True, force=True, executeScriptNodes=False)
        c.undoInfo(state=True)
        c.currentTime(1)
        initial = body()
        before_curves = set(c.ls(type='animCurve', uuid=True) or [])
        before_body_points = mesh_points('BipedBindProxy')
        controller = MayaPanelController()
        if reuse:
            c.file(str(OUT / 'body-face-built-checkpoint.mb'), open=True, force=True, executeScriptNodes=False)
            assert c.getAttr('FaceFitSkeleton.buildCompleted')
            assert c.getAttr('FaceFitSkeleton.buildStep') == 30
        else:
            # Native batch mode suppresses only the explicit replacement dialog.
            c.createNode('transform', name='asBatch')
            report['stage'] = 'fit'; save()
            fit_input(c, om, controller, head_joint='Head_M', geometry_scale=2,
                      opm=True, complete=True, attachments=True)
            assert not c.objExists('Eye_R') and not c.objExists('Eye_L')
        retained = body()
        removed = [row.path for row in initial.body if row.path not in {j.path for j in retained.body}]
        assert removed and all(any(name in path for name in ('Eye', 'Jaw')) for path in removed), removed
        compare(before_body_points, mesh_points('BipedBindProxy'))
        assert before_curves <= set(c.ls(type='animCurve', uuid=True) or [])
        report['body_handoff'] = dict(before=len(initial.body), after=len(retained.body), removed=removed)
        before_identity = scene_identity()
        before_skins = skin_snapshot(include_non_mesh=True)
        if reuse:
            built = {'stages': ()}
        else:
            report['stage'] = 'face-build'; save()
            built = controller.face_original_build(':')
            assert c.getAttr('FaceFitSkeleton.buildCompleted')
            c.file(rename=str(OUT / 'body-face-built-checkpoint.mb'))
            c.file(save=True, type='mayaBinary', force=True)
            assert body() == retained
        state = c.undoInfo(query=True, state=True)
        c.undoInfo(stateWithoutFlush=False)
        try:
            built_poses = poses()
        finally:
            c.undoInfo(stateWithoutFlush=state)
        built_identity = scene_identity()
        built_skin = skin_snapshot(include_non_mesh=True)
        if not reuse:
            c.undo()
            compare(before_identity, scene_identity())
            compare(before_skins, skin_snapshot(include_non_mesh=True))
            assert body() == retained
            c.redo()
            compare(built_identity, scene_identity())
            compare(built_skin, skin_snapshot(include_non_mesh=True))
            assert body() == retained
            c.undoInfo(stateWithoutFlush=False)
            try:
                compare(built_poses, poses())
            finally:
                c.undoInfo(stateWithoutFlush=state)
        report['build'] = dict(stages=list(built['stages']), undo_redo=not reuse,
                               global_animation_error=built_poses['global_animation_error'])
        saved = OUT / 'body-face-built.mb'
        c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
        c.file(str(saved), open=True, force=True, executeScriptNodes=False)
        assert body() == retained
        compare(built_skin, skin_snapshot(include_non_mesh=True))
        compare(built_poses, poses())
        report['saved_reopened'] = True
        report['stage'] = 'face-rebuild'; save()
        before_rebuild_identity = scene_identity()
        rebuilt = controller.face_original_build(':')
        assert body() == retained
        rebuilt_identity = scene_identity()
        rebuilt_skin = skin_snapshot(include_non_mesh=True)
        c.undoInfo(stateWithoutFlush=False)
        try:
            rebuilt_poses = poses()
        finally:
            c.undoInfo(stateWithoutFlush=state)
        report['rebuild'] = dict(stages=list(rebuilt['stages']),
            skin_error=compare(built_skin, rebuilt_skin),
            pose_error=compare(built_poses, rebuilt_poses))
        c.undo()
        compare(before_rebuild_identity, scene_identity())
        compare(built_skin, skin_snapshot(include_non_mesh=True))
        assert body() == retained
        c.redo()
        compare(rebuilt_identity, scene_identity())
        compare(rebuilt_skin, skin_snapshot(include_non_mesh=True))
        assert body() == retained
        report['rebuild']['undo_redo'] = True
        assert before_curves <= set(c.ls(type='animCurve', uuid=True) or [])
        c.file(rename=str(OUT / 'body-face-rebuilt.mb'))
        c.file(save=True, type='mayaBinary', force=True)
        report.update(status='passed', stage='complete')
    except Exception:
        report.update(status='failed', error=traceback.format_exc())
    finally:
        save()
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            utils.executeDeferred(c.quit, force=True)
