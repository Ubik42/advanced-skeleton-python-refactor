"""Edit saved native/Python live guides, then finish through real panel slots.

No rescanning and no synthetic replacement of projection history. The original
saved guide graph is the reference, including its channel locks and connections.
"""
from pathlib import Path
import json, os, sys, traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/auto-place-guide-edit'


def snapshot(namespace=''):
    from maya import cmds as c
    from maya_auto_place_namespace_full import snapshot as fit_snapshot
    prefix = namespace + ':' if namespace else ''
    result = fit_snapshot(namespace)
    result['handles'] = {
        node.rsplit('|', 1)[-1].removeprefix(prefix): {
            attr: dict(value=c.getAttr(node + '.' + attr),
                       locked=c.getAttr(node + '.' + attr, lock=True),
                       keyable=c.getAttr(node + '.' + attr, keyable=True))
            for attr in ('translateX', 'translateY', 'translateZ',
                         'rotateX', 'rotateY', 'rotateZ',
                         'offsetX', 'offsetY', 'offsetZ')}
        for node in c.listRelatives(prefix + 'asFitHandles', allDescendents=True,
                                    type='transform', fullPath=True) or []
        if c.objExists(node + '.xyz')}
    return result


def difference(a, b):
    from maya_auto_place_namespace_full import difference as fit_difference
    error = fit_difference(a, b)
    assert max(abs(row['fat'] - b['joints'][joint]['fat'])
               for joint, row in a['joints'].items()) <= 1e-8
    assert a['skin_visible'] == b['skin_visible']
    assert a['handles'].keys() == b['handles'].keys()
    for handle, attrs in a['handles'].items():
        for attr, row in attrs.items():
            other = b['handles'][handle][attr]
            assert (row['locked'], row['keyable']) == (other['locked'], other['keyable'])
            assert abs(row['value'] - other['value']) <= 1e-8
    return error


def edit(namespace, group):
    from maya import cmds as c
    prefix = namespace + ':' if namespace else ''
    handles = snapshot(namespace)['handles']
    edits = []
    for index, (handle, attrs) in enumerate(sorted(handles.items())):
        for attr, row in attrs.items():
            if row['locked'] or not attr.startswith(group):
                continue
            amount = ((index % 3) - 1) * (1.5 if group == 'rotate' else .025)
            if not amount:
                amount = .5 if group == 'rotate' else .0125
            c.setAttr(prefix + handle + '.' + attr, row['value'] + amount)
            edits.append(handle + '.' + attr)
    assert edits, group
    return edits


def finish_panel(namespace, slot):
    from PySide2 import QtCore
    from adv_py.product.maya_panel import create_panel
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
    from adv_py.core.preparation_objects import PreparationObjectRole as Role
    from maya import cmds as c
    records = MayaPreparationObjectsHost(namespace or ':')
    records.write_objects(Role.SKIN, tuple(c.ls((namespace + ':' if namespace else '') + 'ProxySkin', long=True)))
    panel = create_panel(MayaPanelController())
    try:
        matches = [i for i in range(panel.roles.count())
                   if panel.roles.item(i).data(QtCore.Qt.UserRole) == (namespace or ':')]
        assert len(matches) == 1, matches
        panel.roles.setCurrentRow(matches[0])
        message = getattr(panel, slot)()
        assert '已结束' in message, message
        return message
    finally:
        panel.close(); panel.deleteLater()


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c, mel
    from maya_auto_place_namespace_full import snapshot as fit_snapshot, difference as fit_difference
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), cases=[],
                  scope='Saved full seven-axis proxy live guide edits and real panel slots; not default-model or complete visual acceptance')
    options = {name: c.optionVar(query=name) if c.optionVar(exists=name) else None
               for name in ('asHaveRanThisVersion', 'asDock')}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.workspaceControl('asWorkspaceControl', label='ADV reference', dockToControl=('ToolBox', 'left'), retain=False)
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 1))
        mel.eval('AdvancedSkeleton;')
        reference = None
        cases = [('native', '', 'native-output.mb', None),
                 ('python', '', 'python-output.mb', '_fit_auto_place'),
                 ('namespace', 'OtherRig', 'guides.mb', '_fit_auto_place'),
                 ('namespace-scale', 'OtherRig', 'guides.mb', '_fit_auto_scale')]
        for name, namespace, filename, slot in cases:
            directory = 'auto-place-namespace-full' if namespace else 'auto-place-proxy-full'
            c.file(str(ROOT / 'validation/results' / directory / filename), open=True, force=True, executeScriptNodes=False)
            row = dict(name=name, namespace=namespace, stages=[]); report['cases'].append(row)
            states = [snapshot(namespace)]
            for group in ('translate', 'rotate', 'offsetX', 'offsetY', 'offsetZ'):
                edits = edit(namespace, group); state = snapshot(namespace); states.append(state)
                movement = fit_difference(states[-2], state)
                assert movement > 1e-6, ('Guide edit did not drive Fit', group, movement)
                row['stages'].append(dict(group=group, edits=edits, maximum_fit_matrix_change=movement))
            guide_scene = OUT / (name + '-edited.mb')
            c.file(rename=str(guide_scene)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(guide_scene), open=True, force=True, executeScriptNodes=False)
            row['guide_reopen_error'] = difference(states[-1], snapshot(namespace))
            assert row['guide_reopen_error'] <= 1e-8
            if slot:
                row['panel_message'] = finish_panel(namespace, slot)
            else:
                for field, value in (('Skin', 'ProxySkin'), ('All', ''), ('RightEye', ''), ('LeftEye', '')):
                    c.textField('asBody' + field + 'TextField', edit=True, text=value)
                mel.eval('asFitDeleteGuides;')
            finished = fit_snapshot(namespace); assert not finished['guides'] and finished['skin_visible']
            if slot:
                c.undo(); row['finish_undo_error'] = difference(states[-1], snapshot(namespace))
                c.redo(); row['finish_redo_error'] = fit_difference(finished, fit_snapshot(namespace))
                assert max(row['finish_undo_error'], row['finish_redo_error']) <= 1e-8
            scene = OUT / (name + '-finished.mb')
            c.file(rename=str(scene)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            row['finish_reopen_error'] = fit_difference(finished, fit_snapshot(namespace))
            assert row['finish_reopen_error'] <= 1e-8
            if reference is None:
                reference = (states, finished)
            else:
                row['native_stage_errors'] = [difference(a, b) for a, b in zip(reference[0], states)]
                row['native_finish_error'] = fit_difference(reference[1], finished)
                assert max(row['native_stage_errors'] + [row['native_finish_error']]) <= 1e-4
            row['status'] = 'passed'
            (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', error=traceback.format_exc())
    finally:
        if c.workspaceControl('asWorkspaceControl', exists=True): c.deleteUI('asWorkspaceControl', control=True)
        for name, value in options.items():
            if value is None: c.optionVar(remove=name)
            else: c.optionVar(intValue=(name, int(value)))
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish: Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish: c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1
