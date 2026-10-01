"""Native original Corrective Shapes lifecycle on a complete Face rig."""
from pathlib import Path
import json
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene, output, namespace=":"):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    output.mkdir(parents=True,exist_ok=True)
    if namespace==':':
        cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    else:
        cmds.file(new=True,force=True)
        cmds.file(str(scene),i=True,namespace=namespace,executeScriptNodes=False)
    controller=MayaPanelController()
    report={'status':'running','source_scene':str(scene),'stages':[],'namespace':namespace}
    def physical(name):
        return name if namespace==':' or ':' in name else namespace+':'+name
    mesh=physical('FaceMesh');lip_driver=physical('ctrlLips_M.ty')
    corrective=physical('FaceMeshCorrective');head_skin=physical('HeadSkin')
    sample_index=100
    def point(node, index=None):
        index=sample_index if index is None else index
        return tuple(cmds.xform(node+f'.vtx[{index}]',query=True,worldSpace=True,translation=True))
    def same(a,b):
        return max(abs(x-y) for x,y in zip(a,b))<2e-4
    try:
        neutral_points=tuple(cmds.xform(mesh+'.vtx[*]',query=True,worldSpace=True,translation=True))
        cmds.setAttr(lip_driver,1)
        posed=tuple(cmds.xform(mesh+'.vtx[*]',query=True,worldSpace=True,translation=True))
        sample_index=max(range(len(posed)//3),key=lambda i:max(abs(posed[i*3+a]-neutral_points[i*3+a]) for a in range(3)))
        neutral=neutral_points[sample_index*3:sample_index*3+3]
        uncorrected=point(mesh)
        assert not same(uncorrected,neutral),'Need an actually deformed Skin vertex'
        report['sample_vertex']=sample_index
        cmds.select(mesh,replace=True)
        created=controller.original_corrective_shapes(namespace,'create',q_rotations=False,mirror=False)
        print('CREATE',created,flush=True)
        target=physical(created['target'])
        sculpt=list(point(target));sculpt[2]+=.2
        cmds.xform(target+f'.vtx[{sample_index}]',worldSpace=True,translation=sculpt)
        applied=controller.original_corrective_shapes(namespace,'apply',q_rotations=False,mirror=False)
        print('APPLY',applied,flush=True)
        cmds.undo()
        assert cmds.objExists(target)
        assert not cmds.objExists(corrective)
        cmds.redo()
        assert not cmds.objExists(target)
        assert cmds.objExists(corrective)
        report['stages'].append('create_sculpt_apply_undo_redo')
        assert cmds.getAttr(lip_driver)==0
        cmds.setAttr(lip_driver,1)
        assert same(point(mesh),sculpt),(point(mesh),sculpt)
        cmds.setAttr(lip_driver,0)
        assert same(point(mesh),neutral),(point(mesh),neutral)
        cmds.setAttr(lip_driver,1)
        targets=controller.original_corrective_targets(namespace,edit=True)
        print('CATALOG',targets,flush=True)
        assert len(targets)==1,targets
        full=targets[0]
        edited=controller.original_corrective_shapes(namespace,'edit',target=full,q_rotations=False,mirror=False)
        sculpt[2]+=.1
        cmds.xform(physical(edited['target'])+f'.vtx[{sample_index}]',worldSpace=True,translation=sculpt)
        controller.original_corrective_shapes(namespace,'apply',q_rotations=False,mirror=False)
        cmds.setAttr(lip_driver,1)
        assert same(point(mesh),sculpt)
        report['stages'].append('edit_replace')
        cmds.setAttr(lip_driver,.5)
        half=point(mesh)
        cmds.select(mesh,replace=True)
        created=controller.original_corrective_shapes(namespace,'create',q_rotations=False,mirror=False)
        assert abs(created['inbetween']-.5)<1e-6,created
        half=list(half);half[2]+=.05
        cmds.xform(physical(created['target'])+f'.vtx[{sample_index}]',worldSpace=True,translation=half)
        controller.original_corrective_shapes(namespace,'apply',q_rotations=False,mirror=False)
        cmds.setAttr(lip_driver,.5)
        assert same(point(mesh),half),(point(mesh),half)
        targets=controller.original_corrective_targets(namespace,edit=True)
        assert len(targets)==2,targets
        assert any(t.inbetween for t in targets)
        report['stages'].append('inbetween')
        scene=output/'face-correctives.mb'
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
        assert same(point(mesh),half)
        cmds.setAttr(lip_driver,1);assert same(point(mesh),sculpt)
        cmds.setAttr(lip_driver,0);assert same(point(mesh),neutral)
        report['stages'].append('save_reopen')
        corrective_id=cmds.ls(corrective,uuid=True)[0]
        old_skin=cmds.ls(head_skin,uuid=True)[0]
        result=controller.face_original_build(namespace,cage_smooth=1,jaw_smooth=1)
        assert len(result['stages'])==30
        assert cmds.ls(corrective,uuid=True)[0]==corrective_id
        cmds.undo();assert cmds.ls(head_skin,uuid=True)[0]==old_skin
        cmds.redo();assert not cmds.objExists(physical('prefix_FaceGroup'))
        assert cmds.ls(corrective,uuid=True)[0]==corrective_id
        cmds.setAttr(lip_driver,1);assert same(point(mesh),sculpt),(point(mesh),sculpt)
        cmds.setAttr(lip_driver,.5);assert same(point(mesh),half)
        cmds.setAttr(lip_driver,0);assert same(point(mesh),neutral)
        assert len(controller.original_corrective_targets(namespace,edit=True))==2
        report['stages'].append('full_rebuild_undo_redo')
        cmds.setAttr(lip_driver,.5)
        targets=controller.original_corrective_targets(namespace,edit=True)
        partial=next(t for t in targets if t.inbetween)
        controller.original_corrective_shapes(namespace,'delete',target=partial,q_rotations=False,mirror=False)
        targets=controller.original_corrective_targets(namespace,edit=True)
        assert len(targets)==1,targets
        full=targets[0]
        controller.original_corrective_shapes(namespace,'delete',target=full,q_rotations=False,mirror=False)
        cmds.setAttr(lip_driver,1)
        assert same(point(mesh),uncorrected),(point(mesh),uncorrected)
        assert not controller.original_corrective_targets(namespace)
        report['stages'].append('delete_inbetween_and_full')
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
        raise
    finally:
        (output/'corrective.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'face-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)


if __name__=='__main__':
    namespace=sys.argv[sys.argv.index('--namespace')+1] if '--namespace' in sys.argv else ':'
    main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),namespace=namespace)
