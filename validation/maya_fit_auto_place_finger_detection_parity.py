"""Source four-finger topology detection on identical hand geometry.

This isolates the unedited inline MEL detection block from the enclosing
AutoPlace procedure. It does not assert that a full character scan succeeded.
"""
from pathlib import Path
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'validation'))


def native_procedure(source):
    start = source.index('//$fourFingerHit (double-checking first)',
                         source.index('global proc asFitAutoPlace ()'))
    end = source.index('//nCloth-fingers', start)
    return '''global proc int advPyReferenceDetectFingers () {
int $z=0,$fourFingerHit=0,$numHits=4,$numAgentHits,$a,$y,$checkingCurveNr;
int $closestVtxIndex,$cc,$fingerGrowFail=0,$numCV;
float $xDir=0,$yDir=1,$zDir=0,$zStep=-.16,$scanCurveTx,$fingerDetectPopDist;
float $agenCurveTx,$maxFingerWidth=0,$minX2,$diam,$averageDiam=0;
float $bbMin[],$bbMax[],$posA[],$bb[],$bb2[],$pos[],$prevBB[];
string $zxy[]={"y"},$fingers[]={"Index","Middle","Ring","Pinky"};
string $projectOn="CombinedSkinUpper_M",$checkingCurve,$curveCmd;
string $tempString[],$tempString2[],$tempString3[],$tempString4[],$tempString5[];
string $projectedCurves[];
''' + source[start:end] + '\nreturn $fourFingerHit;\n}'


def native_pipeline(source):
    from maya_fit_auto_place_phases import native_finger_procedure
    detection=native_procedure(source)
    detection=detection[detection.index('//$fourFingerHit'):detection.rindex('return $fourFingerHit;')]
    cloth=native_finger_procedure(source)
    cloth=cloth[cloth.index('//nCloth-fingers'):cloth.rindex('}')]
    return '''global proc int advPyReferenceFingerPipeline () {
int $z=0,$fourFingerHit=0,$hasNCloth=0,$numHits=0,$numAgentHits,$a,$y,$b,$i;
int $checkingCurveNr,$closestVtxIndex,$cc,$fingerGrowFail=0,$numCV;
float $xDir=0,$yDir=1,$zDir=0,$zStep=-.16,$scanCurveTx,$fingerDetectPopDist;
float $agenCurveTx,$maxFingerWidth=0,$minX2,$diam,$averageDiam=0;
float $camOrbitStep=.2,$bbMaxY=10,$bbMinX=-8,$ry,$angleFactor;
float $bbMin[],$bbMax[],$posA[],$posB[],$bb[],$bb2[],$pos[],$prevBB[],$rot1[],$rot2[];
string $zxy[]={"y"},$fingers[]={"Index","Middle","Ring","Pinky"};
string $projectOn="CombinedSkinUpper_M",$checkingCurve,$curveCmd,$closestToBaseVtx;
string $tempString[],$tempString2[],$tempString3[],$tempString4[],$tempString5[];
string $projectedCurves[],$previousSel[],$fingerVtxs[];
setAttr asFitScanCurve.t -type float3 -8 10 0;
for ($i=0;$i<100;$i++) {
    $bbMinX=`getAttr AutoPlacing.bbMinX`;
    $zStep=$bbMinX/50.0;
    move -r -os -wd 0 0 $zStep asFitScanCurve;
    if (`objExists asFitScanPolyProjectionCurves`) delete asFitScanPolyProjectionCurves;
    $tempString=`polyProjectCurve -ch true -direction 0 1 0 -pointsOnEdges 0 -curveSamples 50 -automatic 0 asFitScanCurve CombinedSkinUpper_M`;
    rename $tempString[0] asFitScanPolyProjectionCurves;
    parent asFitScanPolyProjectionCurves asFitScanCurves;
    refresh;
    $projectedCurves=`listRelatives -c -type transform asFitScanPolyProjectionCurves`;
    $numHits=size(`listRelatives -c $projectedCurves`);
''' + detection + cloth + '''
    if ($fourFingerHit && $hasNCloth) return 1;
}
return 0;
}'''


def fixture():
    from maya import cmds as c
    from maya_fit_auto_place_phases import hand_fixture
    hand_fixture()
    c.selectMode(object=True)
    children=c.listRelatives('asFitPivotsFingers',children=True) or []
    if children:c.delete(children)
    c.addAttr('AutoPlacing',longName='fingerWidth',attributeType='double',defaultValue=1.)
    c.createNode('transform',name='asFitHandleWrist',parent='asFitHandles')
    c.setAttr('asFitHandleWrist.translateX',-2.)
    c.setAttr('asFitScanCurve.controlPoints[1].xValue',8.)
    c.setAttr('asFitScanCurve.rotateY',-90.)
    c.setAttr('asFitScanCurve.translate',-6.,10.,0.,type='double3')
    result=c.polyProjectCurve('asFitScanCurve','CombinedSkinUpper_M',
        constructionHistory=True,direction=(0,1,0),pointsOnEdges=False,
        curveSamples=50,automatic=False)
    c.rename(result[0],'asFitScanPolyProjectionCurves')
    c.parent('asFitScanPolyProjectionCurves','asFitScanCurves')
    c.refresh()
    projected=c.listRelatives('asFitScanPolyProjectionCurves',children=True,type='transform') or []
    hits=len(c.listRelatives(projected,children=True) or [])
    assert hits==4,('fixture must cross four fingers',hits)
    c.select(clear=True)


def snapshot():
    from maya import cmds as c
    from maya.api import OpenMaya as om
    pivots={node:c.xform(node,query=True,worldSpace=True,matrix=True)
            for node in c.ls('asFitPivot*Finger*',type='transform')}
    curves={}
    for node in c.ls('FingerCurve*',type='transform'):
        curves[node]=[c.xform(cv,query=True,worldSpace=True,translation=True)
                      for cv in c.ls(node+'.cv[*]',flatten=True)]
    selected=om.MSelectionList();selected.add('CombinedSkinUpper_M')
    mesh=om.MFnMesh(selected.getDagPath(0))
    return {'pivots':pivots,'curves':curves,'finger_width':c.getAttr('AutoPlacing.fingerWidth'),
            'points':[(p.x,p.y,p.z) for p in mesh.getPoints(om.MSpace.kWorld)],
            'faces':mesh.numPolygons}


def compare(native,python):
    assert native.keys()==python.keys()
    assert native['pivots'].keys()==python['pivots'].keys()
    assert native['curves'].keys()==python['curves'].keys()
    assert native['faces']==python['faces']
    assert len(native['points'])==len(python['points'])
    errors=[abs(native['finger_width']-python['finger_width'])]
    for name,values in native['pivots'].items():
        errors.extend(abs(a-b) for a,b in zip(values,python['pivots'][name]))
    for name,points in native['curves'].items():
        assert len(points)==len(python['curves'][name]),name
        errors.extend(abs(a-b) for p,q in zip(points,python['curves'][name]) for a,b in zip(p,q))
    errors.extend(abs(a-b) for p,q in zip(native['points'],python['points']) for a,b in zip(p,q))
    return max(errors,default=0.)


def main(output,initialize=True):
    if initialize:
        import maya.standalone
        maya.standalone.initialize(name='python')
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_state import FitAutoPlaceScanState
    from adv_py.adapters.maya_fit_auto_place_fingers import detect_fingers
    output.mkdir(parents=True,exist_ok=True)
    report={'status':'running','cases':[]}
    source=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8-sig')
    mel.eval(native_procedure(source))
    mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
    mel.eval(native_pipeline(source))
    row={'case':'connected_four_finger_hand'};report['cases'].append(row)
    try:
        fixture()
        scene=output/'input.mb'
        c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        detected=bool(mel.eval('advPyReferenceDetectFingers;'))
        native=snapshot()
        assert len(native['curves'])==4,'reference detection did not sample all four fingers'
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        host=MayaFitJointHost()
        state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-2.,2.,10.,'biped',
            axis='y',hits=4,step_z=-.16,direction=(0,1,0),project_on='CombinedSkinUpper_M')
        with host.transaction('Source four-finger detection'):
            detect_fingers(state)
        python=snapshot()
        error=compare(native,python)
        assert detected==state.four_fingers
        assert error<=1e-6,error
        row.update(status='passed',native_detected=detected,python_detected=state.four_fingers,
                   maximum_error=error,curves=len(python['curves']),pivots=len(python['pivots']))
    except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'detect_straighten_and_rescan'};report['cases'].append(row)
    try:
        from adv_py.adapters.maya_fit_auto_place_fingers import project,straighten_fingers
        fixture()
        scene=output/'pipeline-input.mb'
        c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        detected=bool(mel.eval('advPyReferenceFingerPipeline;'))
        native=snapshot()
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        host=MayaFitJointHost()
        state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-2.,2.,10.,'biped',
            axis='y',step_z=-.16,direction=(0,1,0),project_on='CombinedSkinUpper_M')
        with host.transaction('Source detection to straightening and rescan'):
            c.setAttr('asFitScanCurve.translate',-8.,10.,0.,type='double3')
            while state.index<100:
                state.minimum_x=c.getAttr('AutoPlacing.bbMinX')
                state.step_z=state.minimum_x/50.
                c.move(0,0,state.step_z,'asFitScanCurve',relative=True,objectSpace=True,worldSpaceDistance=True)
                project(state,'CombinedSkinUpper_M',refresh=True)
                detect_fingers(state)
                straighten_fingers(state)
                if state.four_fingers and state.has_ncloth:break
                state.index+=1
        python=snapshot()
        maximum=compare(native,python)
        assert detected and state.four_fingers and state.has_ncloth
        assert maximum<=1e-6,maximum
        row.update(status='passed',native_detected=detected,python_detected=True,
                   maximum_error=maximum,ncloth_completed=True,rescan_completed=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    report['status']='passed' if all(r['status']=='passed' for r in report['cases']) else 'failed'
    (output/'detection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    raise SystemExit(0 if main(Path(sys.argv[1]).resolve())['status']=='passed' else 1)
