"""Actual source Sub duplication versus shared production helper, six cases."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-sub-duplication-current'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[],
        scope='Unedited asCreateController Sub block versus production duplicate helper: FK/IK, Euler orders 0/3/5, compound rotation, native transform and shape flags. Not a complete fresh Body rebuild.')
    try:
        text=(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').read_text(encoding='utf-8')
        proc=text.index('global proc asCreateController (')
        start=text.index('if ($sub)\n',proc);end=text.index('if ($extra)\n',start)
        mel.eval('global proc advNativeSubDuplicate(string $type,string $name,string $side){int $sub=1;'+text[start:end]+'}')
        for kind in ('FK','IK'):
            for order in (0,3,5):
                states=[]
                for mode in ('native','python'):
                    c.file(new=True,force=True)
                    parent=c.createNode('transform',name='ProbeParent')
                    if mode=='python':c.xform(parent,translation=(5,-2,3),rotation=(12,-20,35))
                    control=c.circle(name=kind+'Probe_R',constructionHistory=False)[0]
                    c.parent(control,parent,relative=True)
                    c.setAttr(control+'.rotateOrder',order)
                    c.setAttr(control+'.visibility',True,keyable=False,channelBox=True)
                    c.setAttr(control+'Shape.overrideEnabled',True)
                    sub=kind+'SubProbe_R';path='|ProbeParent|'+control+'|'+sub
                    if mode=='native':mel.eval('advNativeSubDuplicate "'+kind+'" "Probe" "_R";')
                    else:MayaBodyBuildHost()._create_body_sub_control('|ProbeParent|'+control,sub,path)
                    if mode=='native':c.xform(parent,translation=(5,-2,3),rotation=(12,-20,35))
                    assert c.getAttr(sub+'.rotateOrder')==order
                    assert not c.getAttr(sub+'.visibility',keyable=True) and c.getAttr(sub+'.visibility',channelBox=True)
                    c.setAttr(sub+'.rotate',20,-35,15,type='double3')
                    joint=c.createNode('joint',name='DrivenProbe');c.orientConstraint(sub,joint,maintainOffset=False)
                    states.append(dict(sub=c.xform(sub,query=True,worldSpace=True,matrix=True),
                        joint=c.xform(joint,query=True,worldSpace=True,matrix=True),
                        cvs=c.xform(sub+'.cv[*]',query=True,objectSpace=True,translation=True),
                        visible=c.getAttr(sub+'Shape.visibility'),color=c.getAttr(sub+'Shape.overrideColor')))
                a,b=states;assert a['visible']==b['visible'] and a['color']==b['color']==30
                errors={name:max(abs(x-y) for x,y in zip(a[name],b[name])) for name in ('sub','joint','cvs')}
                assert max(errors.values())<=1e-8,errors
                report['cases'].append(dict(kind=kind,rotate_order=order,errors=errors,status='passed'))
        native_scene=ROOT/'validation/results/source-rp-sub-constructor-current/native-sub.mb'
        if native_scene.exists():
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            report['native_sub_handle_paths']={limb+'_'+side:c.ls('IK'+limb+'Handle_'+side,long=True)[0]
                for limb in ('Arm','Leg') for side in ('R','L')}
        report['status']='passed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
