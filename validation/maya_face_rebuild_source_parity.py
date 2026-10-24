"""Unmodified MEL complete Face rebuild from the saved authored input."""
from pathlib import Path
import json
import os
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT = ROOT/'validation/results/face-rebuild-source-parity'


def prepare_source_ui(c):
    from maya import mel
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from adv_py.application.face_pre import FacePreRole
    host = MayaOriginalFaceBuildHost()
    def names(nodes):
        return ' '.join(c.ls(node,shortNames=True)[0] for node in nodes)
    mask = c.getAttr('FaceFitSkeleton.Mask') if c.objExists('FaceFitSkeleton.Mask') else ''
    for field,value in (('Mask',mask),('Face','FaceMesh'),('AllHead',names(host.read_face_objects(FacePreRole.ALL_HEAD))),
        ('HeadJoint','Head_M'),('SkinCluster','HeadSkin'),('RightEye','EyeRight'),('LeftEye','EyeLeft'),
        ('UpperTeeth','UpperTeethMesh'),('LowerTeeth','LowerTeethMesh'),('Tongue','TongueMesh'),
        ('Eyebrow',names(host.read_original_face_parts('Eyebrow'))),
        ('Eyelash',names(host.read_original_face_parts('EyeLash'))),('Extras',names(host.read_original_face_parts('Extras')))):
        c.textField('asFace'+field+'TextField',edit=True,text=value)
    multi=bool(c.getAttr('FaceFitSkeleton.MultiSkinClusters'))
    for control,value in (('asBodyOffsetParentMatrixCheckBox',True),('asFaceMultiSkinClustersCheckBox',multi),
        ('asFaceNonSymCheckBox',False),('asFaceGameEngineCheckBox',False),
        ('asFaceManuallyRunRestoreStepCheckBox',False)):
        if c.checkBox(control,exists=True): c.checkBox(control,edit=True,value=value)
    for option in ('All','SkinWeights','AddedJoints','HeadSquash','CorrectiveShapes',
                   'DrivingSystems','CurveShapes','CustomControls','CustomOrient'):
        c.checkBox('asFaceKeep'+option+'CheckBox',edit=True,value=True)
    c.optionMenu('asFaceRigTypeOptionMenu',edit=True,value='Joints')
    if not c.objExists('FitSkeleton'):
        c.createNode('transform',name='FitSkeleton')
        mel.eval('asEnsureFitSkeletonAttributes;')
        c.setAttr('FitSkeleton.useOffsetParentMatrix',True)
    # The source full build refreshes this UI after every stage.
    mel.eval('asFaceUpdateInfo 0;')


def observe_head():
    """Actual Head joint motion, including rotation and nonuniform scale."""
    from maya import cmds as c
    channels = ('tx','ty','tz','rx','ry','rz','sx','sy','sz')
    values = {attr:c.getAttr('Head_M.'+attr) for attr in channels}
    poses = [({},'neutral'),({'tx':2},'translate'),({'rx':20},'rotate_x'),
        ({'ry':-15},'rotate_y'),({'rz':35},'rotate_z'),
        ({'sx':1.2,'sy':1.2,'sz':1.2},'uniform_scale'),
        ({'sx':1.2,'sy':.9,'sz':1.1},'nonuniform_scale'),
        ({'tx':.7,'ry':17,'rz':-11,'sx':1.2,'sy':.9,'sz':1.1},'combined')]
    result = {}; state=c.undoInfo(query=True,state=True)
    c.undoInfo(stateWithoutFlush=False)
    try:
        for changes,label in poses:
            for attr,value in values.items(): c.setAttr('Head_M.'+attr,changes.get(attr,value))
            c.dgdirty(allPlugs=True)
            result[label]={'groups':{node:c.xform(node,query=True,worldSpace=True,matrix=True)
                for node in ('FaceMotionSystem','FaceDeformationFollowHead','EyeAimFollowHead','LipFollowHeadConstrained')},
                'meshes':{mesh:c.xform(mesh+'.vtx[*]',query=True,worldSpace=True,translation=True)
                    for mesh in ('FaceMesh','EyeRight','EyeLeft','UpperTeethMesh','LowerTeethMesh','TongueMesh',
                                 'EyebrowRight','EyebrowLeft','EyeLashRight','EyeLashLeft')}}
    finally:
        for attr,value in values.items(): c.setAttr('Head_M.'+attr,value)
        c.undoInfo(stateWithoutFlush=state)
    return result


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel,utils
    from maya_face_mixed_parity import load_project_native_plugin
    from maya_face_conversion_parity import skin_snapshot,observe,compare
    OUTPUT.mkdir(parents=True,exist_ok=True)
    report={'status':'running','pid':os.getpid(),'cases':{}}
    def write(): (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    write()
    try:
        load_project_native_plugin()
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
        cases=os.environ.get('ADV_FACE_REBUILD_CASES','ordinary,multi').split(',')
        for name in cases:
            reuse=os.environ.get('ADV_FACE_REBUILD_REUSE')=='1'
            source_scene=(OUTPUT/(name+'-native.mb') if reuse else
                ROOT/('validation/results/face-rebuild-lifecycle/'+name+'-input.mb'))
            c.file(str(source_scene),open=True,force=True,executeScriptNodes=False)
            row={'completed_stages':[],'reused_native':reuse};report['cases'][name]=row;write()
            if not reuse:
                prepare_source_ui(c)
                # Execute the original full-build sequence, with no manual prep.
                for index in range(1,31):
                    label=c.text('stepBuild%dText'%index,query=True,label=True)
                    procedure='asFace'+label.split(':',1)[1].strip()
                    mel.eval(procedure+';');mel.eval('asStepBuildComplete %d;'%index)
                    row['completed_stages'].append(procedure);write()
            row['authored_lip_weight']=c.skinPercent('LipSC' if name=='multi' else 'HeadSkin',
                'FaceMesh.vtx[100]',query=True,transform='upperLipJoint0_M') if name=='multi' else None
            native={'skin':skin_snapshot(include_non_mesh=True),'poses':observe(),'head':observe_head()}
            native['joints']={joint:c.xform(joint,query=True,worldSpace=True,matrix=True) for joint in c.ls(type='joint')}
            (OUTPUT/(name+'-native.json')).write_text(json.dumps(native),encoding='utf8')
            c.file(rename=str(OUTPUT/(name+'-native.mb')));c.file(save=True,type='mayaBinary',force=True)
            python_scene=ROOT/('validation/results/face-rebuild-lifecycle/'+name+'-rebuilt.mb')
            if python_scene.exists():
                c.file(str(python_scene),open=True,force=True,executeScriptNodes=False)
                row['pose_error']=compare(native['poses'],observe())
                row['head_pose_error']=compare(native['head'],observe_head())
                python_skin=skin_snapshot(include_non_mesh=True)
                (OUTPUT/(name+'-python-joints.json')).write_text(json.dumps(
                    {joint:c.xform(joint,query=True,worldSpace=True,matrix=True) for joint in c.ls(type='joint')}),encoding='utf8')
                (OUTPUT/(name+'-python-skin.json')).write_text(json.dumps(python_skin),encoding='utf8')
                row['skin_error']=compare(native['skin'],python_skin)
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
    finally:
        write()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:Path(completion).write_text(json.dumps({'pid':os.getpid(),'status':report['status']}),encoding='utf8')
        if quit_on_finish:utils.executeDeferred(c.quit,force=True)
