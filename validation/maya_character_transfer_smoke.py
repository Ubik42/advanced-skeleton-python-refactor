"""Native retained-node transfer, geometry preservation and atomic rollback."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(source,folder,reopen=False,partner=False,prepared=False,custom=False):
    source_namespace="partner" if partner else "hero"
    target_namespace=source_namespace+"_rebuild"
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (StageBodyCharacterRebuild,TransferStagedBodyCharacterData,CaptureBodyCharacterPreservation)
        cmds.file(str(folder/'transferred.ma' if reopen else source.resolve()),open=True,force=True);cmds.undoInfo(state=True)
        from adv_py.core.character_preservation import character_transfer_error
        if reopen:
            expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
            property_ids=json.loads((folder/'property-ids.json').read_text(encoding='utf-8')) if (folder/'property-ids.json').exists() else {}
            host=MayaBodyBuildHost(namespace=target_namespace);reg=host.read_character_registration()
            rows=[]
            with host._character_sampling_time() as seek:
                for frame,body,spaces,meshes,attachments in expected:
                    seek(frame);pose=host.capture_character_pose(reg)
                    actual_attachments=[]
                    for key,_ in attachments:
                        uuid,separator,attribute=key.partition('.')
                        node=cmds.ls(property_ids.get(uuid,uuid),long=True)[0]
                        if separator:
                            value=cmds.getAttr(node+'.'+attribute,time=frame)
                            values=tuple(value) if isinstance(value,(tuple,list)) else (float(value),)
                        else:values=tuple(cmds.xform(node,q=True,ws=True,matrix=True))
                        actual_attachments.append((key,values))
                    rows.append((frame,pose.body_frames,pose.space_frames,
                        tuple((uuid,tuple(cmds.xform(cmds.ls(uuid,long=True)[0]+'.vtx[*]',q=True,ws=True,t=True))) for uuid,_ in meshes),
                        tuple(actual_attachments)))
            error=character_transfer_error(expected,rows)
            report={'error':error,'status':'passed' if error<1e-4 else 'failed'}
            (folder/'read.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
            return 0 if report['status']=='passed' else 1
        host=MayaBodyBuildHost(namespace=source_namespace);other=MayaBodyBuildHost(namespace='hero' if partner else 'partner')
        reg=host.read_character_registration()
        channel=next(ch for ch in reg.channels if ch.key=='global.translateX')
        if not cmds.connectionInfo(host.scene_address(channel.node+'.'+channel.attribute),sourceFromDestination=True):
            for frame,value in ((1,0.),(11,2.),(21,4.)):
                host._cmds.setKeyframe(channel.node,attribute=channel.attribute,time=frame,value=value)
        curve=cmds.connectionInfo(host.scene_address(channel.node+'.'+channel.attribute),sourceFromDestination=True).rsplit('.',1)[0]
        cmds.keyTangent(curve,edit=True,weightedTangents=True)
        cmds.keyTangent(curve,edit=True,time=(11,11),inTangentType='fixed',outTangentType='fixed',inAngle=17.,outAngle=-12.,inWeight=.7,outWeight=.9)
        cmds.setAttr(curve+'.preInfinity',3);cmds.setAttr(curve+'.postInfinity',4)
        attachment=cmds.createNode('transform',name=source_namespace+':UserAttachment',parent=host.scene_address(reg.spine.ik_control),skipSelect=True)
        cmds.setAttr(attachment+'.translateX',.5)
        cmds.addAttr(attachment,longName='note',dataType='string');cmds.setAttr(attachment+'.note','用户附件',type='string',lock=True)
        cmds.addAttr(attachment,longName='referenceMatrix',dataType='matrix')
        cmds.connectAttr(host.scene_address(reg.body_root)+'.worldMatrix[0]',attachment+'.referenceMatrix')
        cmds.addAttr(attachment,longName='strength',attributeType='double',keyable=True)
        for frame,value in ((1,.2),(11,.8),(21,.4)):cmds.setKeyframe(attachment,at='strength',time=frame,value=value)
        child=cmds.createNode('transform',name=source_namespace+':UserSocket',parent=attachment,skipSelect=True)
        cmds.setAttr(child+'.translateZ',.3)
        if custom:
            control=host.scene_address(reg.spine.ik_control)
            cmds.addAttr(control,longName='userGain',attributeType='double',defaultValue=.5,minValue=0.,maxValue=2.,softMinValue=.1,softMaxValue=1.5,niceName='用户增益',keyable=True)
            for frame,value in ((1,.3),(11,1.2),(21,.8)):cmds.setKeyframe(control,at='userGain',time=frame,value=value)
            cmds.addAttr(control,longName='userMode',attributeType='enum',enumName='Manual=0:Auto=7:Done=9',defaultValue=7,keyable=True)
            cmds.setAttr(control+'.userMode',9)
            cmds.addAttr(control,longName='userNote',dataType='string');cmds.setAttr(control+'.userNote','保留用户属性',type='string',lock=True)
            cmds.addAttr(attachment,longName='drivenGain',attributeType='double',keyable=True)
            cmds.connectAttr(control+'.userGain',attachment+'.drivenGain')
            cmds.setAttr(control+'.userGain',lock=True)
            cmds.setAttr(attachment+'.drivenGain',lock=True)
        attachment=host._cmds.identity.to_local(cmds.ls(attachment,long=True)[0])
        selected_uuid=cmds.ls(host.scene_address(attachment),uuid=True)[0]
        cmds.select(host.scene_address(attachment))
        if prepared:
            from adv_py.application.character_rebuild import StagedCharacterRebuild
            staged=StagedCharacterRebuild(CaptureBodyCharacterPreservation(host).execute(extensions=(attachment,)),target_namespace,
                MayaBodyBuildHost(namespace=target_namespace).read_character_registration(),
                host.plan_character_property_transfer(CaptureBodyCharacterPreservation(host).execute(extensions=(attachment,)),target_namespace))
        else:staged=StageBodyCharacterRebuild(host).apply(target_namespace,extensions=(attachment,))
        untouched=CaptureBodyCharacterPreservation(other).execute()
        original=staged.original
        result=TransferStagedBodyCharacterData(host).apply(staged)
        report={'curves_retained':all(cmds.ls(row.uuid) for row in original.curves),
            'selected_attachment_preserved':cmds.ls(sl=True,uuid=True)==[selected_uuid],
            'skins_retained':all(cmds.ls(row.uuid) for row in original.skins),
            'other_character_unchanged':CaptureBodyCharacterPreservation(other).execute()==untouched}
        cmds.undo();report['undo_restores_original']=CaptureBodyCharacterPreservation(host).execute(extensions=(attachment,))==original
        cmds.redo();host.verify_character_retained_data(staged);report['redo_retains_data']=True
        cmds.undo()
        class FailingHost(MayaBodyBuildHost):
            def verify_character_retained_data(self,*args):
                super().verify_character_retained_data(*args)
                raise RuntimeError('injected retained-data failure')
        try:TransferStagedBodyCharacterData(FailingHost(namespace=source_namespace)).apply(staged)
        except RuntimeError as exc:
            if 'injected' not in str(exc):raise
            report['failure_restores_original']=CaptureBodyCharacterPreservation(host).execute(extensions=(attachment,))==original
        else:report['failure_restores_original']=False
        TransferStagedBodyCharacterData(host).apply(staged)
        expected=host.sample_character_transfer(staged,(1.,6.,11.,16.,21.),target=True)
        (folder/'expected.json').write_text(json.dumps(expected),encoding='utf-8')
        property_ids={row.uuid:cmds.ls(MayaBodyBuildHost(namespace=target_namespace).scene_address(row.path),uuid=True)[0] for row in staged.custom_properties}
        (folder/'property-ids.json').write_text(json.dumps(property_ids),encoding='utf-8')
        cmds.file(rename=str(folder/'transferred.ma'));cmds.file(save=True,type='mayaAscii',force=True)
        report['status']='passed' if all(report.values()) else 'failed'
        (folder/'transfer.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2]),'--reopen' in sys.argv,'--partner' in sys.argv,'--prepared' in sys.argv,'--custom' in sys.argv))
