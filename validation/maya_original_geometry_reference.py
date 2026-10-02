"""Untouched source FitGeometry, PolyBoxes and BoxSkin on a native rig."""
from pathlib import Path
import json
import traceback

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/results/original-geometry-reference'


def mesh_snapshot():
    from maya import cmds as c
    names=c.listRelatives('BoxesGeometry',allDescendents=True,type='mesh',fullPath=True) or []
    meshes={}
    for shape in names:
        if c.getAttr(shape+'.intermediateObject'):continue
        node=c.listRelatives(shape,parent=True,fullPath=True)[0]
        meshes[node.rsplit('|',1)[-1]]={'points':c.xform(node+'.vtx[*]',q=True,ws=True,t=True),
            'scale':c.getAttr(node+'.scale')[0],
            'faces':int(c.polyEvaluate(node,face=True))}
    return meshes


def skin_snapshot():
    from maya import cmds as c
    from maya.api import OpenMaya as om,OpenMayaAnim as oma
    selection=om.MSelectionList();selection.add('BoxSkinMeshSkinCluster')
    skin=oma.MFnSkinCluster(selection.getDependNode(0))
    selection=om.MSelectionList();selection.add('BoxSkinMesh')
    path=selection.getDagPath(0);path.extendToShape()
    component=om.MFnSingleIndexedComponent();obj=component.create(om.MFn.kMeshVertComponent)
    component.addElements(range(om.MFnMesh(path).numVertices))
    weights,count=skin.getWeights(path,obj)
    return {'points':c.xform('BoxSkinMesh.vtx[*]',q=True,ws=True,t=True),
        'influences':[node.partialPathName().rsplit('|',1)[-1] for node in skin.influenceObjects()],
        'weights':list(weights),'influence_count':count,
        'settings':{attr:c.getAttr('BoxSkinMeshSkinCluster.'+attr) for attr in
            ('maxInfluences','maintainMaxInfluences','normalizeWeights','skinningMethod')}}


def main():
    from maya import cmds as c,mel
    OUT.mkdir(parents=True,exist_ok=True)
    report={'status':'running'}
    try:
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        mel.eval('AdvancedSkeleton;')
        report['soft_selection']={flag:c.softSelect(query=True,**{flag:True})
            for flag in ('softSelectEnabled','softSelectDistance','softSelectFalloff','softSelectCurve')}
        base=ROOT/'validation/results/original-bendy-reference/original-bendy-reference.mb'
        c.file(str(base),open=True,force=True,executeScriptNodes=False)
        c.checkBox('asBodyOffsetParentMatrixCheckBox',edit=True,value=True)
        mel.eval('asEnsureFitSkeletonAttributes;')
        c.setAttr('FitSkeleton.visGeo',1)
        mel.eval('asFitGeometry;')
        boxes=c.ls('*Box',type='transform') or []
        report['preview']={name:c.xform(name+'.vtx[*]',q=True,ws=True,t=True) for name in boxes}
        report['preview_surfaces']={name:c.xform(name+'.cv[*][*]',q=True,ws=True,t=True)
            for name in c.ls('*Cyl',type='transform') or []}
        c.file(rename=str(OUT/'preview.mb'));c.file(save=True,type='mayaBinary',force=True)
        # Run the untouched entry from a pristine character again.
        c.file(str(base),open=True,force=True,executeScriptNodes=False)
        mel.eval('asEnsureFitSkeletonAttributes;')
        mel.eval('asCreatePolyBoxes;')
        report['boxes']=mesh_snapshot()
        c.file(rename=str(OUT/'boxes.mb'));c.file(save=True,type='mayaBinary',force=True)
        mel.eval('asCreateBoxSkin;')
        report['skin']=skin_snapshot()
        report['boxes_after_skin']=mesh_snapshot()
        poses=[]
        for name,plug,value in (('main_translate','Main.translateX',2.),
                               ('main_scale','Main.scaleY',1.3),
                               ('shoulder','FKShoulder_R.rotateZ',25.),
                               ('elbow','FKElbow_R.rotateZ',35.),
                               ('root','RootX_M.rotateY',17.)):
            before=c.getAttr(plug);c.setAttr(plug,value)
            poses.append({'name':name,'plug':plug,'value':value,
                          'boxes':mesh_snapshot(),'skin':skin_snapshot()})
            c.setAttr(plug,before)
        report['poses']=poses
        c.file(rename=str(OUT/'box-skin.mb'));c.file(save=True,type='mayaBinary',force=True)
        report['foot_fixtures']={}
        for up in ('y','z'):
            c.file(str(base),open=True,force=True,executeScriptNodes=False)
            mel.eval('asEnsureFitSkeletonAttributes;')
            if not c.objExists('FitSkeleton.fitSkeletonTemplate'):
                c.addAttr('FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
            c.setAttr('FitSkeleton.fitSkeletonTemplate','biped',type='string')
            mel.eval('asSceneUpAxisFlip Group '+up+';')
            mel.eval('asCreatePolyBoxes;')
            report['foot_fixtures'][up]=mesh_snapshot()
        report['status']='passed'
    except Exception:
        report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'reference.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        c.quit(force=True)


if __name__=='__main__':main()
