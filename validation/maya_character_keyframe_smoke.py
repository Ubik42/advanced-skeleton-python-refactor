"""Whole-character current-frame keying; fixed control-space bindings."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(output,with_hand=True):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import build_character
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (RegisterBodyCharacter,ResolveBodyCharacter,CaptureBodyCharacterPose,
            KeyBodyCharacterPose,CaptureAnimatedBodyCharacterPose,ApplyBodyCharacterPose)
        from adv_py.core.character_pose import character_pose_error
        cmds.upAxis(axis='z',rotateView=False);cmds.undoInfo(state=True)
        demo=build_character(with_hand=with_hand);host=demo.host
        reg=RegisterBodyCharacter(host).apply(demo.rig)
        capture=CaptureBodyCharacterPose(host)
        def points(): return tuple(cmds.xform(demo.mesh+'.vtx[*]',q=True,ws=True,t=True))
        def error(a,b): return max(abs(x-y) for x,y in zip(a,b))
        def time(frame):
            cmds.undoInfo(stateWithoutFlush=False)
            try: cmds.currentTime(frame)
            finally: cmds.undoInfo(stateWithoutFlush=True)
        poses=[capture.execute()];meshes=[points()]
        for step in (1,2):
            for channel in reg.channels:
                value=None
                if channel.key=='global.translateX': value=step*2
                elif channel.key=='global.rotateZ': value=step*8
                elif channel.key=='global.globalScale': value=1+step*.1
                elif channel.attribute=='rotateZ' and any(s in channel.key for s in ('Spine1','Elbow','Knee','Index1')): value=step*10
                elif channel.attribute=='handCurl': value=step*4
                if value is not None: cmds.setAttr(channel.node+'.'+channel.attribute,value)
            poses.append(capture.execute());meshes.append(points())
        key=KeyBodyCharacterPose(host)
        time(1);key.apply(poses[0])
        time(20);key.apply(poses[2])
        time(10)
        animated=CaptureAnimatedBodyCharacterPose(host)
        before=animated.execute();before_mesh=points()
        marker=cmds.createNode('transform',name='KeySelection',skipSelect=True);cmds.select(marker)
        cmds.file(modified=False)
        preview=key.plan(poses[1]);checks={'plan_read_only':not cmds.file(q=True,modified=True)}
        result=key.apply(poses[1])
        pose_error=character_pose_error(poses[1],result);mesh_error=error(meshes[1],points())
        checks['keyed_body_and_skin_match']=max(pose_error,mesh_error)<1e-4
        checks['registry_accepts_native_animation']=ResolveBodyCharacter(host).execute()==reg
        cmds.undo()
        checks['undo_restores_interpolated_pose_and_mesh']=character_pose_error(before,animated.execute())<1e-4 and error(before_mesh,points())<1e-4
        cmds.redo()
        checks['redo_restores_keyed_pose']=character_pose_error(poses[1],animated.execute())<1e-4
        errors=[]
        for frame,pose,mesh in zip((1,10,20),poses,meshes):
            time(frame)
            errors.append(max(character_pose_error(pose,animated.execute()),error(mesh,points())))
        checks['all_three_key_frames_reproduce_body_and_mesh']=max(errors)<1e-4
        time(10)
        try:
            ApplyBodyCharacterPose(host).apply(poses[0]);checks['static_apply_keeps_rejecting_animation']=False
        except ValueError: checks['static_apply_keeps_rejecting_animation']=True
        class FailedHost(MayaBodyBuildHost):
            def key_character_pose(self,registration,pose):
                super().key_character_pose(registration,pose)
                raise RuntimeError('Injected full-key failure')
        old=host.capture_character_key_state(reg)
        try:
            KeyBodyCharacterPose(FailedHost()).apply(poses[0]);checks['failure_restores_keys_and_pose']=False
        except RuntimeError as exc:
            if 'Injected' not in str(exc): raise
            checks['failure_restores_keys_and_pose']=host.capture_character_key_state(reg)==old and character_pose_error(poses[1],animated.execute())<1e-4
        first=reg.channels[0];plug=first.node+'.'+first.attribute
        curve=cmds.listConnections(plug,s=True,d=False)[0]
        external=cmds.createNode('transform',name='ForeignCurveConsumer',skipSelect=True)
        cmds.connectAttr(curve+'.output',external+'.translateX')
        try:
            key.apply(poses[0]);checks['shared_curve_rejected']=False
        except ValueError: checks['shared_curve_rejected']=host.capture_character_key_state(reg)==old
        cmds.disconnectAttr(curve+'.output',external+'.translateX')
        checks['selection_and_time_preserved']=cmds.ls(sl=True)==[marker] and cmds.currentTime(q=True)==10
        report={'body_joint_count':len(reg.body),'channel_count':len(reg.channels),**checks,'max_pose_error':pose_error,'max_mesh_error':mesh_error,'max_all_frame_error':max(errors),'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally: maya.standalone.uninitialize()


if __name__=='__main__': raise SystemExit(main(Path(sys.argv[1]),with_hand='--basic' not in sys.argv[2:]))
