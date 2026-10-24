"""Native Aim channels plus fresh/retained character and authored side animation."""
from pathlib import Path
import json, os, shutil, sys, traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
OUT = ROOT/'validation/results/source-fit-aim-controls-current'


def main(*, standalone=False, quit_on_finish=True):
    from maya import cmds as c
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_body_fit_aim import SOURCE_SIDE_CHANNELS
    from adv_py.core.body_fit_aim import capture_body_fit_aim_layouts, TRANSLATION, TRANSFORM
    import maya_source_rp_follow_lifecycle as fresh
    from maya_original_biped_current_smoke import main as build
    import maya_original_body_pose_compare as parity
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(), stage='fresh-character')
    def save(): (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def control_state(node):
        attrs = (*TRANSFORM, 'visibility', 'translate')
        return {attr: (c.getAttr(node+'.'+attr,lock=True),c.getAttr(node+'.'+attr,keyable=True)) for attr in attrs}
    try:
        save()
        assert fresh.main(standalone=False, quit_on_finish=False) == 0
        fresh_report = json.loads((fresh.OUT/'report.json').read_text(encoding='utf-8'))
        report['fresh'] = fresh_report
        folder = fresh.OUT/'traditional'
        native = ROOT/'validation/results/source-spline-part-lifecycle-current/traditional/native.mb'
        c.file(str(native),open=True,force=True,executeScriptNodes=False)
        native_controls = {side:control_state('AimEye_'+side) for side in ('R','L')}
        report['source_control_states'] = native_controls
        report['saved_source_controls_match'] = []
        for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
            c.file(str(folder/scene),open=True,force=True,executeScriptNodes=False)
            registration = MayaBodyBuildHost().read_character_registration()
            layouts = capture_body_fit_aim_layouts(registration.channels)
            assert len(layouts)==1 and layouts[0].stem=='Eye'
            assert layouts[0].center_attributes == TRANSFORM+('follow',)
            assert layouts[0].side_channels == (('R',TRANSLATION),('L',TRANSLATION)), layouts
            for side in ('R','L'):
                control = 'AdvPy_AimEye_'+side
                assert control_state(control)==native_controls[side]
                assert c.getAttr(control+'.'+SOURCE_SIDE_CHANNELS) and c.getAttr(control+'.'+SOURCE_SIDE_CHANNELS,lock=True)
                assert not c.objExists(control+'.follow')
            report['saved_source_controls_match'].append(scene)
        report['stage']='retained-legacy-animation';save()
        legacy = OUT/'legacy';legacy.mkdir(exist_ok=True)
        prior = ROOT/'validation/results/source-fit-aim-follow-lifecycle-final-current/traditional/original-biped-current.mb'
        shutil.copy2(prior,legacy/'original-biped-current.mb')
        c.file(str(legacy/'original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
        old_registration = MayaBodyBuildHost().read_character_registration()
        old_layouts = capture_body_fit_aim_layouts(old_registration.channels)
        assert old_layouts[0].side_channels == (('L',TRANSFORM),('R',TRANSFORM))
        # Legacy Scale starts at one. A zero scale would invalidate the input.
        c.setKeyframe('AdvPy_AimEye_R',attribute='scaleY',time=1,value=1.)
        c.setKeyframe('AdvPy_AimEye_R',attribute='scaleY',time=5,value=1.15)
        c.file(save=True,type='mayaBinary',force=True)
        report['legacy'] = build(prior,legacy,rebuild=True,export=False,standalone=False,reuse_scene=True,
            additional_animation=(('AdvPy_AimEye_R','rotateZ',17.),('AdvPy_AimEye_L','rotateY',-11.)))
        c.file(str(legacy/'original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
        original = MayaBodyBuildHost().read_character_registration()
        bodies = tuple(node.path for node in original.body)
        frames = {}
        for frame in (1,3,5):
            c.currentTime(frame)
            frames[frame] = {node:c.xform(node,q=True,ws=True,matrix=True) for node in bodies}
        c.file(str(legacy/'original-biped-rebuilt.mb'),open=True,force=True,executeScriptNodes=False)
        retained = MayaBodyBuildHost().read_character_registration()
        assert capture_body_fit_aim_layouts(retained.channels)==old_layouts
        error = 0.
        for frame,values in frames.items():
            c.currentTime(frame)
            for node,expected in values.items():
                error=max(error,max(abs(a-b) for a,b in zip(expected,c.xform(node,q=True,ws=True,matrix=True))))
        assert error<=1e-4, error
        for plug, expected in (('AdvPy_AimEye_R.scaleY',1.15),
                               ('AdvPy_AimEye_R.rotateZ',17.),
                               ('AdvPy_AimEye_L.rotateY',-11.)):
            assert abs(c.getAttr(plug)-expected)<=1e-10, (plug,c.getAttr(plug),expected)
        report['legacy_authored_body_frames_maximum_error']=error
        report['legacy_retained_layout']=repr(old_layouts)
        report['legacy_poses']=[]
        old_cases=parity.CASES; old_matrix=parity.matrix_cases
        try:
            parity.CASES=(('neutral',()),
                ('aim_right_move',(('AimEye_R.translateX','AdvPy_AimEye_R.translateX',.5),)),
                ('aim_left_move',(('AimEye_L.translateY','AdvPy_AimEye_L.translateY',-.5),)),
                ('aim_center_scale',(('AimEye_M.scaleX','AdvPy_AimEye_M.scaleX',1.1),)))
            from adv_py.core.spline_names import remap_spline_value
            primary=next(plan for plan in (retained.spine,*retained.additional_spines) if plan and plan.system_name=='Spine_M')
            parity.matrix_cases=lambda:remap_spline_value(old_matrix(),primary.system_name)
            for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
                target=legacy/(scene+'.poses.json')
                parity.main(native,legacy/scene,folder/'reference.json',target,extended=True,source_matrices=True,standalone=False)
                data=json.loads(target.read_text(encoding='utf-8'))
                report['legacy_poses'].append({k:v for k,v in dict(scene=scene,**data).items() if k!='matrices'})
        finally:
            parity.CASES=old_cases;parity.matrix_cases=old_matrix
        report.update(status='passed',stage='complete')
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc())
    finally:
        save()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
