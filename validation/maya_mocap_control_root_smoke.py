"""Retarget a generated MoCap root onto an editable registered Global control."""
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
        from maya.api.OpenMaya import MMatrix
        from maya_complete_character import build_character
        from adv_py.adapters import MayaMocapControlHost
        from adv_py.application import RegisterBodyCharacter,RetargetMocapRootToCharacter

        cmds.file(new=True,force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis='z',rotateView=False)
        built=build_character(with_hand=False)
        reg=RegisterBodyCharacter(built.host).apply(built.rig)
        by_key={channel.key:channel for channel in reg.channels}
        for frame,value in ((1,0.),(10,2.)):
            channel=by_key['global.translateY']
            cmds.setKeyframe(channel.node,attribute=channel.attribute,time=frame,value=value)
        torso=next(channel for channel in reg.channels if channel.key.startswith('torso.') and channel.attribute=='rotateZ')
        cmds.setKeyframe(torso.node,attribute=torso.attribute,time=1,value=0.)
        cmds.setKeyframe(torso.node,attribute=torso.attribute,time=10,value=6.)
        cmds.namespace(add='TakeA')
        source=cmds.createNode('joint',name='TakeA:Hips',skipSelect=True)
        for frame,travel,turn in ((1,0.,0.),(5,4.,15.),(10,9.,30.)):
            cmds.setKeyframe(source,attribute='translateX',time=frame,value=travel)
            cmds.setKeyframe(source,attribute='rotateZ',time=frame,value=turn)
        host=MayaMocapControlHost()
        service=RetargetMocapRootToCharacter(host)
        frames=(1.,5.,10.)
        controls={ch.key:ch for ch in reg.channels}
        global_node=controls['global.translateX'].node
        before_keys=host.capture_character_key_state(reg)
        before_time=float(cmds.currentTime(query=True))
        with host._character_sampling_time() as seek:
            seek(1.)
            source_reference=MMatrix(cmds.xform(source,query=True,worldSpace=True,matrix=True))
            expected=[]
            for frame in frames:
                seek(frame)
                body=MMatrix(cmds.xform(reg.body_root,query=True,worldSpace=True,matrix=True))
                moving=MMatrix(cmds.xform(source,query=True,worldSpace=True,matrix=True))
                expected.append(tuple(body*source_reference.inverse()*moving))
        samples=service.apply('|TakeA:Hips',start_frame=1,end_frame=10,sample_by=1)
        with host._character_sampling_time() as seek:
            errors=[]
            for frame,wanted in zip(frames,expected):
                seek(frame)
                actual=cmds.xform(reg.body_root,query=True,worldSpace=True,matrix=True)
                errors.append(max(abs(a-b) for a,b in zip(actual,wanted)))
        after_keys=host.capture_character_key_state(reg)
        checks={
            'all_frames_written':len(samples)==10,
            'global_curves_are_editable':all(cmds.nodeType((cmds.listConnections(
                controls['global.'+kind+axis].node+'.'+kind+axis,source=True,destination=False) or [''])[0]).startswith('animCurve')
                for kind in ('translate','rotate') for axis in 'XYZ'),
            'body_root_matches_source_delta':max(errors)<1e-4,
            'scene_time_preserved':float(cmds.currentTime(query=True))==before_time,
            'other_controls_untouched':all(before==after for before,after in zip(before_keys[1],after_keys[1])
                                           if not before[0].startswith('global.')),
        }
        class FailedHost(MayaMocapControlHost):
            def write_mocap_root_control_keys(self,plan):
                super().write_mocap_root_control_keys(plan)
                raise RuntimeError('Injected control write failure')
        try:RetargetMocapRootToCharacter(FailedHost()).apply('|TakeA:Hips',start_frame=1,end_frame=10)
        except RuntimeError as exc:
            if 'Injected' not in str(exc):raise
            checks['partial_write_rolls_back']=host.capture_character_key_state(reg)==after_keys
        else:checks['partial_write_rolls_back']=False
        cmds.undo()
        checks['single_undo_restores_keys']=host.capture_character_key_state(reg)==before_keys
        cmds.redo()
        checks['single_redo_restores_keys']=host.capture_character_key_state(reg)==after_keys
        scene=output.parent/'mocap-control-root.ma'
        cmds.file(rename=str(scene));cmds.file(save=True,type='mayaAscii',force=True)
        cmds.file(str(scene),open=True,force=True)
        reopened=MayaMocapControlHost()
        reopened_registration=reopened.read_character_registration()
        with reopened._character_sampling_time() as seek:
            seek(10.)
            actual=cmds.xform(reopened_registration.body_root,query=True,worldSpace=True,matrix=True)
        checks['reopened_control_animation']=(reopened.capture_character_key_state(reopened_registration)==after_keys
            and max(abs(a-b) for a,b in zip(actual,expected[-1]))<1e-4)
        output.parent.mkdir(parents=True,exist_ok=True)
        payload={**checks,'max_root_error':max(errors),'status':'passed' if all(checks.values()) else 'failed'}
        output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
