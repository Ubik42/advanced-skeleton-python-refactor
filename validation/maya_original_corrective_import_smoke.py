"""Imported legacy corrective data, WIP save/reopen and model rename."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene, output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(new=True,force=True)
    cmds.file(str(scene),i=True,namespace='ImportedActor',executeScriptNodes=False)
    controller=MayaPanelController()
    driver='ImportedActor:ctrlLips_M.ty'
    mesh='ImportedActor:FaceMesh'
    targets=controller.original_corrective_targets('ImportedActor',edit=True)
    full=next(t for t in targets if not t.inbetween)
    cmds.setAttr(driver,1)
    baseline=tuple(cmds.xform(mesh+'.vtx[504]',query=True,worldSpace=True,translation=True))
    result=controller.original_corrective_shapes('ImportedActor','edit',target=full,q_rotations=False,mirror=False)
    target='ImportedActor:'+result['target']
    mesh=cmds.rename(mesh,'ImportedActor:RenamedFace')
    controller.original_corrective_shapes('ImportedActor','cancel',q_rotations=False,mirror=False)
    assert not cmds.objExists(target)
    assert cmds.getAttr(mesh+'.v')
    result=controller.original_corrective_shapes('ImportedActor','edit',target=full,q_rotations=False,mirror=False)
    target='ImportedActor:'+result['target']
    expected=list(cmds.xform(target+'.vtx[504]',query=True,worldSpace=True,translation=True));expected[2]+=.1
    cmds.xform(target+'.vtx[504]',worldSpace=True,translation=expected)
    wip=output/'corrective-wip.mb'
    cmds.file(rename=str(wip));cmds.file(save=True,type='mayaBinary',force=True)
    cmds.file(str(wip),open=True,force=True,executeScriptNodes=False)
    controller.original_corrective_shapes('ImportedActor','apply',q_rotations=False,mirror=False)
    assert cmds.getAttr(mesh+'.v')
    cmds.setAttr(driver,1)
    actual=tuple(cmds.xform(mesh+'.vtx[504]',query=True,worldSpace=True,translation=True))
    assert max(abs(a-b) for a,b in zip(actual,expected))<2e-4,(actual,expected,baseline)
    report={'status':'passed','imported_old_string_metadata':True,'rename_cancel_visibility':True,
            'renamed_model_edit':True,'saved_wip_reopen_apply':True,'sample_vertex':504}
    (output/'corrective-import.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    cmds.file(rename=str(output/'corrective-imported.mb'));cmds.file(save=True,type='mayaBinary',force=True)


if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
