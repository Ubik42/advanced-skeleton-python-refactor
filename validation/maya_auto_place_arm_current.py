"""Unedited source shoulder preparation and elbow phases on shared geometry.

This validates the complete upper-body cut/bind/split sequence, not full
character AutoPlace success. Geometry is a connected voxel mannequin.
"""
from pathlib import Path
import json,os,sys,traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/auto-place-arm-current'


def fixture(*,full_body=False):
    from maya import cmds as c,mel
    from maya.api import OpenMaya as om
    from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_GROUPS
    c.file(new=True,force=True)
    c.selectMode(object=True)
    c.polySelectConstraint(mode=0)
    cells=set()
    for x in range(-32 if full_body else -16,32 if full_body else 16):
        for y in range(48):
            for z in range(-10 if full_body else -3,8 if full_body else 3):
                torso=-4<=x<4 and 19<=y<40
                legs=( -4<=x<-1 or 1<=x<4 ) and y<20
                neck=-2<=x<2 and 39<=y<43 and -2<=z<2
                head=-3<=x<3 and 42<=y and -3<=z<3
                arm_y=36-max(0,abs(x)-4)//2
                arms=4<=abs(x)<=16 and arm_y-2<=y<arm_y+2 and -2<=z<2
                palm=full_body and 16<=abs(x)<24 and arm_y-2<=y<arm_y+2 and -8<=z<8
                fingers=full_body and 24<=abs(x)<=32 and arm_y-2<=y<arm_y+2 and -8<=z<8 and z%4 in (1,2)
                thumb=full_body and 16<=abs(x)<21 and arm_y-2<=y<arm_y+2 and -10<=z<-7
                if torso or legs or neck or head or arms or palm or fingers or thumb:cells.add((x,y,z))
    points,counts,connects,indices=[],[],[],{}
    sides=[((-1,0,0),((0,0,0),(0,0,1),(0,1,1),(0,1,0))),
           ((1,0,0),((1,0,1),(1,0,0),(1,1,0),(1,1,1))),
           ((0,-1,0),((0,0,0),(1,0,0),(1,0,1),(0,0,1))),
           ((0,1,0),((0,1,1),(1,1,1),(1,1,0),(0,1,0))),
           ((0,0,-1),((1,0,0),(0,0,0),(0,1,0),(1,1,0))),
           ((0,0,1),((0,0,1),(1,0,1),(1,1,1),(0,1,1)))]
    for cell in sorted(cells):
        for delta,corners in sides:
            if tuple(a+b for a,b in zip(cell,delta)) in cells:continue
            counts.append(4)
            for corner in corners:
                vertex=tuple(a+b for a,b in zip(cell,corner))
                if vertex not in indices:
                    indices[vertex]=len(points);points.append(om.MPoint(*(v*.5 for v in vertex)))
                connects.append(indices[vertex])
    fn=om.MFnMesh();fn.create(points,counts,connects)
    mesh=c.rename(om.MFnDagNode(fn.parent(0)).fullPathName(),'CombinedSkin')
    if full_body:
        mesh=c.rename(mesh,'ProxySkin')
        c.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),i=True,executeScriptNodes=False)
        if not c.objExists('FitSkeleton.fitSkeletonTemplate'):
            c.addAttr('FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
        c.setAttr('FitSkeleton.fitSkeletonTemplate','biped',type='string')
        return (mesh,)
    c.group(empty=True,name='AutoPlacing')
    for name in FIT_AUTO_PLACE_GROUPS:c.group(empty=True,name=name,parent='AutoPlacing')
    c.group(empty=True,name='asFitPivotsFingers',parent='asFitPivots')
    c.group(empty=True,name='asFitAnchors',parent='AutoPlacing')
    c.parent(mesh,'asFitCombinedSkins')
    for name in ('CombinedSkinUpper_M','CombinedSkinLower_M'):
        c.duplicate(mesh,name=name)
    for attr,value in (('bbMinX',-8.),('bbMaxY',24.),('bbMinZ',-1.5),('bbMaxZ',1.5)):
        c.addAttr('AutoPlacing',longName=attr,attributeType='double',defaultValue=value)
    c.createNode('closestPointOnMesh',name='closestSampler')
    for name,point in [('asFitPivotArmPit',(-1.8,16,0)),('asFitPivotNeck',(0,20.5,0)),
                       ('asFitPivotArmTip',(-7.9,14.5,0))]:
        c.createNode('transform',name=name,parent='asFitPivots')
        c.xform(name,worldSpace=True,translation=point)
    c.createNode('transform',name='asFitPivotOrientArmTip',parent='asFitPivotArmTip')
    c.createNode('transform',name='asFitPivotOffsetArmTip',parent='asFitPivotOrientArmTip')
    c.createNode('transform',name='asFitHandleNeck',parent='asFitHandles')
    c.setAttr('asFitHandleNeck.translateY',20.5)
    c.curve(name='asFitScanCurve',degree=1,point=((-8,0,0),(8,0,0)))
    c.rename(c.listRelatives('asFitScanCurve',shapes=True)[0],'asFitScanCurveShape')
    c.parent('asFitScanCurve','asFitScanCurves')
    c.setAttr('asFitScanCurve.rotateY',-90.)
    c.setAttr('asFitScanCurve.translate',-2.5,24,0,type='float3')
    c.duplicate('asFitScanCurve',name='asFitScanCurveArmTip')
    c.group(empty=True,name='asFitProjectionArmTip',parent='asFitProjections')
    mel.eval('asSaveProjection Shoulder "yArmStraight" CombinedSkin "closestToasFitPivotArmPit" 1;')
    c.select(clear=True);c.refresh()


def reference(source):
    start=source.index('$camOrbitStep*=-1;',source.index('//BodyCut'))
    end=source.index('$hasStraightenArm=1;',start)+len('$hasStraightenArm=1;')
    shoulder='''global proc advReferenceShoulder () {
int $a,$numVtxsA,$numVtxsB,$closestVtxIndex,$b,$upperLowerFactor,$z=0,$hasHitArmTip=1,$hasStraightenArm=0;
float $camOrbitStep=.2,$bbMaxY=24,$bbMinX=-8,$rz;
float $tempBBox[],$pos[],$posA[],$posB[],$posC[],$bbMin[];
string $tempString[],$armVtxs[],$side,$upperLower,$zxy[]={"yArmStraight"};
'''+source[start:end]+'\n}'
    start=source.index('$scanCurveTx=`getAttr asFitScanCurve.tx`;',source.index('if ($zxy[$z]=="y" && !`objExists asFitElbowStraight`)'))
    end=source.index('setAttr asFitScanCurve.tx $scanCurveTx;',start)+len('setAttr asFitScanCurve.tx $scanCurveTx;')
    elbow='''global proc advReferenceElbow () {
int $z=0;float $scanCurveTx,$firstNonFingerSplitTx=-6,$bbMinX,$rz;
float $pos[],$posA[],$posB[];string $zxy[]={"y"};
$bbMinX=`getAttr AutoPlacing.bbMinX`;
'''+source[start:end]+'\n}'
    return shoulder,elbow


def snapshot():
    from maya import cmds as c
    meshes={name:c.xform(name+'.vtx[*]',query=True,worldSpace=True,translation=True)
            for name in ('CombinedSkinUpper_M','CombinedSkinLower_M','CombinedSkinHead_M',
                         'CombinedSkinUpper_R','CombinedSkinUpper_L','CombinedSkinLower_R','CombinedSkinLower_L')}
    transforms={name:c.xform(name,query=True,worldSpace=True,matrix=True)
                for name in c.ls('asFitShoulderStraight*','asFitElbowStraight','asFitPivot*',type='transform')}
    influences=c.skinCluster('CombinedSkinUpperSC_M',query=True,influence=True)
    return dict(meshes=meshes,transforms=transforms,influences=influences,
        weights=c.getAttr('CombinedSkinUpperSC_M.weightList[*].weights[*]'),
        minimum_x=c.getAttr('AutoPlacing.bbMinX'),
        nodes=sorted(c.ls('CombinedSkin*','asFitShoulderStraight*','asFitElbowStraight*',long=True)))


def compare(a,b):
    assert a['meshes'].keys()==b['meshes'].keys()
    assert a['transforms'].keys()==b['transforms'].keys()
    assert a['influences']==b['influences'],(a['influences'],b['influences'])
    assert a['nodes']==b['nodes']
    errors=[abs(a['minimum_x']-b['minimum_x'])]
    for group in ('meshes','transforms'):
        for name,values in a[group].items():
            assert len(values)==len(b[group][name]),name
            errors.extend(abs(x-y) for x,y in zip(values,b[group][name]))
    assert len(a['weights'])==len(b['weights'])
    weight=max(abs(x-y) for x,y in zip(a['weights'],b['weights']))
    maximum=max(errors)
    assert maximum<=1e-6 and weight<=1e-8,(maximum,weight)
    return dict(maximum_geometry_matrix_error=maximum,maximum_skin_weight_error=weight,
                mesh_count=len(a['meshes']),influences=len(a['influences']))


def initialization_parity(source):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters import maya_fit_auto_place as engine
    start=source.index('createNode -n AutoPlacing transform;',source.index('global proc asFitAutoPlace ()'))
    end=source.index('if (`objExists closestSampler`)',start)
    mel.eval('global proc advReferenceAutoPlaceGroups () { float $tra[],$rot[];\n'+source[start:end]+'\n}')
    def input_scene(namespace=''):
        c.file(new=True,force=True)
        if namespace:c.namespace(add=namespace);c.namespace(set=namespace)
        fit=c.group(empty=True,name='FitSkeleton')
        c.select(fit);c.joint(name='Root')
        skin=c.polyCube(name='InputSkin',width=2,height=4,depth=2)[0]
        c.delete(skin,constructionHistory=True)
        c.namespace(set=':');c.select(clear=True)
        # Include camera scale: copying a camera matrix can hide a different
        # creation/reparent sequence on ordinary unit-scale cameras.
        c.setAttr('persp.scale',1.2,.9,1.1,type='double3')
        return skin
    def state(namespace=''):
        prefix=namespace+':' if namespace else ''
        root=prefix+'AutoPlacing'
        nodes=[name for name in c.listRelatives(root,allDescendents=True,type='transform',fullPath=True) or []
               if name.rsplit('|',1)[-1].split(':')[-1].startswith('asFit')]
        return dict(children=[name.split(':')[-1] for name in c.listRelatives(root,children=True)],
            matrices={name.rsplit('|',1)[-1].split(':')[-1]:c.xform(name,query=True,worldSpace=True,matrix=True) for name in nodes},
            root_visible=c.getAttr(prefix+'Root.visibility'))
    input_scene();mel.eval('advReferenceAutoPlaceGroups;');native=state()
    rows=[]
    original=engine.capture_combined
    for namespace in ('','SecondCharacter'):
        skin=input_scene(namespace);sample={}
        def capture(host,*args):
            sample.update(state(namespace));raise RuntimeError('Observed complete source initialization')
        engine.capture_combined=capture
        try:
            host=MayaFitJointHost(namespace=namespace or None)
            try:
                with host.transaction('Observe source initialization'):
                    engine.run(host,'FitSkeleton',(skin,),(),())
            except RuntimeError as error:
                assert str(error)=='Observed complete source initialization',str(error)
            else:raise AssertionError('Initialization observation was not reached')
            assert native['children']==sample['children'],(native['children'],sample['children'])
            assert native['root_visible']==sample['root_visible']==False
            assert native['matrices'].keys()==sample['matrices'].keys()
            maximum=max(abs(a-b) for name,values in native['matrices'].items() for a,b in zip(values,sample['matrices'][name]))
            assert maximum<=1e-8,maximum
            assert not c.objExists((namespace+':' if namespace else '')+'AutoPlacing')
            rows.append(dict(namespace=namespace or ':',maximum_matrix_error=maximum,creation_order=True,transaction_restored=True))
        finally:engine.capture_combined=original
    return rows


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_state import FitAutoPlaceScanState
    from adv_py.adapters import maya_fit_auto_place_arm_scan as arm
    OUT.mkdir(parents=True,exist_ok=True)
    initialization_only=os.environ.get('ADV_INITIALIZATION_ONLY')=='1'
    report=dict(status='running',pid=os.getpid(),scope='Whole shoulder cut/bind/split and elbow phase parity; not complete character AutoPlace',cases=[])
    try:
        source=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8-sig')
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        for procedure in reference(source):mel.eval(procedure)
        try:report['initialization']=initialization_parity(source)
        except Exception:report['initialization_error']=traceback.format_exc()
        if initialization_only:
            report['scope']='Root and namespaced source AutoPlace initialization only'
            report['status']='failed' if report.get('initialization_error') else 'passed'
            return 0 if report['status']=='passed' else 1
        fixture()
        scene=OUT/'shoulder-input.mb';c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
        constraints=c.polySelectConstraint(query=True,stateString=True)
        for mode in ('native','python'):
            c.file(str(scene),open=True,force=True,executeScriptNodes=False);mel.eval(constraints)
            if mode=='native':mel.eval('advReferenceShoulder;')
            else:
                host=MayaFitJointHost()
                state=FitAutoPlaceScanState(host,host._cmds,0.,-8.,-1.5,1.5,24.,'biped',axis='yArmStraight')
                with host.transaction('Source complete shoulder preparation'):
                    host._transaction_changed=True
                    arm._cut_body_and_head(state)
                    vertices=arm._sample_arm_vertices(state)
                    arm._create_straight_shoulder(state,vertices)
                    arm._split_limb_skins(state)
            report[mode]=snapshot()
            c.file(rename=str(OUT/(mode+'-shoulder.mb')));c.file(save=True,type='mayaBinary',force=True)
        report['cases'].append(dict(case='complete_shoulder_preparation',**compare(report['native'],report['python'])))
        # Both elbow implementations consume the same accepted native shoulder
        # output, so shoulder differences cannot be hidden by a second phase.
        for mode in ('native','python'):
            c.file(str(OUT/'native-shoulder.mb'),open=True,force=True,executeScriptNodes=False);mel.eval(constraints)
            c.setAttr('asFitScanCurve.translateX',-6.4)
            if mode=='native':mel.eval('advReferenceElbow;')
            else:
                host=MayaFitJointHost()
                state=FitAutoPlaceScanState(host,host._cmds,0.,c.getAttr('AutoPlacing.bbMinX'),-1.5,1.5,24.,'biped',axis='y',first_split_x=-6.)
                with host.transaction('Source complete elbow preparation'):
                    host._transaction_changed=True;arm._straighten_elbow(state)
            report[mode+'_elbow']=snapshot()
        report['cases'].append(dict(case='complete_elbow_preparation',**compare(report['native_elbow'],report['python_elbow'])))
        report['status']='failed' if report.get('initialization_error') else 'passed'
    except Exception:report.update(status='failed',error=traceback.format_exc())
    finally:
        (OUT/('initialization.json' if initialization_only else 'report.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
