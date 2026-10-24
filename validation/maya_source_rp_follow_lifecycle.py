"""Complete native RP follow/PoleAim build and retained legacy lifecycle batch."""
from pathlib import Path
import json, os, sys, traceback, shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT_NAME=os.environ.get('ADV_RP_FOLLOW_OUTPUT','source-rp-follow-lifecycle-current')
if not OUTPUT_NAME or any(part in OUTPUT_NAME for part in ('/','\\','..')):raise ValueError('Invalid RP output folder')
OUT=ROOT/'validation/results'/OUTPUT_NAME


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_source_rp_follow import decode, MARKER
    from maya_original_biped_current_smoke import main as build
    import maya_original_body_pose_compare as parity
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),configurations=[])
    def save(): (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    previous=json.loads((OUT/'report.json').read_text(encoding='utf-8')) if os.environ.get('ADV_RP_FOLLOW_REUSE')=='1' else None
    old_cases=parity.CASES
    old_matrix_cases=parity.matrix_cases
    parity.CASES=(('neutral',()),)
    if os.environ.get('ADV_RP_FOLLOW_AIM_CASES') == '1':
        parity.CASES += (
            ('aim_right_move', (('AimEye_R.translateX','AdvPy_AimEye_R.translateX',.5),)),
            ('aim_left_move', (('AimEye_L.translateY','AdvPy_AimEye_L.translateY',-.5),)),
            ('aim_center_scale', (('AimEye_M.scaleX','AdvPy_AimEye_M.scaleX',1.1),)),
        )
    selected=os.environ.get('ADV_RP_FOLLOW_CASES','traditional,opm,legacy').split(',')
    try:
        for name in selected:
            item=dict(name=name,stage='build');report['configurations'].append(item);save()
            folder=OUT/name;folder.mkdir(exist_ok=True)
            if name=='legacy':
                saved=ROOT/'validation/results/source-body-current-parity/original-biped-current.mb'
                shutil.copy2(saved,folder/'original-biped-current.mb')
                item['lifecycle']=build(saved,folder,rebuild=True,export=False,standalone=False,reuse_scene=True)
                for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
                    c.file(str(folder/scene),open=True,force=True,executeScriptNodes=False)
                    reg=MayaBodyBuildHost().read_character_registration()
                    plans=[decode(c.getAttr(b.ik_control+'.'+MARKER))[0] for b in reg.source_limbs]
                    assert plans and all(not s.source_rp for p in plans for s in p.spaces)
                item['legacy_layout_retained']=True;item['stage']='complete';save();continue
            opm=name=='opm'
            ref=ROOT/'validation/results/source-spline-part-lifecycle-current'/name
            input_scene=ref/'input.ma';native=ref/'native.mb'
            assert input_scene.exists() and native.exists()
            c.file(str(native),open=True,force=True,executeScriptNodes=False)
            nodes=(c.listRelatives('Root_M',allDescendents=True,type='joint',fullPath=True) or [])+c.ls('Root_M',long=True)
            reference=folder/'reference.json'
            reference.write_text(json.dumps(dict(neutral_body={n.rsplit('|',1)[-1]:c.xform(n,q=True,ws=True,matrix=True) for n in nodes})),encoding='utf-8')
            native_defaults={}
            for limb in ('Arm','Leg'):
                for side in ('R','L'):
                    for role in ('IK','Pole'):
                        node=role+limb+'_'+side
                        native_defaults[node]={a:(c.attributeQuery(a,node=node,listDefault=True),c.getAttr(node+'.'+a))
                            for a in c.listAttr(node,userDefined=True) or [] if a.startswith('follow')}
            prior=next((row for row in previous['configurations'] if row['name']==name and row.get('lifecycle',{}).get('status')=='passed'),None) if previous else None
            if prior:
                item['lifecycle']=prior['lifecycle'];item['lifecycle_pid']=prior.get('lifecycle_pid',previous['pid'])
            else:
                item['lifecycle']=build(input_scene,folder,rebuild=True,export=False,opm=opm,standalone=False)
            item['stage']='source-comparison';save();item['poses']=[]
            for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
                c.file(str(folder/scene),open=True,force=True,executeScriptNodes=False)
                reg=MayaBodyBuildHost().read_character_registration()
                plans=[decode(c.getAttr(b.ik_control+'.'+MARKER))[0] for b in reg.source_limbs]
                assert plans and all(s.source_rp and s.use_offset_parent_matrix==opm for p in plans for s in p.spaces)
                for limb in ('Arm','Leg'):
                    for side in ('R','L'):
                        for role,stem in (('IK','IK'),('Pole','PV')):
                            node='AdvPy_'+limb+stem+'_'+side
                            actual={a:(c.attributeQuery(a,node=node,listDefault=True),c.getAttr(node+'.'+a))
                                for a in c.listAttr(node,userDefined=True) or [] if a.startswith('follow')}
                            assert actual==native_defaults[role+limb+'_'+side],(node,actual,native_defaults[role+limb+'_'+side])
                from adv_py.core.spline_names import remap_spline_value
                primary=next(plan for plan in (reg.spine,*reg.additional_spines) if plan and plan.system_name=='Spine_M')
                parity.matrix_cases=lambda:remap_spline_value(old_matrix_cases(),primary.system_name)
                target=folder/(scene+'.poses.json')
                try:
                    parity.main(native,folder/scene,reference,target,extended=True,source_matrices=True,standalone=False)
                except AssertionError as error: item.setdefault('source_failures',[]).append(str(error))
                data=json.loads(target.read_text(encoding='utf-8'))
                item['poses'].append(dict(scene=scene,**{k:v for k,v in data.items() if k!='matrices'}))
                save()
            item['stage']='complete';save()
        report['status']='passed' if all(row['lifecycle']['status']=='passed' and not row.get('source_failures') for row in report['configurations']) else 'failed'
    except Exception: report.update(status='failed',traceback=traceback.format_exc())
    finally:
        parity.CASES=old_cases;parity.matrix_cases=old_matrix_cases;save()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish: Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish: c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
