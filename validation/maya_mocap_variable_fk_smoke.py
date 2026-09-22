"""Variable-spine FK retarget with a generated mapped joint take."""
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output,segments=4,with_hand=False,with_ik=False,with_fbx=False,with_full_ik=False,
         with_mixed=False,mixed_spine_ik=False,with_scheduled=False,
         with_replace=False):
    with_scheduled=with_scheduled or with_replace
    with_ik=with_ik or with_full_ik or with_mixed or with_scheduled
    output.parent.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds,mel
        from adv_py.adapters import MayaBodyBuildHost,MayaMocapControlHost,MayaMocapClipHost
        from adv_py.application import (CreateFitSkeleton,BuildVariableBodySourceFit,
            BuildOrientedBodySkeleton,BuildBodyCharacterRig,RegisterBodyCharacter,
            RetargetMocapVariableFullFkToCharacter,RetargetMocapVariableSplineIkToCharacter,
            RetargetMocapVariableFullIkToCharacter,EnableBodyCharacterSplineAnimation,
            RetargetMocapVariableMixedToCharacter,RetargetMocapVariableScheduledToCharacter,
            EnableBodyCharacterLimbAnimation,ImportMocapFbx)
        from adv_py.core.variable_body_fit import variable_axial_description
        from adv_py.core import MocapJointMapping,MocapMappingPreset

        cmds.file(new=True,force=True);cmds.undoInfo(state=True);cmds.upAxis(axis='z',rotateView=False)
        cmds.namespace(addNamespace='hero');built=MayaBodyBuildHost(namespace='hero')
        CreateFitSkeleton(built).apply()
        BuildVariableBodySourceFit(built).apply(spine_segments=segments,with_hand=with_hand)
        BuildOrientedBodySkeleton(built).apply()
        rig=BuildBodyCharacterRig(built).apply(include_torso=True,include_spine_ik=True,
            include_control_spaces=True,axial_description=variable_axial_description(segments))
        registration=RegisterBodyCharacter(built).apply(rig)
        if with_ik:registration=EnableBodyCharacterSplineAnimation(built).apply()
        if with_full_ik or with_mixed or with_scheduled:
            registration=EnableBodyCharacterLimbAnimation(built).apply()
        target={joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]:joint for joint in registration.body}
        spine=tuple(path.rsplit('|',1)[-1].rsplit(':',1)[-1]
                    for path in registration.spine.body_joints[1:])
        required={'Root_M',*spine,'Neck_M','Head_M','Scapula_R','Scapula_L'}
        required.update(part+'_'+side for side in ('R','L') for part in
            ('Shoulder','Elbow','Wrist','Hip','Knee','Ankle','Toes'))
        if with_hand:
            required.update(f'{digit}{segment}_{side}' for side in ('R','L')
                for digit in ('Thumb','Index','Middle','Ring','Pinky') for segment in (1,2,3))
        names={'Root_M':'Hips',**{name:name.removesuffix('_M') for name in spine}}
        names.update({name:name for name in required if name not in names})
        cmds.namespace(addNamespace='TakeA')
        source={}
        for joint in registration.body:
            name=joint.path.rsplit('|',1)[-1].rsplit(':',1)[-1]
            if name not in required:continue
            parent_name=None if joint.parent is None else joint.parent.rsplit('|',1)[-1].rsplit(':',1)[-1]
            parent=source.get(parent_name)
            source[name]=cmds.createNode('joint',name='TakeA:'+names[name],parent=parent,
                skipSelect=True)
            if parent is not None:cmds.setAttr(source[name]+'.translateX',2.)
        mappings=tuple(MocapJointMapping(names[name],name,name=='Root_M',True)
                       for name in source)
        preset=MocapMappingPreset('Generated variable full FK',mappings,len(registration.body))
        for frame,amount in ((1,0.),(5,1.),(10,2.)):
            cmds.setKeyframe(source['Root_M'],attribute='translateX',time=frame,value=amount*3.)
            for name,path in source.items():
                if name=='Root_M':continue
                value=((3. if segments<=4 else .3) if name in spine else 5.)*amount
                cmds.setKeyframe(path,attribute='rotateZ',time=frame,value=value)
        host=MayaMocapControlHost(namespace='hero')
        mixed_options=dict(spine_mode='ik' if mixed_spine_ik else 'fk',limb_modes={
            ('arm','R'):'ik',('arm','L'):'fk',('leg','R'):'fk',('leg','L'):'ik'})
        scheduled_options=dict(spine_events=((1,'fk'),(5,'ik'),(8,'fk')),
            limb_events={('arm','R'):((1,'fk'),(3,'ik'),(7,'fk')),
                         ('arm','L'):((1,'fk'),),
                         ('leg','R'):((1,'fk'),(6,'ik')),
                         ('leg','L'):((1,'fk'),)},
            replace_existing_modes=with_replace)
        invalid_mixed_rejected=True
        if with_mixed:
            try:RetargetMocapVariableMixedToCharacter(host,spine_mode='other',
                limb_modes=mixed_options['limb_modes'])
            except ValueError:pass
            else:invalid_mixed_rejected=False
            try:RetargetMocapVariableMixedToCharacter(host,spine_mode='fk',
                limb_modes={('arm','R'):'ik'})
            except ValueError:pass
            else:invalid_mixed_rejected=False
        service=(RetargetMocapVariableScheduledToCharacter(host,**scheduled_options)
                 if with_scheduled else
                 RetargetMocapVariableMixedToCharacter(host,**mixed_options) if with_mixed else
                 RetargetMocapVariableFullIkToCharacter(host) if with_full_ik else
                 RetargetMocapVariableSplineIkToCharacter(host) if with_ik else
                 RetargetMocapVariableFullFkToCharacter(host))
        old_channel=next(row for row in registration.channels if row.key=='leg.fk.ToesFK_R.rotateZ')
        for frame,value in ((0,1.),(20,4.)):
            host._cmds.setKeyframe(old_channel.node,attribute=old_channel.attribute,
                time=frame,value=value)
        options=dict(start_frame=1,end_frame=10)
        if with_scheduled:
            channels={channel.key:channel for channel in registration.channels}
            for key in ('spine.spline.spineIkFk','arm.settings.armIkFk_R'):
                channel=channels[key]
                for frame,value in ((0,1.),(1,0.),(10,0.),(11,1.),(20,1.)):
                    host._cmds.setKeyframe(channel.node,attribute=channel.attribute,
                        time=frame,value=value,outTangentType='step')
            if with_replace:
                for key,values in (
                    ('spine.spline.spineIkFk',((2,1.),(4,0.))),
                    ('arm.settings.armIkFk_R',((8,1.),(10,0.)))):
                    channel=channels[key]
                    for frame,value in values:
                        host._cmds.setKeyframe(channel.node,attribute=channel.attribute,
                            time=frame,value=value,outTangentType='step')
                strict_options={**scheduled_options,'replace_existing_modes':False}
                strict=RetargetMocapVariableScheduledToCharacter(host,**strict_options)
                try:strict.plan_with_preset(source['Root_M'],preset,**options)
                except ValueError:invalid_existing_mode_rejected=True
                else:invalid_existing_mode_rejected=False
                channel=channels['spine.spline.spineIkFk']
                host._cmds.setKeyframe(channel.node,attribute=channel.attribute,
                    time=5,value=.5,outTangentType='step')
                fractional_before=host.capture_character_key_state(registration)
                try:service.plan_with_preset(source['Root_M'],preset,**options)
                except ValueError:
                    fractional_mode_rejected=(host.capture_character_key_state(
                        registration)==fractional_before)
                else:fractional_mode_rejected=False
                cmds.cutKey(host.scene_address(channel.node),
                    attribute=channel.attribute,time=(5,5))
            else:
                channel=channels['spine.spline.spineIkFk']
                host._cmds.setKeyframe(channel.node,attribute=channel.attribute,
                    time=5,value=1.,outTangentType='step')
                try:service.plan_with_preset(source['Root_M'],preset,**options)
                except ValueError:invalid_existing_mode_rejected=True
                else:invalid_existing_mode_rejected=False
                cmds.cutKey(host.scene_address(channel.node),
                    attribute=channel.attribute,time=(5,5))
        imported=None
        if with_fbx:
            if not cmds.pluginInfo('fbxmaya',query=True,loaded=True):
                cmds.loadPlugin('fbxmaya',quiet=True)
            with tempfile.TemporaryDirectory(prefix='advpy-variable-mocap-') as directory:
                fbx=Path(directory)/'variable_take.fbx'
                cmds.select(source['Root_M'],replace=True)
                mel.eval('FBXResetExport;')
                mel.eval('FBXExportBakeComplexAnimation -v false;')
                mel.eval('FBXExportInputConnections -v false;')
                mel.eval('FBXExportConstraints -v false;')
                cmds.file(str(fbx),force=True,options='v=0;',type='FBX export',exportSelected=True)
                imported=ImportMocapFbx(MayaMocapClipHost()).apply(fbx,namespace='ExternalTake')
        root=imported.snapshot.root if imported else source['Root_M']
        before=host.capture_character_key_state(registration)
        if with_scheduled:
            def outside_tangents(key):
                channel=channels[key]
                plug=host.scene_address(channel.node)+'.'+channel.attribute
                return tuple((tuple(cmds.keyTangent(plug,query=True,time=(frame,frame),
                    inTangentType=True) or []),
                    tuple(cmds.keyTangent(plug,query=True,time=(frame,frame),
                    outTangentType=True) or [])) for frame in (0,11,20))
            original_mode_tangents={key:outside_tangents(key)
                for key in ('spine.spline.spineIkFk','arm.settings.armIkFk_R')}
        plan=service.plan_with_preset(root,preset,**options)
        group_plans=plan.full_fk.groups if with_scheduled else plan.groups
        class FailedHost(MayaMocapControlHost):
            calls=0
            def write_mocap_fk_group_keys(self,plan):
                result=super().write_mocap_fk_group_keys(plan)
                self.calls+=1
                if self.calls==4:raise RuntimeError('Injected variable group failure')
                return result
        failing=(RetargetMocapVariableScheduledToCharacter(
            FailedHost(namespace='hero'),**scheduled_options) if with_scheduled else
            RetargetMocapVariableMixedToCharacter(FailedHost(namespace='hero'),**mixed_options)
            if with_mixed else RetargetMocapVariableFullIkToCharacter(FailedHost(namespace='hero'))
            if with_full_ik else RetargetMocapVariableSplineIkToCharacter(FailedHost(namespace='hero'))
            if with_ik else RetargetMocapVariableFullFkToCharacter(FailedHost(namespace='hero')))
        try:failing.apply_with_preset(
            root,preset,**options)
        except RuntimeError as exc:
            if 'Injected variable group failure' not in str(exc):raise
            rollback=host.capture_character_key_state(registration)==before
        else:rollback=False
        spine_rollback=True
        if with_ik and not (with_mixed or with_scheduled) and not with_fbx and segments==4 and not with_hand:
            class FailedSpineHost(MayaMocapControlHost):
                def match_character_spine_samples(self,*args,**kwargs):
                    super().match_character_spine_samples(*args,**kwargs)
                    raise RuntimeError('Injected variable spline failure')
            failed_spine=(RetargetMocapVariableFullIkToCharacter(FailedSpineHost(namespace='hero'))
                if with_full_ik else RetargetMocapVariableSplineIkToCharacter(FailedSpineHost(namespace='hero')))
            try:failed_spine.apply_with_preset(root,preset,**options)
            except RuntimeError as exc:
                if 'Injected variable spline failure' not in str(exc):raise
                spine_rollback=host.capture_character_key_state(registration)==before
            else:spine_rollback=False
        limb_rollback=True
        if with_full_ik or with_mixed or with_scheduled:
            class FailedLimbHost(MayaMocapControlHost):
                calls=0
                def match_character_limb_samples(self,*args,**kwargs):
                    result=super().match_character_limb_samples(*args,**kwargs)
                    self.calls+=1
                    if self.calls==(2 if with_mixed or with_scheduled else 3):
                        raise RuntimeError('Injected variable limb failure')
                    return result
            failing_limb=(RetargetMocapVariableScheduledToCharacter(
                FailedLimbHost(namespace='hero'),**scheduled_options)
                if with_scheduled else RetargetMocapVariableMixedToCharacter(
                FailedLimbHost(namespace='hero'),**mixed_options) if with_mixed else
                RetargetMocapVariableFullIkToCharacter(FailedLimbHost(namespace='hero')))
            try:failing_limb.apply_with_preset(root,preset,**options)
            except RuntimeError as exc:
                if 'Injected variable limb failure' not in str(exc):raise
                limb_rollback=host.capture_character_key_state(registration)==before
            else:limb_rollback=False
        unfit_rejected=True
        if with_ik and not (with_mixed or with_scheduled) and segments>=8 and not with_fbx:
            for name in spine:
                for frame,value in ((5,3.),(10,6.)):
                    cmds.setKeyframe(source[name],attribute='rotateZ',time=frame,value=value)
            try:service.apply_with_preset(root,preset,**options)
            except ValueError:
                unfit_rejected=host.capture_character_key_state(registration)==before
            else:unfit_rejected=False
            for name in spine:
                for frame,value in ((5,.3),(10,.6)):
                    cmds.setKeyframe(source[name],attribute='rotateZ',time=frame,value=value)
        if with_scheduled:
            roots,groups,scheduled_conversions=service.apply_with_preset(root,preset,**options)
            conversion=next((row[2] for row in scheduled_conversions if row[0]=='spine'),None)
            limb_conversions=tuple(row[2] for row in scheduled_conversions if row[0]!='spine')
        elif with_full_ik or with_mixed:
            roots,groups,conversion,limb_conversions=service.apply_with_preset(root,preset,**options)
        elif with_ik:
            roots,groups,conversion=service.apply_with_preset(root,preset,**options)
            limb_conversions=()
        else:
            roots,groups=service.apply_with_preset(root,preset,**options)
            conversion=None;limb_conversions=()
        after=host.capture_character_key_state(registration)
        if with_scheduled:
            original_rows={row[0]:row for row in before[1]}
            applied_rows={row[0]:row for row in after[1]}
            def outside_keys(key):
                old=original_rows[key];new=applied_rows[key]
                old_values=dict(zip(old[2],old[3]))
                new_values=dict(zip(new[2],new[3]))
                return all(new_values.get(frame)==old_values[frame]
                    for frame in (0.,11.,20.))
            existing_mode_keys_preserved=all(outside_keys(key)
                for key in ('spine.spline.spineIkFk','arm.settings.armIkFk_R'))
        with host._character_sampling_time() as seek:
            errors=[]
            for group_plan,samples in zip(group_plans,groups):
                for sample in samples:
                    seek(sample.frame)
                    for path,wanted in zip(group_plan.target_joints,sample.body_matrices):
                        actual=cmds.xform(host.scene_address(path),query=True,worldSpace=True,matrix=True)
                        errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        checks={'expected_joint_count':len(registration.body)==(segments+28+(40 if with_hand else 0)),
            'external_fbx_joint_count':not with_fbx or len(imported.clip.joints)==len(required),
            'all_groups_written':len(roots)==10 and len(groups)==7
                and all(len(group)==10 for group in groups),
            'body_pose_matches':max(errors)<(1e-3 if with_full_ik or with_mixed or with_scheduled else 1e-4),
            'spline_ik_mode':with_scheduled or not with_ik or (
                (conversion is not None)==(mixed_spine_ik if with_mixed else True)
                and all(abs(cmds.getAttr(host.scene_address(registration.spine.settings)+
                    '.spineIkFk',time=frame)-
                    (float(mixed_spine_ik) if with_mixed else 1.))<1e-8
                    for frame in range(1,11))),
            'four_limb_ik_modes':with_scheduled or not (with_full_ik or with_mixed) or (
                len(limb_conversions)==(2 if with_mixed else 4) and all(
                abs(cmds.getAttr(host.scene_address(next(ch for ch in registration.channels if ch.key==
                    f'{limb}.settings.{limb}IkFk_{side}').node)+'.'+
                    f'{limb}IkFk_{side}',time=frame)-
                    (float(mixed_options['limb_modes'][(limb,side)]=='ik') if with_mixed else 1.))<1e-8
                for limb in ('arm','leg') for side in ('R','L') for frame in range(1,11))),
            'group_failure_rolls_back':rollback,
            'spline_conversion_failure_rolls_back':spine_rollback,
            'limb_conversion_failure_rolls_back':limb_rollback}
        if with_scheduled:
            checks['existing_mode_keys_outside_preserved']=existing_mode_keys_preserved
            checks['existing_mode_tangents_outside_preserved']=all(
                outside_tangents(key)==original_mode_tangents[key]
                for key in original_mode_tangents)
            checks['existing_ik_inside_range_rejected']=invalid_existing_mode_rejected
            checks['explicit_existing_ik_replacement']=not with_replace or (
                plan.replace_existing_modes and
                any(abs(value-1.)<1e-8 for row in before[1]
                    if row[0] in ('spine.spline.spineIkFk','arm.settings.armIkFk_R')
                    for value in row[3]))
            checks['fractional_existing_mode_rejected']=not with_replace or fractional_mode_rejected
            mode_channels={ch.key:ch for ch in registration.channels}
            def mode_at(key,frame):
                ch=mode_channels[key]
                return float(cmds.getAttr(host.scene_address(ch.node)+'.'+ch.attribute,time=frame))
            checks['scheduled_spine_modes']=all(mode_at('spine.spline.spineIkFk',frame)==
                float(5<=frame<8) for frame in range(1,11))
            checks['scheduled_arm_modes']=all(mode_at('arm.settings.armIkFk_R',frame)==
                float(3<=frame<7) and mode_at('arm.settings.armIkFk_L',frame)==0.
                for frame in range(1,11))
            checks['scheduled_leg_modes']=all(mode_at('leg.settings.legIkFk_R',frame)==
                float(frame>=6) and mode_at('leg.settings.legIkFk_L',frame)==0.
                for frame in range(1,11))
            checks['outside_modes_restored']=(all(mode_at(key,frame)==1.
                for key in ('spine.spline.spineIkFk','arm.settings.armIkFk_R')
                for frame in (0,11,20))
                and all(mode_at('leg.settings.legIkFk_R',frame)==0.
                    for frame in (0,11)))
            checks['step_switches_between_frames']=(
                mode_at('spine.spline.spineIkFk',4.5)==0.
                and mode_at('spine.spline.spineIkFk',7.5)==1.
                and mode_at('arm.settings.armIkFk_R',6.5)==1.)
        checks['invalid_mixed_policy_rejected']=invalid_mixed_rejected
        old_curve=dict(zip(host._cmds.keyframe(old_channel.node,
            attribute=old_channel.attribute,query=True,timeChange=True) or [],
            host._cmds.keyframe(old_channel.node,attribute=old_channel.attribute,
                query=True,valueChange=True) or []))
        checks['outside_keys_preserved']=all(abs(old_curve.get(frame,float('inf'))-value)<1e-8
            for frame,value in ((0.,1.),(20.,4.)))
        checks['unfit_spline_rejected_without_character_edits']=unfit_rejected
        cmds.undo();checks['single_undo_restores_character']=host.capture_character_key_state(registration)==before
        if with_fbx:
            checks['retarget_undo_keeps_import']=bool(cmds.ls(root,long=True,type='joint'))
            cmds.undo()
            checks['import_undo_keeps_character']=(not cmds.ls(root,long=True)
                and host.read_character_registration()==registration)
            cmds.redo()
        cmds.redo();checks['single_redo_restores_character']=host.capture_character_key_state(registration)==after
        scene=output.with_suffix('.ma');cmds.file(rename=str(scene))
        cmds.file(save=True,type='mayaAscii',force=True);cmds.file(str(scene),open=True,force=True)
        reopened=MayaMocapControlHost(namespace='hero');reopened_reg=reopened.read_character_registration()
        reopened_keys=reopened.capture_character_key_state(reopened_reg)
        checks['reopened_keys']=(abs(reopened_keys[0]-after[0])<1e-8
            and len(reopened_keys[1])==len(after[1])
            and all(a[:3]==b[:3] and len(a[3])==len(b[3])
                and all(abs(x-y)<1e-8 for x,y in zip(a[3],b[3]))
                for a,b in zip(reopened_keys[1],after[1])))
        with reopened._character_sampling_time() as seek:
            seek(10.)
            reopened_error=max(abs(a-b) for group_plan,samples in zip(group_plans,groups)
                for path,wanted in zip(group_plan.target_joints,samples[-1].body_matrices)
                for a,b in zip(cmds.xform(reopened.scene_address(path),query=True,
                    worldSpace=True,matrix=True),wanted))
        checks['reopened_pose']=reopened_error<(1e-3 if with_full_ik or with_mixed or with_scheduled else 1e-4)
        if with_scheduled:
            checks['reopened_schedule_modes']=(
                mode_at('spine.spline.spineIkFk',4.5)==0.
                and mode_at('spine.spline.spineIkFk',5.)==1.
                and mode_at('spine.spline.spineIkFk',8.)==0.
                and mode_at('leg.settings.legIkFk_R',6.)==1.
                and mode_at('leg.settings.legIkFk_R',11.)==0.
                and mode_at('spine.spline.spineIkFk',11.)==1.)
        payload={**checks,'segments':segments,'joint_count':len(registration.body),
                 'max_body_error':max(errors),'reopened_body_error':reopened_error,
                 'mixed_modes':with_mixed,
                 'mixed_spine_ik':mixed_spine_ik,
                 'scheduled_modes':with_scheduled,
                 'replace_existing_modes':with_replace,
                 'status':'passed' if all(checks.values()) else 'failed'}
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve(),
    int(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2].isdigit() else 4,
    '--hand' in sys.argv[2:],'--ik' in sys.argv[2:],'--fbx' in sys.argv[2:],
    '--full-ik' in sys.argv[2:],'--mixed' in sys.argv[2:],
    '--mixed-spine-ik' in sys.argv[2:],'--scheduled' in sys.argv[2:],
    '--scheduled-replace' in sys.argv[2:]))
