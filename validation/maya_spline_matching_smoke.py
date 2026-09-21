"""Animated spline-to-FK conversion with real skin, undo and rebuild."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(source,folder):
    folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (EnableBodyCharacterSplineAnimation, CaptureBodyCharacterAnimation,
            BakeBodyCharacterSpineMode, RebuildBodyCharacter, save_character_animation)
        from adv_py.core.character_pose import character_pose_error
        reports=[]
        if '--reopen' in sys.argv:
            from adv_py.application import load_character_animation, ApplyBodyCharacterAnimation
            for count in (1,4,8):
                c.file(str((folder/f'matched-{count}.ma').resolve()),open=True,force=True);c.undoInfo(state=True)
                host=MayaBodyBuildHost(namespace='hero');host.read_character_registration()
                clip=load_character_animation(folder/f'animation-{count}.json')
                sampled=CaptureBodyCharacterAnimation(host).execute(1,21,5)
                body_error=max(character_pose_error(a,b) for (_,a),(_,b) in zip(clip.samples,sampled.samples))
                wanted=json.loads((folder/f'points-{count}.json').read_text(encoding='utf8'))
                with host._character_sampling_time() as seek:
                    mesh_error=0.
                    for (frame,_),points in zip(sampled.samples,wanted):
                        seek(frame);actual=c.xform('hero:SplineProbe.vtx[*]',q=True,ws=True,t=True)
                        mesh_error=max(mesh_error,max(abs(a-b) for a,b in zip(points,actual)))
                ApplyBodyCharacterAnimation(host).apply(clip)
                reports.append(dict(segments=count,body_error=body_error,mesh_error=mesh_error,
                                    continued_editing=True,passed=max(body_error,mesh_error)<1e-4))
            (folder/'reopen.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
            print(json.dumps(reports));return 0 if all(r['passed'] for r in reports) else 1
        for count in ((4,) if "--four" in sys.argv else (1,4,8)):
            c.file(str((source/f'spline-{count}.ma').resolve()),open=True,force=True);c.undoInfo(state=True)
            host=MayaBodyBuildHost(namespace='hero')
            original=host.read_character_registration()
            reg=EnableBodyCharacterSplineAnimation(host).apply()
            first=host.read_character_registration()
            c.undo();upgrade_undo=host.read_character_registration()==original
            c.redo();upgrade_redo=host.read_character_registration()==first
            if count==4:
                from adv_py.application import EnableBodyCharacterLimbAnimation
                reg=EnableBodyCharacterLimbAnimation(host).apply()
            plan=reg.spine
            for frame,stretch,volume,scale in ((1,0.,0.,1.),(11,1.2,1.,1.4),(21,.5,.5,.8)):
                host._cmds.setKeyframe(plan.settings,attribute='translateX',time=frame,value=stretch)
                host._cmds.setKeyframe(plan.settings,attribute='volume',time=frame,value=volume)
                global_ch=next(ch for ch in reg.channels if ch.key=='global.globalScale')
                host._cmds.setKeyframe(global_ch.node,attribute=global_ch.attribute,time=frame,value=scale)
            frames=(1.,6.,11.,16.,21.)
            def points():
                with host._character_sampling_time() as seek:
                    rows=[]
                    for frame in frames:
                        seek(frame);rows.append(tuple(c.xform('hero:SplineProbe.vtx[*]',q=True,ws=True,t=True)))
                    return rows
            wanted=points();before=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            keys=host.capture_character_key_state(reg)
            clip=BakeBodyCharacterSpineMode(host).execute(1,21,'fk',5)
            after=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            body_error=max(abs(a-b) for (_,left),(_,right) in zip(before.samples,after.samples)
                           for (_,x),(_,y) in zip(left.body_frames,right.body_frames) for a,b in zip(x,y))
            error=lambda left,right:max(abs(a-b) for x,y in zip(left,right) for a,b in zip(x,y))
            mesh_error=error(wanted,points())
            all_fk=all(dict(pose.channels)['spine.spline.spineIkFk']==0. for _,pose in after.samples)
            c.undo();undo=host.capture_character_key_state(reg)==keys
            c.redo();redo=error(wanted,points())<1e-4
            if count==4:
                class FailedHost(MayaBodyBuildHost):
                    def write_character_animation(self,registration,samples):
                        super().write_character_animation(registration,samples[:1])
                        raise RuntimeError('Injected spline matching write failure')
                before_failure=host.capture_character_key_state(reg)
                try:BakeBodyCharacterSpineMode(FailedHost(namespace='hero')).execute(1,21,'fk',5)
                except RuntimeError as exc:
                    if 'Injected spline' not in str(exc):raise
                    rollback=host.capture_character_key_state(reg)==before_failure
                else:rollback=False
                RebuildBodyCharacter(host).apply('replacement')
                rebuild_error=error(wanted,points())
            else:rollback=True;rebuild_error=0.
            save_character_animation(after,folder/f'animation-{count}.json')
            (folder/f'points-{count}.json').write_text(json.dumps(wanted),encoding='utf8')
            c.file(rename=str((folder/f'matched-{count}.ma').resolve()));c.file(save=True,type='mayaAscii',force=True)
            c.file(str((folder/f'matched-{count}.ma').resolve()),open=True,force=True)
            host.read_character_registration();reopen_error=error(wanted,points())
            row=dict(segments=count,upgrade_undo=upgrade_undo,upgrade_redo=upgrade_redo,body_error=body_error,
                mesh_error=mesh_error,all_fk=all_fk,undo=undo,redo=redo,rollback=rollback,rebuild_error=rebuild_error,reopen_error=reopen_error)
            row['passed']=all((upgrade_undo,upgrade_redo,all_fk,undo,redo,rollback)) and max(body_error,mesh_error,rebuild_error,reopen_error)<1e-4
            reports.append(row);print(json.dumps(row))
        (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
        return 0 if all(r['passed'] for r in reports) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
