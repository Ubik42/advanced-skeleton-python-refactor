"""Native inline nCloth and Loft helpers on identical, controlled scene inputs.

The nCloth reference is the unedited inline source block compiled into a
validation-only procedure with its MEL locals declared. This is phase parity,
not a claim that the complete original AutoPlace succeeded on Sam.
"""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def hand_fixture():
    from maya import cmds as c
    from maya.api import OpenMaya as om
    from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_GROUPS, FIT_AUTO_PLACE_FINGERS
    c.file(new=True, force=True)
    baseline=set(c.ls(uuid=True) or [])
    c.group(empty=True, name='AutoPlacing')
    for name in FIT_AUTO_PLACE_GROUPS:
        c.group(empty=True, name=name, parent='AutoPlacing')
    c.group(empty=True, name='asFitPivotsFingers', parent='asFitPivots')
    for attr, value in (('bbMinX', -8.), ('bbMaxY', 10.)):
        c.addAttr('AutoPlacing', longName=attr, attributeType='double', defaultValue=value)
    # A watertight palm with four connected rectangular fingers. The fine X
    # grid gives the original topology growth more than four rings per digit.
    cells = {(x, z) for x in range(32) for z in range(16)
             if x >= 16 or z % 4 in (1, 2)}
    points, counts, connects, indices = [], [], [], {}
    def face(corners):
        counts.append(4)
        for corner in corners:
            if corner not in indices:
                indices[corner] = len(points)
                points.append(om.MPoint(-8 + corner[0] * .25, 10 + corner[1] * .25,
                                       -2 + corner[2] * .25))
            connects.append(indices[corner])
    for x, z in sorted(cells):
        face(((x, -1, z), (x+1, -1, z), (x+1, -1, z+1), (x, -1, z+1)))
        face(((x, 1, z+1), (x+1, 1, z+1), (x+1, 1, z), (x, 1, z)))
        if (x-1, z) not in cells:
            face(((x, -1, z), (x, -1, z+1), (x, 1, z+1), (x, 1, z)))
        if (x+1, z) not in cells:
            face(((x+1, -1, z+1), (x+1, -1, z), (x+1, 1, z), (x+1, 1, z+1)))
        if (x, z-1) not in cells:
            face(((x+1, -1, z), (x, -1, z), (x, 1, z), (x+1, 1, z)))
        if (x, z+1) not in cells:
            face(((x, -1, z+1), (x+1, -1, z+1), (x+1, 1, z+1), (x, 1, z+1)))
    fn = om.MFnMesh()
    fn.create(points, counts, connects)
    transform = om.MFnDagNode(fn.parent(0)).fullPathName()
    mesh = c.rename(transform, 'CombinedSkinUpper_M')
    c.parent(mesh, 'asFitCombinedSkins')
    c.createNode('closestPointOnMesh', name='closestSampler')
    c.connectAttr(mesh+'.outMesh', 'closestSampler.inMesh')
    for name, position in (('asFitPivotNeck', (0, 10, 0)),):
        c.createNode('transform', name=name, parent='asFitPivots')
        c.xform(name, worldSpace=True, translation=position)
    for digit, finger in enumerate(FIT_AUTO_PLACE_FINGERS):
        z = -2 + (digit * 4 + 2) * .25
        for segment, x in ((1, -3.75), (4, -8.)):
            node = 'asFitPivot'+finger+'Finger'+str(segment)
            c.createNode('transform', name=node, parent='asFitPivotsFingers')
            c.xform(node, worldSpace=True, translation=(x, 10, z))
    c.select('asFitAutoPlaceJoints')
    for name, position in (('asFitShoulderStraightBase', (0, 10, 0)),
                           ('asFitShoulderStraight', (-1, 10, 0)),
                           ('asFitElbowStraight', (-2, 10, 0))):
        c.joint(name=name, position=position)
    c.skinCluster(('asFitShoulderStraightBase', 'asFitShoulderStraight', 'asFitElbowStraight'),
                  mesh, name='CombinedSkinUpperSC_M', toSelectedBones=True,
                  maximumInfluences=3, dropoffRate=4, removeUnusedInfluence=False)
    c.deltaMush(mesh, name='asFitDeltaMush', smoothingIterations=30,
                smoothingStep=.5, pinBorderVertices=True)
    c.curve(name='asFitScanCurve', degree=1, point=((-8, 0, 0), (0, 0, 0)))
    c.parent('asFitScanCurve', 'asFitScanCurves')
    c.currentTime(1)
    c.refresh()
    return tuple(set(c.ls(uuid=True) or [])-baseline)


def native_finger_procedure(source):
    start = source.index('\t\t//nCloth-fingers', source.index('global proc asFitAutoPlace ()'))
    end = source.index('\n\n\n\t\t}', start)
    block = source[start:end]
    return '''global proc advPyReferenceStraightenFingers () {
int $fourFingerHit=1,$hasNCloth=0,$i,$y,$b,$closestVtxIndex;
float $camOrbitStep=.2,$bbMaxY=10,$bbMinX=-8,$ry,$angleFactor;
float $posA[],$bbMin[],$rot1[],$rot2[];
string $fingers[]={"Index","Middle","Ring","Pinky"};
string $tempString[],$tempString2[],$previousSel[],$fingerVtxs[],$closestToBaseVtx;
''' + block + '\n}'


def native_thumb_procedure(source):
    start=source.index('//thumb (reverse from wrist detection)')
    end=source.index('catchQuiet (`setAttr CombinedSkinLower_M.v 1`);',start)
    return '''global proc advPyReferenceThumb () {
int $hasHitThumbBranch=0,$hasNCloth=1,$r,$t,$closestVtxIndex,$minXupdatedThisRound;
float $zStep=-.16,$xDir=0,$yDir=1,$zDir=0,$bbMaxY=10,$bbMinZ=-2;
float $scanCurveTx,$maxZ,$minX,$maxX;
float $pos[],$posA[],$posB[],$bbMin[],$bbMax[];
string $tempString[],$thumbCurve;
''' + source[start:end] + '\n}'


def thumb_fixture():
    from maya import cmds as c
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_projection import save_projection
    hand_fixture()
    for attr,value in (('bbMinZ',-2.),('bbMaxZ',2.)):
        c.addAttr('AutoPlacing',longName=attr,attributeType='double',defaultValue=value)
    c.rename(c.listRelatives('asFitScanCurve',shapes=True)[0],'asFitScanCurveShape')
    c.setAttr('asFitScanCurve.rotateY',-90.)
    c.setAttr('asFitScanCurve.translate',-3.75,10,0,type='double3')
    c.setAttr('asFitDeltaMush.envelope',0.)
    host=MayaFitJointHost()
    with host.transaction('Native thumb input'):
        save_projection(host,'Wrist','y','CombinedSkinUpper_M','0',True)
    c.group(empty=True,name='asFitScanPolyProjectionCurves',parent='asFitScanCurves')


def thumb_snapshot():
    from maya import cmds as c
    return {name:c.xform(name,query=True,worldSpace=True,matrix=True)
            for name in ('asFitPivotThumbFinger1','asFitPivotThumbFinger4','asFitScanCurve')}


def mesh_snapshot(name):
    from maya import cmds as c
    return {'vertices': c.xform(name+'.vtx[*]', query=True, worldSpace=True, translation=True),
            'count': c.polyEvaluate(name, vertex=True),
            'blend_weight': c.getAttr('straightenBS.weight[0]'),
            'cloth_removed': not c.objExists('asFitNCloth'),
            'finger_pivots_removed': not bool(c.listRelatives('asFitPivotsFingers', children=True)),
            'minimum_x': c.getAttr('AutoPlacing.bbMinX')}


def loft_fixture(axis):
    from maya import cmds as c
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_projection import save_projection
    hand_fixture()
    c.polyCube(name='ProjectionBody', width=8, height=20, depth=4,
               subdivisionsWidth=4, subdivisionsHeight=20, subdivisionsDepth=4)
    c.setAttr('ProjectionBody.translateY', 10.)
    for attr, value in (('bbMinZ', -2.), ('bbMaxZ', 2.)):
        c.addAttr('AutoPlacing', longName=attr, attributeType='double', defaultValue=value)
    c.setAttr('AutoPlacing.bbMaxY', 20.)
    c.setAttr('AutoPlacing.bbMinX', -4.)
    c.rename(c.listRelatives('asFitScanCurve', shapes=True)[0], 'asFitScanCurveShape')
    host = MayaFitJointHost()
    with host.transaction('Identical native Loft inputs'):
        for name, value in ((('Wrist', -3.2), ('Elbow', -2.), ('Shoulder', -1.)) if axis=='yLoft'
                             else (('Root', 8.), ('Neck', 15.), ('Head', 18.))):
            c.setAttr('asFitScanCurve.rotateY', -90. if axis=='yLoft' else 0.)
            c.setAttr('asFitScanCurve.translate', value if axis=='yLoft' else 0,
                      10. if axis=='yLoft' else value, 0, type='double3')
            save_projection(host, name, axis, 'ProjectionBody', 'center', True)
            c.setAttr('asFitHandle'+name+'.offsetZ', .13)
            c.setAttr('asFitPivotOrient'+name+'.rotateX', 7.)
    c.group(empty=True, name='asFitLoftCurves'+axis, parent='AutoPlacing')
    count = 51 if axis=='yLoft' else 24
    for i in range(-1, count):
        name='asFitProjectionLoftCurve'+axis+('a' if i==-1 else str(i))
        c.circle(name=name, normal=(1,0,0) if axis=='yLoft' else (0,1,0),
                 degree=3, sections=8, constructionHistory=False)
        c.parent(name, 'asFitLoftCurves'+axis)
        if axis=='yLoft':
            c.setAttr(name+'.translateX', -4+i*.08)
            c.setAttr(name+'.translateY', 10.)
            c.setAttr(name+'.scale', 1, .75, .65, type='double3')
        else:
            c.setAttr(name+'.translateY', (i+1)*20./24.)
            c.setAttr(name+'.scale', 3.5, 1, 1.5, type='double3')


def loft_snapshot(axis):
    from maya import cmds as c
    reps=('Wrist','Elbow','Shoulder') if axis=='yLoft' else ('Root','Neck','Head')
    return {'vertices': c.xform('asFitLoft'+axis+'.vtx[*]', query=True, worldSpace=True, translation=True),
            'right_vertices': c.xform('asFitLoft'+axis+'_R.vtx[*]', query=True, worldSpace=True, translation=True),
            'pivots': {name: c.xform('asFitPivotOffset'+name, query=True, worldSpace=True, matrix=True) for name in reps},
            'offsets': {name: [c.getAttr('asFitHandle'+name+'.offset'+a) for a in 'XYZ'] for name in reps},
            'contours': {name: c.objExists('asFitProjection'+name+'Contour') for name in reps}}


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c, mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_state import FitAutoPlaceScanState
    from adv_py.adapters.maya_fit_auto_place_fingers import straighten_fingers
    from adv_py.adapters.maya_fit_auto_place_loft import build_loft
    from adv_py.adapters.maya_fit_auto_place_thumb import detect_thumb
    output.mkdir(parents=True, exist_ok=True)
    source=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8')
    mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
    mel.eval(native_finger_procedure(source))
    mel.eval(native_thumb_procedure(source))
    report={'status':'running','cases':[]}
    for case in ('ncloth','zLoft','yLoft'):
        row={'case':case};report['cases'].append(row)
        try:
            (hand_fixture if case=='ncloth' else lambda:loft_fixture(case))()
            scene=output/(case+'-input.mb')
            c.file(rename=str(scene));c.file(save=True, type='mayaBinary', force=True)
            mel.eval('advPyReferenceStraightenFingers;' if case=='ncloth' else 'asFitAutoPlaceLoft '+case+';')
            native=mesh_snapshot('CombinedSkinUpper_M') if case=='ncloth' else loft_snapshot(case)
            c.file(str(scene), open=True, force=True, executeScriptNodes=False)
            host=MayaFitJointHost()
            with host.transaction('Native AutoPlace phase parity'):
                if case=='ncloth':
                    state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-2.,2.,10.,'biped',four_fingers=True)
                    straighten_fingers(state)
                    assert state.has_ncloth and not state.four_fingers and state.index==0
                else:build_loft(host,case)
            python=mesh_snapshot('CombinedSkinUpper_M') if case=='ncloth' else loft_snapshot(case)
            errors={}
            for key in ('vertices','right_vertices'):
                if key not in native:continue
                assert len(native[key])==len(python[key]),(key,len(native[key]),len(python[key]))
                errors[key]=max(abs(a-b) for a,b in zip(native[key],python[key]))
            for key in ('pivots','offsets'):
                if key in native:
                    errors[key]=max(abs(a-b) for name,values in native[key].items() for a,b in zip(values,python[key][name]))
            assert max(errors.values())<=1e-4,errors
            for key in ('count','blend_weight','cloth_removed','finger_pivots_removed','minimum_x','contours'):
                if key in native:assert native[key]==python[key],(key,native[key],python[key])
            row.update(status='passed',errors=errors)
        except Exception:row.update(status='failed',error=traceback.format_exc())
        (output/'phases.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    row={'case':'ncloth_foreign_active_solver'};report['cases'].append(row)
    try:
        hand_fixture()
        # A user's pre-existing solver must survive the source pass's solver
        # rename/delete sequence, including its global active selection.
        c.createNode('nucleus',name='UserNucleus')
        c.setAttr('UserNucleus.spaceScale',.37)
        scale=c.getAttr('UserNucleus.spaceScale')
        uuid=c.ls('UserNucleus',uuid=True)[0]
        mel.eval('setActiveNucleusNode "UserNucleus";')
        host=MayaFitJointHost()
        with host.transaction('AutoPlace separate Nucleus'):
            state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-2.,2.,10.,'biped',four_fingers=True)
            straighten_fingers(state)
        assert c.objExists('UserNucleus') and c.ls('UserNucleus',uuid=True)[0]==uuid
        assert c.getAttr('UserNucleus.spaceScale')==scale
        active=mel.eval('global string $gActiveNucleusNode; $gActiveNucleusNode = $gActiveNucleusNode;')
        assert active=='UserNucleus',active
        assert not c.listConnections('UserNucleus',type='nCloth')
        row.update(status='passed',preserved_solver=True,preserved_active_solver=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'thumb'};report['cases'].append(row)
    try:
        thumb_fixture()
        scene=output/'thumb-input.mb'
        c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
        mel.eval('advPyReferenceThumb;');native=thumb_snapshot()
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        host=MayaFitJointHost()
        with host.transaction('Native thumb phase parity'):
            state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-2.,2.,10.,'biped',
                has_ncloth=True,step_z=-.16,direction=(0,1,0))
            detect_thumb(state)
        python=thumb_snapshot()
        error=max(abs(a-b) for name,values in native.items() for a,b in zip(values,python[name]))
        assert error<=1e-4,error
        assert state.hit_thumb and not c.objExists('angledSamplerOffset')
        row.update(status='passed',maximum_error=error)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'ncloth_character_namespace'};report['cases'].append(row)
    try:
        authored=hand_fixture()
        c.namespace(add='AutoPlaceRig')
        for uuid in authored:
            current=c.ls(uuid,long=True) or []
            if current:
                name=current[0].rsplit('|',1)[-1]
                c.rename(current[0],'AutoPlaceRig:'+name)
        c.createNode('nucleus',name='UserNucleus')
        uuid=c.ls('UserNucleus',uuid=True)[0]
        mel.eval('setActiveNucleusNode "UserNucleus";')
        host=MayaFitJointHost(namespace='AutoPlaceRig')
        with host.transaction('Namespaced native nCloth phase'):
            state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-2.,2.,10.,'biped',four_fingers=True)
            straighten_fingers(state)
        assert state.has_ncloth and c.objExists('AutoPlaceRig:straightenBS')
        assert not c.objExists('AutoPlaceRig:asFitNCloth') and not c.objExists('AutoPlaceRig:asFitNucleus')
        assert c.ls('UserNucleus',uuid=True)[0]==uuid
        assert not c.listConnections('UserNucleus',type='nCloth')
        assert not c.ls('nCloth*','CombinedSkinUpperWrap_M','fingerStraight','asFitNucleus')
        row.update(status='passed',namespace='AutoPlaceRig',foreign_solver_preserved=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    report['status']='passed' if all(row['status']=='passed' for row in report['cases']) else 'failed'
    (output/'phases.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
