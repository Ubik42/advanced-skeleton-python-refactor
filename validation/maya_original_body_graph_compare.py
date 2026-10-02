"""Compare complete untouched ADV Body reference matrices with Python output."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main(scene,reference,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    native=json.loads(reference.read_text(encoding='utf-8'))
    assert native['status']=='native_build_passed'
    cmds.file(str(scene.resolve()),open=True,force=True,executeScriptNodes=False)
    registration=MayaBodyBuildHost().read_character_registration()
    cmds.currentTime(1,update=True)
    def sample(expected):
        missing=[];errors={};positions={}
        for name,matrix in expected.items():
            if not cmds.objExists(name):missing.append(name);continue
            actual=cmds.xform(name,q=True,ws=True,m=True)
            errors[name]=max(abs(a-b) for a,b in zip(matrix,actual))
            positions[name]=dict(native=matrix[12:15],python=actual[12:15])
        return dict(missing=missing,maximum_error=max(errors.values(),default=0.),
                    errors=errors,positions=positions)
    neutral=sample(native['neutral_body'])
    samples=[]
    for row in native['elbow_samples']:
        cmds.setAttr('AdvPy_Elbow_RFK.rotateZ',row['angle'])
        cmds.dgdirty(allPlugs=True)
        samples.append(dict(angle=row['angle'],comparison=sample(row['matrices'])))
    tolerance=1e-4
    passed=not neutral['missing'] and neutral['maximum_error']<=tolerance and all(
        not row['comparison']['missing'] and row['comparison']['maximum_error']<=tolerance for row in samples)
    report=dict(status='passed' if passed else 'failed',tolerance=tolerance,
                scope='90 complete neutral Body/Part joints and three Elbow FK poses',
                native_source_sha256=native['source_sha256'],neutral=neutral,elbow_samples=samples)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report['status'],'neutral',neutral['maximum_error'],'poses',[(row['angle'],row['comparison']['maximum_error']) for row in samples])
    print('largest neutral errors',sorted(neutral['errors'].items(),key=lambda row:row[1],reverse=True)[:12])
    if not passed:raise AssertionError('Complete native Body comparison failed; inspect persisted report')

if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
