"""Native public Complete Face deletion, undo, redo and rebuilding."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maya_original_face_lower_smoke import validate_lower_motion


def main(scene, output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    controller=MayaPanelController()
    meshes=('FaceMesh','EyeRight','EyeLeft','UpperTeethMesh','LowerTeethMesh','TongueMesh',
            'EyebrowRight','EyebrowLeft','EyeLashRight','EyeLashLeft')
    identity={n:cmds.ls(n,uuid=True)[0] for n in (*meshes,'FaceFitSkeleton','Head_M','HeadSkin')}
    baseline=validate_lower_motion(cmds,complete=True,attachments=True)
    assert controller.face_delete_advanced(':')
    assert not cmds.objExists('FaceMotionSystem')
    assert not cmds.objExists('FaceAllSet')
    assert cmds.getAttr('FaceFitSkeleton.buildStep')==0
    assert not cmds.getAttr('FaceFitSkeleton.buildCompleted')
    for n,u in identity.items(): assert cmds.ls(n,uuid=True)[0]==u,n
    cmds.undo()
    assert cmds.getAttr('FaceFitSkeleton.buildCompleted')
    for n,u in identity.items(): assert cmds.ls(n,uuid=True)[0]==u,n
    cmds.redo()
    assert not cmds.objExists('FaceMotionSystem')
    assert not cmds.getAttr('FaceFitSkeleton.buildCompleted')
    for n,u in identity.items(): assert cmds.ls(n,uuid=True)[0]==u,n
    # Motion probes write channels and would clear the native redo queue.
    # Finish the direct undo/redo checks before probing the restored graph.
    cmds.undo()
    restored=validate_lower_motion(cmds,complete=True,attachments=True)
    assert max(abs(restored[k]-v) for k,v in baseline.items())<1e-5
    assert controller.face_delete_advanced(':')
    result=controller.face_original_build(':',cage_smooth=1,jaw_smooth=1)
    assert len(result['stages'])==30
    cmds.undo()
    assert not cmds.objExists('FaceMotionSystem')
    assert not cmds.getAttr('FaceFitSkeleton.buildCompleted')
    cmds.redo()
    assert cmds.getAttr('FaceFitSkeleton.buildStep')==30
    assert cmds.getAttr('FaceFitSkeleton.buildCompleted')
    motion=validate_lower_motion(cmds,complete=True,attachments=True)
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(rename=str(output/'face-deleted-and-rebuilt.mb'))
    cmds.file(save=True,type='mayaBinary',force=True)
    cmds.file(str(output/'face-deleted-and-rebuilt.mb'),open=True,force=True,executeScriptNodes=False)
    reopened=validate_lower_motion(cmds,complete=True,attachments=True)
    assert max(abs(reopened[k]-v) for k,v in motion.items())<1e-5
    report={'status':'passed','delete_undo_redo':True,'production_identity_preserved':True,
            'new_build_undo_redo':True,'saved_reopened':True,
            'stages':list(result['stages']),'motion':motion}
    (output/'face-delete.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
