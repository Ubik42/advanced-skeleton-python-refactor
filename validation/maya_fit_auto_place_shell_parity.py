"""Locate shell leap differences using one identical upper-body rest mesh."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_mesh import grow_past_shell
    output.mkdir(parents=True,exist_ok=True)
    mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
    report={'status':'running','rows':[]}
    scene=ROOT/'validation/results/fit-auto-place-native-trace/shoulder-checkpoint.mb'
    for native in (True,False):
        try:
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            c.setAttr('asFitShoulderStraight.rotateZ',0.)
            c.setAttr('asFitDeltaMush.envelope',0.)
            c.delete('CombinedSkinUpper_M',constructionHistory=True)
            c.connectAttr('CombinedSkinUpper_M.outMesh','closestSampler.inMesh',force=True)
            point=c.xform('asFitPivotOffsetArmTip',query=True,worldSpace=True,translation=True)
            c.select('CombinedSkinUpper_M')
            neck=c.xform('asFitHandleNeck',query=True,worldSpace=True,translation=True)
            c.polySelectConstraint(mode=3,type=1,d=3,db=(0,neck[1]),da=(0,1,0),dp=(0,0,0))
            c.polySelectConstraint(mode=0)
            c.setAttr('closestSampler.inPosition',*point,type='double3')
            index=c.getAttr('closestSampler.closestVertexIndex')
            c.select('CombinedSkinUpper_M.vtx['+str(index)+']')
            for _ in range(999):
                before=c.ls(selection=True,flatten=True) or []
                c.polySelectConstraint(pp=1,type=1)
                if len(c.ls(selection=True,flatten=True) or [])==len(before):break
            before=c.ls(selection=True,flatten=True) or []
            if native:mel.eval('asPolyGrowPastShell;')
            else:grow_past_shell(MayaFitJointHost())
            after=c.ls(selection=True,flatten=True) or []
            report['rows'].append({'native':native,'closest_index':index,'point':point,
                                   'before':before,'after':after})
        except Exception:report['rows'].append({'native':native,'error':traceback.format_exc()})
    report['status']='passed' if len(report['rows'])==2 and 'error' not in report['rows'][0] and report['rows'][0]['after']==report['rows'][1].get('after') else 'failed'
    (output/'shell.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'rows':[{k:(len(v) if k in ('before','after') else v) for k,v in row.items()} for row in report['rows']]},indent=2))


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
