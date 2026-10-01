"""Public Root Motion create/delete on an existing animated OPM character."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    controller=MayaPanelController();host=MayaBodyBuildHost()
    original=host.read_character_registration()
    mesh=cmds.ls('BipedBindProxy',long=True)[0]
    def vertices():return tuple(cmds.pointPosition(mesh+'.vtx[0]',world=True))
    cmds.currentTime(1);baseline=vertices()
    controller.game_engine_root_motion(':',True)
    created=host.read_character_registration()
    assert created.body_root!=original.body_root
    assert max(abs(a-b) for a,b in zip(vertices(),baseline))<1e-4
    cmds.undo();assert host.read_character_registration()==original
    cmds.redo();assert host.read_character_registration()==created
    controller.game_engine_root_motion(':',False)
    removed=host.read_character_registration()
    assert removed==original
    assert max(abs(a-b) for a,b in zip(vertices(),baseline))<1e-4
    cmds.undo();assert host.read_character_registration()==created
    cmds.redo();assert host.read_character_registration()==original
    output.mkdir(parents=True,exist_ok=True)
    saved=output/'opm-root-motion.mb';cmds.file(rename=str(saved.resolve()))
    cmds.file(save=True,type='mayaBinary',force=True)
    cmds.file(str(saved.resolve()),open=True,force=True,executeScriptNodes=False)
    assert host.read_character_registration()==original
    report=dict(status='passed',create_delete=True,single_undo_redo=True,reopened=True)
    (output/'opm-root-motion.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS OPM Root Motion',report)
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
