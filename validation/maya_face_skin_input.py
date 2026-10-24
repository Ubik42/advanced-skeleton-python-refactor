"""Native editable Face Skin input, production lookup and saved scene contract."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/face-skin-input-current'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.core.fit_settings import FitSkeletonValidationError
    report = dict(status='running', pid=os.getpid(), cases=[])
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        for namespace in ('', 'FaceHero'):
            c.file(new=True, force=True)
            if namespace:
                c.namespace(add=namespace)
                c.namespace(set=namespace)
            c.createNode('transform', name='FaceFitSkeleton')
            head = c.createNode('joint', name='Head_M')
            meshes = [c.polyCube(name='FaceMesh' + suffix)[0] for suffix in ('A', 'B')]
            skins = [c.skinCluster(head, mesh, toSelectedBones=True, name='FaceSkin' + suffix)[0]
                     for mesh, suffix in zip(meshes, ('A', 'B'))]
            c.namespace(set=':')
            controller = MayaPanelController()
            scope = namespace or ':'
            host = MayaOriginalFaceBuildHost(namespace=namespace or None)
            controller.face_pre_set_skin_cluster(scope, skins[0])
            controller.face_pre_set_skin_cluster(scope, skins[1])
            assert host.original_face_production_skin('FaceMeshA', 'Head_M') == skins[1]
            c.undo()
            assert controller.face_pre_input_fields(scope)['SkinCluster'] == skins[0]
            c.redo()
            assert controller.face_pre_input_fields(scope)['SkinCluster'] == skins[1]
            for invalid in ('MissingRecordedSkin', ''):
                controller.face_pre_set_skin_cluster(scope, invalid)
                try:
                    host.original_face_production_skin('FaceMeshA', 'Head_M')
                except FitSkeletonValidationError:
                    pass
                else:
                    raise AssertionError('Recorded Skin input was silently replaced')
            controller.face_pre_set_skin_cluster(scope, skins[1])
            scene = OUT / ((namespace or 'root') + '.mb')
            c.file(rename=str(scene))
            c.file(save=True, type='mayaBinary', force=True)
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            assert controller.face_pre_input_fields(scope)['SkinCluster'] == skins[1]
            assert host.original_face_production_skin('FaceMeshA', 'Head_M') == skins[1]
            panel_slot = False
            if not namespace:
                from adv_py.product.maya_panel import create_panel
                panel = create_panel(controller)
                try:
                    assert not panel.face_pre_skin.isReadOnly()
                    panel.face_pre_skin.setText(skins[0])
                    panel.face_pre_skin.setModified(True)
                    panel.face_pre_skin.editingFinished.emit()
                    assert controller.face_pre_input_fields(scope)['SkinCluster'] == skins[0]
                    assert not panel.face_pre_skin.isModified()
                    panel_slot = True
                finally:
                    panel.close()
                    panel.deleteLater()
            report['cases'].append(dict(namespace=namespace, recorded_skin=skins[1],
                undo_redo=True, reopened=True, invalid_input_rejected=True,
                actual_panel_slot=panel_slot))
        report['complete_saved_face_inputs'] = []
        for name in ('ordinary', 'multi'):
            scene = ROOT / 'validation/results/face-optional-full-build' / (name + '.mb')
            assert scene.exists()
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            host = MayaOriginalFaceBuildHost()
            source = host.capture_original_face_prep()
            fit = host._fit(required=True)
            assert source['skin'] == c.getAttr(fit + '.SkinCluster')
            report['complete_saved_face_inputs'].append(dict(name=name,
                selected_skin=source['skin'], preflight_passed=True))
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            c.evalDeferred(lambda: c.quit(force=True))
    return 0 if report['status'] == 'passed' else 1
