"""Two-process registered character pose / deformation acceptance."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(directory,phase,with_hand=True):
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (RegisterBodyCharacter,ResolveBodyCharacter,CaptureBodyCharacterPose,
            ApplyBodyCharacterPose,SwitchBodyControlSpace,MatchBodySpine,save_character_pose,load_character_pose)
        from adv_py.core.character_pose import character_pose_error
        def vertices(): return tuple(cmds.xform('|AdvPy_CharacterProxy.vtx[*]',q=True,ws=True,t=True))
        def error(a,b): return max(abs(x-y) for x,y in zip(a,b))
        def set_value(registration,key,value):
            channel=next(c for c in registration.channels if c.key==key)
            cmds.setAttr(channel.node+'.'+channel.attribute,value)
        checks={}
        if phase=='write':
            from maya_complete_character import build_character
            cmds.upAxis(axis='z',rotateView=False);cmds.undoInfo(state=True)
            demo=build_character(with_hand=with_hand)
            host=demo.host;registration=RegisterBodyCharacter(host).apply(demo.rig)
            for c in registration.channels:
                value=None
                if c.key=='global.translateX': value=3
                elif c.key=='global.rotateZ': value=20
                elif c.key=='global.globalScale': value=1.3
                elif c.key.endswith('rotateZ') and any(token in c.key for token in ('Waist','Spine1','Elbow','Knee')): value=12
                elif c.key.startswith('torso.') and 'Head' in c.key and c.attribute=='rotateY': value=14
                elif c.key.startswith('hand.fk.') and 'Index1' in c.key and c.attribute=='rotateZ': value=18
                elif c.key.startswith('hand.') and c.attribute=='handCurl': value=8
                elif c.key=='arm.settings.armIkFk_R' or c.key=='leg.settings.legIkFk_L': value=1
                elif c.key.startswith(('arm.ik.','leg.ik.')) and c.attribute=='translateY': value=0.25
                elif c.key.startswith('foot.') and c.attribute=='footRoll': value=10
                if value is not None: cmds.setAttr(c.node+'.'+c.attribute,value)
            switch=SwitchBodyControlSpace(host)
            for key in ('head','hand_R','foot_L'):
                switch.execute(registration.spaces,key,'global' if key=='head' else 'body')
            pose=CaptureBodyCharacterPose(host).execute()
            original_vertices=vertices()
            save_character_pose(pose,directory/'target.pose.json')
            (directory/'vertices.json').write_text(json.dumps(original_vertices),encoding='utf-8')
            # Perturb every declared user channel so a forgotten write cannot
            # pass merely because that control happened to retain its target value.
            for channel,(_,value) in zip(registration.channels,pose.channels):
                changed=value+0.125
                if channel.maximum is not None and changed>channel.maximum:
                    changed=value-0.125
                if channel.minimum is not None:
                    changed=max(channel.minimum,changed)
                cmds.setAttr(channel.node+'.'+channel.attribute,changed)
            changed_pose=CaptureBodyCharacterPose(host).execute()
            checks['every_declared_control_perturbed']=all(abs(a-b)>1e-6 for (_,a),(_,b) in zip(pose.channels,changed_pose.channels))
            set_value(registration,'global.translateX',-2)
            set_value(registration,'global.globalScale',0.9)
            cmds.setAttr(registration.spine.fk_controls[1]+'.rotateZ',-22)
            for spec in registration.spaces.spaces:
                switch.execute(registration.spaces,spec.key,'global' if dict(pose.spaces)[spec.key]=='body' else 'body')
            checks['perturbed_mesh_differs']=error(original_vertices,vertices())>0.1
            cmds.file(rename=str(directory/'character.ma'));cmds.file(save=True,type='mayaAscii',force=True)
        else:
            cmds.file(str(directory/'character.ma'),open=True,force=True);cmds.undoInfo(state=True)
            host=MayaBodyBuildHost();registration=ResolveBodyCharacter(host).execute()
            pose=load_character_pose(directory/'target.pose.json')
            original_vertices=json.loads((directory/'vertices.json').read_text(encoding='utf-8'))
            capture=CaptureBodyCharacterPose(host);apply=ApplyBodyCharacterPose(host)
            before=capture.execute();before_vertices=vertices()
            marker=cmds.createNode('transform',name='PoseSelection',skipSelect=True);cmds.select(marker)
            cmds.currentTime(7)
            cmds.file(modified=False)
            undo_name=cmds.undoInfo(q=True,undoName=True)
            preview=apply.plan(pose)
            checks['plan_read_only']=not cmds.file(q=True,modified=True) and cmds.undoInfo(q=True,undoName=True)==undo_name
            result=apply.apply(pose)
            pose_error=character_pose_error(pose,result);mesh_error=error(original_vertices,vertices())
            checks['restores_body_controls_spaces_and_skin']=max(pose_error,mesh_error)<1e-4
            cmds.undo()
            checks['one_undo_restores_prior_pose_and_mesh']=character_pose_error(before,capture.execute())<1e-4 and error(before_vertices,vertices())<1e-4
            cmds.redo()
            checks['redo_restores_target_pose_and_mesh']=character_pose_error(pose,capture.execute())<1e-4 and error(original_vertices,vertices())<1e-4
            target=registration.channels[0];plug=target.node+'.'+target.attribute
            cmds.setAttr(plug,lock=True)
            try:
                apply.apply(before);checks['locked_channel_rejected']=False
            except ValueError: checks['locked_channel_rejected']=error(original_vertices,vertices())<1e-4
            cmds.setAttr(plug,lock=False)
            class FailedHost(MayaBodyBuildHost):
                def write_character_pose(self,registration,pose):
                    super().write_character_pose(registration,pose)
                    raise RuntimeError('Injected pose write failure')
            try:
                ApplyBodyCharacterPose(FailedHost()).apply(before);checks['failed_apply_rolls_back']=False
            except RuntimeError as exc:
                if 'Injected' not in str(exc): raise
                checks['failed_apply_rolls_back']=character_pose_error(pose,capture.execute())<1e-4 and error(original_vertices,vertices())<1e-4
            # A tampered result reference passes syntactic parsing but must fail
            # actual scene readback and roll the entire change back.
            from dataclasses import replace
            key,matrix=before.body_frames[0]
            corrupt_matrix=list(matrix);corrupt_matrix[12]+=1
            corrupt=replace(before,body_frames=((key,tuple(corrupt_matrix)),)+before.body_frames[1:])
            try:
                apply.apply(corrupt);checks['readback_failure_rolls_back']=False
            except RuntimeError:
                checks['readback_failure_rolls_back']=character_pose_error(pose,capture.execute())<1e-4 and error(original_vertices,vertices())<1e-4
            before_nodes=set(cmds.ls(long=True))
            try:
                apply.apply(replace(pose,compatibility='0'*64));checks['incompatible_layout_rejected']=False
            except ValueError:
                checks['incompatible_layout_rejected']=before_nodes==set(cmds.ls(long=True)) and error(original_vertices,vertices())<1e-4
            previous_layers=set(cmds.ls(type='animLayer') or [])
            layer=cmds.animLayer('UnsupportedPoseLayer')
            try:
                apply.apply(before);checks['animation_layer_rejected']=False
            except ValueError: checks['animation_layer_rejected']=error(original_vertices,vertices())<1e-4
            cmds.delete(list(set(cmds.ls(type='animLayer') or [])-previous_layers))
            cmds.setKeyframe(plug,time=7,value=cmds.getAttr(plug))
            anim=cmds.listConnections(plug,s=True,d=False,type='animCurve') or []
            keys=cmds.keyframe(plug,q=True,valueChange=True)
            try:
                apply.apply(before);checks['animation_input_preserved_and_rejected']=False
            except ValueError:
                checks['animation_input_preserved_and_rejected']=bool(anim) and cmds.keyframe(plug,q=True,valueChange=True)==keys and error(original_vertices,vertices())<1e-4
            cmds.undo()
            operational_before=vertices()
            MatchBodySpine(host).execute(registration.spine,'ik')
            MatchBodySpine(host).execute(registration.spine,'fk')
            switch=SwitchBodyControlSpace(host)
            for spec in registration.spaces.spaces:
                switch.execute(registration.spaces,spec.key,'global' if dict(pose.spaces)[spec.key]=='body' else 'body')
            operation_error=error(operational_before,vertices())
            checks['reopened_pose_supports_spine_and_space_operations']=operation_error<1e-4
            apply.apply(pose)
            checks['can_reapply_after_matching_and_rebinding']=character_pose_error(pose,capture.execute())<1e-4 and error(original_vertices,vertices())<1e-4
            checks['selection_and_time_preserved']=cmds.ls(sl=True)==[marker] and cmds.currentTime(q=True)==7
            report_errors={'max_pose_error':pose_error,'max_mesh_error':mesh_error,'max_operational_mesh_error':operation_error}
        report={'phase':phase,'body_joint_count':len(registration.body),**checks,**(report_errors if phase=='read' else {}),'status':'passed' if all(checks.values()) else 'failed'}
        (directory/(phase+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally: maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]),sys.argv[2],with_hand='--basic' not in sys.argv[3:]))
