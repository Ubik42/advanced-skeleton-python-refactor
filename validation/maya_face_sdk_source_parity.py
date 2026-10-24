"""asDsSdk typed drivers, additive keys and native Undo on small real graphs."""
from pathlib import Path
import itertools,json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'validation/results/face-sdk-source-parity'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel,utils
    from adv_py.adapters.maya_face_original_build import MayaOriginalFaceBuildHost
    from maya_face_conversion_parity import compare,scene_identity
    OUTPUT.mkdir(parents=True,exist_ok=True)
    report={'status':'running','pid':os.getpid(),'cases':[]}
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        def fixture(kind,target,output_bw):
            c.file(new=True,force=True);c.undoInfo(state=True)
            c.sets(empty=True,name='FaceAllSet')
            c.createNode('transform',name='FaceMotionSystem')
            c.createNode('transform',name='SDKSample_R',parent='FaceMotionSystem')
            c.sets('SDKSample_R',add='FaceAllSet')
            c.addAttr('SDKSample_R',longName='amount',attributeType='double',keyable=True)
            drivers=[]
            host=MayaOriginalFaceBuildHost()
            for number in range(3):
                node=c.createNode('transform',name='ctrlSample'+str(number)+'_R',parent='FaceMotionSystem')
                c.sets(node,add='FaceAllSet')
                c.addAttr(node,longName='amount',attributeType='double',keyable=True)
                plug=node+'.'+kind;drivers.append(plug)
                if output_bw:host.original_face_output_bw(plug)
            return host,drivers,'SDKSample_R.'+target
        def sample(drivers,driven):
            state=c.undoInfo(query=True,state=True);c.undoInfo(stateWithoutFlush=False)
            try:
                values=[]
                for index in range(3):
                    for value in (-8,-4,0,1,2,4,8):
                        for driver in drivers:c.setAttr(driver,0)
                        c.setAttr(drivers[index],value);values.append(c.getAttr(driven))
                for driver in drivers:c.setAttr(driver,2)
                values.append(c.getAttr(driven))
                for driver in drivers:c.setAttr(driver,0)
                curves=[]
                for curve in c.ls(type='animCurve'):
                    curves.append({'type':c.nodeType(curve),'keys':c.keyframe(curve,query=True,floatChange=True),
                        'values':c.keyframe(curve,query=True,valueChange=True),
                        'pre':c.getAttr(curve+'.preInfinity'),'post':c.getAttr(curve+'.postInfinity'),
                        'weighted':c.keyTangent(curve,query=True,weightedTangents=True),
                        'in':c.keyTangent(curve,query=True,inTangentType=True),'out':c.keyTangent(curve,query=True,outTangentType=True)})
                curves.sort(key=lambda row:json.dumps(row,sort_keys=True))
                return {'values':values,'curves':curves}
            finally:c.undoInfo(stateWithoutFlush=state)
        for kind,target,output_bw in itertools.product(('amount','tx','rx'),('tx','rx','sx','amount'),(False,True)):
            host,drivers,driven=fixture(kind,target,output_bw)
            values=(2.1254,-1.7504,3.3754) if target!='sx' else (1.25,.75,1.5)
            for driver,value in zip(drivers,values):mel.eval('asDsSdk '+json.dumps(driver)+' '+json.dumps(driven)+' 4 '+str(value)+';')
            native=sample(drivers,driven)
            host,drivers,driven=fixture(kind,target,output_bw);before=scene_identity()
            with host.transaction('Source Face SDK typed drivers'):
                for driver,value in zip(drivers,values):host.add_original_face_sdk(driver,driven,4,value)
            python=sample(drivers,driven);error=compare(native,python)
            built=scene_identity();c.undo();compare(before,scene_identity())
            c.redo();compare(built,scene_identity());redo_error=compare(python,sample(drivers,driven))
            report['cases'].append({'driver':kind,'target':target,'output_bw':output_bw,'error':error,'redo_error':redo_error,'poses':22})
        report['status']='passed'
    except Exception:report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion:Path(completion).write_text(json.dumps({'pid':os.getpid(),'status':report['status']}),encoding='utf8')
        if quit_on_finish:utils.executeDeferred(c.quit,force=True)
