"""Rebuild a saved Complete Face in a fresh native Maya process.

Keep this separate from the same-process build/open/undo history probe.
No original ADV MEL procedures run.
"""
from pathlib import Path
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from maya_original_face_lower_smoke import validate_lower_motion


def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    multi=bool(cmds.getAttr('FaceFitSkeleton.MultiSkinClusters'))
    attachments=cmds.objExists('EyebrowRight')
    report={'status':'running','input_scene':str(scene),'multi':multi,'attachments':attachments}
    try:
        assert cmds.getAttr('FaceFitSkeleton.Include',asString=True)=='Complete'
        assert cmds.getAttr('FaceFitSkeleton.buildCompleted')
        cmds.addAttr('ctrlLips_M',longName='authoredLipStrength',attributeType='double',
            minValue=0,maxValue=1,defaultValue=.37,keyable=True)
        if multi:
            cmds.skinPercent('LipSC','FaceMesh.vtx[100]',
                transformValue=[('upperLipJoint0_M',.37),('MultiSkinClustersFaceLipJoint_M',.63)],
                zeroRemainingInfluences=True)
            part_skin=next(node for node in cmds.listHistory('TongueMesh') or []
                if cmds.nodeType(node)=='skinCluster' and node.startswith('UpMidLocSC'))
            cmds.skinPercent(part_skin,'TongueMesh.vtx[1]',
                transformValue=[('upperFaceJoint_M',.31),('middleFaceJoint_M',.69)],
                zeroRemainingInfluences=True)
            report['authored_part_layer']=part_skin
        baseline=validate_lower_motion(cmds,complete=True,attachments=attachments)
        report['motion']=baseline
        old_skin=cmds.ls('LipSC' if multi else 'HeadSkin',uuid=True)[0]
        result=MayaPanelController().face_original_build(':',cage_smooth=1,jaw_smooth=1)
        report['stages']=list(result['stages'])
        report['restore']=result['stages']['RebuildRestore']
        report['prefix_before_undo']=cmds.ls('prefix_FaceGroup*',long=True) or []
        assert not cmds.objExists('prefix_FaceGroup')
        cmds.undo()
        assert cmds.ls('LipSC' if multi else 'HeadSkin',uuid=True)[0]==old_skin
        assert abs(cmds.getAttr('ctrlLips_M.authoredLipStrength')-.37)<1e-8
        cmds.redo()
        assert not cmds.objExists('prefix_FaceGroup')
        report['undo_redo']=True
        rebuilt=validate_lower_motion(cmds,complete=True,attachments=attachments)
        for key,value in baseline.items():
            assert abs(rebuilt[key]-value)<1e-5,(key,value,rebuilt[key])
        report['rebuilt_motion']=rebuilt
        assert abs(cmds.getAttr('ctrlLips_M.authoredLipStrength')-.37)<1e-8
        report['authored_attribute_preserved']=True
        if multi:
            assert abs(cmds.skinPercent('LipSC','FaceMesh.vtx[100]',query=True,
                transform='upperLipJoint0_M')-.37)<1e-8
            assert abs(cmds.skinPercent(part_skin,'TongueMesh.vtx[1]',query=True,
                transform='upperFaceJoint_M')-.31)<1e-8
            report['authored_face_and_part_layer_weights_preserved']=True
        saved=output/'face-rebuilt.mb'
        cmds.file(rename=str(saved));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(saved),open=True,force=True,executeScriptNodes=False)
        reopened=validate_lower_motion(cmds,complete=True,attachments=attachments)
        for key,value in rebuilt.items(): assert abs(reopened[key]-value)<1e-5,key
        report['saved_reopened']=True
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
        raise
    finally:
        (output/'face-rebuild.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__': main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
