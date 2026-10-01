"""Verify independent source Twist references survive native rebuild/reopen."""
from pathlib import Path
import sys, json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_source_part_reference import audit, MARKER
    from adv_py.core.character_registry import CharacterRegistryError, safe_json
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    host=MayaBodyBuildHost()
    registration=host.read_character_registration()
    references=[node for node in cmds.ls(type='transform',long=True) or []
                if cmds.objExists(node+'.'+MARKER)]
    assert references, 'No independent Twist references'
    registered={node.path for node in registration.nodes}
    for reference in references:
        audit(host,reference)
    reference=references[0]
    record=safe_json(cmds.getAttr(reference+'.'+MARKER))
    upstream,destination=record['outputs'][0]
    cmds.undoInfo(openChunk=True)
    try:
        cmds.disconnectAttr(upstream,destination)
    finally:
        cmds.undoInfo(closeChunk=True)
    rejected=False
    try:
        host.read_character_registration()
    except CharacterRegistryError:
        rejected=True
    assert rejected, 'Changed Twist reference graph was accepted'
    cmds.undo()
    audit(host,reference)
    assert host.read_character_registration()==registration
    report=dict(status='passed',scope='Saved rebuilt independent Twist parent references',
                reference_count=len(references),registered_reference_count=sum(node in registered for node in references),
                changed_edge_rejected=rejected,undo_restored=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
