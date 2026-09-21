"""Atomic FK root, spine, two arms and two legs on generated characters."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output,with_hand,with_upper=False):
    output.parent.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import build_character
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import (RegisterBodyCharacter,RetargetMocapFourLimbsToCharacter,
            RetargetMocapUpperAndFourLimbsToCharacter,MocapLimbSource)
        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        built=build_character(with_hand=with_hand)
        registration=RegisterBodyCharacter(built.host).apply(built.rig)
        by_key={channel.key:channel for channel in registration.channels}
        animated=(by_key['global.translateY'],
                  next(channel for channel in registration.channels
                       if channel.node==registration.spine.fk_controls[1] and channel.attribute=='rotateZ'))
        animated+=tuple(by_key[f'{limb}.fk.{part}FK_{side}.rotateZ']
            for limb,part in (('arm','Shoulder'),('leg','Hip')) for side in ('R','L'))
        for index,channel in enumerate(animated):
            for frame,value in ((0,0.),(20,(index+1)*3.)):
                cmds.setKeyframe(channel.node,attribute=channel.attribute,time=frame,value=value)
        cmds.namespace(add='TakeA')
        root=cmds.createNode('joint',name='TakeA:Hips',skipSelect=True)
        spine=cmds.createNode('joint',name='TakeA:Spine',parent=root,skipSelect=True)
        chest=cmds.createNode('joint',name='TakeA:Chest',parent=spine,skipSelect=True)
        cmds.setAttr(spine+'.translateY',5.);cmds.setAttr(chest+'.translateY',5.)
        upper_nodes={}
        if with_upper:
            neck=cmds.createNode('joint',name='TakeA:Neck',parent=chest,skipSelect=True)
            head=cmds.createNode('joint',name='TakeA:Head',parent=neck,skipSelect=True)
            cmds.setAttr(neck+'.translateY',2.);cmds.setAttr(head+'.translateY',2.)
            upper_nodes.update(Neck=neck,Head=head)
            for side in ('R','L'):
                joint=cmds.createNode('joint',name='TakeA:Scapula_'+side,parent=chest,skipSelect=True)
                cmds.setAttr(joint+'.translateX',3. if side=='L' else -3.)
                upper_nodes['Scapula_'+side]=joint
        source_specs=[];source_chains=[]
        for limb,parts,attach in (('arm',('Shoulder','Elbow','Wrist'),chest),
                                  ('leg',('Hip','Knee','Ankle'),root)):
            for side in ('R','L'):
                parent=upper_nodes['Scapula_'+side] if with_upper and limb=='arm' else attach
                chain=[]
                for part in parts:
                    parent=cmds.createNode('joint',name='TakeA:'+part+'_'+side,parent=parent,skipSelect=True)
                    cmds.setAttr(parent+'.translateX',3.)
                    chain.append(parent)
                source_specs.append(MocapLimbSource(limb,side,*(part+'_'+side for part in parts)))
                source_chains.append(tuple(chain))
        for frame,travel,bend,amplitude in ((1,0.,0.,0.),(5,4.,8.,1.),(10,9.,17.,2.)):
            cmds.setKeyframe(root,attribute='translateX',time=frame,value=travel)
            cmds.setKeyframe(spine,attribute='rotateZ',time=frame,value=bend)
            cmds.setKeyframe(chest,attribute='rotateX',time=frame,value=bend*.5)
            if with_upper:
                for name,axis,value in (('Neck','Z',6.),('Head','X',-4.),
                                        ('Scapula_R','Y',7.),('Scapula_L','Y',-7.)):
                    cmds.setKeyframe(upper_nodes[name],attribute='rotate'+axis,time=frame,
                                     value=amplitude*value)
            for index,chain in enumerate(source_chains):
                sign=1. if index%2==0 else -1.
                for joint,axis,amount in zip(chain,('Z','Y','X'),(10.,-14.,7.)):
                    cmds.setKeyframe(joint,attribute='rotate'+axis,time=frame,
                                     value=sign*amplitude*amount)
        host=MayaMocapControlHost()
        before=host.capture_character_key_state(registration)
        options=dict(source_spine='Spine',source_chest='Chest',source_limbs=tuple(source_specs),
                     start_frame=1,end_frame=10)
        upper_options=dict(source_neck='Neck',source_head='Head',
                           source_scapula_right='Scapula_R',source_scapula_left='Scapula_L')
        service=(RetargetMocapUpperAndFourLimbsToCharacter(host) if with_upper
                 else RetargetMocapFourLimbsToCharacter(host))
        if with_upper:
            roots,spines,upper,limbs=service.apply('|TakeA:Hips',**options,**upper_options)
            complete_plan=service.plan('|TakeA:Hips',**options,**upper_options)
            plans=complete_plan.four_limbs.limbs
        else:
            roots,spines,limbs=service.apply('|TakeA:Hips',**options)
            upper=()
            plans=service.plan('|TakeA:Hips',**options).limbs
        after=host.capture_character_key_state(registration)
        with host._character_sampling_time() as seek:
            errors=[]
            if with_upper:
                for sample in upper:
                    seek(sample.frame)
                    for joint,wanted in zip(complete_plan.target_joints,sample.body_matrices):
                        actual=cmds.xform(joint,query=True,worldSpace=True,matrix=True)
                        errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
            for limb_plan,samples in zip(plans,limbs):
                for sample in samples:
                    seek(sample.frame)
                    for joint,wanted in zip(limb_plan.target_joints,sample.body_matrices):
                        actual=cmds.xform(joint,query=True,worldSpace=True,matrix=True)
                        errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        owned={channel.key for channel in registration.channels if channel.key.startswith('global.')
               or channel.node in registration.spine.fk_controls[1:]
               or channel.key.startswith(('arm.fk.','leg.fk.'))
               or (with_upper and channel.key.startswith(('torso.TorsoNeck_MFK.',
                   'torso.TorsoHead_MFK.','torso.TorsoScapula_RFK.','torso.TorsoScapula_LFK.')))}
        checks={
            'all_groups_have_ten_samples':len(roots)==len(spines)==10 and len(limbs)==4
                and all(len(group)==10 for group in limbs),
            'all_four_limb_poses_verified':max(errors)<1e-4,
            'upper_body_written':not with_upper or (len(upper)==10 and all(
                set(range(1,11)).issubset(set(cmds.keyframe(control+'.rotate'+axis,
                    query=True,timeChange=True) or []))
                for control in complete_plan.controls for axis in 'XYZ')),
            'all_fk_curves_written':all(set(range(1,11)).issubset(set(cmds.keyframe(
                control+'.rotate'+axis,query=True,timeChange=True) or []))
                for plan in plans for control in plan.controls for axis in 'XYZ'),
            'other_controls_unchanged':all(a==b for a,b in zip(before[1],after[1]) if a[0] not in owned),
            'outside_keys_preserved':all(all(time in dict(zip(new[2],new[3]))
                and abs(dict(zip(new[2],new[3]))[time]-value)<1e-8
                for time,value in zip(old[2],old[3]) if time<1. or time>10.)
                for old,new in zip(before[1],after[1]) if old[0] in owned),
        }
        class FailedHost(MayaMocapControlHost):
            calls=0
            def write_mocap_limb_control_keys(self,plan):
                result=super().write_mocap_limb_control_keys(plan)
                self.calls+=1
                if self.calls==3:raise RuntimeError('Injected third-limb failure')
                return result
        try:
            failing=(RetargetMocapUpperAndFourLimbsToCharacter(FailedHost()) if with_upper
                     else RetargetMocapFourLimbsToCharacter(FailedHost()))
            failing.apply('|TakeA:Hips',**options,**(upper_options if with_upper else {}))
        except RuntimeError as exc:
            if 'Injected' not in str(exc):raise
            checks['third_limb_failure_rolls_back']=host.capture_character_key_state(registration)==after
        else:checks['third_limb_failure_rolls_back']=False
        cmds.undo();checks['single_undo_restores_every_limb']=host.capture_character_key_state(registration)==before
        cmds.redo();checks['single_redo_restores_every_limb']=host.capture_character_key_state(registration)==after
        scene=output.parent/('mocap-upper-four-limbs-hand.ma' if with_upper and with_hand
            else 'mocap-upper-four-limbs-basic.ma' if with_upper
            else 'mocap-four-limbs-hand.ma' if with_hand else 'mocap-four-limbs-basic.ma')
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaAscii',force=True)
        cmds.file(str(scene),open=True,force=True)
        reopened=MayaMocapControlHost();reopened_registration=reopened.read_character_registration()
        reopened_keys=reopened.capture_character_key_state(reopened_registration)
        def keys_match(left,right):
            return (abs(left[0]-right[0])<1e-8 and len(left[1])==len(right[1])
                and all(a[:3]==b[:3] and len(a[3])==len(b[3])
                    and all(abs(x-y)<1e-8 for x,y in zip(a[3],b[3]))
                    for a,b in zip(left[1],right[1])))
        with reopened._character_sampling_time() as seek:
            seek(10.)
            reopened_pose=all(max(abs(a-b) for a,b in zip(
                cmds.xform(joint,query=True,worldSpace=True,matrix=True),wanted))<1e-4
                for plan,samples in zip(plans,limbs)
                for joint,wanted in zip(plan.target_joints,samples[-1].body_matrices))
            if with_upper:
                reopened_pose=reopened_pose and all(max(abs(a-b) for a,b in zip(
                    cmds.xform(joint,query=True,worldSpace=True,matrix=True),wanted))<1e-4
                    for joint,wanted in zip(complete_plan.target_joints,upper[-1].body_matrices))
        checks['reopened_animation']=keys_match(reopened_keys,after) and reopened_pose
        payload={**checks,'joint_count':len(registration.body),'max_body_error':max(errors),
            'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve(),
    '--hand' in sys.argv[2:],'--upper' in sys.argv[2:]))
