"""Complete Face DS→BS/Mixed compared to unedited source in graphical Maya."""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUTPUT = ROOT / 'validation/results/face-conversion-parity'
SCENE = ROOT / 'validation/results/face-complete-shell-fix-live/face-completed.mb'


def fixture(keep_joints, keep_targets):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.application.face_pre import FacePreRole
    if keep_joints:
        # Source Mixed expects the matrix TGXform graph (including its
        # unconditional ctrlBox rewiring). Build a real OPM Face rather than
        # manufacturing those nodes inside an existing constraint-mode rig.
        from maya.api import OpenMaya as om
        from maya_original_face_lower_smoke import fit_input
        from adv_py.product.maya_panel_controller import MayaPanelController
        opm_scene = OUTPUT / 'complete-opm-source-matrix-input.mb'
        if opm_scene.exists():
            c.file(str(opm_scene), open=True, force=True, executeScriptNodes=False)
        else:
            c.file(new=True, force=True); c.undoInfo(state=True)
            controller = MayaPanelController()
            fit_input(c, om, controller, opm=True, complete=True, attachments=True)
            controller.face_original_build(':', cage_smooth=1, jaw_smooth=1)
            c.file(rename=str(opm_scene)); c.file(save=True, type='mayaBinary', force=True)
        c.createNode('transform', name='FitSkeleton')
        c.addAttr('FitSkeleton', longName='useOffsetParentMatrix', attributeType='bool', defaultValue=True)
        c.checkBox('asBodyOffsetParentMatrixCheckBox', edit=True, value=True)
    else:
        c.file(str(SCENE), open=True, force=True, executeScriptNodes=False)
        c.checkBox('asBodyOffsetParentMatrixCheckBox', edit=True, value=False)
    c.undoInfo(state=True); c.autoKeyframe(state=False); c.currentTime(0)
    # The proxy was authored by MFnMesh, which leaves polySurfaceShape1.
    # Normal Maya model creation names this FaceMeshShape; the source's Mixed
    # duplication relies on automatic matching-transform Shape renaming.
    shape = c.listRelatives('FaceMesh', shapes=True, noIntermediate=True, fullPath=True)[0]
    c.rename(shape, 'FaceMeshShape')
    # This fixture contains Python's complete serialized Fit rows. Populate
    # the native text fields directly; source asFaceUpdateInfo(0) on a fresh
    # source UI clears rows that have not yet been represented by that UI.
    if not c.objExists('FaceFitSkeleton.RigType'):
        c.addAttr('FaceFitSkeleton', longName='RigType', attributeType='enum', enumName='Joints:BlendShapes:Mixed')
    host = MayaOriginalFaceBuildHost()
    def text(nodes):
        return ' '.join(c.ls(node, shortNames=True)[0] for node in nodes)
    for name, value in (('Face', 'FaceMesh'), ('AllHead', text(host.read_face_objects(FacePreRole.ALL_HEAD))),
                        ('HeadJoint', 'Head_M'), ('SkinCluster', 'HeadSkin'), ('RightEye', 'EyeRight'), ('LeftEye', 'EyeLeft'),
                        ('UpperTeeth', 'UpperTeethMesh'), ('LowerTeeth', 'LowerTeethMesh'), ('Tongue', 'TongueMesh'),
                        ('Eyebrow', text(host.read_original_face_parts('Eyebrow'))),
                        ('Eyelash', text(host.read_original_face_parts('EyeLash'))),
                        ('Extras', text(host.read_original_face_parts('Extras')))):
        c.textField('asFace' + name + 'TextField', edit=True, text=value)
    for name, value in (('asKeepJointsCheckBox', keep_joints), ('asKeepBSTargetsCheckBox', keep_targets)):
        if not c.checkBox(name, exists=True):
            c.checkBox(name, value=value)
        else:
            c.checkBox(name, edit=True, value=value)


def snapshot():
    from maya import cmds as c
    result = {'blendshapes': {}, 'meshes': {}}
    for node in c.ls('asFaceBS*', type='blendShape'):
        aliases = c.aliasAttr(node, query=True) or []
        targets = {}
        for alias, plug in zip(aliases[::2], aliases[1::2]):
            index = int(plug.split('[')[1][:-1])
            base = node + f'.inputTarget[0].inputTargetGroup[{index}].inputTargetItem[6000]'
            # Empty Maya typed arrays read None before save and [] after
            # reopen. Both represent an empty target, not a numeric tolerance.
            targets[alias] = {'points': c.getAttr(base + '.inputPointsTarget') or [],
                              'components': c.getAttr(base + '.inputComponentsTarget') or []}
        result['blendshapes'][node] = targets
    for mesh in ('FaceMesh', 'EyeRight', 'EyeLeft', 'UpperTeethMesh', 'LowerTeethMesh', 'TongueMesh',
                 'EyebrowRight', 'EyebrowLeft', 'EyeLashRight', 'EyeLashLeft'):
        if not c.objExists(mesh):
            continue
        result['meshes'][mesh] = c.xform(mesh + '.vtx[*]', query=True, worldSpace=True, translation=True)
    return result


def poses():
    from maya import cmds as c
    result = {'neutral': snapshot()}
    for plug, value in (('ctrlEye_R.blink', 10), ('ctrlEye_L.squint', 10),
                        ('ctrlMouth_M.ty', -1), ('ctrlLips_M.tx', .75), ('ctrlLips_M.upperRoll', 10),
                        ('ctrlBrow_R.ty', 1), ('ctrlNose_R.ty', 1),
                        ('ctrlPhonemes_M.aaa', 10), ('ctrlPhonemes_M.rrr', 10), ('ctrlEmotions_M.happy', 10)):
        if not c.objExists(plug):
            continue
        c.setAttr(plug, value)
        result[plug] = snapshot()
        c.setAttr(plug, 0)
    return result


def observe():
    from maya import cmds as c
    state = c.undoInfo(query=True, state=True)
    c.undoInfo(stateWithoutFlush=False)
    try:
        return poses()
    finally:
        c.undoInfo(stateWithoutFlush=state)


def compare(a, b, path=''):
    if isinstance(a, dict):
        assert a.keys() == b.keys(), (path, a.keys() - b.keys(), b.keys() - a.keys())
        return max((compare(a[k], b[k], path + '/' + k) for k in a), default=0.)
    if isinstance(a, (list, tuple)):
        assert len(a) == len(b), (path, len(a), len(b))
        return max((compare(x, y, path) for x, y in zip(a, b)), default=0.)
    if isinstance(a, (int, float)):
        error = abs(a - b)
        assert error <= 1e-4, (path, a, b, error)
        return error
    assert a == b, (path, a, b)
    return 0.


def main(modes=None):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.application.face_conversion import ConvertOriginalFaceToBlendShapes
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'cases': {}}
    (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 0)); mel.eval('AdvancedSkeleton;')
        for keep_joints, keep_targets in ((False, False), (False, True), (True, False)):
            name = ('mixed' if keep_joints else 'blendshape') + ('-targets' if keep_targets else '')
            if modes is not None and name not in modes:
                continue
            print('CONVERSION CASE', name, flush=True)
            fixture(keep_joints, keep_targets)
            checkpoint = OUTPUT / (name + '-input.mb')
            c.file(rename=str(checkpoint)); c.file(save=True, type='mayaBinary', force=True)
            mel.eval('asBSConvertDStoBS;')
            native = observe()
            (OUTPUT / (name + '-native.json')).write_text(json.dumps(native), encoding='utf8')
            c.file(rename=str(OUTPUT / (name + '-native.mb')))
            c.file(save=True, type='mayaBinary', force=True)
            c.file(str(checkpoint), open=True, force=True, executeScriptNodes=False)
            # A source operation can leave Maya's global undo switch off.
            # Validate the Python transaction with undo explicitly enabled,
            # as the channel and complete-build parity runners do.
            c.undoInfo(state=True)
            result = ConvertOriginalFaceToBlendShapes(MayaOriginalFaceBuildHost()).apply(keep_joints=keep_joints, keep_targets=keep_targets)
            python = observe()
            # Preserve both graphs and numeric records even when the strict
            # comparison fails; the next correction starts at that boundary.
            (OUTPUT / (name + '-python.json')).write_text(json.dumps(python), encoding='utf8')
            row = {'targets': len(result['targets']),
                   'blendshape_nodes': len(python['neutral']['blendshapes']), 'poses': len(python),
                   'source_comparison_passed': False}
            report['cases'][name] = row
            try:
                row['maximum_error'] = compare(native, python)
            except Exception:
                c.file(rename=str(OUTPUT / (name + '-python.mb')))
                c.file(save=True, type='mayaBinary', force=True)
                raise
            row['source_comparison_passed'] = True
            row['undo_enabled'] = c.undoInfo(query=True, state=True)
            row['undo_name'] = c.undoInfo(query=True, undoName=True)
            c.undo(); assert not c.objExists('asFaceBS')
            c.redo(); assert c.objExists('asFaceBS')
            row['undo_redo_error'] = compare(python, observe())
            saved = OUTPUT / (name + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            row['reopened_error'] = compare(python, observe())
            report['cases'][name] = row
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        from maya import utils
        utils.executeDeferred(c.quit, force=True)
