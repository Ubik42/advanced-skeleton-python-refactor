"""Native legacy graph, weighted curves, explicit upgrade and rebuild acceptance."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main(source, output, namespace=':'):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    from adv_py.application.source_spline_mode_upgrade import UpgradeSourceSplineMode
    from adv_py.application import source_body_build
    from adv_py.core.spline_control_rebuild import splines
    if namespace == ':':
        cmds.file(str(source.resolve()), open=True, force=True, executeScriptNodes=False)
    else:
        cmds.file(new=True, force=True)
        cmds.file(str(source.resolve()), i=True, namespace=namespace, executeScriptNodes=False)
    cmds.undoInfo(state=True)
    controller = MayaPanelController()
    mesh = cmds.polyCube(name=('' if namespace == ':' else namespace + ':') + 'SplineUpgradeProxy', subdivisionsY=5)[0]
    cmds.setAttr(mesh + '.translateY', 100)
    native_planner = source_body_build.plan_source_body_splines
    def legacy(*args, **kwargs):
        fk, plans = native_planner(*args, **kwargs)
        return fk, tuple(replace(plan, source_mode=None, source_fit_control_count=None)
                         for plan in plans)
    with patch.object(source_body_build, 'plan_source_body_splines', legacy):
        controller.body_build(namespace, meshes=(mesh,), segment_influences=True)
    output.mkdir(parents=True, exist_ok=True)
    legacy_scene = output / 'legacy-spline.ma'
    cmds.file(rename=str(legacy_scene.resolve()))
    cmds.file(save=True, type='mayaAscii', force=True)
    host = MayaBodyBuildHost(namespace=None if namespace == ':' else namespace)
    c = host._cmds
    old = host.read_character_registration()
    spline = splines(old)[0]
    assert spline.source_mode is None
    # Reproduce the exact historical OPM self-inverse wiring, then exercise
    # its repair in the same native Undo operation as the mode upgrade.
    legacy_matrices = {'AdvPy_SourceRootFollowMM': 2, 'AdvPy_SourceLegLockOutputMM': 1,
                       spline.node_name('AdvPy_SplineFirstFixedMM'): 1}
    legacy_matrices.update({node.path.rsplit('|', 1)[-1] + 'LegLockMM': 2
                            for node in old.nodes})
    with host.transaction('Historical Source OPM fixture'):
        for matrix, index in legacy_matrices.items():
            if not c.objExists(matrix):
                continue
            for target in c.connectionInfo(matrix + '.matrixSum', destinationFromSource=True) or ():
                if not target.endswith('.offsetParentMatrix'):
                    continue
                node = host._resolve_connected_node(target.split('.', 1)[0])
                destination = matrix + f'.matrixIn[{index}]'
                source = c.connectionInfo(destination, sourceFromDestination=True)
                host._transaction_changed = True
                c.disconnectAttr(source, destination)
                c.connectAttr(node + '.parentInverseMatrix[0]', destination)
    assert host.read_character_registration() == old
    for frame, value in ((1., 0.), (4., .7), (9., 1.)):
        c.setKeyframe(spline.mode_control, attribute=spline.mode_attribute, time=frame, value=value)
    curve = c.connectionInfo(spline.mode_plug, sourceFromDestination=True).split('.', 1)[0]
    c.keyTangent(curve, edit=True, weightedTangents=True)
    c.keyTangent(curve, edit=True, inTangentType='fixed', outTangentType='fixed')
    c.keyTangent(curve, edit=True, lock=False, weightLock=False)
    c.keyTangent(curve, edit=True, inAngle=6., outAngle=6., inWeight=.8, outWeight=.8)
    c.setAttr(curve + '.preInfinity', 3)
    c.setAttr(curve + '.postInfinity', 3)
    for attribute in ('FKVis', 'IKVis'):
        c.setKeyframe(spline.visibility_settings, attribute=attribute, time=1, value=1)
        c.setKeyframe(spline.visibility_settings, attribute=attribute, time=9, value=0)
    c.setKeyframe(spline.targets[-1], attribute='translateZ', time=1, value=0)
    c.setKeyframe(spline.targets[-1], attribute='translateZ', time=9, value=2)
    c.currentTime(4)
    frames = tuple(float(value) for value in range(-2, 13))
    curve_uuid = c.ls(curve, uuid=True)[0]
    curve_values = tuple(c.keyframe(curve, query=True, valueChange=True))
    curve_samples = tuple(c.keyframe(curve, query=True, eval=True, time=(frame, frame))[0]
                          for frame in frames)
    tangent_types = (tuple(c.keyTangent(curve, q=True, inTangentType=True)),
                     tuple(c.keyTangent(curve, q=True, outTangentType=True)))
    capture = CaptureBodyCharacterPreservation(host).execute()
    native_nodes = {node.path: node.uuid for node in old.nodes}
    # Shared animation curves are rejected before any graph edits.
    extra = c.createNode('transform', name='SplineSharedCurveGuard', skipSelect=True)
    c.addAttr(extra, longName='value', attributeType='double')
    c.connectAttr(curve + '.output', extra + '.value')
    try:
        UpgradeSourceSplineMode(host).apply()
    except ValueError:
        pass
    else:
        raise AssertionError('shared mode curve was scaled')
    assert host.read_character_registration() == old
    assert tuple(c.keyframe(curve, query=True, valueChange=True)) == curve_values
    c.disconnectAttr(curve + '.output', extra + '.value')
    c.delete(extra)
    # Force a late validation failure to exercise atomic rollback.
    validate = host._validate_character_registration
    def late_failure(registration):
        if splines(registration)[0].source_mode is not None:
            raise RuntimeError('rollback probe')
        return validate(registration)
    with patch.object(host, '_validate_character_registration', side_effect=late_failure):
        try:
            UpgradeSourceSplineMode(host).apply()
        except RuntimeError as error:
            assert str(error) == 'rollback probe', str(error)
        else:
            raise AssertionError('rollback probe did not fail')
    assert host.read_character_registration() == old
    assert tuple(c.keyframe(curve, query=True, valueChange=True)) == curve_values
    upgraded = UpgradeSourceSplineMode(host).apply()
    new = splines(upgraded)[0]
    assert new.source_mode is not None and new.mode_maximum == 10.
    assert c.connectionInfo(new.mode_plug, sourceFromDestination=True).split('.', 1)[0] == curve
    assert c.ls(curve, uuid=True) == [curve_uuid]
    assert tuple(c.keyframe(curve, query=True, valueChange=True)) == tuple(v * 10 for v in curve_values)
    scaled = tuple(c.keyframe(curve, query=True, eval=True, time=(frame, frame))[0] for frame in frames)
    assert max(abs(a * 10 - b) for a, b in zip(curve_samples, scaled)) < 1e-6
    assert tangent_types == (tuple(c.keyTangent(curve, q=True, inTangentType=True)),
                             tuple(c.keyTangent(curve, q=True, outTangentType=True)))
    assert c.getAttr(curve + '.preInfinity') == 3 and c.getAttr(curve + '.postInfinity') == 3
    assert all(next(row for row in upgraded.nodes if row.path == path).uuid == uuid
               for path, uuid in native_nodes.items())
    after = CaptureBodyCharacterPreservation(host).execute()
    assert capture.skins == after.skins
    assert {row.uuid for row in capture.curves} == {row.uuid for row in after.curves}
    cmds.undo()
    assert host.read_character_registration() == old
    assert tuple(c.keyframe(curve, query=True, valueChange=True)) == curve_values
    cmds.redo()
    assert host.read_character_registration() == upgraded
    assert UpgradeSourceSplineMode(host).apply() == upgraded
    output.mkdir(parents=True, exist_ok=True)
    scene = output / 'spline-mode-upgraded.mb'
    cmds.file(rename=str(scene.resolve()))
    cmds.file(save=True, type='mayaBinary', force=True)
    cmds.file(str(scene.resolve()), open=True, force=True, executeScriptNodes=False)
    assert host.read_character_registration() == upgraded
    controller.body_rebuild(namespace, 'SplineModeRebuild')
    rebuilt = host.read_character_registration()
    assert splines(rebuilt)[0].source_mode == new.source_mode
    assert c.ls(curve, uuid=True) == [curve_uuid]
    assert max(abs(a * 10 - b) for a, b in zip(curve_samples,
        (c.keyframe(curve, query=True, eval=True, time=(frame, frame))[0] for frame in frames))) < 1e-6
    report = dict(status='passed', namespace=namespace, mode=new.mode_plug,
        body_joints=len(upgraded.body), weighted_curve_samples=len(frames),
        native_curve_uuid=True, skin_unchanged=True, shared_curve_guard=True,
        late_failure_rollback=True, undo_redo=True, saved_reopened=True,
        ordinary_rebuild=True, idempotent=True, historical_opm_repair=True)
    (output / 'spline-mode-upgrade.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS native Spline mode upgrade', report)


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else ':')
