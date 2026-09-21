"""Variable Fit -> oriented body -> complete FK torso/limbs -> real skin."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(folder):
    folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import CreateFitSkeleton,BuildVariableBodySourceFit,BuildOrientedBodySkeleton,BuildBodyCharacterRig,BindSkin
        from adv_py.core.variable_body_fit import variable_axial_description
        reports=[]
        for count,scale,hand,axis in ((1,.5,False,'z'),(4,1.,True,'z'),(8,2.,False,'y')):
            c.file(new=True,force=True);c.undoInfo(state=True);c.upAxis(axis=axis,rotateView=False)
            c.namespace(addNamespace='hero')
            host=MayaBodyBuildHost(namespace='hero')
            CreateFitSkeleton(host).apply()
            BuildVariableBodySourceFit(host).apply(spine_segments=count,scale=scale,with_hand=hand)
            body=BuildOrientedBodySkeleton(host).apply().snapshot
            baseline={j.path:tuple(c.xform(host.scene_address(j.path),q=True,ws=True,matrix=True)) for j in body.joints}
            rig=BuildBodyCharacterRig(host).apply(include_torso=True,include_control_spaces=True,axial_description=variable_axial_description(count))
            plan=rig.plan.torso.torso
            neutral=max(abs(a-b) for path,values in baseline.items() for a,b in zip(values,c.xform(host.scene_address(path),q=True,ws=True,matrix=True)))
            c.undo();removed=not c.objExists('hero:AdvPy_TorsoControls')
            c.redo();host.capture_body_torso(plan)
            chest=next(j for j in body.joints if j.name=='Chest_M')
            mesh=c.polyCube(name='hero:TorsoProbe',constructionHistory=False)[0]
            c.xform(mesh,ws=True,t=chest.world_position)
            mesh=host._cmds.identity.to_local(c.ls(mesh,long=True)[0])
            BindSkin(host).apply(mesh,(chest.path,),skin_name='AdvPy_TorsoProbeSkin',maximum_influences=1)
            points=lambda:tuple(c.xform(host.scene_address(mesh)+'.vtx[*]',q=True,ws=True,t=True))
            before=points()
            control=plan.controls.controls[1].control_path
            c.setAttr(host.scene_address(control)+'.rotateZ',20.)
            moved=max(abs(a-b) for a,b in zip(before,points()))
            expected=points()
            filename=folder/f'body-{count}.ma';c.file(rename=str(filename.resolve()));c.file(save=True,type='mayaAscii',force=True)
            c.file(str(filename.resolve()),open=True,force=True)
            reopen=max(abs(a-b) for a,b in zip(expected,points()))
            report={'segments':count,'body_joints':len(body.joints),'torso_controls':len(plan.controls.controls),
                    'neutral_error':neutral,'undo_removes_rig':removed,'skin_displacement':moved,'reopen_error':reopen}
            report['passed']=neutral<1e-4 and removed and moved>.01 and reopen<1e-4 and len(plan.controls.controls)==count+5
            reports.append(report);print(json.dumps(report))
        (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
        return 0 if all(r['passed'] for r in reports) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1])))
