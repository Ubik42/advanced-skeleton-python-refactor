"""Prove legacy self-OPM repair on a saved, animated and skinned Body."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main(scene, output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_source_parent_inverse import repair, parent_world_inverse
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    host=MayaBodyBuildHost()
    registration=host.read_character_registration()
    assert repair(host,registration)==(), 'Current graph must need no repair'
    candidates=[]
    for row in registration.nodes:
        node=row.path
        if not cmds.objExists(node+'.offsetParentMatrix'):continue
        source=cmds.connectionInfo(node+'.offsetParentMatrix',sourceFromDestination=True)
        if not source:continue
        matrix=source.split('.',1)[0]
        if cmds.nodeType(matrix)=='pickMatrix':
            source=cmds.connectionInfo(matrix+'.inputMatrix',sourceFromDestination=True)
            if not source:continue
            matrix=source.split('.',1)[0]
        if cmds.nodeType(matrix)!='multMatrix':continue
        parent=parent_world_inverse(host,node)
        for destination in cmds.listConnections(parent,s=False,d=True,p=True) or []:
            if (destination.split('.',1)[0]==matrix and '.matrixIn[' in destination):
                candidates.append((node,parent,destination))
    assert candidates, 'No registered OPM receiver found'
    node,parent,destination=next((row for row in candidates if 'Cup' in row[0]),candidates[0])
    mesh=(cmds.ls('BipedBindProxy',long=True) or [])[0]
    def snapshot():
        result=[]
        for frame in (1,3,5):
            cmds.currentTime(frame)
            result.append((tuple(cmds.xform(node,q=True,ws=True,m=True)),
                           tuple(cmds.pointPosition(mesh+'.vtx[0]',world=True))))
        return result
    baseline=snapshot()
    curves={curve.uuid for curve in CaptureBodyCharacterPreservation(host).execute().curves}
    old=node+'.parentInverseMatrix[0]'
    # Deliberately install the historical bug only in this validation fixture.
    cmds.disconnectAttr(parent,destination)
    cmds.connectAttr(old,destination)
    with host.transaction('Repair historical OPM parent input'):
        edits=repair(host,registration)
    assert edits==((old,parent,destination),),edits
    assert cmds.isConnected(parent,destination)
    after=snapshot()
    error=max(abs(a-b) for lhs,rhs in zip(baseline,after)
              for lgroup,rgroup in zip(lhs,rhs) for a,b in zip(lgroup,rgroup))
    assert error<1e-4,error
    assert curves=={curve.uuid for curve in CaptureBodyCharacterPreservation(host).execute().curves}
    # Time changes are undoable; repair again without intervening commands.
    cmds.disconnectAttr(parent,destination);cmds.connectAttr(old,destination)
    with host.transaction('Repair historical OPM parent input undo proof'):
        assert repair(host,registration)==edits
    cmds.undo();assert cmds.isConnected(old,destination)
    cmds.redo();assert cmds.isConnected(parent,destination)
    output.mkdir(parents=True,exist_ok=True)
    saved=output/'opm-parent-repaired.mb'
    cmds.file(rename=str(saved.resolve()));cmds.file(save=True,type='mayaBinary',force=True)
    cmds.file(str(saved.resolve()),open=True,force=True,executeScriptNodes=False)
    assert cmds.isConnected(parent,destination)
    assert repair(MayaBodyBuildHost(),registration)==()
    report=dict(status='passed',receiver=node,edits=edits,max_matrix_skin_error=error,
                native_curve_identity_preserved=True,single_undo_redo=True,reopened=True)
    (output/'opm-parent-repair.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS legacy OPM repair',report)

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
