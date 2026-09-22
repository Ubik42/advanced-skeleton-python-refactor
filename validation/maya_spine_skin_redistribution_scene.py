"""Generate and inspect separate Maya scenes for changed-spine Skin transfer."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

import maya.standalone


def chain(c,prefix,count):
    result=[]
    parent=None
    for index in range(count):
        name=(prefix+'Root' if index==0 else prefix+'Chest' if index==count-1
              else prefix+'Spine'+str(index))
        node=c.createNode('joint',name=name,skipSelect=True,
            **({'parent':parent} if parent else {}))
        if index:c.setAttr(node+'.translateY',3./(count-1))
        parent=c.ls(node,long=True)[0]
        result.append(parent)
    arm=c.createNode('joint',name=prefix+'Arm',skipSelect=True)
    c.setAttr(arm+'.translateX',2.)
    return tuple(result),c.ls(arm,long=True)[0]


def run(mode,folder):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import (CaptureSkinWeightSurfaceSource,
            EditSkinWeights,TransferSkinWeightsBySurface,
            save_skin_weight_surface_source,
            load_skin_weight_surface_source)
        from adv_py.core import (SkinInfluenceWeight,SkinVertexWeights,
            linear_spine_weight_redistribution)
        from adv_py.product.maya_panel_controller import MayaPanelController
        folder=folder.resolve()
        folder.mkdir(parents=True,exist_ok=True)
        c.file(new=True,force=True)
        c.undoInfo(state=True)
        c.upAxis(axis='y',rotateView=False)
        host=MayaFaceHost()
        if mode=='source':
            spine,arm=chain(c,'Src',4)
            mesh=c.polyPlane(name='SourceMesh',width=2.,height=2.,
                subdivisionsX=1,subdivisionsY=1,constructionHistory=False)[0]
            mesh=c.ls(mesh,long=True)[0]
            c.skinCluster(*spine,arm,mesh,name='SourceSkin',
                maximumInfluences=2,toSelectedBones=True)
            rows=[]
            for index,point in enumerate(host.capture_face_mesh(mesh).points):
                influences=((spine[1],.5),(arm,.5)) if point[0]<0 else (
                    (spine[2],.75),(spine[-1],.25))
                rows.append(SkinVertexWeights(index,tuple(
                    SkinInfluenceWeight(path,weight) for path,weight in influences)))
            EditSkinWeights(host).apply('SourceSkin',mesh,tuple(rows))
            source=CaptureSkinWeightSurfaceSource(host).execute('SourceSkin',mesh)
            save_skin_weight_surface_source(source,folder/'source_asset.json')
            c.file(rename=str(folder/'source.ma'))
            c.file(save=True,type='mayaAscii',force=True)
            return 0
        if mode=='target':
            source=load_skin_weight_surface_source(folder/'source_asset.json')
            spine,arm=chain(c,'Dst',6)
            mesh=c.polyPlane(name='TargetMesh',width=2.,height=2.,
                subdivisionsX=2,subdivisionsY=2,constructionHistory=False)[0]
            mesh=c.ls(mesh,long=True)[0]
            c.skinCluster(*spine,arm,mesh,name='TargetSkin',
                maximumInfluences=4,toSelectedBones=True)
            source_spine=tuple(path for path in source.weights.influence_paths
                if path.rsplit('|',1)[-1].startswith(('SrcRoot','SrcSpine','SrcChest')))
            source_spine=tuple(sorted(source_spine,key=lambda path:
                0 if path.endswith('SrcRoot') else 99 if path.endswith('SrcChest')
                else int(path.rsplit('SrcSpine',1)[1])))
            source_arm=next(path for path in source.weights.influence_paths
                if path.endswith('SrcArm'))
            mapping=linear_spine_weight_redistribution(source_spine,spine,
                target_skin_name='TargetSkin',target_mesh_path=mesh,
                other_influences=((source_arm,arm),))
            (folder/'redistribution.json').write_text(json.dumps({
                'target_skin':mapping.target_skin_name,
                'target_mesh':mapping.target_mesh_path,
                'target_influences':mapping.target_influence_paths,
                'influences':[{'source':row.source_path,
                    'targets':[asdict(target) for target in row.targets]}
                    for row in mapping.influences]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            c.file(rename=str(folder/'target_before.ma'))
            c.file(save=True,type='mayaAscii',force=True)
            before=host.capture_all_skin_weights('TargetSkin',mesh)
            _,changed=TransferSkinWeightsBySurface(host).apply_from_documents(
                source.weights,source.geometry,'TargetSkin',mesh,
                max_distance=1e-6,redistribution=mapping)
            after=host.capture_all_skin_weights('TargetSkin',mesh)
            c.undo()
            undone=host.capture_all_skin_weights('TargetSkin',mesh)
            c.redo()
            redone=host.capture_all_skin_weights('TargetSkin',mesh)
            c.undo()
            panel_result=MayaPanelController().skin_surface_transfer(':',
                'TargetSkin',mesh,1e-6,source_asset=folder/'source_asset.json',
                redistribution_file=folder/'redistribution.json')
            panel_after=host.capture_all_skin_weights('TargetSkin',mesh)
            c.undo()
            panel_undone=host.capture_all_skin_weights('TargetSkin',mesh)
            native={'changed_vertices':changed.changed_vertex_count,
                'undo_restored':undone==before,'redo_restored':redone==after,
                'panel_controller_matches_application':panel_result.vertices==9
                    and panel_result.changed_vertices>0 and panel_after==after,
                'panel_controller_single_undo':panel_undone==before}
            (folder/'native.json').write_text(json.dumps(native,indent=2)+'\n',encoding='utf-8')
            return 0 if all((native['changed_vertices']>0,native['undo_restored'],
                             native['redo_restored'],
                             native['panel_controller_matches_application'],
                             native['panel_controller_single_undo'])) else 1
        if mode=='inspect':
            c.file(folder/'target_after.ma',open=True,force=True)
            state=host.capture_all_skin_weights('TargetSkin','|TargetMesh')
            points=host.capture_face_mesh('|TargetMesh').points
            corner=next(row for row in state.vertices if points[row.vertex_index][0]<-.9)
            actual={entry.influence_path:entry.weight for entry in corner.weights}
            names={path.rsplit('|',1)[-1]:path for path in state.influence_paths}
            checks={
                'source_geometry_absent':not c.objExists('SourceMesh'),
                'target_has_six_spine_joints':len(state.influence_paths)==7,
                'corner_arm_weight':abs(actual.get(names['DstArm'],0)-.5)<1e-6,
                'corner_spine_split':abs(actual.get(names['DstSpine1'],0)-1/6)<1e-6
                    and abs(actual.get(names['DstSpine2'],0)-1/3)<1e-6,
                'every_vertex_normalized':all(abs(sum(entry.weight for entry
                    in row.weights)-1.)<1e-6 for row in state.vertices),
            }
            prior=c.xform(f'|TargetMesh.vtx[{corner.vertex_index}]',query=True,
                worldSpace=True,translation=True)
            c.setAttr(names['DstSpine1']+'.rotateZ',20.)
            moved=c.xform(f'|TargetMesh.vtx[{corner.vertex_index}]',query=True,
                worldSpace=True,translation=True)
            checks['transferred_weights_drive_real_mesh']=max(abs(a-b) for a,b in
                zip(prior,moved))>.01
            payload={**checks,'status':'passed' if all(checks.values()) else 'failed'}
            (folder/'inspection.json').write_text(json.dumps(payload,ensure_ascii=False,
                indent=2)+'\n',encoding='utf-8')
            return 0 if all(checks.values()) else 1
        raise ValueError(mode)
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(run(sys.argv[1],Path(sys.argv[2])))
