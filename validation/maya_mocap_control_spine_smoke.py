"""Transfer a generated three-joint motion into Global and Spine FK curves."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import build_character
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import RegisterBodyCharacter,RetargetMocapSpineToCharacter
        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        built=build_character(with_hand=False)
        registration=RegisterBodyCharacter(built.host).apply(built.rig)
        waist_control,chest_control=registration.spine.fk_controls[1:]
        for frame,waist_value,chest_value in ((1,0.,0.),(10,5.,-4.)):
            cmds.setKeyframe(waist_control,attribute='rotateZ',time=frame,value=waist_value)
            cmds.setKeyframe(chest_control,attribute='rotateY',time=frame,value=chest_value)
        cmds.namespace(add='TakeA')
        root=cmds.createNode('joint',name='TakeA:Hips',skipSelect=True)
        waist=cmds.createNode('joint',name='TakeA:Spine',parent=root,skipSelect=True)
        chest=cmds.createNode('joint',name='TakeA:Chest',parent=waist,skipSelect=True)
        cmds.setAttr(waist+'.translateY',5.)
        cmds.setAttr(chest+'.translateY',5.)
        for frame,travel,bend,twist in ((1,0.,0.,0.),(5,4.,12.,-9.),(10,9.,25.,-18.)):
            cmds.setKeyframe(root,attribute='translateX',time=frame,value=travel)
            cmds.setKeyframe(waist,attribute='rotateZ',time=frame,value=bend)
            cmds.setKeyframe(chest,attribute='rotateX',time=frame,value=twist)
        host=MayaMocapControlHost()
        before=host.capture_character_key_state(registration)
        root_samples,spine_samples=RetargetMocapSpineToCharacter(host).apply('|TakeA:Hips',
            source_spine='Spine',source_chest='Chest',start_frame=1,end_frame=10)
        after=host.capture_character_key_state(registration)
        changed_keys={channel.key for channel in registration.channels if channel.key.startswith('global.')
                      or channel.node in registration.spine.fk_controls[1:]}
        with host._character_sampling_time() as seek:
            errors=[]
            for sample in spine_samples:
                seek(sample.frame)
                for path,wanted in zip(registration.spine.body_joints[1:],sample.body_matrices):
                    actual=cmds.xform(path,query=True,worldSpace=True,matrix=True)
                    errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        checks={
            'all_ten_frames':len(root_samples)==len(spine_samples)==10,
            'fk_spine_keyed':all(len(cmds.keyframe(control+'.rotate'+axis,query=True,timeChange=True) or [])==10
                for control in registration.spine.fk_controls[1:] for axis in 'XYZ'),
            'spine_pose_verified':max(errors)<1e-4,
            'spine_motion_visible':any(abs(value)>1. for value in spine_samples[-1].control_values),
            'other_character_channels_preserved':all(a==b for a,b in zip(before[1],after[1])
                if a[0] not in changed_keys),
        }
        class FailedHost(MayaMocapControlHost):
            def write_mocap_spine_control_keys(self,plan):
                super().write_mocap_spine_control_keys(plan)
                raise RuntimeError('Injected spine write failure')
        try:RetargetMocapSpineToCharacter(FailedHost()).apply('|TakeA:Hips',
            source_spine='Spine',source_chest='Chest',start_frame=1,end_frame=10)
        except RuntimeError as exc:
            if 'Injected' not in str(exc):raise
            checks['partial_failure_rolls_back']=host.capture_character_key_state(registration)==after
        else:checks['partial_failure_rolls_back']=False
        cmds.undo();checks['single_undo']=host.capture_character_key_state(registration)==before
        cmds.redo();checks['single_redo']=host.capture_character_key_state(registration)==after
        scene=output.parent/'mocap-control-spine.ma'
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaAscii',force=True)
        cmds.file(str(scene),open=True,force=True)
        reopened=MayaMocapControlHost();registered=reopened.read_character_registration()
        with reopened._character_sampling_time() as seek:
            seek(10.)
            latest=tuple(tuple(cmds.xform(path,query=True,worldSpace=True,matrix=True))
                         for path in registered.spine.body_joints[1:])
        checks['reopened_spine_animation']=(reopened.capture_character_key_state(registered)==after
            and all(max(abs(a-b) for a,b in zip(actual,wanted))<1e-4
                    for actual,wanted in zip(latest,spine_samples[-1].body_matrices)))
        payload={**checks,'max_spine_error':max(errors),'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
