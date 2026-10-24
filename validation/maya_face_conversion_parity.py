"""Complete Face DS→BS/Mixed compared to unedited source in graphical Maya."""
from pathlib import Path
import json
import os
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
                        ('ctrlPhonemes_M.aaa', 10), ('ctrlPhonemes_M.rrr', 10), ('ctrlEmotions_M.happy', 10),
                        ('upperFace_M.ty', .5), ('middleFace_M.ty', .5), ('lowerFace_M.ty', .5)):
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


def skin_snapshot(*, include_non_mesh=False):
    """Read all Skin bind matrices and mesh-output vertex weights."""
    from maya import cmds as c
    from maya.api import OpenMaya as om, OpenMayaAnim as oma
    result = {}
    for node in c.ls(type='skinCluster'):
        selection = om.MSelectionList(); selection.add(node)
        fn = oma.MFnSkinCluster(selection.getDependNode(0))
        influences = fn.influenceObjects()
        outputs = {}
        for obj in fn.getOutputGeometry():
            path = om.MDagPath.getAPathTo(obj)
            if obj.hasFn(om.MFn.kMesh):
                count = om.MFnMesh(path).numVertices
                component = om.MFnSingleIndexedComponent()
                vertices = component.create(om.MFn.kMeshVertComponent)
                component.addElements(range(count))
            elif include_non_mesh:
                # Read native membership for curves and surfaces, including
                # component-tag skins. Keep Maya's component ordering.
                geometry_filter = oma.MFnGeometryFilter(fn.object())
                index = geometry_filter.indexForOutputShape(obj)
                vertices = geometry_filter.getComponentAtIndex(index)
                if vertices.isNull():
                    if obj.hasFn(om.MFn.kNurbsCurve):
                        component = om.MFnSingleIndexedComponent()
                        vertices = component.create(om.MFn.kCurveCVComponent)
                        component.addElements(range(om.MFnNurbsCurve(path).numCVs))
                    elif obj.hasFn(om.MFn.kNurbsSurface):
                        surface = om.MFnNurbsSurface(path)
                        component = om.MFnDoubleIndexedComponent()
                        vertices = component.create(om.MFn.kSurfaceCVComponent)
                        component.addElements([(u, v) for u in range(surface.numCVsInU)
                                                for v in range(surface.numCVsInV)])
                    else:
                        raise AssertionError('Unsupported Skin output: ' + path.fullPathName())
            else:
                continue
            weights, width = fn.getWeights(path, vertices)
            assert width == len(influences), node + ' influence width'
            assert len(weights) % width == 0, node + ' component weight width'
            outputs[path.fullPathName()] = {
                influence.partialPathName(): list(weights[index::width])
                for index, influence in enumerate(influences)}
        result[node] = {'geometry': outputs,
            'bind_pre': {influence.partialPathName(): c.getAttr(node + '.bindPreMatrix[%d]' % fn.indexForInfluenceObject(influence))
                         for influence in influences}}
    return result


def control_states():
    """Capture the source's visible-control membership and TRS lock/display flags."""
    from maya import cmds as c
    result = {}
    for node in c.sets('FaceControlSet', query=True) or []:
        paths = c.ls(node, long=True) or []
        assert len(paths) == 1, node
        channels = {}
        for attribute in ('tx','ty','tz','rx','ry','rz','sx','sy','sz','v'):
            plug = paths[0] + '.' + attribute
            if c.objExists(plug):
                channels[attribute] = {'locked': c.getAttr(plug, lock=True),
                    'keyable': c.getAttr(plug, keyable=True), 'channel_box': c.getAttr(plug, channelBox=True)}
        result[paths[0]] = channels
    return result


def scene_identity():
    """Undo must restore node identities, names, types and all DAG parents."""
    from maya import cmds as c
    result = {}
    for node in c.ls(long=True):
        uuid = c.ls(node, uuid=True)[0]
        result[uuid] = {'name': node, 'type': c.nodeType(node),
                        'parents': c.listRelatives(node, allParents=True, fullPath=True) or []}
    return result


def main(modes=None, *, standalone=False, quit_on_finish=True):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.application.face_conversion import ConvertOriginalFaceToBlendShapes
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'status': 'running', 'pid': os.getpid(), 'cases': {}}
    (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    try:
        mel.eval('source "' + (ROOT / 'local/adv_6_925/AdvancedSkeleton.mel').as_posix() + '";')
        # Keep the source panel docked inside this task's Maya window on the
        # secondary display rather than opening a separate floating panel.
        c.optionVar(intValue=('asHaveRanThisVersion', 1)); c.optionVar(intValue=('asDock', 1)); mel.eval('AdvancedSkeleton;')
        for keep_joints, keep_targets in ((False, False), (False, True), (True, False)):
            name = ('mixed' if keep_joints else 'blendshape') + ('-targets' if keep_targets else '')
            if modes is not None and name not in modes:
                continue
            print('CONVERSION CASE', name, flush=True)
            checkpoint = OUTPUT / (name + '-input.mb')
            if os.environ.get('ADV_FACE_REUSE_NATIVE') == '1':
                native = json.loads((OUTPUT / (name + '-native.json')).read_text(encoding='utf8'))
                # Re-read every geometry type from the preserved source rig.
                # Earlier numeric records intentionally covered mesh weights only.
                c.file(str(OUTPUT / (name + '-native.mb')), open=True, force=True, executeScriptNodes=False)
                native_skin = skin_snapshot(include_non_mesh=True)
                native_controls = control_states()
                (OUTPUT / (name + '-native-skin.json')).write_text(json.dumps(native_skin), encoding='utf8')
            else:
                fixture(keep_joints, keep_targets)
                c.file(rename=str(checkpoint)); c.file(save=True, type='mayaBinary', force=True)
                mel.eval('asBSConvertDStoBS;')
                native = observe()
                native_controls = control_states()
                native_skin = skin_snapshot(include_non_mesh=True)
                (OUTPUT / (name + '-native-skin.json')).write_text(json.dumps(native_skin), encoding='utf8')
                (OUTPUT / (name + '-native.json')).write_text(json.dumps(native), encoding='utf8')
                c.file(rename=str(OUTPUT / (name + '-native.mb')))
                c.file(save=True, type='mayaBinary', force=True)
            c.file(str(checkpoint), open=True, force=True, executeScriptNodes=False)
            # A source operation can leave Maya's global undo switch off.
            # Validate the Python transaction with undo explicitly enabled,
            # as the channel and complete-build parity runners do.
            c.undoInfo(state=True)
            before_identity = scene_identity()
            before_poses = observe()
            before_skin = skin_snapshot(include_non_mesh=True)
            before_controls = control_states()
            host = MayaOriginalFaceBuildHost()
            result = ConvertOriginalFaceToBlendShapes(host).apply(keep_joints=keep_joints, keep_targets=keep_targets)
            python = observe()
            python_skin = skin_snapshot(include_non_mesh=True)
            (OUTPUT / (name + '-python-skin.json')).write_text(json.dumps(python_skin), encoding='utf8')
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
            row['skin_weight_bind_error'] = compare(native_skin, python_skin)
            python_controls = control_states()
            compare(native_controls, python_controls)
            row['control_membership_locks_match'] = True
            row['skin_nodes'] = len(python_skin)
            row['skin_geometry_count'] = sum(len(skin['geometry']) for skin in python_skin.values())
            row['skin_weight_value_count'] = sum(len(weights) for skin in python_skin.values()
                for geometry in skin['geometry'].values() for weights in geometry.values())
            row['source_comparison_passed'] = True
            row['undo_enabled'] = c.undoInfo(query=True, state=True)
            row['undo_name'] = c.undoInfo(query=True, undoName=True)
            from maya import OpenMaya as legacy
            undo_messages = []
            def record_message(message, kind, client):
                undo_messages.append(str(message))
            callback = legacy.MCommandMessage.addCommandOutputCallback(record_message)
            try:
                c.undo()
            finally:
                legacy.MMessage.removeCallback(callback)
            undone_identity = scene_identity()
            (OUTPUT / 'undo-difference.json').write_text(json.dumps({
                'messages': undo_messages,
                'added': {key: value for key, value in undone_identity.items() if key not in before_identity},
                'missing': {key: value for key, value in before_identity.items() if key not in undone_identity},
                'changed': {key: [value, undone_identity[key]] for key, value in before_identity.items()
                            if key in undone_identity and value != undone_identity[key]}}, indent=2), encoding='utf8')
            assert not c.objExists('asFaceBS')
            compare(before_identity, scene_identity())
            row['undo_identity_restored'] = True
            compare(before_controls, control_states())
            row['undo_control_locks_restored'] = True
            row['undo_pose_error'] = compare(before_poses, observe())
            row['undo_skin_error'] = compare(before_skin, skin_snapshot(include_non_mesh=True))
            c.redo(); assert c.objExists('asFaceBS')
            compare(python_controls, control_states())
            row['redo_control_locks_restored'] = True
            redone = observe()
            redone_skin = skin_snapshot(include_non_mesh=True)
            (OUTPUT / (name + '-redone.json')).write_text(json.dumps(redone), encoding='utf8')
            (OUTPUT / (name + '-redone-skin.json')).write_text(json.dumps(redone_skin), encoding='utf8')
            row['redo_skin_error'] = compare(python_skin, redone_skin)
            row['redo_mesh_error'] = max(compare(python[pose]['meshes'], redone[pose]['meshes']) for pose in python)
            row['undo_redo_error'] = compare(python, redone)
            saved = OUTPUT / (name + '.mb')
            c.file(rename=str(saved)); c.file(save=True, type='mayaBinary', force=True)
            c.file(str(saved), open=True, force=True, executeScriptNodes=False)
            row['reopened_error'] = compare(python, observe())
            compare(python_controls, control_states())
            row['reopened_control_locks_restored'] = True
            row['reopened_skin_error'] = compare(python_skin, skin_snapshot(include_non_mesh=True))
            report['cases'][name] = row
            (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
    finally:
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:
            Path(completion).write_text(json.dumps({'pid': os.getpid(), 'status': report['status']}), encoding='utf8')
        if quit_on_finish:
            from maya import utils
            utils.executeDeferred(c.quit, force=True)
