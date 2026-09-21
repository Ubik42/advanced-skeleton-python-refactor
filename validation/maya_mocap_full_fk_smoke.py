"""Generated 21/51-joint mocap into the registered standard FK body."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output,with_hand=False,with_ik=False):
    output.parent.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import build_character
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import (RegisterBodyCharacter,RetargetMocapFullFkToCharacter,
            RetargetMocapFullLimbIkToCharacter,EnableBodyCharacterLimbAnimation,MocapLimbSource)
        from adv_py.core import MocapJointMapping,MocapMappingPreset

        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        built=build_character(with_hand=with_hand)
        registration=RegisterBodyCharacter(built.host).apply(built.rig)
        cmds.namespace(add='TakeA')
        def joint(name,parent=None,offset=(0.,0.,0.)):
            path=cmds.createNode('joint',name='TakeA:'+name,parent=parent,skipSelect=True)
            for axis,value in zip('XYZ',offset):cmds.setAttr(path+'.translate'+axis,value)
            return path
        root=joint('Hips');spine=joint('Spine',root,(0.,5.,0.))
        chest=joint('Chest',spine,(0.,5.,0.))
        neck=joint('Neck',chest,(0.,2.,0.));joint('Head',neck,(0.,2.,0.))
        source={'Hips':root,'Spine':spine,'Chest':chest}
        for name in ('Neck','Head'):source[name]=cmds.ls('TakeA:'+name,long=True,type='joint')[0]
        specs=[];distal={};animated=[]
        for side in ('R','L'):
            scapula=joint('Scapula_'+side,chest,(-3. if side=='R' else 3.,0.,0.))
            source['Scapula_'+side]=scapula
            for limb,parts,attach in (('arm',('Shoulder','Elbow','Wrist'),scapula),
                                      ('leg',('Hip','Knee','Ankle'),root)):
                parent=attach
                for part in parts:
                    name=part+'_'+side
                    parent=joint(name,parent,(3.,0.,0.));source[name]=parent
                    animated.append((parent,'rotateZ',5. if side=='R' else -5.))
                specs.append(MocapLimbSource(limb,side,*(part+'_'+side for part in parts)))
                if limb=='leg':
                    name='Toes_'+side;toe=joint(name,parent,(1.,0.,0.))
                    source[name]=toe;distal[name]=name
                    animated.append((toe,'rotateY',12. if side=='R' else -12.))
                elif with_hand:
                    for digit in ('Thumb','Index','Middle','Ring','Pinky'):
                        parent_finger=parent
                        for segment in (1,2,3):
                            name=f'{digit}{segment}_{side}'
                            parent_finger=joint(name,parent_finger,(.4,0.,.3))
                            source[name]=parent_finger;distal[name]=name
                            animated.append((parent_finger,'rotateY',segment*(3. if side=='R' else -3.)))
        for frame,amount in ((1,0.),(5,1.),(10,2.)):
            cmds.setKeyframe(root,attribute='translateX',time=frame,value=amount*4.)
            for name,axis,value in (('Spine','Z',8.),('Chest','X',5.),('Neck','Z',6.),
                                    ('Head','X',-4.),('Scapula_R','Y',7.),('Scapula_L','Y',-7.)):
                cmds.setKeyframe(source[name],attribute='rotate'+axis,time=frame,value=amount*value)
            for path,attribute,value in animated:
                cmds.setKeyframe(path,attribute=attribute,time=frame,value=amount*value)
        host=MayaMocapControlHost()
        if with_ik:registration=EnableBodyCharacterLimbAnimation(host).apply()
        service=(RetargetMocapFullLimbIkToCharacter(host) if with_ik else
                 RetargetMocapFullFkToCharacter(host))
        channels={row.key:row for row in registration.channels}
        old_keys=(channels['leg.fk.ToesFK_R.rotateZ'],)
        if with_hand:
            old_keys+=(channels['hand.fk.Index1FK_R.rotateZ'],)
            hand_pose=channels['hand.R.handCurl']
            cmds.setKeyframe(hand_pose.node,attribute=hand_pose.attribute,time=0,value=0.)
            cmds.setKeyframe(hand_pose.node,attribute=hand_pose.attribute,time=20,value=12.)
        for index,row in enumerate(old_keys):
            for frame in (0,20):
                cmds.setKeyframe(row.node,attribute=row.attribute,time=frame,
                    value=(index+1)*(frame+1))
        mappings=[MocapJointMapping('Hips','Root_M',True,True)]
        mappings.extend((MocapJointMapping('Spine','Spine1_M'),MocapJointMapping('Chest','Chest_M'),
            MocapJointMapping('Neck','Neck_M'),MocapJointMapping('Head','Head_M')))
        mappings.extend(MocapJointMapping(name,name) for name in source if name not in
            ('Hips','Spine','Chest','Neck','Head'))
        preset=MocapMappingPreset('Generated full FK mapping',tuple(mappings),len(registration.body))
        options=dict(start_frame=1,end_frame=10)
        before=host.capture_character_key_state(registration)
        plan=service.plan_with_preset(root,preset,**options)
        class FailedHost(MayaMocapControlHost):
            def write_mocap_distal_control_keys(self,plan):
                super().write_mocap_distal_control_keys(plan)
                raise RuntimeError('Injected distal failure')
        failure_service=(RetargetMocapFullLimbIkToCharacter(FailedHost()) if with_ik else
                         RetargetMocapFullFkToCharacter(FailedHost()))
        try:failure_service.apply_with_preset(root,preset,**options)
        except RuntimeError as exc:
            if 'Injected distal failure' not in str(exc):raise
            distal_rollback=host.capture_character_key_state(registration)==before
        else:distal_rollback=False
        conversion_rollback=True
        if with_ik:
            class FailedConversionHost(MayaMocapControlHost):
                calls=0
                def match_character_limb_samples(self,*args,**kwargs):
                    result=super().match_character_limb_samples(*args,**kwargs)
                    self.calls+=1
                    if self.calls==3:raise RuntimeError('Injected third IK conversion failure')
                    return result
            try:RetargetMocapFullLimbIkToCharacter(FailedConversionHost()).apply_with_preset(
                root,preset,**options)
            except RuntimeError as exc:
                if 'Injected third IK conversion failure' not in str(exc):raise
                conversion_rollback=host.capture_character_key_state(registration)==before
            else:conversion_rollback=False
        if with_ik:
            roots,spines,uppers,limbs,distals,conversions=service.apply_with_preset(root,preset,**options)
        else:
            roots,spines,uppers,limbs,distals=service.apply_with_preset(root,preset,**options)
            conversions=()
        after=host.capture_character_key_state(registration)
        with host._character_sampling_time() as seek:
            errors=[]
            for sample in distals:
                seek(sample.frame)
                for path,wanted in zip(plan.target_joints,sample.body_matrices):
                    actual=cmds.xform(path,query=True,worldSpace=True,matrix=True)
                    errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        checks={
            'all_groups_have_ten_samples':len(roots)==len(spines)==len(uppers)==len(distals)==10
                and len(limbs)==4 and all(len(group)==10 for group in limbs),
            'all_distal_controls_written':all(set(range(1,11)).issubset(set(
                cmds.keyframe(control+'.rotate'+axis,query=True,timeChange=True) or []))
                for control in plan.controls for axis in 'XYZ'),
            'distal_body_pose_matches':max(errors)<(1e-3 if with_ik else 1e-4),
            'expected_source_and_target_count':len(plan.controls)==(32 if with_hand else 2),
            'all_limb_modes_ik':not with_ik or (len(conversions)==4 and all(
                abs(cmds.getAttr(next(ch for ch in registration.channels if ch.key==
                    f'{limb}.settings.{limb}IkFk_{side}').node+'.'+
                    f'{limb}IkFk_{side}',time=frame)-1.)<1e-8
                for limb in ('arm','leg') for side in ('R','L') for frame in range(1,11))),
            'outside_keys_preserved':all(all(time in (cmds.keyframe(row.node+'.'+row.attribute,
                query=True,timeChange=True) or []) for time in (0.,20.)) for row in old_keys),
            'distal_failure_rolls_back':distal_rollback,
            'ik_conversion_failure_rolls_back':conversion_rollback,
        }
        try:service.apply_with_preset(root,MocapMappingPreset('Incomplete',preset.mappings[:-1],
            len(registration.body)),**options)
        except ValueError:checks['incomplete_preset_rejected']=host.capture_character_key_state(registration)==after
        else:checks['incomplete_preset_rejected']=False
        cmds.undo();checks['single_undo_restores_character']=host.capture_character_key_state(registration)==before
        cmds.redo();checks['single_redo_restores_character']=host.capture_character_key_state(registration)==after
        scene=output.with_suffix('.ma')
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaAscii',force=True)
        cmds.file(str(scene),open=True,force=True)
        reopened=MayaMocapControlHost();reopened_reg=reopened.read_character_registration()
        reopened_keys=reopened.capture_character_key_state(reopened_reg)
        checks['reopened_keys']=(abs(reopened_keys[0]-after[0])<1e-8
            and len(reopened_keys[1])==len(after[1])
            and all(a[:3]==b[:3] and len(a[3])==len(b[3])
                and all(abs(x-y)<1e-8 for x,y in zip(a[3],b[3]))
                for a,b in zip(reopened_keys[1],after[1])))
        with reopened._character_sampling_time() as seek:
            seek(10.)
            checks['reopened_distal_pose']=all(max(abs(a-b) for a,b in zip(
                    cmds.xform(path,query=True,worldSpace=True,matrix=True),wanted))<(1e-3 if with_ik else 1e-4)
                for path,wanted in zip(plan.target_joints,distals[-1].body_matrices))
        result={**checks,'joint_count':len(registration.body),'max_body_error':max(errors),
            'status':'passed' if all(checks.values()) else 'failed'}
        output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve(),
    '--hand' in sys.argv[2:],'--ik' in sys.argv[2:]))
