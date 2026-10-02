"""Concentrated guide / projection source parity in an unchanged ADV GUI."""
from pathlib import Path
import sys,json,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'validation/results/fit-auto-place-lifecycle'


def fixture(case):
    from maya import cmds as c
    from maya_original_fit_auto_scale_parity import fixture as scale_fixture
    skin,all_objects,_=scale_fixture('softmod' if case=='softmod' else 'ordinary')
    c.group(empty=True,name='AutoPlacing')
    for name in ('asFitPivots','asFitHandles','asFitProjections','asFitScanCurves','asFitConstraints'):
        c.group(empty=True,name=name,parent='AutoPlacing')
    c.group(empty=True,name='asFitPivotsFingers',parent='asFitPivots')
    c.group(empty=True,name='asFitAnchors',parent='asFitPivots')
    for attr,value in (('bbMinZ',-2.5),('bbMaxZ',2.5),('bbMinX',-4.),('bbMaxY',20.),('fingerWidth',.25)):
        c.addAttr('AutoPlacing',longName=attr,attributeType='double',defaultValue=value)
    c.setAttr('Root.visibility',False)
    for mesh in (*skin,*all_objects):c.setAttr(mesh+'.visibility',False)
    if case=='arm':
        joint=c.createNode('joint',name='asFitShoulderStraight',parent='AutoPlacing')
        c.xform(joint,worldSpace=True,translation=c.xform('Shoulder',query=True,worldSpace=True,translation=True))
        c.setAttr(joint+'.rotateZ',-25.)
        child=c.createNode('joint',name='asFitElbowStraight',parent=joint)
        c.xform(child,worldSpace=True,translation=c.xform('Elbow',query=True,worldSpace=True,translation=True))
        c.setAttr(child+'.rotateZ',12.)
    if case=='fingers':
        driver=c.duplicate(skin[0],name='CombinedSkinUpper_M')[0]
        c.parent(driver,'AutoPlacing',absolute=True)
        target=c.duplicate(driver,name='fingerStraight')[0]
        c.move(0,0,.35,target+'.vtx[*]',relative=True,worldSpace=True)
        c.blendShape(target,driver,name='straightenBS',frontOfChain=True,origin='world',weight=(0,1.))
        c.delete(target)
    c.select(skin[0],replace=True)
    return skin,all_objects


def snapshot():
    from maya_original_fit_auto_scale_parity import snapshot as scale_snapshot
    result=scale_snapshot()
    from maya import cmds as c
    result['auto_placing']=c.objExists('AutoPlacing')
    result['shoulder_guide']=c.objExists('asFitShoulderStraight')
    return result


def main():
    from maya import cmds as c,mel
    from adv_py.application.fit_auto_place import FinishFitAutoPlace
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_projection import projected_curve,save_projection,update_projection,width_min
    report={'status':'running','guides':[],'projections':[]};OUTPUT.mkdir(parents=True,exist_ok=True)
    def joint_error(a,b):
        return max(abs(x-y) for joint,row in a['joints'].items()
                   for x,y in zip(row['matrix'],b['joints'][joint]['matrix']))
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0));mel.eval('AdvancedSkeleton;')
        for case in ('ordinary','arm','softmod','fingers'):
            skin,all_objects=fixture(case)
            c.textField('asBodySkinTextField',edit=True,text=' '.join(skin))
            c.textField('asBodyAllTextField',edit=True,text=' '.join(all_objects))
            mel.eval('asFitDeleteGuides;');native=snapshot()
            skin,all_objects=fixture(case);before=snapshot()
            result=FinishFitAutoPlace(MayaFitJointHost()).apply(skin=skin,all_objects=all_objects)
            python=snapshot()
            difference=max(abs(a-b) for joint,row in native['joints'].items()
                           for a,b in zip(row['matrix'],python['joints'][joint]['matrix']))
            report['guides'].append({'case':case,'maximum_error':difference,
                'restored_fingers':result.restored_fingers,'restored_arm':result.restored_arm,
                'removed_softmods':result.removed_softmods})
            assert difference<=1e-4,(case,difference)
            for key in ('auto_placing','shoulder_guide','softmods','selection','body_visibility','extra_visibility'):
                assert python[key]==native[key],(case,key,python[key],native[key])
            c.undo();undo_error=joint_error(snapshot(),before);assert undo_error<=1e-8,(case,'undo',undo_error)
            c.redo();redo_error=joint_error(snapshot(),python);assert redo_error<=1e-8,(case,'redo',redo_error)
            report['guides'][-1].update(undo_error=undo_error,redo_error=redo_error)
        for axis in ('x','z','y'):
            fixture('ordinary')
            c.curve(name='asFitScanCurve',degree=1,point=((-4,0,0),(4,0,0)))
            c.rename(c.listRelatives('asFitScanCurve',shapes=True)[0],'asFitScanCurveShape')
            c.parent('asFitScanCurve','asFitScanCurves')
            c.setAttr('asFitScanCurve.translate',-4 if axis=='y' else 0,10,0,type='double3')
            if axis!='z':c.setAttr('asFitScanCurve.rotateY',-90.)
            mel.eval('asSaveProjection Probe '+axis+' ScaleBody "center" 1;')
            native_matrix=c.xform('asFitPivotOffsetProbe',query=True,worldSpace=True,matrix=True)
            native_curve=mel.eval('asGetProjectedCurve asFitProjectionProbe "center";')
            native_width=mel.eval('asGetProjectedCurveWidthMin '+native_curve+';')
            fixture('ordinary')
            c.curve(name='asFitScanCurve',degree=1,point=((-4,0,0),(4,0,0)))
            c.rename(c.listRelatives('asFitScanCurve',shapes=True)[0],'asFitScanCurveShape')
            c.parent('asFitScanCurve','asFitScanCurves')
            c.setAttr('asFitScanCurve.translate',-4 if axis=='y' else 0,10,0,type='double3')
            if axis!='z':c.setAttr('asFitScanCurve.rotateY',-90.)
            host=MayaFitJointHost()
            with host.transaction('Native projection parity'):
                save_projection(host,'Probe',axis,'ScaleBody','center',True)
                chosen=projected_curve(host,'asFitProjectionProbe','center');width=width_min(host,chosen)
            matrix=c.xform('asFitPivotOffsetProbe',query=True,worldSpace=True,matrix=True)
            difference=max(abs(a-b) for a,b in zip(matrix,native_matrix))
            assert difference<=1e-4 and abs(width-native_width)<=1e-4,(axis,difference,width,native_width)
            with host.transaction('Native projection update'):
                update_projection(host,'Probe',axis,'ScaleBody','center',True)
            assert max(abs(a-b) for a,b in zip(c.xform('asFitPivotOffsetProbe',query=True,worldSpace=True,matrix=True),matrix))<=1e-4
            report['projections'].append({'axis':axis,'maximum_error':difference,'width_error':abs(width-native_width),'reprojected':True})
        c.file(rename=str(OUTPUT/'guides.mb'));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(OUTPUT/'guides.mb'),open=True,force=True,executeScriptNodes=False)
        assert c.objExists('AutoPlacing') and c.objExists('asFitPivotOffsetProbe')
        report['saved_reopened']=True;report['status']='passed'
    except Exception:report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUTPUT/'parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        c.quit(force=True)
