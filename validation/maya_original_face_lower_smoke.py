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


def create_face(cmds, om, *, transform_point=None):
    points = []
    for iy in range(41):
        y = 1 + iy * .1
        for ix in range(41):
            x = -2 + ix * .1
            point = (x, y, 1.2 - .12*x*x + .03*(y-3)**2)
            points.append(om.MPoint(*(transform_point(point) if transform_point else point)))
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


def fit_input(cmds, om, controller, *, multi=False, opm=False, lip_controls=12,
              complete=False, attachments=False, head_joint=None, geometry_scale=1.0):
    if multi and not cmds.objExists('DeformationSystem'):
        cmds.createNode('transform', name='DeformationSystem')
    cmds.select(clear=True)
    head = head_joint or cmds.joint(name='Head_M', position=(0, 3, 0))
    head_position = cmds.xform(head, query=True, worldSpace=True, translation=True)
    def point(value):
        if head_joint is None and geometry_scale == 1.0:
            return value
        return tuple(head_position[i] + geometry_scale * (value[i] - (0, 3, 0)[i])
                     for i in range(3))
    mesh, ring, vertex_index = create_face(cmds, om, transform_point=point)
    for side, x in (('Right', -.8), ('Left', .8)):
        eye = cmds.polySphere(name='Eye'+side, radius=.31 * geometry_scale, subdivisionsX=16,
                              subdivisionsY=12, constructionHistory=False)[0]
        cmds.xform(eye, translation=point((x, 4, 1.05)), worldSpace=True)
        cmds.makeIdentity(eye,apply=True,translate=True,rotate=True,scale=True)
        cmds.skinCluster(head, eye, toSelectedBones=True, name=eye+'HeadSkin')
    cmds.skinCluster(head, mesh, toSelectedBones=True, name='HeadSkin')
    cmds.select(mesh+'.f[*]', replace=True); controller.face_pre_record_mask(':')
    for role in ('Face', 'AllHead'):
        cmds.select([mesh, 'EyeRight', 'EyeLeft'] if role == 'AllHead' else mesh, replace=True)
        controller.face_pre_record_objects(':', role, head)
    fit = 'FaceFitSkeleton'
    for attr, value in (('RightEye', 'EyeRight'), ('LeftEye', 'EyeLeft')):
        if not cmds.objExists(fit+'.'+attr): cmds.addAttr(fit, longName=attr, dataType='string')
        cmds.setAttr(fit+'.'+attr, value, type='string')
    controller.face_fit_eye_ball(':', '|EyeRight', head)
    if head_joint:
        # The native Body-to-Face operation starts at the old Body eye.
        # Author this procedural fixture's Fit at its own actual eye center.
        cmds.xform('FitEyeBall', translation=point((-.8, 4, 1.05)), worldSpace=True)
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
    if complete:
        for section, x, y in (('EyeBrowInner', -.4, 4.6), ('EyeBrowOuter', -1.2, 4.6),
                              ('EyeBrowCenter', 0, 4.5), ('EyeBrowMid1', -.8, 4.7)):
            index=vertex_index[round((y-1)*10)*41+round((x+2)*10)]
            cmds.select(f'{mesh}.vtx[{index}]',replace=True)
            controller.face_fit_marker(':',section)
        corners=[vertex_index[iy*41+ix] for ix,iy in ((20,27),(20,40),(2,33))]
        cmds.select([f'{mesh}.vtx[{v}]' for v in corners],replace=True)
        controller.face_fit_marker(':','ForeHead')
        controller.face_fit_marker(':','UpMidLo')
        parts=[]
        for name,y,width,depth in (('UpperTeethMesh',2.65,.6,.3),
                                   ('LowerTeethMesh',2.35,.6,.3),('TongueMesh',2.45,.35,.7)):
            part=cmds.polyCube(name=name,width=width*geometry_scale,height=.1*geometry_scale,depth=depth*geometry_scale,
                subdivisionsWidth=4,subdivisionsHeight=2,subdivisionsDepth=8,
                constructionHistory=False)[0]
            cmds.xform(part,translation=point((0,y,.6)),worldSpace=True)
            cmds.makeIdentity(part,apply=True,translate=True,rotate=True,scale=True)
            cmds.skinCluster(head,part,toSelectedBones=True,name=name+'HeadSkin')
            parts.append(part)
        if attachments:
            for role,y,height in (('Eyebrow',4.65,.16),('EyeLash',4.32,.06)):
                fitted=[]
                for side,x in (('Right',-.8),('Left',.8)):
                    part=cmds.polyPlane(name=role+side,width=.8*geometry_scale,height=height*geometry_scale,
                        subdivisionsX=8,subdivisionsY=2,axis=(0,0,1),constructionHistory=False)[0]
                    cmds.xform(part,translation=point((x,y,1.16)),worldSpace=True)
                    cmds.makeIdentity(part,apply=True,translate=True,rotate=True,scale=True)
                    cmds.skinCluster(head,part,toSelectedBones=True,name=part+'HeadSkin')
                    parts.append(part); fitted.append(part)
                cmds.select(fitted,replace=True); controller.face_teeth_record(':',role)
        cmds.select([mesh,'EyeRight','EyeLeft',*parts],replace=True)
        controller.face_pre_record_objects(':','AllHead',head)
        for role,node in (('UpperTeeth','UpperTeethMesh'),('LowerTeeth','LowerTeethMesh')):
            cmds.select(node,replace=True); controller.face_teeth_record(':',role)
        cmds.select('TongueMesh',replace=True); controller.face_tongue(':','record')
        controller.face_tongue(':','fit')
        cmds.setAttr(fit+'.Include',0)
    return fit


def validate_lower_motion(cmds, *, complete=False, attachments=False):
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
    if complete:
        report.update(validate_complete_motion(cmds, attachments=attachments))
    return report


def validate_complete_motion(cmds, *, attachments=False):
    """Read actual production meshes, including all fitted oral parts."""
    def points(mesh):
        values=tuple(cmds.xform(mesh+'.vtx[*]',query=True,worldSpace=True,translation=True))
        assert values and all(isfinite(v) for v in values), mesh
        return values
    report={}
    cases=(('ctrlBrow_R.ty',1,'FaceMesh'),('ctrlBrow_R.tx',1,'FaceMesh'),
           ('ctrlBrow_R.squeeze',10,'FaceMesh'),('ctrlBrow_L.outerUpDown',10,'FaceMesh'),
           ('ctrlEye_R.blink',10,'FaceMesh'),('ctrlEye_R.squint',10,'FaceMesh'),
           ('upperFace_M.ty',.15,'FaceMesh'),('middleFace_M.tx',.15,'FaceMesh'),
           ('lowerFace_M.ty',.15,'FaceMesh'),('upperTeeth_M.ty',.15,'UpperTeethMesh'),
           ('lowerTeeth_M.ty',.15,'LowerTeethMesh'),('Tongue1_M.rz',15,'TongueMesh'),
           ('Tongue3_M.ty',.15,'TongueMesh'),('ctrlMouth_M.ty',-1,'LowerTeethMesh'),
           ('ctrlMouth_M.ty',-1,'TongueMesh'),('ctrlPhonemes_M.rrr',10,'TongueMesh'),
           ('ctrlPhonemes_M.lntd',10,'TongueMesh'))
    if attachments:
        cases+= (('ctrlBrow_R.ty',1,'EyebrowRight'),('ctrlBrow_L.squeeze',10,'EyebrowLeft'),
                 ('ctrlEye_R.blink',10,'EyeLashRight'),('ctrlEye_L.squint',10,'EyeLashLeft'))
    for plug,value,mesh in cases:
        assert cmds.objExists(plug),plug
        baseline=points(mesh)
        cmds.setAttr(plug,value)
        moved=points(mesh)
        delta=max(abs(a-b) for a,b in zip(baseline,moved))
        assert delta>1e-5,(plug,value,mesh,'production mesh did not deform')
        report[f'{plug}={value}/{mesh}']=delta
        cmds.setAttr(plug,0)
        reset=max(abs(a-b) for a,b in zip(baseline,points(mesh)))
        assert reset<1e-4,(plug,mesh,'neutral pose changed',reset)
    for mesh in ('UpperTeethMesh','LowerTeethMesh','TongueMesh','EyeRight','EyeLeft'):
        baseline=points(mesh)
        cmds.setAttr('Head_M.tx',2)
        moved=points(mesh)
        assert max(abs(moved[i]-baseline[i]-2) for i in range(0,len(moved),3))<1e-4,mesh
        cmds.setAttr('Head_M.tx',0)
        report['head_follow/'+mesh]=True
    return report


def main(output, full=False, resume=None, rebuild=False, multi=False, opm=False, lip_controls=12, complete=False, attachments=False):
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
              'include': 'Complete' if complete else 'Skip Above Eyes', 'stages': [], 'multi': multi, 'opm': opm,
              'lip_controls': lip_controls, 'full_entry': full, 'attachments': attachments}
    try:
        if resume:
            cmds.file(str(resume), open=True, force=True, executeScriptNodes=False)
            fit = 'FaceFitSkeleton'
        else:
            fit = fit_input(cmds, om, controller, multi=multi, opm=opm, lip_controls=lip_controls,complete=complete,attachments=attachments)
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
            # Retained Fit curves must survive the build's native redo too.
            # A rig-group existence check alone can miss an aborted chunk or
            # a broken temporary ForeHead construction history.
            fit_curves = {node: tuple(cmds.xform(node + '.cv[*]', query=True,
                worldSpace=True, translation=True)) for node in
                ('ForeHeadCurve', 'ForeHeadCurveLeft') if cmds.objExists(node)}
            cmds.undo(); assert not cmds.objExists('FaceMotionSystem')
            cmds.redo(); assert cmds.objExists('FaceMotionSystem')
            assert cmds.getAttr(fit+'.buildCompleted')
            assert cmds.getAttr(fit+'.buildStep') == len(ORIGINAL_FACE_BUILD_STEPS)
            for node, points in fit_curves.items():
                restored = tuple(cmds.xform(node + '.cv[*]', query=True,
                    worldSpace=True, translation=True))
                assert len(restored) == len(points), (node, 'Fit topology changed on redo')
                assert max(abs(a-b) for a,b in zip(points,restored)) < 1e-5, node
            report['fit_curves_undo_redo'] = list(fit_curves)
            report['single_undo_redo'] = True
        if multi:
            # Author a layer weight before the baseline. A rebuild must keep
            # this edit, rather than merely regenerate similar default data.
            cmds.skinPercent('LipSC', 'FaceMesh.vtx[100]',
                transformValue=[('upperLipJoint0_M', .37), ('MultiSkinClustersFaceLipJoint_M', .63)],
                zeroRemainingInfluences=True)
            report['authored_layer_weight'] = cmds.skinPercent('LipSC', 'FaceMesh.vtx[100]',
                query=True, transform='upperLipJoint0_M')
            if complete:
                part_skin=next(node for node in cmds.listHistory('TongueMesh') or []
                    if cmds.nodeType(node)=='skinCluster' and node.startswith('UpMidLocSC'))
                cmds.skinPercent(part_skin,'TongueMesh.vtx[1]',
                    transformValue=[('upperFaceJoint_M',.31),('middleFaceJoint_M',.69)],
                    zeroRemainingInfluences=True)
                report['authored_part_layer']={'skin':part_skin,'weight':cmds.skinPercent(part_skin,
                    'TongueMesh.vtx[1]',query=True,transform='upperFaceJoint_M')}

        report['motion'] = validate_lower_motion(cmds, complete=complete, attachments=attachments)
        scene = output/'face-completed.mb'
        cmds.file(rename=str(scene)); cmds.file(save=True, type='mayaBinary', force=True)
        cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
        reopened = validate_lower_motion(cmds, complete=complete, attachments=attachments)
        assert max(abs(reopened[k]-v) for k, v in report['motion'].items()) < 1e-5
        report['saved_reopened'] = True
        if rebuild:
            cmds.addAttr('ctrlLips_M', longName='authoredLipStrength', attributeType='double',
                         minValue=0, maxValue=1, defaultValue=.37, keyable=True)
            old_skin_id = cmds.ls('LipSC' if multi else 'HeadSkin', uuid=True)[0]
            rebuilt=controller.face_original_build(':', cage_smooth=1, jaw_smooth=1)
            report['restore_result']=rebuilt['stages']['RebuildRestore']
            report['prefix_before_undo']=cmds.ls('prefix_FaceGroup*',long=True) or []
            assert not cmds.objExists('prefix_FaceGroup'), ('before Undo',report['restore_result'])
            cmds.undo()
            assert cmds.ls('LipSC' if multi else 'HeadSkin', uuid=True)[0] == old_skin_id
            assert abs(cmds.getAttr('ctrlLips_M.authoredLipStrength')-.37) < 1e-8
            cmds.redo()
            report['rebuild_undo_redo'] = True
            assert not cmds.objExists('prefix_FaceGroup')
            report['rebuilt_motion'] = validate_lower_motion(cmds, complete=complete, attachments=attachments)
            assert max(abs(report['rebuilt_motion'][k]-v) for k, v in report['motion'].items()) < 1e-5
            assert abs(cmds.getAttr('ctrlLips_M.authoredLipStrength')-.37) < 1e-8
            if multi:
                value = cmds.skinPercent('LipSC', 'FaceMesh.vtx[100]',query=True,transform='upperLipJoint0_M')
                assert abs(value-report['authored_layer_weight']) < 1e-8
                report['authored_layer_weight_preserved'] = True
                if complete:
                    authored=report['authored_part_layer']
                    value=cmds.skinPercent(authored['skin'],'TongueMesh.vtx[1]',
                        query=True,transform='upperFaceJoint_M')
                    assert abs(value-authored['weight'])<1e-8,(authored,value)
                    report['authored_part_layer_preserved']=True

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
         lip_controls=lip_controls,complete='--complete' in sys.argv,attachments='--attachments' in sys.argv)
