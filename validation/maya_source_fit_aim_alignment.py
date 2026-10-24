"""Source AimAt alignment and parent-local composition under nonuniform scale."""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-fit-aim-alignment-current'

def main(standalone=False,quit_on_finish=False):
    from maya import cmds as c,mel
    from types import SimpleNamespace as NS
    from adv_py.core.body_fit_aim_at import BodyFitAimAtSpec,BodyFitAimAtState
    from adv_py.adapters.maya_source_fit_aim_at import create,capture
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),scope='Native asAlign + two-target constraint against source Python AimAt, nonuniform parents and existing receiver OPM',cases=[])
    def matrix(node):return tuple(c.xform(node,query=True,worldSpace=True,matrix=True))
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        for up in ('self','target'):
          for sign in (1,-1):
            c.file(new=True,force=True)
            fixtures=[]
            for prefix in ('N','P'):
                root=c.createNode('transform',name=prefix+'Root')
                c.setAttr(root+'.translate',2,3,1,type='double3');c.setAttr(root+'.rotate',12,-7,16,type='double3')
                offset=c.createNode('transform',name=prefix+'Offset',parent=root)
                c.setAttr(offset+'.translate',1,4,2,type='double3');c.setAttr(offset+'.scale',.7,1.3,.9,type='double3')
                receiver=c.createNode('transform',name=prefix+'Receiver',parent=offset)
                c.setAttr(receiver+'.inheritsTransform',os.environ.get('ADV_ATTACHMENT_NO_INHERIT')!='1')
                c.setAttr(receiver+'.translate',.3,-.2,.1,type='double3');c.setAttr(receiver+'.rotate',7,11,-4,type='double3')
                old=c.createNode('composeMatrix',name=prefix+'OldOPM')
                c.setAttr(old+'.inputTranslate',.2,.3,-.1,type='double3');c.setAttr(old+'.inputRotate',3,5,2,type='double3')
                c.connectAttr(old+'.outputMatrix',receiver+'.offsetParentMatrix')
                control=c.createNode('transform',name=prefix+'FK',parent=receiver)
                target_parent=c.createNode('transform',name=prefix+'TargetParent')
                c.setAttr(target_parent+'.scale',1.4,.8,1.2,type='double3');c.setAttr(target_parent+'.rotate',-8,21,5,type='double3')
                target=c.createNode('transform',name=prefix+'Target',parent=target_parent)
                c.setAttr(target+'.translate',7,8,-2,type='double3');c.setAttr(target+'.rotate',-11,9,17,type='double3')
                fixtures.append((offset,receiver,control,target,old))
            offset,receiver,control,target,old=fixtures[0]
            aimed=c.createNode('transform',name='NAimed',parent=offset)
            aim=c.createNode('transform',name='NAim',parent=offset)
            static=c.createNode('transform',name='NStatic',parent=offset)
            for node in (aim,static):mel.eval('asAlign "'+node+'" "'+target+'" 1 1 0 0;')
            c.parent(receiver,aimed);c.parent(aim,target)
            constraint=c.aimConstraint(aim,static,aimed,offset=(0,0,0),aimVector=(sign,0,0),upVector=(0,sign,0),worldUpType='object' if up=='self' else 'objectrotation',worldUpVector=(0,sign,0),worldUpObject=offset if up=='self' else aim)[0]
            aliases=c.aimConstraint(constraint,query=True,weightAliasList=True)
            offset,receiver,control,target,old=fixtures[1]
            offset=c.ls(offset,long=True)[0];receiver=c.ls(receiver,long=True)[0]
            control=c.ls(control,long=True)[0];target=c.ls(target,long=True)[0]
            spec=BodyFitAimAtSpec('Body_R','Target_R',control,offset,receiver,target,'x','y',up,sign,'PAimed','PAim','PStatic','PRange','PConstraint','unused','PBridge',True)
            state=BodyFitAimAtState(matrix(offset),matrix(receiver),matrix(target),old+'.outputMatrix',tuple(c.getAttr(receiver+'.offsetParentMatrix')),os.environ.get('ADV_ATTACHMENT_NO_INHERIT')!='1')
            host=NS(_cmds=c,_transaction_changed=False)
            create(host,spec,state)
            assert capture(host,spec,state)
            for weight in (0.,5.,10.):
                c.setAttr('NTarget.translateX',9.);c.setAttr('PTarget.translateX',9.)
                c.setAttr('NTarget.rotateZ',28.);c.setAttr('PTarget.rotateZ',28.)
                c.setAttr(constraint+'.'+aliases[0],weight/10);c.setAttr(constraint+'.'+aliases[1],1-weight/10)
                c.setAttr(control+'.aimAt',weight)
                actual=matrix(control);expected=matrix('NFK')
                error=max(abs(a-b) for a,b in zip(actual,expected))
                report['cases'].append(dict(up=up,sign=sign,weight=weight,maximum_error=error))
            assert max(row['maximum_error'] for row in report['cases'])<=1e-5
        report['status']='passed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
