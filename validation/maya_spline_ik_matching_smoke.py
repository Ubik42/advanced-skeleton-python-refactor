"""Native spline IK fitting after FK conversion and IK-control perturbation."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(source,folder):
    folder.mkdir(parents=True,exist_ok=True);maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (EnableBodyCharacterSplineAnimation, BakeBodyCharacterSpineMode,
            CaptureBodyCharacterAnimation, RebuildBodyCharacter, save_character_animation)
        reports=[]
        if '--reopen' in sys.argv:
            from adv_py.application import load_character_animation, ApplyBodyCharacterAnimation
            from adv_py.core.character_pose import character_pose_error
            for count in (1,4,8):
                c.file(str((folder/f'ik-{count}.ma').resolve()),open=True,force=True);c.undoInfo(state=True)
                host=MayaBodyBuildHost(namespace='hero');host.read_character_registration()
                expected=load_character_animation(folder/f'animation-{count}.json')
                actual=CaptureBodyCharacterAnimation(host).execute(1,21,10)
                body_error=max(character_pose_error(a,b) for (_,a),(_,b) in zip(expected.samples,actual.samples))
                points=json.loads((folder/f'points-{count}.json').read_text(encoding='utf8'))
                with host._character_sampling_time() as seek:
                    mesh_error=0.
                    for (frame,_),wanted in zip(actual.samples,points):
                        seek(frame);current=c.xform('hero:SplineProbe.vtx[*]',q=True,ws=True,t=True)
                        mesh_error=max(mesh_error,max(abs(a-b) for a,b in zip(wanted,current)))
                ApplyBodyCharacterAnimation(host).apply(expected)
                reports.append(dict(segments=count,body_error=body_error,mesh_error=mesh_error,
                                    continued_editing=True,passed=max(body_error,mesh_error)<1e-4))
            (folder/'reopen.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
            print(json.dumps(reports));return 0 if all(r['passed'] for r in reports) else 1
        for count in ((4,) if '--four' in sys.argv else (1,4,8)):
            c.file(str((source/f'spline-{count}.ma').resolve()),open=True,force=True);c.undoInfo(state=True)
            host=MayaBodyBuildHost(namespace='hero');reg=EnableBodyCharacterSplineAnimation(host).apply();plan=reg.spine
            frames=(1.,11.,21.)
            global_channel=next(ch for ch in reg.channels if ch.key=="global.globalScale")
            for frame,t in zip(frames,(0.,.5,1.)):
                for node,attr,value in ((global_channel.node,global_channel.attribute,1.+t*.3),(plan.settings,'spineIkFk',1.),(plan.settings,'translateX',t*.8),
                        (plan.settings,'volume',.7+t*.3),(plan.targets[1],'translateY',t*.6),
                        (plan.targets[2],'translateZ',-t*.3),(plan.targets[0],'rotateX',t*5.),
                        (plan.settings,'rotateX',-t*8.),(plan.settings,'rotateZ',t*4.)):
                    host._cmds.setKeyframe(node,attribute=attr,time=frame,value=value)
            def points():
                with host._character_sampling_time() as seek:
                    result=[]
                    for frame in frames:
                        seek(frame);result.append(tuple(c.xform('hero:SplineProbe.vtx[*]',q=True,ws=True,t=True)))
                    return result
            expected=CaptureBodyCharacterAnimation(host).execute(1,21,10);wanted=points()
            BakeBodyCharacterSpineMode(host).execute(1,21,'fk',10)
            for node,attr,delta in ((plan.targets[1],'translateY',.2),(plan.settings,'translateX',.1),
                                    (plan.targets[0],'rotateX',3.),(plan.settings,'rotateZ',-2.)):
                host._cmds.keyframe(node,attribute=attr,edit=True,relative=True,valueChange=delta)
            original_keys=host.capture_character_key_state(reg)
            BakeBodyCharacterSpineMode(host).execute(1,21,'ik',10)
            actual=CaptureBodyCharacterAnimation(host).execute(1,21,10)
            body_error=max(abs(a-b) for (_,x),(_,y) in zip(expected.samples,actual.samples)
                           for (_,left),(_,right) in zip(x.body_frames,y.body_frames) for a,b in zip(left,right))
            error=lambda a,b:max(abs(x-y) for left,right in zip(a,b) for x,y in zip(left,right))
            mesh_error=error(wanted,points())
            ik=all(dict(p.channels)['spine.spline.spineIkFk']==1. for _,p in actual.samples)
            c.undo();undo=host.capture_character_key_state(reg)==original_keys
            c.redo();redo=error(wanted,points())<1e-4
            if count==4:
                RebuildBodyCharacter(host).apply('replacement')
                reg=host.read_character_registration();plan=reg.spine
                rebuild=error(wanted,points())<1e-4
            else:rebuild=True
            save_character_animation(actual,folder/f'animation-{count}.json')
            (folder/f'points-{count}.json').write_text(json.dumps(wanted),encoding='utf8')
            filename=(folder/f'ik-{count}.ma').resolve();c.file(rename=str(filename));c.file(save=True,type='mayaAscii',force=True)
            c.file(str(filename),open=True,force=True);host.read_character_registration()
            reopened=error(wanted,points())
            rejected=True
            if count==4:
                BakeBodyCharacterSpineMode(host).execute(11,11,'fk')
                host._cmds.setKeyframe(plan.fk_controls[2],attribute='translateX',time=11,value=.25)
                keys=host.capture_character_key_state(reg)
                try:BakeBodyCharacterSpineMode(host).execute(11,11,'ik')
                except ValueError as exc:
                    rejected=host.capture_character_key_state(reg)==keys and '伸展比不一致' in str(exc)
                else:rejected=False
            row=dict(segments=count,body_error=body_error,mesh_error=mesh_error,ik=ik,undo=undo,redo=redo,
                     rebuild=rebuild,reopened=reopened,unrepresentable_rejected=rejected)
            row['passed']=max(body_error,mesh_error,reopened)<1e-4 and all((ik,undo,redo,rebuild,rejected))
            reports.append(row);print(json.dumps(row),flush=True)
        (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
        return 0 if all(r['passed'] for r in reports) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
