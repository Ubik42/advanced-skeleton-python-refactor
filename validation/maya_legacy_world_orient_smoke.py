"""Verify original worldOrient precedence, editing and native undo/reopen."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main(source,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.core.fit_metadata import FitJointField,FitJointFieldEdit
    cmds.file(str(source.resolve()),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    host=MayaBodyBuildHost();field=FitJointField.WORLD_ORIENT_UP
    original=host.read_fit_joint_metadata('Ankle')
    assert original.world_orient_up=='xDown' and field in original.present_fields
    with host.transaction('Edit original worldOrient spelling'):
        host.apply_fit_joint_edit('Ankle',FitJointFieldEdit(field,'yUp'))
    assert cmds.getAttr('Ankle.worldOrient')==1 and not cmds.objExists('Ankle.worldOrientUp')
    cmds.undo();assert host.read_fit_joint_metadata('Ankle')==original
    cmds.redo();assert host.read_fit_joint_metadata('Ankle').world_orient_up=='yUp'
    cmds.addAttr('Ankle',ln='worldOrientUp',at='enum',en='xUp:yUp:zUp:xDown:yDown:zDown')
    cmds.setAttr('Ankle.worldOrientUp',2)
    assert host.read_fit_joint_metadata('Ankle').world_orient_up=='zUp'
    with host.transaction('Remove both original worldOrient representations'):
        host.apply_fit_joint_edit('Ankle',FitJointFieldEdit(field,None))
    assert not cmds.objExists('Ankle.worldOrient') and not cmds.objExists('Ankle.worldOrientUp')
    cmds.undo();assert host.read_fit_joint_metadata('Ankle').world_orient_up=='zUp'
    output.mkdir(parents=True,exist_ok=True)
    scene=output/'legacy-world-orient.mb';cmds.file(rename=str(scene.resolve()));cmds.file(save=True,type='mayaBinary',force=True)
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    assert host.read_fit_joint_metadata('Ankle').world_orient_up=='zUp'
    assert cmds.getAttr('Ankle.worldOrient')==1
    report=dict(status='passed',legacy_read=True,authored_spelling_preserved=True,new_field_overrides_legacy=True,
                removal_clears_both=True,undo_redo=True,saved_reopened=True)
    (output/'legacy-world-orient.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
