"""Fit preview and complete PolyBoxes→BoxSkin source comparison."""
from pathlib import Path
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maya_original_geometry_reference import mesh_snapshot,skin_snapshot


def main(*,standalone=True):
    import maya.standalone
    if standalone:maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_fit_geometry import MayaFitGeometryHost
    from adv_py.application.fit_geometry import UpdateFitGeometry
    from adv_py.adapters.maya_geometry_poly_boxes import MayaPolyBoxesHost
    from adv_py.application.geometry_poly_boxes import CreatePolyBoxes,DeletePolyBoxes
    from adv_py.adapters.maya_geometry_box_skin import MayaBoxSkinHost
    from adv_py.application.geometry_box_skin import CreateBoxSkin,DeleteBoxSkin
    output=ROOT/'validation/results/geometry-source-parity';output.mkdir(parents=True,exist_ok=True)
    report={'status':'running'}
    native=json.loads((ROOT/'validation/results/original-geometry-reference/reference.json').read_text(encoding='utf8'))
    def maximum(left,right):
        assert len(left)==len(right),(len(left),len(right))
        return max((abs(a-b) for a,b in zip(left,right)),default=0.)
    def compare_boxes(reference,actual):
        assert reference.keys()==actual.keys(),(sorted(reference.keys()-actual.keys()),sorted(actual.keys()-reference.keys()))
        return {name:maximum(row['points'],actual[name]['points']) for name,row in reference.items()}
    def compare_skin(reference,actual):
        assert set(reference['influences'])==set(actual['influences'])
        assert reference['settings']==actual['settings']
        count=reference['influence_count'];assert count==actual['influence_count']
        order=[actual['influences'].index(name) for name in reference['influences']]
        weights=[actual['weights'][offset+index] for offset in range(0,len(actual['weights']),count) for index in order]
        return {'points':maximum(reference['points'],actual['points']),
                'weights':maximum(reference['weights'],weights)}
    base=ROOT/'validation/results/original-bendy-reference/original-bendy-reference.mb'
    try:
        assert native['status']=='passed',native.get('traceback')
        if native.get('soft_selection'):c.softSelect(**native['soft_selection'])
        c.file(str(ROOT/'validation/results/original-geometry-reference/preview.mb'),
               open=True,force=True,executeScriptNodes=False)
        native_meshes={}
        for shape in c.listRelatives('FitSkeletonVisualizers',allDescendents=True,
                                     type='mesh',fullPath=True) or []:
            if c.getAttr(shape+'.intermediateObject'):continue
            parent=c.listRelatives(shape,parent=True,fullPath=True)[0]
            name=parent.rsplit('|',1)[-1]
            if name.endswith(('Sphere','Bone')):
                native_meshes[name]=c.xform(parent+'.vtx[*]',q=True,ws=True,t=True)
        c.file(str(base),open=True,force=True,executeScriptNodes=False)
        c.undoInfo(state=True)
        before_attributes=set(c.listAttr('FitSkeleton'))
        before_joints={c.ls(joint,uuid=True)[0]:c.getAttr(joint+'.jointOrient')[0]
            for joint in c.listRelatives('FitSkeleton',allDescendents=True,type='joint')}
        preview=MayaFitGeometryHost()
        report['preview_segments']=UpdateFitGeometry(preview).execute(visible=True,geometry_type='boxes')
        report['undo_after_preview']=c.undoInfo(query=True,undoName=True)
        actual={name:c.xform(name+'.vtx[*]',q=True,ws=True,t=True) for name in native['preview']}
        report['preview_errors']={name:maximum(points,actual[name]) for name,points in native['preview'].items()}
        report['surface_errors']={name:maximum(points,c.xform(name+'.cv[*][*]',q=True,ws=True,t=True))
                                  for name,points in native['preview_surfaces'].items()}
        report['preview_mesh_errors']={name:maximum(points,c.xform(name+'.vtx[*]',q=True,ws=True,t=True))
                                      for name,points in native_meshes.items()}
        report['undo_after_sampling']=c.undoInfo(query=True,undoName=True)
        c.undo()
        report['preview_after_undo']=c.ls('*FitSkeletonVisualizers*',long=True)
        report['undo_after_undo']=c.undoInfo(query=True,undoName=True)
        report['redo_after_undo']=c.undoInfo(query=True,redoName=True)
        assert not c.objExists('FitSkeletonVisualizers')
        assert set(c.listAttr('FitSkeleton'))==before_attributes
        for identifier,orientation in before_joints.items():
            joint=c.ls(identifier)[0]
            assert maximum(orientation,c.getAttr(joint+'.jointOrient')[0])<1e-9
        report['preview_fit_undo']=True
        c.redo();assert c.objExists('FitSkeletonVisualizers')
        report['preview_undo_redo']=True
        c.file(str(base),open=True,force=True,executeScriptNodes=False)
        class DiagnosticBoxes(MayaPolyBoxesHost):
            def capture_created(self,plan):
                report['box_diagnostics']={
                    'scale_source':c.connectionInfo('BoxesGeometry.scaleX',sourceFromDestination=True),
                    'missing':[spec.name for spec in plan if not c.objExists(spec.name)],
                    'foot_heights':{spec.name:[c.xform(vertex,q=True,ws=True,t=True)[1]
                        for vertex in c.ls(spec.name+'.vtx[*]',flatten=True)]
                        for spec in plan if spec.floor_foot and c.objExists(spec.name)}}
                report['box_errors']=compare_boxes(native['boxes'],mesh_snapshot())
                return super().capture_created(plan)
        report['box_count']=CreatePolyBoxes(DiagnosticBoxes()).execute()
        report['box_errors']=compare_boxes(native['boxes'],mesh_snapshot())
        report['skin_vertices']=CreateBoxSkin(MayaBoxSkinHost()).execute()
        report['skin_errors']=compare_skin(native['skin'],skin_snapshot())
        report['box_after_skin_errors']=compare_boxes(native['boxes_after_skin'],mesh_snapshot())
        poses=[]
        for pose in native['poses']:
            before=c.getAttr(pose['plug']);c.setAttr(pose['plug'],pose['value'])
            poses.append({'name':pose['name'],'boxes':compare_boxes(pose['boxes'],mesh_snapshot()),
                          'skin':compare_skin(pose['skin'],skin_snapshot())})
            c.setAttr(pose['plug'],before)
        report['poses']=poses
        c.file(rename=str(output/'box-skin.mb'));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(output/'box-skin.mb'),open=True,force=True,executeScriptNodes=False)
        report['reopened_skin_errors']=compare_skin(native['skin'],skin_snapshot())
        report['save_reopen']=True
        DeleteBoxSkin(MayaBoxSkinHost()).execute();assert not c.objExists('BoxSkinGeometry')
        c.undo();assert c.objExists('BoxSkinGeometry')
        c.redo();assert not c.objExists('BoxSkinGeometry')
        DeletePolyBoxes(MayaPolyBoxesHost()).execute()
        report['automatic_skin_vertices']=CreateBoxSkin(MayaBoxSkinHost()).execute()
        assert not c.objExists('BoxesGeometry') and not c.objExists('PolyBoxes')
        report['automatic_boxes_cleanup']=True
        report['automatic_skin_errors']=compare_skin(native['skin'],skin_snapshot())
        report['foot_errors']={}
        for up,reference in native.get('foot_fixtures',{}).items():
            c.file(str(base),open=True,force=True,executeScriptNodes=False)
            if not c.objExists('FitSkeleton.fitSkeletonTemplate'):
                c.addAttr('FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
            c.setAttr('FitSkeleton.fitSkeletonTemplate','biped',type='string')
            for axis in 'XYZ':c.setAttr('Group.rotate'+axis,lock=False)
            c.setAttr('Group.rotate',90 if up=='z' else 0,0,0,type='double3')
            c.upAxis(axis=up,rotateView=False)
            class DiagnosticFoot(MayaPolyBoxesHost):
                def capture_created(self,plan):
                    report['foot_errors'][up]=compare_boxes(reference,mesh_snapshot())
                    report['foot_ground_diagnostics']={spec.name:[c.xform(vertex,q=True,ws=True,t=True)
                        for vertex in c.ls(spec.name+'.vtx[*]',flatten=True)]
                        for spec in plan if spec.floor_foot}
                    return super().capture_created(plan)
            CreatePolyBoxes(DiagnosticFoot()).execute()
            report['foot_errors'][up]=compare_boxes(reference,mesh_snapshot())
        c.file(new=True,force=True);c.upAxis(axis='y',rotateView=False)
        c.file(str(base),i=True,namespace='GeometryActor',mergeNamespacesOnClash=False)
        foreign=c.polyCube(name='ExternalGeometrySentinel')[0]
        foreign_id=c.ls(foreign,uuid=True)[0]
        c.namespace(add='UnrelatedEditor');c.namespace(set='UnrelatedEditor')
        UpdateFitGeometry(MayaFitGeometryHost('GeometryActor')).execute(visible=True,geometry_type='bones')
        assert c.namespaceInfo(currentNamespace=True,absoluteName=True)==':UnrelatedEditor'
        c.undo();assert not c.objExists('GeometryActor:FitSkeletonVisualizers')
        c.redo();assert c.objExists('GeometryActor:FitSkeletonVisualizers')
        CreatePolyBoxes(MayaPolyBoxesHost('GeometryActor')).execute()
        CreateBoxSkin(MayaBoxSkinHost('GeometryActor')).execute()
        assert c.objExists('GeometryActor:BoxSkinMesh')
        assert c.ls(foreign_id)==[foreign]
        assert c.namespaceInfo(currentNamespace=True,absoluteName=True)==':UnrelatedEditor'
        report['independent_namespace']=True
        numeric=[*report['preview_errors'].values(),*report['surface_errors'].values(),
                 *report['preview_mesh_errors'].values(),
                 *report['box_errors'].values(),*report['skin_errors'].values(),
                 *report['box_after_skin_errors'].values()]
        numeric.extend(report['automatic_skin_errors'].values())
        numeric.extend(report['reopened_skin_errors'].values())
        for errors in report['foot_errors'].values():numeric.extend(errors.values())
        for pose in poses:numeric.extend(pose['boxes'].values());numeric.extend(pose['skin'].values())
        report['maximum_error']=max(numeric,default=0.)
        assert report['maximum_error']<1e-4,report['maximum_error']
        report['status']='passed'
    except Exception:
        report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (output/'parity.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps({key:value for key,value in report.items() if key not in
            ('preview_errors','surface_errors','box_errors','box_after_skin_errors','poses')},indent=2))
        if standalone:maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
