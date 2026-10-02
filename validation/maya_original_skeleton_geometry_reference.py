"""Untouched skeleton template pipeline, including anatomical deformations."""
import json,traceback
from template_geometry_fixture import ROOT,setup,sample,poses
OUT=ROOT/'validation/results/original-skeleton-geometry-reference'
def main():
    from maya import cmds as c,mel
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    try:
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";');mel.eval('AdvancedSkeleton;')
        setup('normal');mel.eval('asCreateSkeleton;')
        report['meshes']=sample('SkeletonGeometry');assert report['meshes']
        report['poses']=poses('SkeletonGeometry')
        c.file(rename=str(OUT/'skeleton.mb'));c.file(save=True,type='mayaBinary',force=True)
        mel.eval('asDeleteSkeleton;');assert not c.objExists('SkeletonGeometry');report['delete']=True
        setup('generic_no_profile');mel.eval('asCreateSkeleton;')
        report['generic_no_profile']={'meshes':sample('SkeletonGeometry')}
        report['mirrors']={}
        for direction in ('R','L'):
            c.file(str(OUT/'skeleton.mb'),open=True,force=True,executeScriptNodes=False)
            c.move(.2,.03,.05,'HumerusBone_'+direction+'.vtx[0]',relative=True,worldSpace=True)
            opposite='L' if direction=='R' else 'R'
            c.setAttr('HumerusBone_'+opposite+'.scaleX',lock=True)
            mel.eval('asMirrorGeometry Skeleton '+('0' if direction=='R' else '1')+';')
            report['mirrors'][direction]=sample('SkeletonGeometry')
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'reference.json').write_text(json.dumps(report),encoding='utf8');c.quit(force=True)
