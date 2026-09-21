"""Space events on animated, skinned characters; native scene reopen mode."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(source,folder,reopen=False,faults=False):
    source=source.resolve();folder=folder.resolve()
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (EnableBodyCharacterSpaceAnimation,SwitchBodyCharacterSpace,
            CaptureBodyCharacterAnimation,ApplyBodyCharacterAnimation)
        from adv_py.core.character_animation import encode_character_animation,decode_character_animation
        from adv_py.core.body_control_spaces import control_space_pose_error
        folder.mkdir(parents=True,exist_ok=True)
        cmds.file(str(folder/'spaces.ma' if reopen or faults else source),open=True,force=True)
        cmds.undoInfo(state=True)
        host=MayaBodyBuildHost();reg=host.read_character_registration()
        meshes=('|AdvPy_CharacterProxy','ShapeProbeMesh')
        frames=(1.,5.,9.,9.5,10.,10.5,11.,14.,15.,19.,20.,21.)
        def snapshot(frames=frames):
            with host._character_sampling_time() as seek:
                result=[]
                for frame in frames:
                    seek(frame)
                    result.append((host.capture_control_space_pose(reg.spaces),tuple(
                        tuple(cmds.xform(m+'.vtx[*]',q=True,ws=True,t=True)) for m in meshes)))
                return result
        def error(left,right):
            return max(max(abs(a-b) for (_,m),(_,n) in zip(x[0],y[0]) for a,b in zip(m,n))
                for x,y in zip(left,right)),max(abs(a-b) for x,y in zip(left,right) for m,n in zip(x[1],y[1]) for a,b in zip(m,n))
        checks={};maximum=(0.,0.)
        if faults:
            from adv_py.application import KeyBodyCharacterPose
            keys=host.capture_character_key_state(reg);before=snapshot()
            pose=host.sample_character_animation(reg,(10.,))[0][1]
            KeyBodyCharacterPose(host).apply(pose)
            checks['whole_pose_key_with_different_space']=host.capture_character_pose(reg).spaces==pose.spaces
            cmds.undo()
            checks['whole_pose_key_undo']=host.capture_character_key_state(reg)==keys and max(error(before,snapshot()))<1e-4
            from adv_py.core.character_spaces import space_proxy_path
            spec=reg.spaces.space('hand_R');proxy=space_proxy_path(spec,0,'body')
            foreign=cmds.createNode('transform',name='ForeignSpaceOutput',skipSelect=True)
            cmds.connectAttr(proxy+'.translateX',foreign+'.translateX')
            try:host.read_character_registration();checks['foreign_output_rejected']=False
            except ValueError:checks['foreign_output_rejected']=True
            cmds.disconnectAttr(proxy+'.translateX',foreign+'.translateX')
            mode=next(ch for ch in reg.channels if ch.key=='space.hand_R.mode')
            plug=mode.node+'.'+mode.attribute
            cmds.keyTangent(plug,edit=True,outTangentType='linear')
            try:host.read_character_registration();checks['non_step_mode_rejected']=False
            except ValueError:checks['non_step_mode_rejected']=True
            cmds.keyTangent(plug,edit=True,outTangentType='step')
            class FailingHost(MayaBodyBuildHost):
                def switch_character_space(self,*args):
                    super().switch_character_space(*args)
                    raise RuntimeError('injected space write failure')
            keys=host.capture_character_key_state(reg);before=snapshot()
            try:SwitchBodyCharacterSpace(FailingHost()).execute('hand_R','body',23);checks['failure_rolls_back']=False
            except RuntimeError as exc:
                if 'injected' not in str(exc):raise
                checks['failure_rolls_back']=host.capture_character_key_state(reg)==keys and max(error(before,snapshot()))<1e-4
        elif reopen:
            expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
            maximum=error(expected,snapshot());checks['reopen_pose_and_skin']=max(maximum)<1e-4
            old=snapshot((22.,))
            SwitchBodyCharacterSpace(host).execute('hand_R','body',22)
            checks['reopen_continue']=max(error(old,snapshot((22.,))))<1e-4
            from adv_py.application import BakeBodyCharacterLimbMode,BakeBodyCharacterSpineMode
            sample_frames=tuple(float(t) for t in range(1,22,5));old=snapshot(sample_frames)
            BakeBodyCharacterLimbMode(host).execute(1,21,'arm','R','fk',step=5)
            checks['limb_bake_with_space_events']=max(error(old,snapshot(sample_frames)))<1e-4
            BakeBodyCharacterSpineMode(host).execute(1,21,'ik',step=5)
            checks['spine_bake_with_space_events']=max(error(old,snapshot(sample_frames)))<1e-4
        else:
            channels={ch.key:ch for ch in reg.channels}
            moving=[ch for ch in reg.channels if ch.key.startswith('torso.') and ch.attribute=='rotateY']
            for index,frame in enumerate((1.,11.,21.)):
                for ch,value in [(channels['global.translateX'],index*2.),(channels['global.rotateZ'],index*8.),
                                 (channels['global.globalScale'],1.+index*.1)]+[(ch,index*3.) for ch in moving]:
                    cmds.setKeyframe(ch.node,at=ch.attribute,time=frame,value=value,inTangentType='linear',outTangentType='linear')
            old=reg;baseline=snapshot()
            marker=cmds.createNode('transform',name='SpaceSelection',skipSelect=True);cmds.select(marker)
            time=cmds.currentTime(q=True)
            class BadInstallHost(MayaBodyBuildHost):
                def install_character_space_animation(self,*args):
                    super().install_character_space_animation(*args)
                    raise RuntimeError('injected installation failure')
            try:EnableBodyCharacterSpaceAnimation(BadInstallHost()).apply();checks['install_failure_rollback']=False
            except RuntimeError as exc:
                if 'injected' not in str(exc):raise
                checks['install_failure_rollback']=host.read_character_registration()==old and max(error(baseline,snapshot()))<1e-4
            reg=EnableBodyCharacterSpaceAnimation(host).apply()
            maximum=error(baseline,snapshot());checks['upgrade_animation_and_skin']=max(maximum)<1e-4
            checks['107_channels']=len(reg.channels)==len(old.channels)+107
            cmds.undo();checks['upgrade_undo']=host.read_character_registration()==old
            cmds.redo();checks['upgrade_redo']=host.read_character_registration()==reg
            checks['idempotent']=EnableBodyCharacterSpaceAnimation(host).apply()==reg
            # Authored torso/global motion makes following the new source observable.
            channels={ch.key:ch for ch in reg.channels}
            for key in ('head','hand_R','hand_L','foot_R','foot_L'):
                spec=reg.spaces.space(key)
                source_mode=dict(host.sample_character_animation(reg,(10.,))[0][1].spaces)[key]
                target_mode='global' if source_mode=='body' else 'body'
                early=snapshot((1.,5.,9.,9.5));at=snapshot((10.,));later=snapshot((11.,));keys=host.capture_character_key_state(reg)
                SwitchBodyCharacterSpace(host).execute(key,target_mode,10)
                delta=error(at,snapshot((10.,)));maximum=tuple(max(a,b) for a,b in zip(maximum,delta))
                checks[key+'_no_jump']=max(delta)<1e-4
                checks[key+'_past_preserved']=max(error(early,snapshot((1.,5.,9.,9.5))))<1e-4
                checks[key+'_new_source_follows']=error(later,snapshot((11.,)))[0]>1e-4
                after=snapshot();cmds.undo()
                checks[key+'_undo']=host.capture_character_key_state(reg)==keys and max(error(at,snapshot((10.,))))<1e-4
                cmds.redo();checks[key+'_redo']=max(error(after,snapshot()))<1e-4
                at=snapshot((20.,));SwitchBodyCharacterSpace(host).execute(key,source_mode,20)
                checks[key+'_return_no_jump']=max(error(at,snapshot((20.,))))<1e-4
                # Insert an earlier event after future events have been authored.
                future=snapshot((20.,21.));at=snapshot((15.,))
                SwitchBodyCharacterSpace(host).execute(key,source_mode,15)
                checks[key+'_insert_preserves_future']=max(error(future,snapshot((20.,21.))))<1e-4
                checks[key+'_insert_no_jump']=max(error(at,snapshot((15.,))))<1e-4
            clip=CaptureBodyCharacterAnimation(host).execute(1,21)
            checks['clip_v2']=json.loads(encode_character_animation(clip))['version']==2
            checks['clip_roundtrip']=decode_character_animation(encode_character_animation(clip))==clip
            before=snapshot();ApplyBodyCharacterAnimation(host).apply(clip)
            checks['clip_reapply']=max(error(before,snapshot()))<1e-4
            checks['selection_time_preserved']=(cmds.ls(sl=True) or [])==[marker] and cmds.currentTime(q=True)==time
            host.read_character_registration()
            (folder/'expected.json').write_text(json.dumps(snapshot()),encoding='utf-8')
            cmds.file(rename=str(folder/'spaces.ma'));cmds.file(save=True,type='mayaAscii',force=True)
        report={**checks,'body_error':maximum[0],'mesh_error':maximum[1],
                'status':'passed' if all(checks.values()) else 'failed'}
        (folder/('faults.json' if faults else 'read.json' if reopen else 'write.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2]),'--reopen' in sys.argv,'--faults' in sys.argv))
