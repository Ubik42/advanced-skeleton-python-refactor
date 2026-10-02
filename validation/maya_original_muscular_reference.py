"""Unchanged MEL muscle curves, lofts and Skin data on native skeleton geometry."""
from pathlib import Path
import json,traceback
from template_geometry_fixture import ROOT
OUT=ROOT/'validation/results/original-muscular-reference'

def sample():
    from maya import cmds as c
    rows={}
    for shape in c.listRelatives('MuscularGeometry',allDescendents=True,fullPath=True) or []:
        kind=c.nodeType(shape)
        if kind not in ('nurbsCurve','nurbsSurface') or c.getAttr(shape+'.intermediateObject'):continue
        owner=c.listRelatives(shape,parent=True,fullPath=True)[0]
        key=owner.rsplit('|',1)[-1]
        cvs=c.ls(owner+('.cv[*]' if kind=='nurbsCurve' else '.cv[*][*]'),flatten=True)
        row={'kind':kind,'points':c.xform(cvs,q=True,ws=True,t=True)}
        skins=[node for node in c.listHistory(shape) or [] if c.nodeType(node)=='skinCluster']
        if kind=='nurbsCurve' and skins:
            skin=skins[0];row['influences']=c.skinCluster(skin,q=True,influence=True)
            row['weights']=[c.skinPercent(skin,cv,q=True,value=True) for cv in cvs]
            row['method']=c.getAttr(skin+'.skinningMethod')
        rows[key]=row
    return rows

def main():
    from maya import cmds as c,mel
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    try:
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";');mel.eval('AdvancedSkeleton;')
        c.file(str(ROOT/'validation/results/original-skeleton-geometry-reference/skeleton.mb'),open=True,force=True,executeScriptNodes=False)
        mel.eval('asCreateMuscular;');report['curves']=sample();assert report['curves']
        report['poses']=[]
        for name,plug,value in [('main_move','Main.translateX',2.),('main_scale','Main.scaleY',1.3),('shoulder','FKShoulder_R.rotateZ',25.),('elbow','FKElbow_R.rotateZ',35.)]:
            old=c.getAttr(plug);c.setAttr(plug,value);report['poses'].append({'name':name,'curves':sample()});c.setAttr(plug,old)
        c.file(rename=str(OUT/'muscular.mb'));c.file(save=True,type='mayaBinary',force=True)
        mel.eval('asDeleteMuscular;');assert not c.objExists('MuscularGeometry');report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'reference.json').write_text(json.dumps(report),encoding='utf8');c.quit(force=True)
