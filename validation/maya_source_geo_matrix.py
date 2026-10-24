"""Compare literal MEL Advanced Attach with the source adapter parent bridge."""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-geo-matrix-current'

def main(standalone=False,quit_on_finish=True):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_source_fit_geo_attach import create,capture
    from adv_py.core.body_fit_geo_attach import BodyFitGeoAttachSpec,BodyFitGeoAttachState
    class Host:
        _cmds=c; _transaction_changed=False
        def scene_address(self,value):return value
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),cases=[])
    def matrix(node):return tuple(c.xform(node,q=True,ws=True,matrix=True))
    try:
        source=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
        mel.eval('source "'+source.as_posix()+'";')
        text=source.read_text(encoding='utf-8')
        block=text.split('//Advanced Attach',1)[1].split('//Advanced Pin',1)[0]
        for inherits in (True,False):
            for reflected in (False,True):
                for mode in ('point','orient','parent'):
                    c.file(new=True,force=True)
                    fixtures=[]
                    for prefix in ('N','P'):
                        mesh=c.polyPlane(name=prefix+'Mesh',width=40,height=40,subdivisionsX=8,subdivisionsY=8)[0]
                        parent=c.createNode('transform',name=prefix+'Parent')
                        c.setAttr(parent+'.translate',1,2,3,type='double3')
                        c.setAttr(parent+'.rotate',4,7,9,type='double3')
                        c.setAttr(parent+'.scale',-1.2 if reflected else 1.2,.9,1.4,type='double3')
                        offset=c.createNode('transform',name='FKOffset'+prefix+'_R',parent=parent)
                        c.setAttr(offset+'.inheritsTransform',inherits)
                        c.setAttr(offset+'.translate',2,3,1,type='double3')
                        c.setAttr(offset+'.rotate',3,8,11,type='double3')
                        old=c.createNode('composeMatrix',name=prefix+'Old')
                        c.setAttr(old+'.inputTranslate',.2,.1,-.3,type='double3')
                        c.connectAttr(old+'.outputMatrix',offset+'.offsetParentMatrix')
                        fk=c.createNode('transform',name='FK'+prefix+'_R',parent=offset)
                        fit=c.createNode('joint',name=prefix)
                        c.xform(fit,ws=True,translation=c.xform(offset,q=True,ws=True,translation=True))
                        fixtures.append((mesh,parent,offset,fk,fit,old))
                    declarations='string $fitJoints[]={"N"}; string $fitJointSide[]={"_R"}; int $fitJointUnderNonSymmetry[]={0}; int $fitJointNoMirrorCode[]={-1}; int $fitJointIsEndJoint[]={0}; string $fitJointsAttachTo[]={"NMesh"}; string $fitJointsAttachMode[]={"'+mode+'"}; string $name,$side,$offsetParent,$tempString[]; float $temp[]; int $b,$b2,$i;'
                    mel.eval('{'+declarations+block+'}')
                    mesh,parent,offset,fk,fit,old=fixtures[1]
                    parent=c.ls(parent,long=True)[0];offset=c.ls(offset,long=True)[0];fk=c.ls(fk,long=True)[0]
                    spec=BodyFitGeoAttachSpec(fit,fk,offset,parent,mesh,mode,'R','PSurface','PPoly','PStatic','PAttached','PLayer','PWeight','PBridge',True,fit,1)
                    state=BodyFitGeoAttachState(c.listRelatives(mesh,shapes=True,fullPath=True)[0],tuple(c.xform(fit,q=True,ws=True,translation=True)),matrix(offset),matrix(parent),old+'.outputMatrix',tuple(c.getAttr(offset+'.offsetParentMatrix')),inherits)
                    host=Host();create(host,spec,state);assert capture(host,spec,state)
                    for weight in (0.,5.,10.):
                        for prefix in ('N','P'):
                            c.setAttr(prefix+'Mesh.translateX',1.5)
                            c.setAttr(prefix+'Mesh.rotateZ',12)
                            c.setAttr('FK'+prefix+'_R.attach',weight)
                        error=max(abs(a-b) for a,b in zip(matrix('FKN_R'),matrix('FKP_R')))
                        report['cases'].append(dict(inherits_transform=inherits,reflected=reflected,mode=mode,weight=weight,maximum_error=error))
        report['maximum_error']=max(row['maximum_error'] for row in report['cases'])
        report['status']='passed' if report['maximum_error']<=1e-5 else 'failed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
