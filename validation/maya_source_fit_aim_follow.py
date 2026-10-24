"""Actual generic Aim constructor against MEL's central follow graph."""
from pathlib import Path
import json, os, sys, traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/source-fit-aim-follow-current'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_body_fit_aim import MayaBodyFitAimMixin, SOURCE_FOLLOW
    from adv_py.core.body_fit_aim import BodyFitAimSpec

    class Host(MayaBodyFitAimMixin):
        _cmds = c
        _transaction_changed = False
        def _require_transaction(self): pass

    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), cases=[], legacy_tr_readable=0, saved_graphs_reopened=0)
    def matrix(node): return tuple(c.xform(node, query=True, worldSpace=True, matrix=True))
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        for opm in (False, True):
            for authored_main in (False, True):
                outputs = []
                for native in (True, False):
                    c.file(new=True, force=True)
                    c.createNode('transform', name='FitSkeleton')
                    c.addAttr('FitSkeleton', longName='useOffsetParentMatrix', attributeType='bool')
                    c.setAttr('FitSkeleton.useOffsetParentMatrix', opm)
                    main_node = c.createNode('transform', name='Main')
                    if authored_main:
                        c.setAttr(main_node + '.translate', 2., -1., 3., type='double3')
                        c.setAttr(main_node + '.rotate', 7., -13., 19., type='double3')
                        c.setAttr(main_node + '.scale', 1.2, .9, 1.1, type='double3')
                    target = c.createNode('transform', name='Head_M')
                    c.setAttr(target + '.translate', 3., 5., 1., type='double3')
                    c.setAttr(target + '.rotate', 11., 23., -9., type='double3')
                    system = c.createNode('transform', name='AimSystem')
                    spec = BodyFitAimSpec('Eye', 'Eye', '|AimSystem|AdvPy_AimEye',
                        '|AimSystem|AdvPy_AimEye|AdvPy_AimOffsetEye',
                        '|AimSystem|AdvPy_AimEye|AdvPy_AimOffsetEye|AdvPy_AimFollowEye',
                        '|AimSystem|AdvPy_AimEye|AdvPy_AimOffsetEye|AdvPy_AimFollowEye|AdvPy_AimEye_M',
                        (0., 6., 4.), .5, '|Head_M', ())
                    if native:
                        root = c.createNode('transform', name='NativeAimEye', parent=system)
                        offset = c.createNode('transform', name='NativeAimOffsetEye', parent=root)
                        follow = c.createNode('transform', name='NativeAimFollowEye', parent=offset)
                        driver = c.createNode('transform', name='NativeAimEye_M', parent=follow)
                        c.xform(offset, worldSpace=True, translation=spec.center_position)
                        mel.eval('asParentConstraintBlend "' + driver + '" "' + follow + '" "Head_M";')
                        local = c.createNode('multMatrix', name='NativeAimFollowEyeMM')
                        c.connectAttr('NativeAimFollowEyeBM.outputMatrix', local + '.matrixIn[0]')
                        c.connectAttr(offset + '.worldInverseMatrix[0]', local + '.matrixIn[1]')
                        destination = follow + ('.offsetParentMatrix' if opm else 'DM.inputMatrix')
                        c.connectAttr(local + '.matrixSum', destination, force=True)
                    else:
                        host = Host()
                        host.create_body_fit_aim(spec, global_control='|Main', use_offset_parent_matrix=opm)
                        assert host.capture_body_fit_aim(spec, global_control='|Main', use_offset_parent_matrix=opm)
                        follow, driver = spec.follow, spec.center_control
                        if not opm:
                            dm = spec.follow_local_name + 'DM'
                            c.disconnectAttr(dm + '.outputScale', follow + '.scale')
                            assert not host.capture_body_fit_aim(spec, global_control='|Main', use_offset_parent_matrix=False)
                            marker = spec.follow_blend_name + '.' + SOURCE_FOLLOW
                            c.setAttr(marker, lock=False)
                            c.deleteAttr(marker)
                            assert host.capture_body_fit_aim(spec, global_control='|Main', use_offset_parent_matrix=False)
                            report['legacy_tr_readable'] += 1
                            c.addAttr(spec.follow_blend_name, longName=SOURCE_FOLLOW, attributeType='bool', defaultValue=True)
                            c.setAttr(marker, True, lock=True)
                            c.connectAttr(dm + '.outputScale', follow + '.scale')
                            c.setAttr(dm + '.inputRotateOrder', 1)
                            assert not host.capture_body_fit_aim(spec, global_control='|Main', use_offset_parent_matrix=False)
                            c.setAttr(dm + '.inputRotateOrder', c.getAttr(follow + '.rotateOrder'))
                        saved = OUT / ('follow-' + str(int(opm)) + '-' + str(int(authored_main)) + '.mb')
                        c.file(rename=str(saved))
                        c.file(save=True, type='mayaBinary', force=True)
                        c.file(str(saved), open=True, force=True, executeScriptNodes=False)
                        assert host.capture_body_fit_aim(spec, global_control='|Main', use_offset_parent_matrix=opm)
                        report['saved_graphs_reopened'] += 1
                    rows = []
                    for weight in (0., 5., 10.):
                        for pose in ('neutral', 'head_scale', 'main_scale'):
                            c.setAttr(target + '.scale', 1.3 if pose == 'head_scale' else 1.,
                                .8 if pose == 'head_scale' else 1., 1.1 if pose == 'head_scale' else 1., type='double3')
                            initial = (1.2, .9, 1.1) if authored_main else (1., 1., 1.)
                            scales = tuple(value * factor for value, factor in zip(initial,
                                (1.4, .7, 1.2) if pose == 'main_scale' else (1., 1., 1.)))
                            c.setAttr(main_node + '.scale', *scales, type='double3')
                            c.setAttr(driver + '.follow', weight)
                            c.dgdirty(allPlugs=True)
                            rows.append(dict(weight=weight, pose=pose, matrix=matrix(follow)))
                    outputs.append(rows)
                for expected, actual in zip(*outputs):
                    error = max(abs(a-b) for a,b in zip(expected['matrix'], actual['matrix']))
                    report['cases'].append(dict(opm=opm, authored_main=authored_main,
                        weight=actual['weight'], pose=actual['pose'], maximum_error=error))
        assert max(row['maximum_error'] for row in report['cases']) <= 1e-5
        report['status'] = 'passed'
        if os.environ.get('ADV_AIM_FOLLOW_LIFECYCLE') == '1':
            report.update(status='running', component_status='passed', stage='character-lifecycle')
            (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            import maya_source_rp_follow_lifecycle as lifecycle
            result = lifecycle.main(standalone=False, quit_on_finish=False)
            report['lifecycle_report'] = str(lifecycle.OUT / 'report.json')
            report.update(status='passed' if result == 0 else 'failed', stage='complete')
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish: c.evalDeferred(lambda: c.quit(force=True))
    return 0 if report['status'] == 'passed' else 1
