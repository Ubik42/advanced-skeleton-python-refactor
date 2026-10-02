"""Whole original AutoPlace versus Python on the same public Sam geometry."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'validation/results/fit-auto-place-sam-source'
MODEL=ROOT/'validation/results/fit-auto-place-sam/sam-model.ma'


def fixture():
    from maya import cmds as c
    c.file(new=True,force=True)
    c.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),i=True,executeScriptNodes=False)
    c.file(str(MODEL),i=True,executeScriptNodes=False)
    if not c.objExists('FitSkeleton.fitSkeletonTemplate'):c.addAttr('FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
    c.setAttr('FitSkeleton.fitSkeletonTemplate','biped',type='string')
    return tuple(c.listRelatives(shape,parent=True)[0] for shape in c.ls(type='mesh',noIntermediate=True))


def snapshot():
    from maya import cmds as c
    return {'guides':c.objExists('AutoPlacing'),'joints':{
        joint:{'matrix':c.xform(joint,query=True,worldSpace=True,matrix=True),
               'fat':c.getAttr(joint+'.fat') if c.objExists(joint+'.fat') else None}
        for joint in c.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True)}}


def main():
    from maya import cmds as c,mel
    from adv_py.application.fit_auto_place import AutoPlaceFit
    from adv_py.adapters.maya_fit import MayaFitJointHost
    OUTPUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0));mel.eval('AdvancedSkeleton;')
        skin=fixture()
        for field,value in (('Skin',' '.join(skin)),('All',''),('RightEye',''),('LeftEye','')):
            c.textField('asBody'+field+'TextField',edit=True,text=value)
        try:mel.eval('asFitAutoPlace;');report['native_returned']=True
        except Exception:report['native_returned']=False;report['native_error']=traceback.format_exc()
        report['native']=snapshot()
        c.file(rename=str(OUTPUT/'native-checkpoint.mb'));c.file(save=True,type='mayaBinary',force=True)
        (OUTPUT/'parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        skin=fixture()
        try:
            result=AutoPlaceFit(MayaFitJointHost()).apply(skin=skin)
            report['python_returned']=True;report['axes']=result.axes_completed
        except Exception:report['python_returned']=False;report['python_error']=traceback.format_exc()
        report['python']=snapshot()
        error=max(abs(a-b) for joint,row in report['native']['joints'].items()
                  for a,b in zip(row['matrix'],report['python']['joints'][joint]['matrix']))
        report['maximum_error']=error
        report['status']='passed' if (report['native_returned'] and report['python_returned'] and
            error<=1e-4 and report['native']['guides']==report['python']['guides']) else 'failed'
    except Exception:report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUTPUT/'parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8');c.quit(force=True)
