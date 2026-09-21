"""Transfer one generated FK arm or leg along with root and spine motion."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output,limb):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import build_character
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import RegisterBodyCharacter,RetargetMocapLimbToCharacter
        if limb not in ('arm','leg'):raise ValueError(limb)
        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        built=build_character(with_hand=False)
        registration=RegisterBodyCharacter(built.host).apply(built.rig)
        cmds.namespace(add='TakeA')
        root=cmds.createNode('joint',name='TakeA:Hips',skipSelect=True)
        spine=cmds.createNode('joint',name='TakeA:Spine',parent=root,skipSelect=True)
        chest=cmds.createNode('joint',name='TakeA:Chest',parent=spine,skipSelect=True)
        cmds.setAttr(spine+'.translateY',5.)
        cmds.setAttr(chest+'.translateY',5.)
        parts=('Shoulder','Elbow','Wrist') if limb=='arm' else ('Hip','Knee','Ankle')
        parent=chest if limb=='arm' else root
        source=[]
        for part in parts:
            parent=cmds.createNode('joint',name='TakeA:'+part,parent=parent,skipSelect=True)
            cmds.setAttr(parent+'.translateX',3.)
            source.append(parent)
        for frame,travel,bend,upper,middle,end in (
                (1,0.,0.,0.,0.,0.),(5,4.,8.,12.,-16.,9.),(10,9.,17.,25.,-30.,18.)):
            cmds.setKeyframe(root,attribute='translateX',time=frame,value=travel)
            cmds.setKeyframe(spine,attribute='rotateZ',time=frame,value=bend)
            for joint,axis,value in zip(source,('Z','Y','X'),(upper,middle,end)):
                cmds.setKeyframe(joint,attribute='rotate'+axis,time=frame,value=value)
        host=MayaMocapControlHost()
        before=host.capture_character_key_state(registration)
        options=dict(source_spine='Spine',source_chest='Chest',limb=limb,side='R',
            source_upper=parts[0],source_middle=parts[1],source_end=parts[2],
            start_frame=1,end_frame=10)
        roots,spines,limbs=RetargetMocapLimbToCharacter(host).apply('|TakeA:Hips',**options)
        after=host.capture_character_key_state(registration)
        with host._character_sampling_time() as seek:
            errors=[]
            for sample in limbs:
                seek(sample.frame)
                for joint,wanted in zip((next(j.path for j in registration.body if j.path.endswith(part+'_R'))
                    for part in parts),sample.body_matrices):
                    actual=cmds.xform(joint,query=True,worldSpace=True,matrix=True)
                    errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        changed={channel.key for channel in registration.channels if channel.key.startswith('global.')
                 or channel.node in registration.spine.fk_controls[1:]
                 or channel.key.startswith(limb+'.fk.')}
        checks={
            'ten_complete_samples':len(roots)==len(spines)==len(limbs)==10,
            'body_pose_verified':max(errors)<1e-4,
            'limb_control_motion':any(abs(value)>1. for value in limbs[-1].control_values),
            'other_control_curves_preserved':all(a==b for a,b in zip(before[1],after[1]) if a[0] not in changed),
        }
        cmds.undo();checks['single_undo']=host.capture_character_key_state(registration)==before
        cmds.redo();checks['single_redo']=host.capture_character_key_state(registration)==after
        payload={**checks,'limb':limb,'max_body_error':max(errors),
            'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve(),sys.argv[2]))
