"""Observe repeat evaluation without modifying the character graph."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    host=MayaBodyBuildHost();reg=host.read_character_registration()
    names=['Shoulder_L','Elbow_L','ElbowPart1_L','MicroXElbowPart1_L',
           'AdvPy_BendElbowStartSource_L','BendMPXElbow1_L','MicroOffsetElbowPart1_L']
    modes=[]
    for mode in ('off','serial','parallel'):
        cmds.evaluationManager(mode=mode)
        rows=[]
        for frame in (1,3,5,1):
            cmds.currentTime(frame,update=True)
            for iteration in range(4):
                cmds.dgdirty(allPlugs=True)
                matrices={node:cmds.getAttr(node+'.worldMatrix[0]') for node in names}
                rows.append(dict(frame=frame,iteration=iteration,matrices=matrices))
        modes.append(dict(mode=mode,rows=rows))
    output.mkdir(parents=True,exist_ok=True)
    (output/'bendy-evaluation.json').write_text(json.dumps(modes,indent=2),encoding='utf-8')
    maximum = 0.0
    for mode in modes:
        for frame in (1,3,5):
            samples=[row for row in mode['rows'] if row['frame']==frame]
            first=samples[0]['matrices']
            errors={node:max(abs(a-b) for row in samples for a,b in zip(first[node],row['matrices'][node])) for node in names}
            maximum = max(maximum, *errors.values())
            print(mode['mode'],frame,errors)
    report = dict(status='passed' if maximum <= 1e-5 else 'failed',
                  scope='Seven selected Bendy nodes; repeated same-pose evaluation',
                  nodes=names, modes=['off','serial','parallel'], maximum_error=maximum, tolerance=1e-5)
    (output/'bendy-evaluation-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if maximum > 1e-5:
        raise AssertionError('Repeated Bendy evaluation drift: '+str(maximum))
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
