"""Compare QRotation graphs and SDK curves against unmodified local ADV MEL.

Source procedures are loaded only by this validation harness. The QRotation
procedure's isolated finalization error is recorded separately; graph parity
is asserted only after all source nodes/attributes exist and evaluate.
"""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
REFERENCE=Path('D:/3D/_tools/_DCC/MayaScope/AnalyseAdv/ADV_6.925_reference/AdvancedSkeleton.mel')


def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds,mel
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    host=MayaCorrectiveShapesHost()
    with host.transaction('Reference build pose'):
        host.go_to_original_corrective_build_pose();host.set_original_corrective_all_fk()
    neutral=output/'neutral.mb'
    cmds.file(rename=str(neutral));cmds.file(save=True,type='mayaBinary',force=True)
    mel.eval('source "'+str(REFERENCE).replace('\\','/')+'";')
    report={'status':'running','source_q_finalize_errors':{},'samples':{}}
    poses=[(0,0,0),(30,20,10),(-30,-20,-10),(60,30,-20)]
    poses += [tuple(amount if i==axis else 0 for i in range(3)) for axis in range(3) for amount in (45,-45,90,-90)]
    joints=('Shoulder_R','Wrist_R')
    def sample(joint,control):
        result=[]
        for pose in poses:
            cmds.setAttr(control+'.rotate',*pose,type='double3');cmds.dgdirty(allPlugs=True)
            result.append(tuple(cmds.getAttr(joint+'.qRotate'+axis) for axis in 'XYZ'))
        cmds.setAttr(control+'.rotate',0,0,0,type='double3');cmds.dgdirty(allPlugs=True)
        return result
    try:
        # Prepare the neutral pose with the port, then suppress GUI pose entry
        # by removing its selection-set name from the isolated source scene.
        cmds.rename('ControlSet','ReferenceControlSet')
        source={}
        for joint in joints:
            cmds.select(joint,replace=True)
            try:mel.eval('asCreateQRotateAttrs "'+joint+'";')
            except RuntimeError as error:report['source_q_finalize_errors'][joint]=str(error)
            assert all(cmds.objExists(joint+'.qRotate'+axis) for axis in 'XYZ')
            assert len(cmds.ls(joint[:-2]+'QRotate*',type='quatToEuler'))==3
            source[joint]=sample(joint,'AdvPy_'+joint+'FK')
        cmds.file(str(neutral),open=True,force=True,executeScriptNodes=False)
        for joint in joints:
            with host.transaction('Port source QRotation'):
                host.create_original_q_rotate_attrs(joint)
            actual=sample(joint,'AdvPy_'+joint+'FK')
            difference=max(abs(a-b) for row,other in zip(actual,source[joint]) for a,b in zip(row,other))
            assert difference<1e-6,(joint,difference)
            report['samples'][joint]={'count':len(poses),'maximum_error':difference,'pure_x90':actual[6]}
        # Independent native source SDK construction on the same live driver.
        cmds.createNode('network',name='SourceRotationWeights');cmds.createNode('network',name='PortRotationWeights')
        aliases=[]
        for axis in 'XYZ':
            for sign in (-1,1):
                alias='qRotate'+axis+('Neg' if sign<0 else 'Pos');aliases.append(alias)
                for node in ('SourceRotationWeights','PortRotationWeights'):
                    cmds.addAttr(node,longName=alias,attributeType='double')
                    for driver,value in ((0,0),(sign*90,1)):
                        cmds.setDrivenKeyframe(node+'.'+alias,currentDriver='Wrist_R.qRotate'+axis,
                                               driverValue=driver,value=value,inTangentType='linear',outTangentType='linear')
                mel.eval('asTweakSDKCurveForRotation "SourceRotationWeights.'+alias+'";')
                host._corrective_sdk_rotation_tangents('PortRotationWeights.'+alias)
        largest=0.
        for pose in poses:
            cmds.setAttr('AdvPy_Wrist_RFK.rotate',*pose,type='double3');cmds.dgdirty(allPlugs=True)
            for alias in aliases:
                error=abs(cmds.getAttr('SourceRotationWeights.'+alias)-cmds.getAttr('PortRotationWeights.'+alias))
                largest=max(largest,error)
        assert largest<1e-7,largest
        report['sdk_samples']=len(poses)*len(aliases);report['sdk_maximum_error']=largest
        report['status']='passed_graph_and_sdk_parity'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'source-parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'source-parity.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
