"""Run the public AutoPlace lifecycle and retain errors, not guessed passes."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from maya_original_fit_auto_scale_parity import fixture,snapshot
    from adv_py.application.fit_auto_place import AutoPlaceFit,FinishFitAutoPlace
    from adv_py.adapters.maya_fit import MayaFitJointHost
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    report={'status':'running','cases':[]}
    templates=('sam',) if '--sample' in sys.argv else ('horse','biped')
    for template in templates:
        if template=='sam':
            sample=Path('D:/3D/_tools/_DCC/MayaCraft/files/Rigged/sam/sam.mb')
            c.file(str(sample),open=True,force=True,executeScriptNodes=False)
            originals=c.skinCluster('skinCluster21',query=True,geometry=True)
            copies=[]
            for index,shape in enumerate(originals):
                transform=c.listRelatives(shape,parent=True,fullPath=True)[0]
                copy=c.duplicate(transform,name='AutoPlaceSample'+str(index),returnRootsOnly=True)[0]
                copy=c.parent(copy,world=True,absolute=True)[0];c.delete(copy,constructionHistory=True)
                c.setAttr(copy+'.visibility',True);copies.append(copy)
            c.select(copies,replace=True)
            model=output/'sam-model.ma';c.file(str(model),exportSelected=True,type='mayaAscii',force=True)
            c.file(new=True,force=True)
            c.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),i=True,executeScriptNodes=False)
            c.file(str(model),i=True,executeScriptNodes=False)
            skin=tuple(copies);all_objects=();eye=()
            def current_snapshot():
                return {'joints':{joint:{'matrix':c.xform(joint,query=True,worldSpace=True,matrix=True)}
                                 for joint in c.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True)}}
            snapshot=current_snapshot
        else:skin,all_objects,eye=fixture('ordinary')
        c.undoInfo(state=True)
        if not c.objExists('FitSkeleton.fitSkeletonTemplate'):c.addAttr('FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
        c.setAttr('FitSkeleton.fitSkeletonTemplate','biped' if template=='sam' else template,type='string')
        before=snapshot();row={'template':template};report['cases'].append(row)
        try:
            result=AutoPlaceFit(MayaFitJointHost()).apply(skin=skin,all_objects=all_objects,right_eye=eye)
            row.update(status='passed' if result.guides_active else 'not_detected',
                       axes=result.axes_completed,joints=result.joints,guides=result.guides_active)
            if result.guides_active:
                scaled=snapshot()
                c.undo();undone=snapshot()
                assert max(abs(a-b) for joint,data in before['joints'].items() for a,b in zip(data['matrix'],undone['joints'][joint]['matrix']))<1e-8
                c.redo()
                c.file(rename=str(output/(template+'-guides.mb')));c.file(save=True,type='mayaBinary',force=True)
                c.file(str(output/(template+'-guides.mb')),open=True,force=True,executeScriptNodes=False)
                finished=FinishFitAutoPlace(MayaFitJointHost()).apply(skin=skin,all_objects=all_objects)
                assert finished.finished and not c.objExists('AutoPlacing')
                assert c.getAttr(skin[0]+'.visibility')
                row.update(undo_redo=True,saved_reopened=True,finished=True)
        except Exception:
            row.update(status='failed',error=traceback.format_exc())
            after=snapshot()
            error=max(abs(a-b) for joint,data in before['joints'].items() for a,b in zip(data['matrix'],after['joints'][joint]['matrix']))
            row.update(rollback_error=error,rolled_back=not c.objExists('AutoPlacing') and error<1e-4)
        (output/'smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    report['status']=('failed' if any(row['status']=='failed' for row in report['cases']) else
                      'passed' if all(row['status']=='passed' for row in report['cases']) else 'incomplete')
    (output/'smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1])))
