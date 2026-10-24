"""Authored left/right Follow, spaces, named targets and constraints against MEL."""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-non-symmetry-attachments-opm-current'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from maya_original_biped_current_smoke import main as build
    from maya_source_rp_sub_constructor import snapshot,difference
    OUT.mkdir(parents=True,exist_ok=True)
    previous=json.loads((OUT/'report.json').read_text(encoding='utf-8')) if os.environ.get('ADV_NON_SYMMETRY_ATTACHMENTS_OPM_POSES_ONLY')=='1' else None
    report=dict(status='running',pid=os.getpid(),scope='OPM authored asymmetric Fit AimAt, self/target Up Object and 0/5/10 weights; GeoAttach point/orient/parent and Pin with attachment meshes; full preserved rebuild; no FBX.')
    from maya.api import OpenMaya as om
    messages=[]
    def capture_output(message,kind,*unused):
        messages.append((int(kind),message))
        if len(messages)>100:del messages[:-100]
    callback=om.MCommandMessage.addCommandOutputCallback(capture_output)
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None
        for name in ('asHaveRanThisVersion','asDock')}
    def checkpoint(stage):
        report['stage']=stage
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        c.file(str(ROOT/'validation/results/source-non-symmetry-current/asymmetric-input.ma'),open=True,force=True,executeScriptNodes=False)
        for side,x in (('R',-4.),('L',4.)):
            mesh=c.polyPlane(name='Attachment_'+side,width=20,height=20,subdivisionsX=6,subdivisionsY=6)[0]
            c.setAttr(mesh+'.translate',x,12.,0.,type='double3')
        rows=(('IndexFinger1','geoAttach','Attachment_R'),('IndexFinger1_NonSymmetry','geoAttach','Attachment_R'),
              ('RingFinger1','geoAttach','Attachment_R'),('RingFinger1_NonSymmetry','geoAttach','Attachment_R'),
              ('PinkyFinger1','proximityPin','Attachment_R'),('PinkyFinger1_NonSymmetry','proximityPin','Attachment_R'),
              ('MiddleFinger1','aimAt','IndexFinger1'),('MiddleFinger1_NonSymmetry','aimAt','RingFinger1'))
        for node,attribute,value in rows:
            if not c.objExists(node+'.'+attribute):
                if isinstance(value,str):c.addAttr(node,longName=attribute,attributeType='enum',enumName=value,keyable=True)
                else:c.addAttr(node,longName=attribute,attributeType='bool' if isinstance(value,bool) else 'double')
            if isinstance(value,str):c.setAttr(node+'.'+attribute,0)
            else:c.setAttr(node+'.'+attribute,value)
        for node in ('MiddleFinger1','MiddleFinger1_NonSymmetry'):
            for attr, labels in (('aimAxis','x:y:z'),('aimUpAxis','x:y:z'),('aimUpObject','self:target')):
                if not c.objExists(node+'.'+attr):c.addAttr(node,longName=attr,attributeType='enum',enumName=labels,keyable=True)
            c.setAttr(node+'.aimAxis',0);c.setAttr(node+'.aimUpAxis',1)
            c.setAttr(node+'.aimUpObject',0 if node=='MiddleFinger1' else 1)
        for node,mode in (('IndexFinger1',0),('IndexFinger1_NonSymmetry',1),('RingFinger1',2),('RingFinger1_NonSymmetry',2)):
            c.addAttr(node,longName='geoAttachMode',attributeType='enum',enumName='point:orient:parent',keyable=True)
            c.setAttr(node+'.geoAttachMode',mode)
        c.setAttr('FitSkeleton.useOffsetParentMatrix',True)
        report['authored_fields']=rows
        input_scene=OUT/'input.ma'
        c.file(rename=str(input_scene));c.file(save=True,type='mayaAscii',force=True)
        checkpoint('original_build')
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1))
        c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
        mel.eval('AdvancedSkeleton;')
        for field in ('SubControllers','ExtraControllers','OffsetParentMatrix'):
            c.checkBox('asBody'+field+'CheckBox',edit=True,value=field=='OffsetParentMatrix')
        assert mel.eval('asGetOpm;') == 1
        c.scriptEditorInfo(historyFilename=str(OUT/'native-history.log'),writeHistory=True,suppressErrors=False,suppressWarnings=False)
        native_scene=OUT/'native.mb'
        if os.environ.get('ADV_REUSE_NON_SYMMETRY_ATTACHMENTS_OPM_REFERENCE')=='1':
            assert native_scene.is_file()
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            report['native_reference_pid']=int(os.environ['ADV_ATTACHMENTS_OPM_NATIVE_PID'])
        else:
            c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
            c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
        neutral=snapshot()
        poses=(
            ('geo_right_move',(('Attachment_R.translateX','Attachment_R.translateX',-2.),)),
            ('geo_left_turn',(('Attachment_L.rotateZ','Attachment_L.rotateZ',20.),)),
            ('geo_point_half',(('FKIndexFinger1_R.attach','AdvPy_IndexFinger1_RFK.attach',5.),('Attachment_R.translateX','Attachment_R.translateX',-2.))),
            ('geo_orient_half',(('FKIndexFinger1_L.attach','AdvPy_IndexFinger1_LFK.attach',5.),('Attachment_L.rotateZ','Attachment_L.rotateZ',20.))),
            ('geo_parent_zero',(('FKRingFinger1_R.attach','AdvPy_RingFinger1_RFK.attach',0.),('Attachment_R.translateX','Attachment_R.translateX',-2.))),
            ('geo_parent_half',(('FKRingFinger1_L.attach','AdvPy_RingFinger1_LFK.attach',5.),('Attachment_L.rotateZ','Attachment_L.rotateZ',20.))),
            ('pin_scale',(('Attachment_R.scaleX','Attachment_R.scaleX',1.3),('Attachment_R.scaleZ','Attachment_R.scaleZ',.8))),
            ('pin_half',(('FKPinkyFinger1_L.pin','AdvPy_PinkyFinger1_LFK.pin',5.),('Attachment_L.translateY','Attachment_L.translateY',13.))),
            ('pin_zero',(('FKPinkyFinger1_R.pin','AdvPy_PinkyFinger1_RFK.pin',0.),('Attachment_R.translateX','Attachment_R.translateX',-2.))),
            ('aim_attachment_half',(('FKMiddleFinger1_L.aimAt','AdvPy_MiddleFinger1_LFK.aimAt',5.),('Attachment_R.translateX','Attachment_R.translateX',-2.))))
        native={}
        for label,edits in poses:
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            for a,b,value in edits:c.setAttr(a,value)
            native[label]=snapshot()
            assert difference(neutral,native[label])>1e-3,label
        checkpoint('python_build_and_rebuild')
        if previous is not None:
            report['lifecycle']=previous['lifecycle'];assert report['lifecycle']['status']=='passed'
            report['lifecycle_pid']=previous.get('lifecycle_pid',previous['pid'])
        else:
            import adv_py.adapters.maya_source_fit_proximity_pin as pin_module
            capture_pin=pin_module.capture
            def diagnosed_capture(host,spec,state):
                ok=capture_pin(host,spec,state)
                if not ok:
                    (OUT/'pin-capture.json').write_text(json.dumps(dict(spec=repr(spec),factor=host._cmds.getAttr(spec.weight_node+'.conversionFactor'),flags={a:host._cmds.getAttr(spec.blend_matrix+'.target[0].'+a) for a in ('translateWeight','rotateWeight','scaleWeight','shearWeight')},sources={plug:host._cmds.connectionInfo(plug,sourceFromDestination=True) for plug in (spec.weight_node+'.input',spec.blend_matrix+'.target[0].weight',spec.receiver+'.offsetParentMatrix')}),indent=2),encoding='utf-8')
                return ok
            pin_module.capture=diagnosed_capture
            report['lifecycle']=build(input_scene,OUT/'python',rebuild=True,export=False,bendy=True,opm=True,standalone=False,
                reuse_scene=os.environ.get('ADV_ATTACHMENTS_OPM_REUSE_BUILD')=='1')
        report['poses']=[]
        for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
            c.file(str(OUT/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
            actual=snapshot()
            report.setdefault('neutral_errors',{})[scene]=difference(neutral,actual)
            errors={name:max(abs(a-b) for a,b in zip(neutral[name],actual[name])) for name in neutral}
            report.setdefault('neutral_largest',{})[scene]=sorted(errors.items(),key=lambda row:row[1],reverse=True)[:12]
            report.setdefault('neutral_matrices',{})[scene]={'native':neutral,'python':actual}
            for label,edits in poses:
                c.file(str(OUT/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                for a,b,value in edits:c.setAttr(b,value)
                report['poses'].append(dict(scene=scene,case=label,maximum_error=difference(native[label],snapshot())))
        report['status']='passed' if max(report['neutral_errors'].values())<=1e-4 and all(row['maximum_error']<=1e-4 for row in report['poses']) else 'failed'
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc(),joint_count=len(c.ls(type='joint') or []),root_exists=c.objExists('Root_M'),fit_exists=c.objExists('FitSkeleton'),script_location=mel.eval('asGetScriptLocation;'))
    finally:
        c.scriptEditorInfo(writeHistory=False)
        report['maya_messages']=messages
        om.MMessage.removeCallback(callback)
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
