"""Explicit FK-length registration on a saved, animated full character."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(folder,output,registration_only=False,reopen=False):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import EnableBodyCharacterLimbAnimation, CaptureBodyCharacterAnimation, ApplyBodyCharacterAnimation, BakeBodyCharacterLimbMode
        from adv_py.core.character_pose import character_pose_error
        cmds.file(str(output.with_suffix('.ma') if reopen else folder/'animated.ma'),open=True,force=True);cmds.undoInfo(state=True)
        host=MayaBodyBuildHost();before=host.read_character_registration()
        if reopen:
            from adv_py.application import load_character_animation
            expected=json.loads(output.with_suffix('.expected.json').read_text(encoding='utf-8'))
            original=load_character_animation(folder/'animation.json')
            originals={t:pose for t,pose in original.samples}
            actual=CaptureBodyCharacterAnimation(host).execute(1,21,10)
            body_error=max(abs(a-b) for frame,pose in actual.samples for (_,left),(_,right) in zip(pose.body_frames,originals[frame].body_frames) for a,b in zip(left,right))
            with host._character_sampling_time() as seek:
                mesh_error=0.
                for frame,wanted in zip((1,11,21),expected['points']):
                    seek(frame)
                    points=cmds.xform(expected['mesh']+'.vtx[*]',q=True,ws=True,t=True)
                    mesh_error=max(mesh_error,max(abs(a-b) for a,b in zip(wanted,points)))
            BakeBodyCharacterLimbMode(host).execute(1,21,'arm','R','ik',step=10)
            BakeBodyCharacterLimbMode(host).execute(1,21,'arm','R','fk',step=10)
            from adv_py.adapters.maya_limb_orientation import bindings
            b=bindings(before)[0]
            foreign=cmds.createNode('network',name='ForeignOrientationConsumer',skipSelect=True)
            cmds.addAttr(foreign,longName='input',attributeType='double')
            cmds.connectAttr(b.node+'OutX.output',foreign+'.input')
            rejected=False
            try:host.read_character_registration()
            except ValueError:rejected=True
            report={'reopened_body_error':body_error,'reopened_mesh_error':mesh_error,'continued_conversion':True,
                    'foreign_correction_consumer_rejected':rejected,'status':'passed' if max(body_error,mesh_error)<1e-4 and rejected else 'failed'}
            output.with_name(output.stem+'-read.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        old_keys=host.capture_character_key_state(before)
        mesh=json.loads((folder/'expected.json').read_text(encoding='utf-8'))['mesh']
        points=tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True))
        service=EnableBodyCharacterLimbAnimation(host)
        cmds.file(modified=False);preview=service.plan()
        checks={'plan_read_only':not cmds.file(q=True,modified=True)}
        after=service.apply()
        checks['length_and_orientation_channels_registered']=len(after.channels)==len(before.channels)+32
        checks['old_animation_unchanged']=host.capture_character_key_state(before)==old_keys
        checks['skin_unchanged']=tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True))==points
        cmds.undo();checks['undo_restores_old_registration']=host.read_character_registration()==before
        checks['undo_removes_correction_graph']=not cmds.ls('AdvPy_*IKOrientation_*') and not cmds.objExists('AdvPy_ArmSettings.upperMatchOffsetX_R')
        cmds.redo();checks['redo_restores_extended_registration']=host.read_character_registration()==after
        cmds.file(modified=False)
        checks['idempotent']=service.apply()==after and not cmds.file(q=True,modified=True)
        clip=CaptureBodyCharacterAnimation(host).execute(1,21,5)
        ApplyBodyCharacterAnimation(host).apply(clip)
        checks['extended_animation_readback']=all(character_pose_error(a,b)<1e-4 for (_,a),(_,b) in zip(clip.samples,CaptureBodyCharacterAnimation(host).execute(1,21,5).samples))
        checks['all_length_channels_keyed']=all(cmds.keyframe(ch.node,at=ch.attribute,q=True,keyframeCount=True)==5 for ch in after.channels if '.fkLength.' in ch.key)
        class FailedHost(MayaBodyBuildHost):
            def extend_character_limb_registration(self,before,after):
                super().extend_character_limb_registration(before,after)
                raise RuntimeError('Injected registry extension failure')
        cmds.undo();cmds.undo()
        # The idempotent call and sampling added no undo operations.
        checks['returns_to_original_registry']=host.read_character_registration()==before
        try:
            EnableBodyCharacterLimbAnimation(FailedHost()).apply();checks['extension_failure_rolls_back']=False
        except RuntimeError as exc:
            if 'Injected' not in str(exc):raise
            checks['extension_failure_rolls_back']=host.read_character_registration()==before and not cmds.ls('AdvPy_*IKOrientation_*') and not cmds.objExists('AdvPy_ArmSettings.upperMatchOffsetX_R')
        service.apply()
        def sample_skin():
            with host._character_sampling_time() as seek:
                samples=[]
                for frame in (1,11,21):
                    seek(frame);samples.append(tuple(cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True)))
                return samples
        wanted=sample_skin();errors=[]
        bake=BakeBodyCharacterLimbMode(host)
        for limb in (() if registration_only else ('arm','leg')):
            for side in ('R','L'):
                for mode in ('ik','fk'):
                    old_state=host.capture_character_key_state(after)
                    result=bake.execute(1,21,limb,side,mode,step=10)
                    new_state=host.capture_character_key_state(after)
                    if limb=='arm' and side=='R' and mode=='ik':
                        cmds.undo();checks['conversion_undo_restores_curves']=host.capture_character_key_state(after)==old_state
                        cmds.redo();checks['conversion_redo_restores_curves']=host.capture_character_key_state(after)==new_state
                    error=max(abs(a-b) for left,right in zip(wanted,sample_skin()) for a,b in zip(left,right))
                    errors.append(error)
                    checks[f'{limb}_{side}_{mode}_skin_preserved']=error<1e-4
                    checks[f'{limb}_{side}_{mode}_keys']=all(dict(p.channels)[f'{limb}.settings.{limb}IkFk_{side}']==(1 if mode=='ik' else 0) for _,p in result.samples)
        checks['all_limb_keys_resolve']=host.read_character_registration()==after
        if not registration_only:
            class FailedMatchHost(MayaBodyBuildHost):
                def apply_body_arm_fk_to_ik(self,plan):
                    super().apply_body_arm_fk_to_ik(plan)
                    raise RuntimeError('Injected compensated match failure')
            previous=host.capture_character_key_state(after)
            try:
                BakeBodyCharacterLimbMode(FailedMatchHost()).execute(1,21,'arm','R','ik',step=10)
                checks['conversion_failure_restores_curves']=False
            except RuntimeError as exc:
                if 'Injected' not in str(exc):raise
                checks['conversion_failure_restores_curves']=host.capture_character_key_state(after)==previous
            # Persist the new registration, correction graph and animated channels.
            cmds.file(rename=str(output.with_suffix('.ma').absolute()));cmds.file(save=True,type='mayaAscii')
            output.with_suffix('.expected.json').write_text(json.dumps({'mesh':mesh,'points':wanted}),encoding='utf-8')
        report={**checks,'channel_count':len(after.channels),'status':'passed' if all(checks.values()) else 'failed'}
        report['max_limb_mesh_error']=max(errors,default=0.)
        report['scope']='registration' if registration_only else 'full_limb_animation'
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).absolute(),Path(sys.argv[2]),registration_only='--registration-only' in sys.argv[3:],reopen='--reopen' in sys.argv[3:]))
