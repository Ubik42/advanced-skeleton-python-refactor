"""Lossless rebuild checkpoint on real curves, skin storage and attachments."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(source,output):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import CaptureBodyCharacterPreservation
        cmds.file(str(source.resolve()),open=True,force=True);cmds.undoInfo(state=True)
        host=MayaBodyBuildHost(namespace='hero');reg=host.read_character_registration()
        curve=cmds.connectionInfo(host.scene_address(reg.channels[0].node+'.'+reg.channels[0].attribute),sourceFromDestination=True).rsplit('.',1)[0]
        cmds.keyTangent(curve,edit=True,weightedTangents=True)
        cmds.keyTangent(curve,edit=True,time=(11,11),inTangentType='fixed',outTangentType='fixed',inAngle=17.,outAngle=-12.,inWeight=.7,outWeight=.9)
        cmds.setAttr(curve+'.preInfinity',3);cmds.setAttr(curve+'.postInfinity',4)
        root=cmds.createNode('transform',name='hero:UserProp',parent=host.scene_address(reg.spine.ik_control),skipSelect=True)
        cmds.addAttr(root,longName='label',dataType='string');cmds.setAttr(root+'.label','测试附件',type='string',lock=True)
        cmds.addAttr(root,longName='strength',attributeType='double',keyable=True);cmds.setAttr(root+'.strength',.75)
        cmds.setAttr(root+'.translateX',1.5)
        local=host._cmds.identity.to_local(cmds.ls(root,long=True)[0])
        cmds.select('partner:Root_M');selection=cmds.ls(sl=True,long=True);time=cmds.currentTime(q=True)
        cmds.file(modified=False)
        service=CaptureBodyCharacterPreservation(host)
        snapshot=service.execute(extensions=(local,))
        again=service.execute(extensions=(local,))
        captured=next(c for c in snapshot.curves if host.scene_address(c.node)==curve)
        report={'repeat_identical':snapshot==again,'digest_stable':snapshot.content_digest==again.content_digest,
            'native_curve_count':len(snapshot.curves),'skin_count':len(snapshot.skins),
            'read_only':not cmds.file(q=True,modified=True) and cmds.currentTime(q=True)==time and cmds.ls(sl=True,long=True)==selection,
            'weighted_tangents':captured.weighted and captured.in_angles[1]==17. and captured.out_angles[1]==-12.,
            'infinity_preserved':captured.pre_infinity==3 and captured.post_infinity==4,
            'extension_preserved':snapshot.extensions[0].parent==reg.spine.ik_control and any(row[:5]==('label','string','测试附件',True,False) for row in snapshot.extensions[0].attributes),
            'weights_complete':len(snapshot.skins)==1 and len(snapshot.skins[0].weights)==348,
            'other_character_excluded':all('partner:' not in skin.node for skin in snapshot.skins)}
        report['status']='passed' if all(v for k,v in report.items() if k not in ('native_curve_count','skin_count')) else 'failed'
        output.resolve().parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
        return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
