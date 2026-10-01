"""Unmodified MEL Partial graph vs Python on the identical current Body.

Maya GUI entry. Only fixture Main/FK identity is translated for native MEL;
this measures Partial behavior, not equivalence of the whole Body builder.
"""
from pathlib import Path
import hashlib, json, sys, traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
SOURCE = ROOT / 'local/adv_6_925/AdvancedSkeleton.mel'
REFERENCE = Path('D:/3D/_tools/_DCC/MayaScope/AnalyseAdv/ADV_6.925_reference/AdvancedSkeleton.mel')


def main(opm=False):
    from maya import cmds, mel
    from adv_py.product.maya_panel_controller import MayaPanelController
    output = ROOT / ('validation/results/partial-joints-opm-parity' if opm else
                     'validation/results/partial-joints-source-parity')
    fixture = ROOT / ('validation/results/partial-joints-opm/neutral-body.mb' if opm else
                      'validation/results/partial-joints-native/neutral-body.mb')
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'opm': opm, 'cases': [],
              'scope': 'Original Partial algorithms on the identical Python Body; whole original Body graph not compared'}
    try:
        assert SOURCE.read_bytes() == REFERENCE.read_bytes()
        report['source_sha256'] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        mel.eval('source "' + SOURCE.as_posix() + '";')
        cmds.optionVar(intValue=('asHaveRanThisVersion', 1))
        cmds.optionVar(intValue=('asDock', 0))
        mel.eval('AdvancedSkeleton;')

        def run(native, count, control, side):
            cmds.file(str(fixture), open=True, force=True, executeScriptNodes=False)
            driver = 'AdvPy_Elbow_' + side + 'FK'
            main_control = 'AdvPy_Global'
            if native:
                main_control = cmds.rename(main_control, 'Main')
                driver = cmds.rename(driver, 'FKElbow_' + side)
                # Current Body stores portable pose values. Original confirms
                # legacy udAttr, absent here, and returns without a dialog.
                if cmds.objExists('buildPose.udAttr'):
                    cmds.deleteAttr('buildPose.udAttr')
                cmds.createNode('transform', name='asBatch')
                cmds.checkBox('asBodyPartialJointsIncCtrlCheckBox', e=True, v=control)
                cmds.checkBox('asBodyMultiPartialJointsBindCheckBox', e=True, v=count > 1)
                cmds.intFieldGrp('multiPartialJointsIntFieldGrp', e=True, value1=count)
                cmds.select('Elbow_' + side, r=True)
                mel.eval('asCreatePartialJoints;' if count == 1 else 'asCreateMultiPartialJoints;')
            else:
                cmds.select(driver, r=True)
                MayaPanelController().partial_joints_create(':', count=count,
                    include_controller=control, auto_bind=count > 1)
            joints = ['ElbowPartial_' + side] if count == 1 else [
                'ElbowPartial%d_%s' % (index, side) for index in range(1, count + 1)]
            samples = []
            for scale in (1., 1.5):
                cmds.setAttr(main_control + '.globalScale', scale)
                for rotation in (0., 45., -30.):
                    cmds.setAttr(driver + '.rz', rotation)
                    for follow in ((0., 5., 10.) if count == 1 else (None,)):
                        if follow is not None:
                            cmds.setAttr(('FK' if control else '') + joints[0] + '.follow', follow)
                        cmds.dgdirty(allPlugs=True)
                        samples.append([cmds.xform(joint, q=True, ws=True, matrix=True) for joint in joints])
            return samples

        for count, control, side in ((1, False, 'R'), (1, True, 'R'),
                                      (1, True, 'L'), (6, False, 'R'), (6, False, 'L')):
            native = run(True, count, control, side)
            port = run(False, count, control, side)
            error = max(abs(a-b) for ns, ps in zip(native, port)
                        for nm, pm in zip(ns, ps) for a, b in zip(nm, pm))
            case = {'count': count, 'control': control, 'side': side,
                    'samples': len(native), 'maximum_world_matrix_error': error}
            report['cases'].append(case)
            assert error < 1e-5, case
        report['status'] = 'passed_source_parity'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (output / 'partial-parity.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        cmds.quit(force=True)
