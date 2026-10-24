"""Inspect saved native/Python Part graphs without rebuilding the character."""
from pathlib import Path
import json, os, traceback
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
OUT = ROOT / 'validation/results/source-rp-part-snapshot-current'
CURRENT = os.environ.get('ADV_RP_PART_CURRENT', 'source-rp-part-position-final-current')
if not CURRENT or any(part in CURRENT for part in ('/', '\\', '..')):
    raise ValueError('Invalid RP current scene folder')


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c
    report = dict(status='running', pid=os.getpid(), scenes={})
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        for version, scene in (
            ('native', ROOT/'validation/results/source-spline-part-lifecycle-current/opm/native.mb'),
            ('python', ROOT/'validation/results'/CURRENT/'opm/original-biped-current.mb'),
            ('native_neck', ROOT/'validation/results/source-spline-part-lifecycle-current/traditional/native.mb'),
            ('python_neck', ROOT/'validation/results'/CURRENT/'traditional/original-biped-current.mb'),
            ('python_neck_source_frame', ROOT/'validation/results'/CURRENT/'traditional/original-biped-current.mb'),
        ):
            report['scenes'][version] = {}
            native = version.startswith('native')
            neck = 'neck' in version
            for pose in (('neutral', 'neck_scale') if neck else ('neutral', 'stretch', 'length')):
                c.file(str(scene), open=True, force=True, executeScriptNodes=False)
                c.currentTime(1)
                if version == 'python_neck_source_frame':
                    # Exercise the production constructor on the saved input.
                    # Receiver order remains unchanged, as in MEL 74620.
                    from adv_py.adapters.maya_body_fit_aim import create_source_aim_decompose
                    for receiver in c.ls('AdvPy_Eye_*FKAim', type='transform'):
                        source = c.connectionInfo(receiver+'.rotate', sourceFromDestination=True)
                        if not source:
                            source = c.connectionInfo(receiver+'.rotateX', sourceFromDestination=True)
                        assert source and source.rsplit('.', 1)[1] in ('outputRotate', 'outputRotateX')
                        dm = source.rsplit('.', 1)[0]
                        matrix = c.connectionInfo(dm+'.inputMatrix', sourceFromDestination=True)
                        c.delete(dm)
                        create_source_aim_decompose(c, matrix, receiver, dm)
                control = 'IKArm_R' if native else 'AdvPy_ArmIK_R'
                if pose in ('stretch', 'length'):
                    c.setAttr('FKIKArm_R.FKIKBlend', 10.)
                if pose == 'stretch':
                    c.setAttr(control+'.translateX', -2.)
                    c.setAttr(control+'.stretchy', 10.)
                if pose == 'length':
                    c.setAttr(control+'.Lenght1', 1.2)
                if pose == 'neck_scale':
                    control = 'FKNeck_M' if native else 'AdvPy_Neck_MFK'
                    c.setAttr(control+'.scaleY', 1.3)
                    c.setAttr(control+'.scaleZ', .8)
                c.dgdirty(allPlugs=True)
                nodes = {}
                for node in c.ls(long=True):
                    short = node.rsplit('|', 1)[-1]
                    selected = any(s in short for s in ('Neck', 'Head', 'Eye')) if neck else (
                        any(s in short for s in ('Shoulder', 'Elbow', 'Wrist')) and '_R' in short)
                    if not selected:
                        continue
                    kind = c.nodeType(node)
                    row = dict(kind=kind)
                    if c.objectType(node, isAType='transform'):
                        row['parent'] = c.listRelatives(node, parent=True, fullPath=True)
                        row['world'] = c.xform(node, q=True, ws=True, matrix=True)
                        for attr in ('translate', 'scale', 'rotate', 'rotateOrder', 'shear', 'jointOrient', 'offsetParentMatrix', 'inheritsTransform', 'segmentScaleCompensate'):
                            if c.attributeQuery(attr, node=node, exists=True):
                                row[attr] = c.getAttr(node+'.'+attr)
                    row['inputs'] = c.listConnections(node, source=True, destination=False, connections=True, plugs=True) or []
                    if kind == 'multMatrix':
                        row['matrixIn'] = {str(i):c.getAttr(node+'.matrixIn['+str(i)+']') for i in c.getAttr(node+'.matrixIn', multiIndices=True) or []}
                    nodes[short] = row
                report['scenes'][version][pose] = nodes
        report['status'] = 'passed'  # Collection completed, not a parity assertion.
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
