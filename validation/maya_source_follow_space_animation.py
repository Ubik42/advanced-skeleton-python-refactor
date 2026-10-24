"""OPM FK follow-space blends and native follow-weight animation preservation."""
from pathlib import Path
import json,os,sys,traceback,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
SOURCE=ROOT/'validation/results/source-non-symmetry-follow-opm-current'
OUT=ROOT/'validation/results/source-follow-space-animation-current'

def main(standalone=False,quit_on_finish=True):
    from maya import cmds as c
    from maya_source_rp_sub_constructor import snapshot,difference
    from maya_original_biped_current_smoke import main as lifecycle
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.character_preservation import CaptureBodyCharacterPreservation
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),poses=[])
    def checkpoint(stage):
        report['stage']=stage
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        base=json.loads((SOURCE/'report.json').read_text(encoding='utf-8'))
        assert base['status']=='passed' and base['lifecycle']['status']=='passed'
        report['source_lifecycle_pid']=base['pid']
        checkpoint('space_blend_comparisons')
        poses=[]
        for side in ('R','L'):
            for weight in (0.,5.,10.):
                for label,edits in (
                  ('main_translate',(('Main.translateX','AdvPy_Global.translateX',3.),)),
                  ('main_rotate',(('Main.rotateZ','AdvPy_Global.rotateZ',12.),)),
                  ('main_scale',(('Main.scaleX','AdvPy_Global.scaleX',1.2),)),
                  ('root_rotate',(('RootX_M.rotateY','AdvPy_RootX_M.rotateY',13.),)),
                  ('chest_rotate',(('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',12.),))):
                    target='Root' if label=='root_rotate' else 'Chest' if label=='chest_rotate' else 'Main'
                    weights=((f'FKPinkyFinger1_{side}.followParent',f'AdvPy_PinkyFinger1_{side}FK.followParent',10.-weight),(f'FKPinkyFinger1_{side}.follow'+target,f'AdvPy_PinkyFinger1_{side}FK.follow'+target,weight))
                    poses.append((side+'_'+label+'_'+str(int(weight)),weights+edits))
        native={}
        for label,edits in poses:
            c.file(str(SOURCE/'native.mb'),open=True,force=True,executeScriptNodes=False)
            for a,b,value in edits:c.setAttr(a,value)
            native[label]=snapshot()
        for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
            for label,edits in poses:
                c.file(str(SOURCE/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                # The fixture Global curve is unrelated to this static source pose.
                for a,b,value in edits:
                    upstream=c.connectionInfo(b,sourceFromDestination=True) or None
                    if upstream and c.nodeType(upstream.split('.')[0]).startswith('animCurve'):c.disconnectAttr(upstream,b)
                    c.setAttr(b,value)
                report['poses'].append(dict(scene=scene,case=label,maximum_error=difference(native[label],snapshot())))
        report['maximum_error']=max(row['maximum_error'] for row in report['poses'])
        assert report['maximum_error']<=1e-4,report['poses']
        checkpoint('weight_animation_preserved_rebuild')
        folder=OUT/'python';folder.mkdir(parents=True,exist_ok=True)
        shutil.copy2(SOURCE/'python/original-biped-current.mb',folder/'original-biped-current.mb')
        animated=(("AdvPy_PinkyFinger1_RFK","followParent",10.),("AdvPy_PinkyFinger1_RFK","followChest",7.),("AdvPy_PinkyFinger1_LFK","followRoot",5.),("AdvPy_Scapula_LFK","follow",8.),("AdvPy_RingFinger1_RFK","followRoot",6.),("AdvPy_ArmIK_L","ikFollow",9.),("AdvPy_IndexFinger1_RFK","parentConstraint",4.))
        report['lifecycle']=lifecycle(SOURCE/'input.ma',folder,rebuild=True,export=False,bendy=True,opm=True,standalone=False,reuse_scene=True,additional_animation=animated)
        assert report['lifecycle']['status']=='passed'
        c.file(str(folder/'original-biped-rebuilt.mb'),open=True,force=True,executeScriptNodes=False)
        report['animated_weights']=[]
        for node,attr,end in animated:
            source=c.connectionInfo(node+'.'+attr,sourceFromDestination=True)
            assert source and c.nodeType(source.split('.')[0]).startswith('animCurve')
            times=c.keyframe(source.split('.')[0],query=True,timeChange=True)
            values=c.keyframe(source.split('.')[0],query=True,valueChange=True)
            assert times==[1.,5.] and values==[0.,end],(node,attr,times,values)
            report['animated_weights'].append(dict(node=node,attribute=attr,times=times,values=values))
        report['status']='passed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
