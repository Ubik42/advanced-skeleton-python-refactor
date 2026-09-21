"""Two independently built characters in one native Maya scene."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(folder,reopen=False,references=False,verify=False,faults=False):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from maya_complete_character import CharacterExampleHost,build_character
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (RegisterBodyCharacter,EnableBodyCharacterLimbAnimation,EnableBodyCharacterStretchMatching,
            EnableBodyCharacterSpaceAnimation,KeyBodyCharacterPose,CaptureBodyCharacterAnimation,ApplyBodyCharacterAnimation,
            SwitchBodyCharacterSpace,BakeBodyCharacterLimbMode,BakeBodyCharacterSpineMode)
        cmds.file(new=True,force=True);cmds.upAxis(axis='z');cmds.undoInfo(state=True)
        if references:
            cmds.file(str(folder/'characters.ma'),reference=True,namespace='shot')
            found=MayaBodyBuildHost.discover_scene_characters()
            report={'reference_discovery':tuple(r.identity.namespace for r in found)==('shot:hero','shot:partner') and all(r.referenced for r in found)}
            cmds.file(modified=False)
            try:MayaBodyBuildHost(namespace='shot:hero').read_character_registration()
            except ValueError:report['reference_edit_boundary']=True
            else:report['reference_edit_boundary']=False
            report['read_only_rejection']=not cmds.file(q=True,modified=True)
            report['status']='passed' if all(report.values()) else 'failed'
            (folder/'references.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        if reopen or verify or faults:
            from dataclasses import replace
            cmds.file(str(folder/('animated.ma' if verify or faults else 'characters.ma')),open=True,force=True)
            hero=MayaBodyBuildHost(namespace='hero');partner=MayaBodyBuildHost(namespace='partner')
            registrations=[h.read_character_registration() for h in (hero,partner)]
            marker=cmds.createNode('transform',name='UnrelatedSelection',skipSelect=True);cmds.select(marker)
            def snapshot(host):
                reg=host.read_character_registration()
                with host._character_sampling_time() as seek:
                    rows=[]
                    for frame in (1.,11.,21.):
                        seek(frame)
                        rows.append((host.capture_character_pose(reg),tuple(host._cmds.xform('|AdvPy_CharacterProxy.vtx[*]',q=True,ws=True,t=True))))
                    return tuple(rows),host.capture_character_key_state(reg)
            report={'discovery':tuple(x.identity.namespace for x in hero.discover_scene_characters())==('hero','partner')}
            from adv_py.core.character_pose import encode_character_pose,decode_character_pose,character_pose_error
            if faults:
                original=snapshot(hero);untouched=snapshot(partner)
                class FailingHost(MayaBodyBuildHost):
                    def key_character_pose(self,*args):
                        super().key_character_pose(*args)
                        raise RuntimeError('injected character write failure')
                try:KeyBodyCharacterPose(FailingHost(namespace='hero')).apply(original[0][0][0])
                except RuntimeError as exc:
                    if 'injected' not in str(exc):raise
                    report['write_failure_rolls_back']=snapshot(hero)==original and snapshot(partner)==untouched
                else:report['write_failure_rolls_back']=False
                ch=registrations[0].channels[0];plug=hero.scene_address(ch.node+'.'+ch.attribute)
                source=cmds.connectionInfo(plug,sourceFromDestination=True)
                foreign=cmds.createNode('animCurveTL',name='partner:ForeignCurve',skipSelect=True)
                cmds.connectAttr(foreign+'.output',plug,force=True)
                try:hero.read_character_registration()
                except ValueError:report['foreign_animation_rejected']=True
                else:report['foreign_animation_rejected']=False
                cmds.connectAttr(source,plug,force=True)
                report['other_character_untouched']=snapshot(partner)==untouched
                report['status']='passed' if all(report.values()) else 'failed'
                (folder/'faults.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
                return 0 if report['status']=='passed' else 1
            if verify:
                expected=json.loads((folder/'animation-expected.json').read_text(encoding='utf-8'))
                for h in (hero,partner):
                    rows,_=snapshot(h);saved=expected[h.namespace]
                    report[h.namespace+'_reopened_animation']=all(character_pose_error(pose,decode_character_pose(wanted[0]))<1e-4
                        and max(abs(a-b) for a,b in zip(mesh,wanted[1]))<1e-4 for (pose,mesh),wanted in zip(rows,saved))
                untouched=snapshot(hero)
                SwitchBodyCharacterSpace(partner).execute('head','global',11)
                BakeBodyCharacterLimbMode(partner).execute(1,21,'arm','L','ik',step=10)
                report['partner_edit_leaves_hero_unchanged']=snapshot(hero)==untouched
                report['status']='passed' if all(report.values()) else 'failed'
                (folder/'verify.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
                return 0 if report['status']=='passed' else 1
            baseline=snapshot(partner)
            for frame,offset in ((1,0.),(11,2.),(21,4.)):
                cmds.currentTime(frame)
                pose=hero.capture_character_pose(registrations[0])
                pose=replace(pose,channels=tuple((k,offset if k=='global.translateX' else v) for k,v in pose.channels))
                # Body/space reference matrices are sampled after a temporary
                # static edit; the public writer must reconstruct that result.
                with hero.transaction('prepare expected keyed pose'):
                    with hero._character_static_controls(registrations[0],pose):
                        target=hero.capture_character_pose(registrations[0])
                KeyBodyCharacterPose(hero).apply(target)
            cmds.currentTime(baseline[1][0])
            report['keys_leave_other_character_unchanged']=snapshot(partner)==baseline
            SwitchBodyCharacterSpace(hero).execute('hand_R','body',11)
            report['space_leaves_other_character_unchanged']=snapshot(partner)==baseline
            clip=CaptureBodyCharacterAnimation(hero).execute(1,21,step=10)
            ApplyBodyCharacterAnimation(hero).apply(clip)
            original=snapshot(hero)
            BakeBodyCharacterLimbMode(hero).execute(1,21,'arm','R','ik',step=10)
            after=snapshot(hero);cmds.undo()
            report['bake_undo']=snapshot(hero)==original and snapshot(partner)==baseline
            cmds.redo();report['bake_redo']=snapshot(hero)==after and snapshot(partner)==baseline
            BakeBodyCharacterSpineMode(hero).execute(1,21,'ik',step=10)
            report['bake_leaves_other_character_unchanged']=snapshot(partner)==baseline
            report['selection_and_namespace_restored']=cmds.ls(sl=True)==[marker] and cmds.namespaceInfo(currentNamespace=True)==':'
            try:hero._cmds.setAttr('partner:AdvPy_GlobalControl.translateX',100.)
            except ValueError:report['cross_character_write_rejected']=True
            else:report['cross_character_write_rejected']=False
            report['registrations_survive']=hero.read_character_registration()==registrations[0] and partner.read_character_registration()==registrations[1]
            expected={h.namespace:[(encode_character_pose(pose),mesh) for pose,mesh in snapshot(h)[0]] for h in (hero,partner)}
            (folder/'animation-expected.json').write_text(json.dumps(expected),encoding='utf-8')
            cmds.file(rename=str(folder/'animated.ma'));cmds.file(save=True,type='mayaAscii',force=True)
            report['status']='passed' if all(report.values()) else 'failed'
            (folder/'animation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        characters=[]
        checks={}
        for namespace in ('hero','partner'):
            cmds.namespace(addNamespace=namespace)
            host=CharacterExampleHost(namespace=namespace)
            print('BUILD',namespace,flush=True)
            built=build_character(with_hand=namespace=='partner',host=host)
            original=tuple(host._cmds.xform(built.mesh+'.vtx[*]',q=True,ws=True,t=True))
            cmds.undo();checks[namespace+'_build_undo']=not cmds.objExists(host.scene_address(built.mesh))
            cmds.redo();checks[namespace+'_build_redo']=tuple(host._cmds.xform(built.mesh+'.vtx[*]',q=True,ws=True,t=True))==original
            reg=RegisterBodyCharacter(host).apply(built.rig)
            EnableBodyCharacterLimbAnimation(host).apply()
            EnableBodyCharacterStretchMatching(host).apply()
            reg=EnableBodyCharacterSpaceAnimation(host).apply()
            characters.append((host,built,reg))
            print('REGISTERED',namespace,len(reg.channels),flush=True)
        report={**checks,'two_characters':len(characters)==2,'distinct_roots':len({h.scene_address(r.body_root) for h,_,r in characters})==2,
                'independent_registration':all(h.read_character_registration()==r for h,_,r in characters)}
        cmds.file(rename=str(folder/'characters.ma'));cmds.file(save=True,type='mayaAscii',force=True)
        report['status']='passed' if all(report.values()) else 'failed'
        (folder/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),'--reopen' in sys.argv,'--references' in sys.argv,'--verify' in sys.argv,'--faults' in sys.argv))
