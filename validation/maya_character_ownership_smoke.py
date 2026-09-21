"""Read-only rig ownership audit and undeclared user boundary rejection."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(source,folder):
    folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import StageBodyCharacterRebuild
        from adv_py.core.character_registry import CharacterRegistryError
        c.file(str(source.resolve()),open=True,force=True);c.undoInfo(state=True)
        host=MayaBodyBuildHost(namespace='hero')
        stage=StageBodyCharacterRebuild(host).apply('hero_audit')
        before=(c.currentTime(q=True),c.file(q=True,modified=True),c.undoInfo(q=True,undoName=True))
        result=host.audit_character_rebuild_ownership(stage)
        report={'owned_nodes':len(result.nodes),'implicit_conversions':sum(n[0].startswith('@conversion:') for n in result.nodes),
                'read_only':before==(c.currentTime(q=True),c.file(q=True,modified=True),c.undoInfo(q=True,undoName=True)),
                'stage_records_ownership':stage.ownership==result}
        root=host.scene_address(stage.original.registration.body_root)
        child=c.createNode('transform',name='UserChild',parent=root,skipSelect=True)
        try:host.audit_character_rebuild_ownership(stage)
        except CharacterRegistryError:report['undeclared_child_rejected']=True
        else:report['undeclared_child_rejected']=False
        c.delete(child)
        outside=c.createNode('network',name='UserConsumer',skipSelect=True)
        c.addAttr(outside,longName='rig',attributeType='message')
        c.connectAttr(root+'.message',outside+'.rig')
        try:host.audit_character_rebuild_ownership(stage)
        except CharacterRegistryError:report['undeclared_consumer_rejected']=True
        else:report['undeclared_consumer_rejected']=False
        c.delete(outside)
        conversion=next(row[1] for row in result.nodes if row[3]=='unitConversion')
        node=c.ls(conversion,long=True)[0]
        outside=c.createNode('network',name='SharedConversionConsumer',skipSelect=True)
        c.addAttr(outside,longName='value',attributeType='double')
        c.connectAttr(node+'.output',outside+'.value')
        try:host.audit_character_rebuild_ownership(stage)
        except CharacterRegistryError:report['shared_conversion_rejected']=True
        else:report['shared_conversion_rejected']=False
        c.delete(outside)
        curve=next(row[1] for row in result.nodes if row[3]=='nurbsCurve')
        shape=c.ls(curve,long=True)[0];point=shape+'.cv[0]'
        position=c.xform(point,q=True,objectSpace=True,t=True)
        c.xform(point,objectSpace=True,t=(position[0]+.1,*position[1:]))
        try:host.audit_character_rebuild_ownership(stage)
        except CharacterRegistryError:report['edited_control_shape_rejected']=True
        else:report['edited_control_shape_rejected']=False
        c.xform(point,objectSpace=True,t=position)
        report['audit_restored']=host.audit_character_rebuild_ownership(stage)==result
        report['status']='passed' if all(report.values()) else 'failed'
        (folder/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report,indent=2))
        return 0 if report['status']=='passed' else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
