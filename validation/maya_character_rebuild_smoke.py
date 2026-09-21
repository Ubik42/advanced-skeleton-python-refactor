"""Full character rebuild: one undo, retained data, cleanup and late rollback."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(source,folder,partner=False,reopen=False):
    if reopen:
        from maya_character_transfer_smoke import main as read_transfer
        return read_transfer(source,folder,reopen=True,partner=partner,promoted=True)
    folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import RebuildBodyCharacter,CaptureBodyCharacterPreservation
        c.file(str(source.resolve()),open=True,force=True);c.undoInfo(state=True)
        namespace='partner' if partner else 'hero';temporary=namespace+'_replacement'
        class TraceHost(MayaBodyBuildHost):
            def sample_character_transfer(self,*args,**kwargs):
                value=super().sample_character_transfer(*args,**kwargs)
                (folder/('sample-target.json' if kwargs.get('target') else 'sample-source.json')).write_text(json.dumps(value),encoding='utf8')
                if kwargs.get('target') and '--debug' in sys.argv:
                    c.file(rename=str((folder/'handoff-debug.ma').resolve()));c.file(save=True,type='mayaAscii',force=True)
                return value
        host=TraceHost(namespace=namespace)
        other=MayaBodyBuildHost(namespace='hero' if partner else 'partner')
        reg=host.read_character_registration()
        control=host.scene_address(reg.spine.ik_control)
        attachment=c.createNode('transform',name=namespace+':UserAttachment',parent=control,skipSelect=True)
        c.setAttr(attachment+'.translateX',.7)
        c.addAttr(control,longName='userNote',dataType='string')
        c.setAttr(control+'.userNote','原位重建保留',type='string',lock=True)
        c.addAttr(control,longName='userGain',attributeType='double',keyable=True,minValue=0,maxValue=2,defaultValue=.5)
        for frame,value in ((1,.2),(11,1.1),(21,.4)):c.setKeyframe(control,at='userGain',time=frame,value=value)
        c.addAttr(attachment,longName='gain',attributeType='double')
        c.connectAttr(control+'.userGain',attachment+'.gain')
        c.setAttr(control+'.userGain',lock=True);c.setAttr(attachment+'.gain',lock=True)
        extension=host._cmds.identity.to_local(c.ls(attachment,long=True)[0])
        original=CaptureBodyCharacterPreservation(host).execute(extensions=(extension,))
        untouched=CaptureBodyCharacterPreservation(other).execute()
        c.select(control)
        result=RebuildBodyCharacter(host).apply(temporary,extensions=(extension,))
        sampled=host.sample_character_transfer(result,(1.,6.,11.,16.,21.),target=True)
        selected=c.ls(sl=True,uuid=True)
        control_uuid=c.ls(host.scene_address(reg.spine.ik_control),uuid=True)[0]
        report={'selected_control_replaced':selected==[control_uuid],
                'old_rig_removed':all(not c.ls(old) for _,old,_,_ in result.ownership.nodes),
                'original_fit_preserved':all(c.ls(n.uuid) for n in original.registration.nodes if n.path==reg.container or n.path.startswith(reg.container+'|')),
                'temporary_namespace_removed':not c.namespace(exists=temporary),
                'other_character_unchanged':CaptureBodyCharacterPreservation(other).execute()==untouched}
        c.undo()
        report['single_undo_restores_original']=CaptureBodyCharacterPreservation(host).execute(extensions=(extension,))==original
        c.redo();host.verify_character_retained_data(result)
        report['single_redo_restores_rebuild']=host.read_character_registration()==result.registration
        from adv_py.core.character_preservation import character_transfer_error
        report['redo_geometry_preserved']=character_transfer_error(sampled,host.sample_character_transfer(result,(1.,6.,11.,16.,21.),target=True))<1e-4
        c.undo()
        class FailingHost(MayaBodyBuildHost):
            def promote_character_rebuild(self,staged):
                super().promote_character_rebuild(staged)
                raise RuntimeError('injected after cleanup')
        try:RebuildBodyCharacter(FailingHost(namespace=namespace)).apply(temporary,extensions=(extension,))
        except RuntimeError as exc:
            if 'injected after cleanup' not in str(exc):raise
            report['late_failure_restores_original']=CaptureBodyCharacterPreservation(host).execute(extensions=(extension,))==original
        else:report['late_failure_restores_original']=False
        result=RebuildBodyCharacter(host).apply(temporary,extensions=(extension,))
        expected=host.sample_character_transfer(result,(1.,6.,11.,16.,21.),target=True)
        property_ids={row.uuid:c.ls(host.scene_address(row.path),uuid=True)[0] for row in result.custom_properties}
        for name,value in (('expected.json',expected),('property-ids.json',property_ids),('shapes.json',result.ownership.shapes)):
            (folder/name).write_text(json.dumps(value),encoding='utf8')
        c.file(rename=str((folder/'transferred.ma').resolve()));c.file(save=True,type='mayaAscii',force=True)
        report['status']='passed' if all(report.values()) else 'failed'
        (folder/'rebuild.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
        return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2]),'--partner' in sys.argv,'--reopen' in sys.argv))
