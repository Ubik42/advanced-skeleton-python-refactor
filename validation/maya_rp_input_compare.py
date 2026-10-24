"""Inspect saved native/Python RP solver inputs without rebuilding either rig."""
from pathlib import Path
import json
import os
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation/results' / os.environ.get('ADV_RP_OUTPUT', 'rp-input-current')
SCENES = {
    'native': ROOT / 'validation/results/original-spline-multi-nonopm-reference/original-spline-multi-nonopm-reference.mb',
    'python': ROOT / 'validation/results/source-body-current-parity/original-biped-current.mb',
}
if os.environ.get('ADV_RP_PYTHON_SCENE'):
    SCENES['python'] = Path(os.environ['ADV_RP_PYTHON_SCENE'])


def snapshot(c):
    handles = {}
    for handle in c.ls(type='ikHandle', long=True) or []:
        joints = c.ikHandle(handle, query=True, jointList=True) or []
        if not any('shoulder' in joint.lower() and '_l' in joint.lower() for joint in joints):
            continue
        end = c.ikHandle(handle, query=True, endEffector=True)
        end_joint = c.listConnections(end + '.translateX', source=True, destination=False, type='joint') or []
        if not end_joint:
            end_joint = c.listRelatives(end, parent=True, fullPath=True) or []
        chain = list(dict.fromkeys([*joints, *end_joint]))
        records = {}
        for joint in chain:
            records[joint] = {
                attr: c.getAttr(joint + '.' + attr)
                for attr in ('translate', 'rotate', 'scale', 'jointOrient',
                             'preferredAngle', 'rotateOrder', 'rotateAxis', 'segmentScaleCompensate',
                             'inverseScale', 'matrix', 'parentMatrix[0]', 'worldMatrix[0]')
            }
            records[joint]['inputs'] = c.listConnections(joint, connections=True, plugs=True,
                                                        source=True, destination=False) or []
        ancestors = {}
        parent = c.listRelatives(chain[0], parent=True, fullPath=True) or []
        while parent and len(ancestors) < 8:
            node = parent[0]
            ancestors[node] = {attr: c.getAttr(node + '.' + attr)
                               for attr in ('translate', 'rotate', 'scale', 'matrix',
                                            'offsetParentMatrix', 'worldMatrix[0]')}
            ancestors[node]['inputs'] = c.listConnections(node, source=True, destination=False,
                                                          connections=True, plugs=True) or []
            parent = c.listRelatives(node, parent=True, fullPath=True) or []
        solver=c.ikHandle(handle,query=True,solver=True)
        configuration={node:{attribute:c.getAttr(node+'.'+attribute)
            for attribute in ('maxIterations','tolerance','ikBlend','snapHandleFlagToggle',
                'stickiness','priority','weight','poWeight','positionWeight','autoPriority',
                'rootTwistMode','solverEnable','ikFkManipulation','dTwistControlEnable')
            if c.objExists(node+'.'+attribute)} for node in (handle,solver)}
        handles[handle] = dict(joints=records, ancestors=ancestors,configuration=configuration,
                              solver=c.ikHandle(handle, query=True, solver=True),
                              matrix=c.getAttr(handle + '.worldMatrix[0]'),
                              effector=dict(path=end, translate=c.getAttr(end + '.translate'),
                                            rotate=c.getAttr(end + '.rotate'),
                                            parent=c.listRelatives(end,parent=True,fullPath=True),
                                            matrix=c.getAttr(end + '.worldMatrix[0]')),
                              poleVector=c.getAttr(handle + '.poleVector'),
                              twist=c.getAttr(handle + '.twist'),
                              inputs=c.listConnections(handle, connections=True, plugs=True,
                                                       source=True, destination=False) or [])
    if not handles:
        raise RuntimeError('Saved reference has no left shoulder RP handle')
    graph = {}
    for node in c.ls() or []:
        if not (('Arm' in node or 'Shoulder' in node or 'Elbow' in node)
                and ('_L' in node or '_L_' in node)):
            continue
        kind = c.nodeType(node)
        if kind not in ('multiplyDivide', 'distanceBetween', 'animCurveUU', 'blendTwoAttr', 'clamp'):
            continue
        attrs = {
            'multiplyDivide': ('operation', 'input1', 'input2', 'output'),
            'distanceBetween': ('distance', 'point1', 'point2', 'inMatrix1', 'inMatrix2'),
            'animCurveUU': ('input', 'output', 'preInfinity', 'postInfinity'),
            'blendTwoAttr': ('input[0]', 'input[1]', 'attributesBlender', 'output'),
            'clamp': ('input', 'min', 'max', 'output'),
        }[kind]
        graph[node] = dict(kind=kind, values={attr: c.getAttr(node + '.' + attr) for attr in attrs},
                           inputs=c.listConnections(node, connections=True, plugs=True,
                                                    source=True, destination=False) or [])
        if kind == 'animCurveUU':
            graph[node]['keys'] = [c.keyframe(node, query=True, floatChange=True),
                                   c.keyframe(node, query=True, valueChange=True)]
    body = {node: c.getAttr(node + '.worldMatrix[0]')
            for node in ('Shoulder_L', 'Elbow_L', 'Wrist_L') if c.objExists(node)}
    fit = {}
    roots = c.ls('FitSkeleton', long=True) or []
    if len(roots) == 1:
        for joint in c.listRelatives(roots[0], allDescendents=True, type='joint', fullPath=True) or []:
            if joint.rsplit('|', 1)[-1] in ('Shoulder', 'Elbow', 'Wrist'):
                fit[joint] = c.xform(joint, query=True, worldSpace=True, translation=True)
    controls = {}
    for name in ('FKIKArm_R','FKIKArm_L','FKIKLeg_R','FKIKLeg_L','AdvPy_ArmSettings','AdvPy_LegSettings'):
        if c.objExists(name):
            controls[name] = {attr: c.getAttr(name + '.' + attr)
                              for attr in ('FKIKBlend','armIkFk_R','armIkFk_L','legIkFk_R','legIkFk_L')
                              if c.objExists(name + '.' + attr)}
    targets = {}
    for name in ('IKArm_L', 'PoleArm_L', 'AdvPy_ArmIK_L', 'AdvPy_ArmPole_L'):
        if c.objExists(name):
            targets[name] = {attr: c.getAttr(name + '.' + attr)
                for attr in ('translate','rotate','scale','rotateOrder','rotatePivot',
                             'rotatePivotTranslate','scalePivot','scalePivotTranslate',
                             'offsetParentMatrix','worldMatrix[0]')}
    return dict(handles=handles, graph=graph, body=body, fit=fit, controls=controls, targets=targets)


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), scope='Read-only saved RP inputs; no parity acceptance')
    try:
        for label, path in SCENES.items():
            c.file(str(path), open=True, force=True, executeScriptNodes=False)
            c.currentTime(1)
            report[label] = dict(neutral=snapshot(c))
            mode = 'FKIKArm_L.FKIKBlend' if label == 'native' else 'AdvPy_ArmSettings.armIkFk_L'
            control = 'IKArm_L' if label == 'native' else 'AdvPy_ArmIK_L'
            from maya_original_body_pose_compare import set_edit
            set_edit(c, ('FKIKArm_L.FKIKBlend', 'AdvPy_ArmSettings.armIkFk_L', 10., 1.),
                     0 if label == 'native' else 1)
            c.setAttr(control + '.translateZ', .7)
            c.dgdirty(allPlugs=True)
            report[label]['left_arm_ik'] = snapshot(c)
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and (standalone or quit_on_finish):
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1
