"""Isolate saved native RP input differences in disposable, unsaved scenes."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results' / os.environ.get('ADV_RP_ISOLATION_OUTPUT', 'rp-source-input-isolation')
NATIVE = ROOT / 'validation/results/original-spline-multi-nonopm-reference/original-spline-multi-nonopm-reference.mb'
PYTHON = ROOT / 'validation/results/source-ik-native-creation-current/original-biped-current.mb'


def numeric_state(commands, node):
    values = {}
    for attr in commands.listAttr(node, scalar=True) or ():
        # listAttr can include children of an uninstantiated container array.
        # They are definitions, not numeric RP inputs; do not read/create them.
        if '[' in attr or '.' in attr or attr.startswith('advPy'):
            continue
        plug = node + '.' + attr
        if commands.getAttr(plug, type=True) in (
                'bool','byte','char','short','long','enum','double','float',
                'doubleAngle','doubleLinear','time'):
            values[attr] = commands.getAttr(plug)
    return values


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        raise ValueError('Use the owned Maya GUI runner')
    from maya import cmds as c
    from maya_original_body_pose_compare import set_edit
    from maya_rp_input_compare import snapshot

    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(),
                  scope='Disposable native-input isolation; not a production fix or parity acceptance')
    try:
        c.file(str(NATIVE), open=True, force=True, executeScriptNodes=False)
        c.currentTime(1)
        native = snapshot(c)
        native_handle = next(iter(native['handles']))
        native_nodes = list(native['handles'][native_handle]['joints'])
        native_states = [numeric_state(c, node) for node in (*native_nodes, native_handle)]
        set_edit(c, ('FKIKArm_L.FKIKBlend','AdvPy_ArmSettings.armIkFk_L',10.,1.), 0)
        c.setAttr('IKArm_L.translateZ', .7)
        c.dgdirty(allPlugs=True)
        reference = {name: c.xform(name, query=True, worldSpace=True, matrix=True)
                     for name in ('Shoulder_L','Elbow_L','Wrist_L')}
        posed = snapshot(c)
        nh = next(iter(native['handles'].values()))
        nj = list(nh['joints'].values())
        na = list(nh['ancestors'].values())
        target = posed['targets']['IKArm_L']['worldMatrix[0]']
        rows = []
        cases = (('baseline',) if os.environ.get('ADV_RP_SCALARS_ONLY') == '1' else
                 ('baseline','jointOrient','jointTranslations','rootOffset',
                  'rootFrame','target','poleVector','combined'))
        for case in cases:
            c.file(str(PYTHON), open=True, force=True, executeScriptNodes=False)
            c.currentTime(1)
            ph = next(iter(snapshot(c)['handles'].values()))
            joints = list(ph['joints'])
            ancestors = list(ph['ancestors'])
            handle = next(iter(snapshot(c)['handles']))
            if case == 'baseline':
                report['neutral_scalar_differences'] = [
                    dict(node=node, differences={attr:dict(native=value,python=actual.get(attr))
                        for attr,value in expected.items() if actual.get(attr)!=value})
                    for node,expected,actual in zip((*joints,handle),native_states,
                        (numeric_state(c,node) for node in (*joints,handle)))]
            if case in ('jointOrient','combined'):
                for node, row in zip(joints, nj):
                    c.setAttr(node+'.jointOrient', *row['jointOrient'][0], type='double3')
            if case in ('jointTranslations','combined'):
                for node, row in zip(joints, nj):
                    for axis, value in zip('XYZ', row['translate'][0]):
                        plug = node+'.translate'+axis
                        source = c.connectionInfo(plug, sourceFromDestination=True)
                        if source:
                            c.disconnectAttr(source, plug)
                        c.setAttr(plug, value)
            for offset, name in ((0,'rootOffset'),(1,'rootFrame')):
                if case not in (name,'combined'):
                    continue
                node = ancestors[offset]
                for attr in ('translate','rotate','scale'):
                    compound = node+'.'+attr
                    for plug in (compound, *(compound+axis for axis in 'XYZ')):
                        source = c.connectionInfo(plug, sourceFromDestination=True)
                        if source:
                            c.disconnectAttr(source, plug)
                    c.setAttr(compound, *na[offset][attr][0], type='double3')
            set_edit(c, ('FKIKArm_L.FKIKBlend','AdvPy_ArmSettings.armIkFk_L',10.,1.), 1)
            c.setAttr('AdvPy_ArmIK_L.translateZ', .7)
            if case in ('target','combined'):
                c.xform('AdvPy_ArmIK_L', worldSpace=True, matrix=target)
            if case in ('poleVector','combined'):
                for axis in 'XYZ':
                    plug=handle+'.poleVector'+axis
                    source=c.connectionInfo(plug,sourceFromDestination=True)
                    if source:
                        c.disconnectAttr(source,plug)
                c.setAttr(handle+'.poleVector',*nh['poleVector'][0],type='double3')
            c.dgdirty(allPlugs=True)
            actual = {name: c.xform(name,query=True,worldSpace=True,matrix=True)
                      for name in reference}
            errors = {name:max(abs(a-b) for a,b in zip(reference[name],actual[name]))
                      for name in reference}
            rows.append(dict(case=case, errors=errors, maximum_error=max(errors.values())))
        report.update(status='passed', rows=rows,
                      note='No scenes saved; copying input values is diagnostic only')
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        (OUT / 'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:
            c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
