"""Capture exact Bendy export matrix differences before transaction rollback."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    original=MayaBodyBuildHost.capture_body_export_skeleton
    output.mkdir(parents=True,exist_ok=True)
    def capture(host,plan):
        result=original(host,plan)
        rows=[]
        for joint in plan.joints:
            source=cmds.xform(joint.source_path,q=True,ws=True,m=True)
            target=cmds.xform(joint.output_path,q=True,ws=True,m=True)
            error=max(abs(a-b) for a,b in zip(source,target))
            if error>1e-5:
                values={}
                for attr in ('translate','rotate','scale','shear','jointOrient','rotateAxis','segmentScaleCompensate','inverseScale','inheritsTransform','rotatePivot','rotatePivotTranslate','scalePivot','scalePivotTranslate','offsetParentMatrix'):
                    values[attr]={'source':cmds.getAttr(joint.source_path+'.'+attr),
                                  'export':cmds.getAttr(joint.output_path+'.'+attr)}
                rows.append(dict(source=joint.source_path,target=joint.output_path,error=error,
                                 source_world=source,export_world=target,attributes=values))
        if rows:
            (output/'bendy-export-difference.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        return result
    MayaBodyBuildHost.capture_body_export_skeleton=capture
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    MayaPanelController().publish_fbx(':',output/'bendy.fbx',start=1,end=5,include_skins=True)
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
