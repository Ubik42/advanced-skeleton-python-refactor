"""Native GameSkeleton axes, constraints and Skin handoff against ADV 6.925.

The same authored joint/mesh input is used on both sides. This is the Custom
Orient Joints branch, not a claim about all Game Engine or full Body parity.
"""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/game-skeleton-current'
JOINTS = ('Root_M', 'Spine1_M', 'Shoulder_R', 'Elbow_R', 'Wrist_R')
POSES = ({}, {'Spine1_M.rotateZ': 18.}, {'Shoulder_R.rotateX': 25.},
         {'Elbow_R.rotateY': -12.}, {'Root_M.translateX': 3.},
         {'Root_M.scaleY': 1.2}, {'Wrist_R.rotateZ': 35.})


def setup(legacy_root=False):
    from maya import cmds as c
    c.file(new=True, force=True)
    c.undoInfo(state=True)
    c.createNode('transform', name='Group')
    c.createNode('transform', name='DeformationSystem', parent='Group')
    parent = 'DeformationSystem'
    for name, position, orientation in zip(JOINTS,
            ((0, 0, 0), (0, 5, 0), (-3, 4, 0), (-5, 0, .5), (-4, 0, -.5)),
            ((0, 0, 0), (5, 10, 0), (10, 15, -5), (0, 8, 2), (0, -8, -2))):
        joint = c.createNode('joint', name=name, parent=parent)
        c.setAttr(joint + '.translate', *position, type='double3')
        c.setAttr(joint + '.jointOrient', *orientation, type='double3')
        parent = joint
    if legacy_root:
        c.createNode('joint', name='root', parent='DeformationSystem')
        c.parent('Root_M', 'root')
    mesh = c.polyCube(name='Mesh', width=20, height=12, depth=4, subdivisionsX=6)[0]
    c.setAttr(mesh + '.translate', -4, 6, 0, type='double3')
    c.skinCluster(JOINTS, mesh, name='Skin', toSelectedBones=True,
                  maximumInfluences=3, normalizeWeights=1)


def snapshot():
    from maya import cmds as c
    result = []
    for name in JOINTS:
        node = 'GameSkeleton' + name
        result.extend(c.xform(node, query=True, worldSpace=True, matrix=True))
        for attribute in ('translate', 'rotate', 'jointOrient', 'scale'):
            result.extend(c.getAttr(node + '.' + attribute)[0])
    result.extend(c.xform('Mesh.vtx[*]', query=True, worldSpace=True, translation=True))
    return result


def samples():
    from maya import cmds as c
    baseline = {plug: c.getAttr(plug) for pose in POSES for plug in pose}
    result = []
    for pose in POSES:
        for plug, value in baseline.items():
            c.setAttr(plug, value)
        for plug, value in pose.items():
            c.setAttr(plug, value)
        c.dgdirty(allPlugs=True)
        result.append(snapshot())
    for plug, value in baseline.items():
        c.setAttr(plug, value)
    return result


def maximum_error(expected, actual):
    assert len(expected) == len(actual)
    assert all(len(left) == len(right) for left, right in zip(expected, actual))
    return max(abs(a - b) for left, right in zip(expected, actual) for a, b in zip(left, right))


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c, mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters import maya_original_game_skeleton as port
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'cases': {}}
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        # Supply only the two original option controls; execute the unchanged
        # source procedures, without opening a separate ADV window.
        window = c.window('AdvGameOptionsFixture')
        parent = c.columnLayout(parent=window)
        for name in ('asCustomOrientJointsPrimaryAxisOptionMenu',
                     'asCustomOrientJointsSecondaryAxisOptionMenu'):
            if c.optionMenu(name, exists=True):
                c.deleteUI(name)
            c.optionMenu(name, parent=parent)
            for axis in 'XYZ':
                c.menuItem(label=axis)
        for primary, secondary, legacy_root in (
                ('X','Y',False), ('X','Z',False), ('Y','X',False),
                ('Y','Z',False), ('Z','X',False), ('Z','Y',False),
                ('X','Z',True)):
            label = primary + secondary + ('-legacyRoot' if legacy_root else '')
            report['active_case'] = label
            setup(legacy_root)
            c.optionMenu('asCustomOrientJointsPrimaryAxisOptionMenu', edit=True, value=primary)
            c.optionMenu('asCustomOrientJointsSecondaryAxisOptionMenu', edit=True, value=secondary)
            mel.eval('asCustomOrientJointsCreate;asCustomOrientJointsConnect;')
            expected = samples()
            mel.eval('asCustomOrientTransferSkin;')
            transferred = samples()
            mel.eval('asCustomOrientTransferSkin;')
            restored = samples()
            setup(legacy_root)
            host = MayaBodyBuildHost()
            with host.transaction('GameSkeleton source axis and connect'):
                port.create(host, primary, secondary)
                port.connect(host)
            error = maximum_error(expected, samples())
            with host.transaction('GameSkeleton Skin transfer'):
                port.transfer_skin(host)
            error = max(error, maximum_error(transferred, samples()))
            with host.transaction('GameSkeleton Skin return'):
                port.transfer_skin(host)
            error = max(error, maximum_error(restored, samples()))
            assert error <= 1e-4, (label, error)
            scene = OUT / (label + '.mb')
            c.file(rename=str(scene)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            error = max(error, maximum_error(restored, samples()))
            with host.transaction('GameSkeleton disconnect'):
                port.disconnect(host)
            assert not c.ls('GameSkeleton*_parentConstraint1', 'GameSkeleton*_scaleConstraint1')
            c.undo()
            error = max(error, maximum_error(restored, samples()))
            assert error <= 1e-4, (label, error)
            before_delete = snapshot()
            with host.transaction('GameSkeleton delete'):
                port.delete(host)
            assert not c.objExists('GameSkeletonRoot_M')
            assert not c.objExists('GameSkeletonRoot')
            c.undo()
            assert c.objExists('GameSkeletonRoot_M')
            # Pose setters clear Maya's redo queue. Read the restored graph
            # without changing it until the deletion has been redone.
            error = max(error, maximum_error([before_delete], [snapshot()]))
            assert error <= 1e-4, (label, error)
            c.redo()
            assert not c.objExists('GameSkeletonRoot_M')
            report['cases'][label] = {'maximum_error': error, 'poses': len(POSES),
                                     'skin_transfer_return': True,
                                     'reopen_disconnect_undo': True,
                                     'delete_undo_redo': True,
                                     'legacy_root_wrapper': legacy_root}
        report.pop('active_case', None)
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'
        report['traceback'] = traceback.format_exc()
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (quit_on_finish or standalone):
            Path(completion).write_text(json.dumps({'pid': os.getpid(), 'status': report['status']}), encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main(standalone=True))
