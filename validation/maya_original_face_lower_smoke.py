"""Native original-stage lower Face on one connected curved topology.

The procedural face is a graph fixture, not an appearance or Sam benchmark.
All fits are authored through public Python entry points; no ADV MEL runs.
"""
from pathlib import Path
import json
import sys
import traceback
from math import isfinite

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def create_face(cmds, om):
    points = []
    for iy in range(41):
        y = 1 + iy * .1
        for ix in range(41):
            x = -2 + ix * .1
            points.append(om.MPoint(x, y, 1.2 - .12*x*x + .03*(y-3)**2))
    counts, vertices = [], []
    holes = ((10, 14, 28, 32), (26, 30, 28, 32), (14, 26, 13, 17))
    for iy in range(40):
        for ix in range(40):
            if any(x0 <= ix < x1 and y0 <= iy < y1 for x0, x1, y0, y1 in holes):
                continue
            # Winding faces toward the positive Z side.
            vertices.extend((iy*41+ix, iy*41+ix+1, (iy+1)*41+ix+1, (iy+1)*41+ix))
            counts.append(4)
    used = sorted(set(vertices))
    vertex_index = {old: new for new, old in enumerate(used)}
    vertices = [vertex_index[old] for old in vertices]
    points = [points[old] for old in used]
    mesh = cmds.createNode('transform', name='FaceMesh')
    parent = om.MSelectionList(); parent.add(mesh)
    om.MFnMesh().create(points, counts, vertices, parent=parent.getDependNode(0))
    cmds.sets(mesh, edit=True, forceElement='initialShadingGroup')
    def ring(x0, x1, y0, y1):
        selection = om.MSelectionList(); selection.add(mesh)
        path = selection.getDagPath(0); path.extendToShape()
        fn = om.MFnMesh(path)
        border = {vertex_index[iy*41+ix] for iy in range(y0, y1+1) for ix in range(x0, x1+1)
                  if ix in (x0, x1) or iy in (y0, y1)}
        edges = [f'{mesh}.e[{i}]' for i in range(fn.numEdges)
                 if set(fn.getEdgeVertices(i)).issubset(border)]
        assert len(edges) == 2*(x1-x0+y1-y0), (x0, x1, y0, y1, len(edges))
        return edges

    return mesh, ring, vertex_index


def fit_input(cmds, om, controller, *, multi=False, opm=False, lip_controls=12):
    if multi: cmds.createNode('transform', name='DeformationSystem')
    cmds.select(clear=True)
    head = cmds.joint(name='Head_M', position=(0, 3, 0))
    mesh, ring, vertex_index = create_face(cmds, om)
    for side, x in (('Right', -.8), ('Left', .8)):
        eye = cmds.polySphere(name='Eye'+side, radius=.31, subdivisionsX=16,
                              subdivisionsY=12, constructionHistory=False)[0]
        cmds.xform(eye, translation=(x, 4, 1.05), worldSpace=True)
        cmds.skinCluster(head, eye, toSelectedBones=True, name=eye+'HeadSkin')
    cmds.skinCluster(head, mesh, toSelectedBones=True, name='HeadSkin')
    cmds.select(mesh+'.f[*]', replace=True); controller.face_pre_record_mask(':')
    for role in ('Face', 'AllHead'):
        cmds.select([mesh, 'EyeRight', 'EyeLeft'] if role == 'AllHead' else mesh, replace=True)
        controller.face_pre_record_objects(':', role, head)
    controller.face_fit_eye_ball(':', '|EyeRight', head)
    fit = 'FaceFitSkeleton'
    for attr, value in (('RightEye', 'EyeRight'), ('LeftEye', 'EyeLeft')):
        if not cmds.objExists(fit+'.'+attr): cmds.addAttr(fit, longName=attr, dataType='string')
        cmds.setAttr(fit+'.'+attr, value, type='string')
    if not cmds.objExists(fit+'.Include'):
        cmds.addAttr(fit, longName='Include', attributeType='enum',
                     enumName='Complete:Skip Above Eyes:Skip Below Eyes:Skip Above+Below Eyes')
    cmds.setAttr(fit+'.Include', 1)
    for attr, value in (('MultiSkinClusters', multi), ('useOffsetParentMatrix', opm)):
        if not cmds.objExists(fit+'.'+attr): cmds.addAttr(fit, longName=attr, attributeType='bool')
        cmds.setAttr(fit+'.'+attr, value)
    if lip_controls != 12:
        assert lip_controls >= 8 and lip_controls % 4 == 0
        cmds.addAttr(fit, longName='LipCtrls', attributeType='enum',
                     enumName=':'.join(str(i) for i in range(8, 105, 4)))
        cmds.setAttr(fit+'.LipCtrls', (lip_controls-8)//4)
    for layer, radius in (('Outer', 4), ('Main', 3), ('Inner', 2)):
        cmds.select(ring(12-radius, 12+radius, 30-radius, 30+radius), replace=True)
        controller.face_fit_eye_lid(':', layer)
    for layer, bounds in (('Outer', (12, 28, 11, 19)), ('Main', (13, 27, 12, 18)),
                          ('Inner', (14, 26, 13, 17))):
        x0, x1, y0, y1 = bounds
        corners = tuple(vertex_index[v] for v in (y1*41+20, y0*41+20, ((y0+y1)//2)*41+x0))
        cmds.select(ring(*bounds)+[f'{mesh}.vtx[{v}]' for v in corners], replace=True)
        controller.face_fit_lip(':', layer)
    markers = {'JawPivot': (-1.6, 2.5), 'JawCorner': (-1.6, 2), 'JawLine': (-1.4, 1.8),
               'Jaw': (0, 1.3), 'ChinCrease': (0, 1.6), 'Throat': (0, 1.1),
               'Cheek': (-1.4, 3), 'CheekBone': (-1.4, 3.5), 'SmileBulge': (-1.1, 2.8),
               'FrownBulge': (-1.1, 2.3), 'Nose': (0, 3.4), 'NoseUnder': (0, 3.1),
               'NoseCorner': (-.3, 3.1), 'NoseSide': (-.4, 3.4), 'NoseBridge': (0, 3.7),
               'Nostril': (-.2, 3.2)}
    for section, (x, y) in markers.items():
        index = vertex_index[round((y-1)*10)*41 + round((x+2)*10)]
        cmds.select(f'{mesh}.vtx[{index}]', replace=True)
        controller.face_fit_marker(':', section)
    controller.face_build_jaw_fit_curves(':')
    return fit


def validate_lower_motion(cmds):
    def points():
        values = tuple(cmds.xform('FaceMesh.vtx[*]', query=True, worldSpace=True, translation=True))
        assert values and all(isfinite(v) for v in values)
        return values

    baseline = points()
    report = {}
    for plug, value in (('ctrlMouth_M.ty', -1), ('ctrlMouth_M.tx', .75),
                        ('ctrlLips_M.ty', 1), ('ctrlLips_M.ty', -1), ('ctrlLips_M.tx', .75),
                        ('ctrlLips_M.upperRoll', 10), ('ctrlLips_M.lowerPucker', 10),
                        ('ctrlMouthCorner_R.smile', 1), ('ctrlCheek_R.tx', 1),
                        ('ctrlNose_R.ty', 1), ('ctrlPhonemes_M.aaa', 10), ('ctrlEmotions_M.happy', 10)):
        assert cmds.objExists(plug), plug
        # Original smile is computed from the two-dimensional mouth-corner
        # slider; animate its public translation channels, not that output.
        drivers = ((plug.replace('.smile', '.tx'), value),
                   (plug.replace('.smile', '.ty'), value)) if plug.endswith('.smile') else ((plug, value),)
        for driver, setting in drivers: cmds.setAttr(driver, setting)
        moved = points()
        delta = max(abs(a-b) for a, b in zip(baseline, moved))
        assert delta > 1e-5, (plug, value, 'production face did not deform')
        report[f'{plug}={value}'] = delta
        for driver, _ in drivers: cmds.setAttr(driver, 0)
        reset = max(abs(a-b) for a, b in zip(baseline, points()))
        assert reset < 1e-4, (plug, value, 'neutral pose changed', reset)
    cmds.setAttr('Head_M.tx', 2)
    moved = points()
    assert max(abs(moved[i]-baseline[i]-2) for i in range(0, len(moved), 3)) < 1e-4
    cmds.setAttr('Head_M.tx', 0)
    report['head_follow'] = True
    return report


def main(output, full=False, resume=None, rebuild=False, multi=False, opm=False, lip_controls=12):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from maya.api import OpenMaya as om
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.core.face_original_build import ORIGINAL_FACE_BUILD_STEPS
    output.mkdir(parents=True, exist_ok=True)
    cmds.file(new=True, force=True); cmds.undoInfo(state=True)
    controller = MayaPanelController()
    report = {'status': 'running', 'input': 'connected curved three-hole face proxy',
              'include': 'Skip Above Eyes', 'stages': [], 'multi': multi, 'opm': opm,
              'lip_controls': lip_controls, 'full_entry': full}
    try:
        if resume:
            cmds.file(str(resume), open=True, force=True, executeScriptNodes=False)
            fit = 'FaceFitSkeleton'
        else:
            fit = fit_input(cmds, om, controller, multi=multi, opm=opm, lip_controls=lip_controls)
            cmds.file(rename=str(output/'face-fit-input.mb'))
            cmds.file(save=True, type='mayaBinary', force=True)
        if full:
            result = controller.face_original_build(':', cage_smooth=1, jaw_smooth=1)
            report['stages'] = list(result['stages'])
        else:
            start = int(cmds.getAttr(fit+'.buildStep')) if cmds.objExists(fit+'.buildStep') else 0
            report['stages'] = list(ORIGINAL_FACE_BUILD_STEPS[:start])
            for index, stage in enumerate(ORIGINAL_FACE_BUILD_STEPS, 1):
                if index <= start: continue
                print('STAGE', index, stage, flush=True)
                controller.face_original_build(':', step=index, cage_smooth=1, jaw_smooth=1)
                assert cmds.getAttr(fit+'.buildStep') == index
                report['stages'].append(stage)
        assert cmds.getAttr(fit+'.buildCompleted')
        if full:
            cmds.undo(); assert not cmds.objExists('FaceMotionSystem')
            cmds.redo(); assert cmds.objExists('FaceMotionSystem')
            report['single_undo_redo'] = True
        if multi:
            # Author a layer weight before the baseline. A rebuild must keep
            # this edit, rather than merely regenerate similar default data.
            cmds.skinPercent('LipSC', 'FaceMesh.vtx[100]',
                transformValue=[('upperLipJoint0_M', .37), ('MultiSkinClustersFaceLipJoint_M', .63)],
                zeroRemainingInfluences=True)
            report['authored_layer_weight'] = cmds.skinPercent('LipSC', 'FaceMesh.vtx[100]',
                query=True, transform='upperLipJoint0_M')
        report['motion'] = validate_lower_motion(cmds)
        scene = output/'face-completed.mb'
        cmds.file(rename=str(scene)); cmds.file(save=True, type='mayaBinary', force=True)
        cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
        reopened = validate_lower_motion(cmds)
        assert max(abs(reopened[k]-v) for k, v in report['motion'].items()) < 1e-5
        report['saved_reopened'] = True
        if rebuild:
            cmds.addAttr('ctrlLips_M', longName='authoredLipStrength', attributeType='double',
                         minValue=0, maxValue=1, defaultValue=.37, keyable=True)
            old_skin_id = cmds.ls('LipSC' if multi else 'HeadSkin', uuid=True)[0]
            controller.face_original_build(':', cage_smooth=1, jaw_smooth=1)
            cmds.undo()
            assert cmds.ls('LipSC' if multi else 'HeadSkin', uuid=True)[0] == old_skin_id
            assert abs(cmds.getAttr('ctrlLips_M.authoredLipStrength')-.37) < 1e-8
            cmds.redo()
            report['rebuild_undo_redo'] = True
            assert not cmds.objExists('prefix_FaceGroup')
            report['rebuilt_motion'] = validate_lower_motion(cmds)
            assert max(abs(report['rebuilt_motion'][k]-v) for k, v in report['motion'].items()) < 1e-5
            assert abs(cmds.getAttr('ctrlLips_M.authoredLipStrength')-.37) < 1e-8
            if multi:
                value = cmds.skinPercent('LipSC', 'FaceMesh.vtx[100]',query=True,transform='upperLipJoint0_M')
                assert abs(value-report['authored_layer_weight']) < 1e-8
                report['authored_layer_weight_preserved'] = True
            report['rebuilt'] = True
        report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'; report['error'] = traceback.format_exc()
        raise
    finally:
        (output/'face-stages.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        cmds.file(rename=str(output/'face-current.mb')); cmds.file(save=True, type='mayaBinary', force=True)


if __name__ == '__main__':
    resume = Path(sys.argv[sys.argv.index('--resume')+1]).resolve() if '--resume' in sys.argv else None
    lip_controls = int(sys.argv[sys.argv.index('--lip-controls')+1]) if '--lip-controls' in sys.argv else 12
    main(Path(sys.argv[1]).resolve(), full='--full' in sys.argv, resume=resume,
         rebuild='--rebuild' in sys.argv, multi='--multi' in sys.argv, opm='--opm' in sys.argv,
         lip_controls=lip_controls)
