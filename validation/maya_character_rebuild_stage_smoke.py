"""Replacement build must leave the source rig and every retained object intact."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(source,folder,faults=False):
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import StageBodyCharacterRebuild,CaptureBodyCharacterPreservation
        cmds.file(str(source.resolve()),open=True,force=True);cmds.undoInfo(state=True)
        hero=MayaBodyBuildHost(namespace='hero');partner=MayaBodyBuildHost(namespace='partner')
        old=CaptureBodyCharacterPreservation(hero).execute();untouched=CaptureBodyCharacterPreservation(partner).execute()
        if faults:
            class FailingHost(MayaBodyBuildHost):
                def create_character_rebuild_host(self,namespace):
                    stage=super().create_character_rebuild_host(namespace)
                    install=stage.install_character_stretch_matching
                    def fail(*args):
                        install(*args)
                        raise RuntimeError('injected stage failure')
                    stage.install_character_stretch_matching=fail
                    return stage
            try:StageBodyCharacterRebuild(FailingHost(namespace='partner')).apply('failed_rebuild')
            except RuntimeError as exc:
                if 'injected' not in str(exc):raise
                report={'failed_stage_removed':not cmds.ls('failed_rebuild:*'),
                    'original_preserved':CaptureBodyCharacterPreservation(partner).execute()==untouched,
                    'other_character_preserved':CaptureBodyCharacterPreservation(hero).execute()==old}
            else:report={'failure_was_raised':False}
            report['status']='passed' if all(report.values()) else 'failed'
            (folder/'faults.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        result=StageBodyCharacterRebuild(hero).apply('hero_rebuild')
        report={'original_unchanged':CaptureBodyCharacterPreservation(hero).execute()==old,
                'other_character_unchanged':CaptureBodyCharacterPreservation(partner).execute()==untouched,
                'new_identity':result.registration.nodes[0].uuid!=old.registration.nodes[0].uuid,
                'matching_channels':tuple(ch.key for ch in result.registration.channels)==tuple(ch.key for ch in old.registration.channels)}
        cmds.undo();report['undo_removes_stage']=not cmds.ls('hero_rebuild:*')
        hero.preflight_character_rebuild_namespace('hero_rebuild')
        report['empty_stage_identity_reusable']=True
        report['undo_preserves_original']=CaptureBodyCharacterPreservation(hero).execute()==old
        cmds.redo();report['redo_restores_stage']=MayaBodyBuildHost(namespace='hero_rebuild').read_character_registration()==result.registration
        cmds.file(rename=str(folder/'staged.ma'));cmds.file(save=True,type='mayaAscii',force=True)
        report['status']='passed' if all(report.values()) else 'failed'
        (folder/'stage.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2]),'--faults' in sys.argv))
