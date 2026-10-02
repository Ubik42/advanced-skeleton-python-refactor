"""Source CV projection on a complete reference rig and actual Sam mesh."""
from pathlib import Path
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def points(controls):
    from maya import cmds as c
    return {control:c.xform(control+'.cv[*]',query=True,objectSpace=True,translation=True)
            for control in controls}


def matrices():
    from maya import cmds as c
    return {node:c.xform(node,query=True,worldSpace=True,matrix=True)
            for node in c.ls(type='joint',long=True) or []}


def error(first,second):
    assert first.keys()==second.keys()
    assert all(len(values)==len(second[key]) for key,values in first.items())
    return max((abs(a-b) for key,values in first.items() for a,b in zip(values,second[key])),default=0.)


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c,mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.control_curves import AutoScaleControlCurves
    output.mkdir(parents=True,exist_ok=True)
    report={'status':'running'}
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.file(str(ROOT/'validation/results/original-spline-multi-nonopm-reference/'
                       'original-spline-multi-nonopm-reference.mb'),open=True,force=True,executeScriptNodes=False)
        c.file(str(ROOT/'validation/results/fit-auto-place-sam/sam-model.ma'),i=True,executeScriptNodes=False)
        mesh=(c.ls('AutoPlaceSample*',type='transform') or [])[0]
        for axis in 'XYZ':c.setAttr(mesh+'.scale'+axis,lock=False)
        bounds=c.exactWorldBoundingBox(mesh)
        ratio=17.176120465447045/bounds[4]
        c.scale(ratio,ratio,ratio,mesh,absolute=True)
        c.makeIdentity(mesh,apply=True,translate=False,rotate=False,scale=True)
        skin=c.skinCluster('Root_M',mesh,toSelectedBones=True,maximumInfluences=3)[0]
        c.setKeyframe('FKElbow_R.rotateZ',time=1,value=0.)
        c.setKeyframe('FKElbow_R.rotateZ',time=3,value=15.)
        c.currentTime(1)
        controls=tuple(node for node in c.sets('ControlSet',query=True) or []
                       if c.listRelatives(node,children=True,type='nurbsCurve'))
        assert len(controls)>50,len(controls)
        c.select(controls,replace=True)
        input_scene=output/'character-input.mb'
        c.file(rename=str(input_scene));c.file(save=True,type='mayaBinary',force=True)
        before=points(controls)
        body_before=matrices()
        for control in controls:
            mel.eval('asProjectControlCurve "'+control+'" "'+mesh+'";')
        native=points(controls)
        c.file(str(input_scene),open=True,force=True,executeScriptNodes=False)
        c.select(controls,replace=True)
        baseline=set(c.ls(uuid=True) or [])
        skin_uuid=c.ls(skin,uuid=True)[0]
        animation={node:c.ls(node,uuid=True)[0] for node in c.ls(type='animCurve') or []}
        result=AutoScaleControlCurves(MayaBodyBuildHost()).apply(controls,mesh)
        python=points(controls)
        maximum=error(native,python)
        assert maximum<=1e-5,maximum
        assert error(body_before,matrices())<=1e-8
        assert baseline==set(c.ls(uuid=True) or [])
        assert c.ls(skin,uuid=True)==[skin_uuid]
        assert all(c.ls(node,uuid=True)==[uuid] for node,uuid in animation.items())
        c.undo();assert error(before,points(controls))<=1e-8
        c.redo();assert error(python,points(controls))<=1e-8
        persisted=output/'character-python.mb'
        c.file(rename=str(persisted));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(persisted),open=True,force=True,executeScriptNodes=False)
        assert error(python,points(controls))<=1e-8
        assert c.ls(skin,uuid=True)==[skin_uuid]
        report.update(status='passed',controls=len(controls),projected_points=result.projected_points,
            source_point_error=maximum,body_matrix_error=error(body_before,matrices()),
            skin_preserved=True,animation_preserved=True,scene_nodes_preserved=True,
            undo_redo=True,save_reopen=True)
    except Exception:report.update(status='failed',error=traceback.format_exc())
    (output/'character.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    raise SystemExit(0 if main(Path(sys.argv[1]).resolve())['status']=='passed' else 1)
