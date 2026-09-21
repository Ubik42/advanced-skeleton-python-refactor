"""Animation files, whole-clip rollback and fresh-process persistence on real skin."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(folder,mode,with_hand):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (RegisterBodyCharacter, CaptureBodyCharacterPose,
            CaptureBodyCharacterAnimation, ApplyBodyCharacterAnimation, save_character_animation, load_character_animation)
        from adv_py.core.character_animation import CharacterAnimation
        from adv_py.core.character_pose import character_pose_error
        from dataclasses import replace
        folder.mkdir(parents=True,exist_ok=True)
        host=MayaBodyBuildHost();checks={}
        if mode=='write':
            from maya_complete_character import build_character
            cmds.upAxis(axis='z',rotateView=False);cmds.undoInfo(state=True)
            demo=build_character(with_hand=with_hand);host=demo.host
            reg=RegisterBodyCharacter(host).apply(demo.rig)
            poses=[]
            for amount in (0,1,2):
                for ch in reg.channels:
                    value=None
                    if ch.key=='global.translateX':value=amount*2
                    elif ch.key=='global.rotateZ':value=amount*5
                    elif ch.key=='global.globalScale':value=1+amount*.1
                    elif ch.attribute=='rotateZ' and any(x in ch.key for x in ('Spine1','Elbow','Knee','Index1')):value=amount*8
                    if value is not None:cmds.setAttr(ch.node+'.'+ch.attribute,value)
                poses.append(CaptureBodyCharacterPose(host).execute())
            clip=CharacterAnimation(host.character_time_unit(),tuple(zip((1.,11.,21.),poses)))
            apply=ApplyBodyCharacterAnimation(host)
            marker=cmds.createNode('transform',name='AnimationSelection',skipSelect=True);cmds.select(marker)
            cmds.currentTime(7)
            cmds.file(modified=False)
            apply.plan(clip)
            checks['plan_read_only']=not cmds.file(q=True,modified=True)
            apply.apply(clip)
            cmds.file(modified=False)
            sampled=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            checks['sampling_read_only']=not cmds.file(q=True,modified=True)
            save_character_animation(sampled,folder/'animation.json')
            checks['file_roundtrip']=load_character_animation(folder/'animation.json')==sampled
            mesh=demo.mesh
            def points():return tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True))
            with host._character_sampling_time() as seek:
                expected=[]
                for frame,_ in sampled.samples:
                    seek(frame);expected.append(points())
            # Preserve existing keys outside the clip while replacing all clip keys.
            for ch in reg.channels:
                for frame in (0,30):cmds.setKeyframe(ch.node,at=ch.attribute,t=frame,v=dict(poses[0].channels)[ch.key])
                cmds.keyframe(ch.node,at=ch.attribute,e=True,time=(1,21),relative=True,valueChange=.01)
            with host._character_sampling_time() as seek:seek(7)
            before=host.capture_character_key_state(reg);before_pose=host.capture_character_pose(reg)
            apply.apply(sampled)
            restored=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            checks['whole_clip_body_restored']=all(character_pose_error(a,b)<1e-4 for (_,a),(_,b) in zip(sampled.samples,restored.samples))
            with host._character_sampling_time() as seek:
                errors=[]
                for (frame,_),wanted in zip(sampled.samples,expected):
                    seek(frame);errors.append(max(abs(a-b) for a,b in zip(wanted,points())))
            checks['whole_clip_skin_restored']=max(errors)<1e-4
            after=host.capture_character_key_state(reg)
            checks['outside_keys_preserved']=all(dict(zip(a[2],a[3]))[t]==dict(zip(b[2],b[3]))[t] for a,b in zip(before[1],after[1]) for t in (0,30))
            cmds.undo()
            checks['single_undo_restores_all_curves']=host.capture_character_key_state(reg)==before and character_pose_error(before_pose,host.capture_character_pose(reg))<1e-4
            cmds.redo()
            checks['single_redo_restores_all_curves']=host.capture_character_key_state(reg)==after
            class FailedHost(MayaBodyBuildHost):
                def write_character_animation(self,registration,samples):
                    super().write_character_animation(registration,samples[:1])
                    raise RuntimeError('Injected partial clip failure')
            try:
                ApplyBodyCharacterAnimation(FailedHost()).apply(clip);checks['partial_failure_rolls_back']=False
            except RuntimeError as exc:
                if 'Injected' not in str(exc):raise
                checks['partial_failure_rolls_back']=host.capture_character_key_state(reg)==after
            try:
                apply.apply(replace(sampled,time_unit='pal' if sampled.time_unit!='pal' else 'film'));checks['fps_mismatch_rejected']=False
            except ValueError:checks['fps_mismatch_rejected']=host.capture_character_key_state(reg)==after
            checks['selection_and_time_preserved']=cmds.currentTime(q=True)==7 and cmds.ls(sl=True)==[marker]
            cmds.file(rename=str(folder/'animated.ma'));cmds.file(save=True,type='mayaAscii')
            (folder/'expected.json').write_text(json.dumps({'mesh':mesh,'points':expected}),encoding='utf-8')
        else:
            cmds.file(str(folder/'animated.ma'),open=True,force=True)
            cmds.undoInfo(state=True)
            expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
            mesh=expected['mesh'];sampled=load_character_animation(folder/'animation.json')
            restored=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            checks['reopened_body_animation']=all(character_pose_error(a,b)<1e-4 for (_,a),(_,b) in zip(sampled.samples,restored.samples))
            with host._character_sampling_time() as seek:
                errors=[]
                for (frame,_),wanted in zip(sampled.samples,expected['points']):
                    seek(frame);actual=cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True)
                    errors.append(max(abs(a-b) for a,b in zip(wanted,actual)))
            checks['reopened_skin_animation']=max(errors)<1e-4
            ApplyBodyCharacterAnimation(host).apply(sampled)
            checks['reopened_can_continue_editing']=True
        report={**checks,'max_mesh_error':max(errors),'status':'passed' if all(checks.values()) else 'failed'}
        (folder/(mode+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).absolute(),sys.argv[2],with_hand='--basic' not in sys.argv[3:]))
