"""Native mirrored corrective geometry and original driver catalogue."""
from pathlib import Path
import json
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene, output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    controller=MayaPanelController()
    report={'status':'running','stages':[]}
    def points():return tuple(cmds.xform('FaceMesh.vtx[*]',query=True,worldSpace=True,translation=True))
    def point(index):return tuple(cmds.xform(f'FaceMesh.vtx[{index}]',query=True,worldSpace=True,translation=True))
    def same(a,b):return max(abs(x-y) for x,y in zip(a,b))<2e-3
    try:
        neutral=points()
        cmds.setAttr('ctrlBrow_R.ty',1);right=points()
        index=max(range(len(right)//3),key=lambda i:max(abs(right[i*3+a]-neutral[i*3+a]) for a in range(3)))
        location=neutral[index*3:index*3+3]
        other=min(range(len(right)//3),key=lambda i:abs(neutral[i*3]+location[0])+abs(neutral[i*3+1]-location[1])+abs(neutral[i*3+2]-location[2]))
        cmds.setAttr('ctrlBrow_R.ty',0);cmds.setAttr('ctrlBrow_L.ty',1)
        left=point(other)
        cmds.setAttr('ctrlBrow_L.ty',0);cmds.setAttr('ctrlBrow_R.ty',1)
        cmds.select('FaceMesh',replace=True)
        created=controller.original_corrective_shapes(':','create',q_rotations=False,mirror=True)
        target=created['target']
        sculpt=list(cmds.xform(target+f'.vtx[{index}]',query=True,worldSpace=True,translation=True));sculpt[2]+=.2
        cmds.xform(target+f'.vtx[{index}]',worldSpace=True,translation=sculpt)
        result=controller.original_corrective_shapes(':','apply',q_rotations=False,mirror=True)
        print('MIRROR',result,flush=True)
        assert result['mirrored']
        cmds.undo();assert cmds.objExists(target)
        cmds.redo();assert not cmds.objExists(target)
        cmds.setAttr('ctrlBrow_R.ty',1);assert same(point(index),sculpt),(point(index),sculpt)
        cmds.setAttr('ctrlBrow_R.ty',0);cmds.setAttr('ctrlBrow_L.ty',1)
        expected=list(left);expected[2]+=.2
        assert same(point(other),expected),(point(other),expected,index,other)
        cmds.setAttr('ctrlBrow_L.ty',0)
        assert same(point(index),neutral[index*3:index*3+3])
        assert same(point(other),neutral[other*3:other*3+3])
        targets=controller.original_corrective_targets(':')
        assert len(targets)==2,targets
        report['stages'].append('mirror_geometry_driver_undo_redo')
        scene=output/'face-mirrored-corrective.mb'
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
        cmds.setAttr('ctrlBrow_L.ty',1);assert same(point(other),expected)
        cmds.setAttr('ctrlBrow_L.ty',0)
        report['stages'].append('save_reopen')
        targets=controller.original_corrective_targets(':')
        target=next(t for t in targets if t.driver_object=='ctrlBrow_R')
        controller.original_corrective_shapes(':','delete',target=target,q_rotations=False,mirror=True)
        targets=controller.original_corrective_targets(':')
        assert len(targets)==1 and targets[0].driver_object=='ctrlBrow_L',targets
        cmds.setAttr('ctrlBrow_L.ty',1);assert same(point(other),expected)
        cmds.setAttr('ctrlBrow_L.ty',0)
        controller.original_corrective_shapes(':','delete',target=targets[0],q_rotations=False,mirror=False)
        assert not controller.original_corrective_targets(':')
        report['stages'].append('delete_each_side')
        report['status']='passed';report['sample_vertices']=[index,other]
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'corrective-mirror.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'face-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)


if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
