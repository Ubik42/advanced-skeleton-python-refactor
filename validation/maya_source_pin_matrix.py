"""Native asProximityPin local channels under nonuniform parent scaling."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-pin-matrix-current'
def main(standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_body_fit_proximity_pin import MayaBodyFitProximityPinMixin
    from adv_py.adapters.maya_source_fit_proximity_pin import create,capture
    from adv_py.core.body_fit_proximity_pin import BodyFitProximityPinSpec,BodyFitProximityPinState
    class Host(MayaBodyFitProximityPinMixin):
        _cmds=c;namespace='';_transaction_changed=False
        def scene_address(self,value):return value
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[])
    def matrix(n):return tuple(c.xform(n,q=True,ws=True,matrix=True))
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        for mirrored in (False,True):
            c.file(new=True,force=True)
            fixtures=[]
            for prefix in ('N','P'):
                mesh=c.polyPlane(name=prefix+'Mesh',width=40,height=40,subdivisionsX=8,subdivisionsY=8)[0]
                offset=c.createNode('transform',name=prefix+'Offset')
                c.setAttr(offset+'.translate',2,3,1,type='double3');c.setAttr(offset+'.rotate',4,8,12,type='double3')
                c.setAttr(offset+'.scale',-1.2 if mirrored else 1.2,.9,1.4,type='double3')
                receiver=c.createNode('transform',name=prefix+'Receiver',parent=offset)
                c.setAttr(receiver+'.inheritsTransform',os.environ.get('ADV_ATTACHMENT_NO_INHERIT')!='1')
                c.setAttr(receiver+'.translate',.3,.2,-.1,type='double3');c.setAttr(receiver+'.rotate',3,9,7,type='double3')
                old=c.createNode('composeMatrix',name=prefix+'Old')
                c.setAttr(old+'.inputTranslate',.2,.1,-.3,type='double3');c.connectAttr(old+'.outputMatrix',receiver+'.offsetParentMatrix')
                fk=c.createNode('transform',name=prefix+'FK',parent=receiver)
                fixtures.append((mesh,offset,receiver,fk,old))
            mesh,offset,receiver,fk,old=fixtures[0]
            pin=c.createNode('transform',name='PinN_R',parent=offset)
            c.select(mesh,pin,replace=True);mel.eval('asProximityPin;')
            bm=c.createNode('blendMatrix',name='NBM');mm=c.createNode('multMatrix',name='NMM')
            c.connectAttr('proximityPinPinN_R.outputMatrix[0]',bm+'.target[0].targetMatrix')
            c.connectAttr(offset+'.worldMatrix[0]',bm+'.inputMatrix')
            c.connectAttr(bm+'.outputMatrix',mm+'.matrixIn[0]');c.connectAttr(offset+'.worldInverseMatrix[0]',mm+'.matrixIn[1]')
            c.connectAttr(mm+'.matrixSum',pin+'.offsetParentMatrix',force=True)
            c.parent(receiver,pin,relative=True)
            mesh,offset,receiver,fk,old=fixtures[1]
            offset=c.ls(offset,long=True)[0];receiver=c.ls(receiver,long=True)[0];fk=c.ls(fk,long=True)[0]
            spec=BodyFitProximityPinSpec('Body_R',fk,offset,receiver,mesh,'R','PPin','PPinNode','PUnused','PBM','PWeight','PMM','PBridge',True)
            state=BodyFitProximityPinState(c.ls(mesh,long=True)[0],matrix(offset),matrix(receiver),old+'.outputMatrix',tuple(c.getAttr(receiver+'.offsetParentMatrix')),os.environ.get('ADV_ATTACHMENT_NO_INHERIT')!='1')
            host=Host();create(host,spec,state);assert capture(host,spec,state)
            report.setdefault('local_scale',[]).append(dict(mirrored=mirrored,native=c.getAttr(pin+'.scale'),python=c.getAttr(spec.input_transform+'.scale')))
            for weight in (0.,5.,10.):
                c.setAttr('NMesh.translateX',1.5);c.setAttr('PMesh.translateX',1.5)
                c.setAttr('NMesh.scaleX',1.3);c.setAttr('PMesh.scaleX',1.3)
                c.setAttr(bm+'.target[0].weight',weight/10);c.setAttr(fk+'.pin',weight)
                error=max(abs(a-b) for a,b in zip(matrix('NFK'),matrix('PFK')))
                report['cases'].append(dict(mirrored=mirrored,weight=weight,maximum_error=error))
        report['status']='passed' if max(row['maximum_error'] for row in report['cases'])<=1e-5 else 'failed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
