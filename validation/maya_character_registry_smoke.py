"""Run write and read in separate mayapy processes, using an ignored directory."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'examples')]
import maya.standalone


def main(directory,phase,with_hand=True):
    directory=directory.resolve()
    directory.mkdir(parents=True,exist_ok=True)
    scene=directory/'character.ma'
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import RegisterBodyCharacter,ResolveBodyCharacter,MatchBodySpine,SwitchBodyControlSpace
        from adv_py.core.character_registry import REGISTRY_NAME,CharacterRegistryError
        from adv_py.core.body_control_spaces import control_space_pose_error
        checks={}
        if phase=='write':
            from maya_complete_character import build_character
            cmds.upAxis(axis='z',rotateView=False)
            cmds.undoInfo(state=True)
            demo=build_character(with_hand=with_hand)
            host=demo.host
            class FailedHost(MayaBodyBuildHost):
                def create_character_registration(self,plan):
                    super().create_character_registration(plan)
                    raise RuntimeError('Injected registration failure')
            try:
                RegisterBodyCharacter(FailedHost()).apply(demo.rig)
                checks['failed_registration_rolls_back']=False
            except RuntimeError as exc:
                if 'Injected' not in str(exc): raise
                checks['failed_registration_rolls_back']=not cmds.objExists(REGISTRY_NAME) and cmds.objExists(demo.skin)
            registration=RegisterBodyCharacter(host).apply(demo.rig)
            cmds.undo()
            checks['one_undo_removes_registry_only']=not cmds.objExists(REGISTRY_NAME) and cmds.objExists(demo.skin)
            cmds.redo()
            checks['redo_restores_registration']=ResolveBodyCharacter(host).execute()==registration
            (directory/'expected.json').write_text(json.dumps({'digest':registration.compatibility_digest,'channels':len(registration.channels),'body':len(registration.body)}),encoding='utf-8')
            cmds.file(rename=str(scene))
            cmds.file(save=True,type='mayaAscii',force=True)
        else:
            cmds.file(str(scene),open=True,force=True)
            cmds.undoInfo(state=True)
            host=MayaBodyBuildHost()
            resolver=ResolveBodyCharacter(host)
            expected=json.loads((directory/'expected.json').read_text(encoding='utf-8'))
            cmds.file(modified=False)
            before=(cmds.currentTime(q=True),cmds.ls(sl=True,long=True),cmds.undoInfo(q=True,undoName=True))
            discovered=resolver.discover()
            registration=resolver.execute()
            checks['new_process_discovers_registered_character']=discovered==(REGISTRY_NAME,) and registration.compatibility_digest==expected['digest'] and len(registration.channels)==expected['channels'] and len(registration.body)==expected['body']
            checks['resolve_read_only']=not cmds.file(q=True,modified=True) and before==(cmds.currentTime(q=True),cmds.ls(sl=True,long=True),cmds.undoInfo(q=True,undoName=True))
            cmds.setAttr(registration.spine.fk_controls[1]+'.rotateZ',-15)
            pose=host.capture_control_space_pose(registration.spaces)
            MatchBodySpine(host).execute(registration.spine,'ik')
            MatchBodySpine(host).execute(registration.spine,'fk')
            for spec in registration.spaces.spaces:
                SwitchBodyControlSpace(host).execute(registration.spaces,spec.key,'global' if spec.initial_mode=='body' else 'body')
            checks['reopened_spine_and_spaces_preserve_pose']=control_space_pose_error(pose,host.capture_control_space_pose(registration.spaces))<1e-4
            checks['resolve_after_rebinding']=resolver.execute()==registration
            driven=registration.body[1].path
            source=cmds.connectionInfo(driven+'.rotateX',sourceFromDestination=True)
            if source:
                cmds.disconnectAttr(source,driven+'.rotateX')
                try:
                    resolver.execute();checks['changed_body_input_rejected']=False
                except CharacterRegistryError: checks['changed_body_input_rejected']=True
                cmds.undo()
            else:
                raise RuntimeError('Expected a driven body channel')
            target=registration.spine.pole_control
            renamed=cmds.rename(target,'UnexpectedPole')
            try:
                resolver.execute();checks['renamed_member_rejected']=False
            except CharacterRegistryError: checks['renamed_member_rejected']=True
            cmds.undo()
            checks['undo_rename_restores_identity']=resolver.execute()==registration
            doc=REGISTRY_NAME+'.advPyRegistryDocument'
            cmds.setAttr(doc,lock=False)
            cmds.setAttr(doc,'{}',type='string')
            try:
                resolver.execute();checks['corrupt_document_rejected']=False
            except CharacterRegistryError: checks['corrupt_document_rejected']=True
        report={'phase':phase,'body_joint_count':len(registration.body),'channel_count':len(registration.channels),**checks,'status':'passed' if all(checks.values()) else 'failed'}
        (directory/(phase+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2))
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]),sys.argv[2],with_hand='--basic' not in sys.argv[3:]))
