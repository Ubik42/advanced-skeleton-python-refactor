"""Native Fit Non-Symmetry toggle and asymmetric full Body lifecycle."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-non-symmetry-current'


def fit_snapshot(c,namespace=''):
    prefix=namespace+':' if namespace else ''
    root=c.ls(prefix+'Root',long=True)[0]
    joints=[root]+(c.listRelatives(root,allDescendents=True,type='joint',fullPath=True) or [])
    return {node.rsplit('|',1)[-1].removeprefix(prefix):dict(
        parent=(c.listRelatives(node,parent=True,fullPath=True) or [''])[0].rsplit('|',1)[-1].removeprefix(prefix),
        matrix=c.xform(node,query=True,worldSpace=True,matrix=True),
        attrs={attr:c.getAttr(node+'.'+attr) if c.objExists(node+'.'+attr) else None
               for attr in ('rotateOrder','type','otherType','noMirror','noMirrorLeft')})
        for node in joints}


def fit_error(a,b):
    assert a.keys()==b.keys(),(a.keys()-b.keys(),b.keys()-a.keys())
    for name in a:
        assert a[name]['parent']==b[name]['parent'],name
        assert a[name]['attrs']==b[name]['attrs'],(name,a[name]['attrs'],b[name]['attrs'])
    return max(abs(x-y) for name in a for x,y in zip(a[name]['matrix'],b[name]['matrix']))


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    from maya_source_rp_sub_constructor import snapshot,difference
    from maya_original_biped_current_smoke import main as build
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[],scope=
        'Unedited asCreateNonSymmetryJoints creation/removal with original biped Fit, '
        'authored flags and namespace; asymmetrically edited left Wrist/Hip Body source poses, '
        'Skin/animation/save/reopen/preserving rebuild and Undo/Redo; proxy mesh, no FBX.')
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None
             for name in ('asHaveRanThisVersion','asDock')}
    def checkpoint(stage):
        report['stage']=stage
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1))
        c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
        source=ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'
        # Original UI supplies the attribute selector used by the procedure.
        c.file(str(source),open=True,force=True,executeScriptNodes=False);mel.eval('AdvancedSkeleton;')
        input_scene=OUT/'asymmetric-input.ma'
        native_scene=OUT/'native-body.mb'
        reuse=os.environ.get('ADV_REUSE_NON_SYMMETRY')=='1'
        if reuse:
            previous=json.loads((OUT/'report.json').read_text(encoding='utf-8'))
            assert len(previous['cases'])==3 and all(row['status']=='passed' for row in previous['cases'])
            assert input_scene.is_file() and native_scene.is_file()
            report['cases']=previous['cases']
            report['reused_fit_native_pid']=previous.get('reused_fit_native_pid',previous['pid'])
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
        else:
            checkpoint('fit_toggle_source_comparison')
            for namespace,authored in (('',False),('OtherRig',False),('',True)):
                states={};lifecycle_errors={}
                for mode in ('native','python'):
                    report['active_case']=dict(namespace=namespace,authored_flags=authored,mode=mode)
                    c.namespace(set=':');c.namespace(relativeNames=False)
                    if namespace:
                        c.file(new=True,force=True)
                        c.file(str(source),i=True,namespace=namespace,mergeNamespacesOnClash=False,
                               executeScriptNodes=False)
                    else:c.file(str(source),open=True,force=True,executeScriptNodes=False)
                    prefix=namespace+':' if namespace else ''
                    if authored:
                        for attr,value in (('noMirror',True),('noMirrorLeft',False)):
                            plug=prefix+'Scapula.'+attr
                            if not c.objExists(plug):c.addAttr(prefix+'Scapula',longName=attr,attributeType='bool',keyable=True)
                            c.setAttr(plug,value)
                    c.undoInfo(state=True)
                    host=MayaBodyBuildHost(namespace=namespace)
                    def toggle():
                        if mode=='python':return host.toggle_fit_non_symmetry_joints()
                        c.undoInfo(openChunk=True,chunkName='Original Non-Symmetry toggle')
                        try:
                            c.namespace(set=':'+namespace);c.namespace(relativeNames=bool(namespace))
                            mel.eval('asCreateNonSymmetryJoints;')
                        finally:
                            c.namespace(relativeNames=False);c.namespace(set=':');c.undoInfo(closeChunk=True)
                    before=fit_snapshot(c,namespace)
                    toggle();created=fit_snapshot(c,namespace)
                    assert any(name.endswith('_NonSymmetry') for name in created)
                    c.undo();creation_undo=fit_error(before,fit_snapshot(c,namespace))
                    c.redo();assert fit_error(created,fit_snapshot(c,namespace))<=1e-6
                    scene=OUT/(mode+'-'+(namespace or 'root')+'-'+str(authored)+'.mb')
                    c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
                    c.file(str(scene),open=True,force=True,executeScriptNodes=False)
                    assert fit_error(created,fit_snapshot(c,namespace))<=1e-6
                    if mode=='native' and not namespace and not authored:
                        c.setAttr('Wrist_NonSymmetry.translateY',c.getAttr('Wrist_NonSymmetry.translateY')+3.)
                        c.setAttr('Hip_NonSymmetry.rotateZ',c.getAttr('Hip_NonSymmetry.rotateZ')+5.)
                        mel.eval('asFitModeManualUpdate;')
                        for attr in ('useOffsetParentMatrix','subControllers','extraControllers'):
                            if not c.objExists('FitSkeleton.'+attr):
                                c.addAttr('FitSkeleton',longName=attr,attributeType='bool')
                            c.setAttr('FitSkeleton.'+attr,False)
                        input_scene=OUT/'asymmetric-input.ma'
                        c.file(rename=str(input_scene));c.file(save=True,type='mayaAscii',force=True)
                        # Reopen the unedited toggle fixture for removal parity.
                        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
                    toggle();removed=fit_snapshot(c,namespace)
                    assert not any(name.endswith('_NonSymmetry') for name in removed)
                    c.undo();assert fit_error(created,fit_snapshot(c,namespace))<=1e-6
                    c.redo();assert fit_error(removed,fit_snapshot(c,namespace))<=1e-6
                    states[mode]=(created,removed)
                    lifecycle_errors[mode]=dict(creation_undo_error=creation_undo)
                errors=[fit_error(a,b) for a,b in zip(states['native'],states['python'])]
                assert max(errors)<=1e-6,errors
                report['cases'].append(dict(namespace=namespace,authored_flags=authored,
                    create_error=errors[0],remove_error=errors[1],lifecycle=lifecycle_errors,
                    creation_undo_precision_passed=all(row['creation_undo_error']<=1e-6 for row in lifecycle_errors.values()),
                    redo_remove_undo_and_reopen_passed=True,status='passed'))
            checkpoint('native_asymmetric_body')
            c.file(str(input_scene),open=True,force=True,executeScriptNodes=False)
            for field in ('SubControllers','ExtraControllers','OffsetParentMatrix'):
                c.checkBox('asBody'+field+'CheckBox',edit=True,value=False)
            for joint in ('Shoulder','Shoulder_NonSymmetry','Elbow','Elbow_NonSymmetry'):
                if not c.objExists(joint+'.bendyCtrls'):c.addAttr(joint,longName='bendyCtrls',attributeType='long')
                c.setAttr(joint+'.bendyCtrls',3)
            c.file(rename=str(input_scene));c.file(save=True,type='mayaAscii',force=True)
            c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
            native_scene=OUT/'native-body.mb';c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
        native=snapshot()
        pose_cases=(('left_fk',(('FKShoulder_L.rotateZ','AdvPy_Shoulder_LFK.rotateZ',20.),)),
            ('left_ik',(('FKIKArm_L.FKIKBlend','FKIKArm_L.FKIKBlend',10.),
                        ('IKArm_L.translateY','AdvPy_ArmIK_L.translateY',.3))),
            ('right_fk',(('FKShoulder_R.rotateY','AdvPy_Shoulder_RFK.rotateY',15.),)),
            ('left_leg',(('IKLeg_L.translateZ','AdvPy_LegIK_L.translateZ',.3),)),
            ('left_stretch',(('FKIKArm_L.FKIKBlend','FKIKArm_L.FKIKBlend',10.),
                ('IKArm_L.translateX','AdvPy_ArmIK_L.translateX',1.),
                ('IKArm_L.stretchy','AdvPy_ArmIK_L.stretchy',10.))),
            ('left_anti_pop',(('FKIKArm_L.FKIKBlend','FKIKArm_L.FKIKBlend',10.),
                ('IKArm_L.translateY','AdvPy_ArmIK_L.translateY',-.5),
                ('IKArm_L.antiPop','AdvPy_ArmIK_L.antiPop',10.))),
            ('left_pole_lock',(('FKIKArm_L.FKIKBlend','FKIKArm_L.FKIKBlend',10.),
                ('PoleArm_L.lock','AdvPy_ArmPV_L.lock',5.))))
        native_poses={}
        for label,changes in pose_cases:
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            for a,b,value in changes:c.setAttr(a,value)
            native_poses[label]=snapshot()
            assert difference(native,native_poses[label])>1e-3,label
        from adv_py.adapters import maya_character_properties as properties
        from adv_py.adapters.maya_character_preservation import capture_extension
        from adv_py.core.body_character_global import fit_character_height
        original_property_plan=properties.plan
        def inspect_properties(host,original,namespace,**kwargs):
            target=MayaBodyBuildHost(namespace=namespace)
            rows={row.path:row for row in original.properties}
            main=next(path for path in rows if path.endswith('|AdvPy_Global'))
            old={a[0]:a for a in rows[main].attributes}
            new={a[0]:a for a in capture_extension(target,main).attributes}
            points=target.capture_fit_hierarchy('FitSkeleton').joints
            report['staged_height']=dict(original=old.get('height'),replacement=new.get('height'),
                live_fit_height=fit_character_height(tuple(node.world_position for node in points)),
                extrema=sorted(((node.short_name,node.world_position) for node in points),
                               key=lambda row:row[1][1])[:2]+sorted(
                    ((node.short_name,node.world_position) for node in points),key=lambda row:row[1][1])[-2:])
            checkpoint('staged_property_transfer')
            return original_property_plan(host,original,namespace,**kwargs)
        properties.plan=inspect_properties
        checkpoint('python_asymmetric_body_lifecycle')
        python=OUT/'python'
        if os.environ.get('ADV_NON_SYMMETRY_POSES_ONLY')=='1':
            report['lifecycle']=previous['lifecycle']
            assert report['lifecycle']['status']=='passed'
            report['lifecycle_pid']=previous.get('lifecycle_pid',previous['pid'])
        else:
            report['lifecycle']=build(input_scene,python,rebuild=True,export=False,bendy=True,standalone=False,
                reuse_scene=os.environ.get('ADV_REUSE_NON_SYMMETRY_PYTHON')=='1')
        report['neutral_errors']={}
        report['poses']=[]
        for scene_name in ('original-biped-current.mb','original-biped-rebuilt.mb'):
            c.file(str(python/scene_name),open=True,force=True,executeScriptNodes=False)
            c.currentTime(1)
            report['neutral_errors'][scene_name]=difference(native,snapshot())
            for label,changes in pose_cases:
                c.file(str(python/scene_name),open=True,force=True,executeScriptNodes=False)
                c.currentTime(1)
                for a,b,value in changes:c.setAttr(b,value)
                error=difference(native_poses[label],snapshot())
                report['poses'].append(dict(scene=scene_name,case=label,maximum_error=error))
        report['neutral_error']=max(report['neutral_errors'].values())
        report['status']=('passed' if report['neutral_error']<=1e-4
            and all(row['maximum_error']<=1e-4 for row in report['poses']) else 'failed')
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        if 'original_property_plan' in locals():properties.plan=original_property_plan
        c.namespace(relativeNames=False);c.namespace(set=':')
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
