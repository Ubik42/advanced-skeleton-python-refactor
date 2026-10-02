"""Compare whole native Body graph output under representative control edits."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
CASES=(('neutral',()),
       ('shoulder_fk',(('FKShoulder_R.rotateZ','AdvPy_Shoulder_RFK.rotateZ',30.),)),
       ('wrist_fk',(('FKWrist_R.rotateX','AdvPy_Wrist_RFK.rotateX',25.),)),
       ('bendy_twist',(('BendShoulder_R.rotateX','BendShoulder_R.rotateX',30.),)),
       ('bendy_translation',(('BendElbow_R.translateY','BendElbow_R.translateY',.3),)),
       ('global_scale',tuple(('Main.scale'+axis,'AdvPy_Global.globalScale',1.25) for axis in 'XYZ')),
       ('root_leg_lock',(('FKRoot_M.legLock','AdvPy_Root_MFK.legLock',0.),
                         ('RootX_M.rotateY','AdvPy_RootX_M.rotateY',30.))))

def main(native,python_scene,reference,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    names=tuple(json.loads(reference.read_text())['neutral_body'])
    matrices={}
    for index,(label,scene) in enumerate((('native',native),('python',python_scene))):
        matrices[label]={}
        for name,edits in CASES:
            cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
            cmds.currentTime(1,update=True)
            for row in edits:
                assert cmds.objExists(row[index]),row[index]
                cmds.setAttr(row[index],row[2])
            cmds.dgdirty(allPlugs=True)
            matrices[label][name]={node:cmds.xform(node,q=True,ws=True,m=True) for node in names}
    rows=[]
    for name,edits in CASES:
        errors={node:max(abs(a-b) for a,b in zip(matrices['native'][name][node],matrices['python'][name][node])) for node in names}
        rows.append(dict(case=name,maximum_error=max(errors.values()),errors=errors,
                         largest=sorted(errors.items(),key=lambda row:row[1],reverse=True)[:8]))
    passed=all(row['maximum_error']<=1e-4 for row in rows)
    report=dict(status='passed' if passed else 'failed',scope='90 Body/Part joints, seven representative control cases',tolerance=1e-4,rows=rows,matrices=matrices)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print([(row['case'],row['maximum_error'],row['largest'][:2]) for row in rows])
    if not passed:raise AssertionError('Whole Body pose comparison failed')

if __name__=='__main__':main(*(Path(arg) for arg in sys.argv[1:5]))
