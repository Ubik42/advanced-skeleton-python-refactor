"""Native custom blended-attribute graph vs unmodified ADV source.

Includes different discovered objects: the original intentionally addresses
both graph channels on its first object. Compare connections, stored dv values,
negation, clamp and actual evaluated output, without correcting the algorithm.
"""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
REFERENCE=Path('D:/3D/_tools/_DCC/MayaScope/AnalyseAdv/ADV_6.925_reference/AdvancedSkeleton.mel')


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds,mel
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(new=True,force=True)
    mel.eval('source "'+REFERENCE.as_posix()+'";')
    host=MayaCorrectiveShapesHost();report={'status':'running','cases':[]}
    try:
        for number,values in enumerate(((20,35,7),(-1,30,8),(45,-1,-9))):
            source='Source'+str(number)+'_R';other='Other'+str(number)+'_R';port='Port'+str(number)+'_R';port_other='PortOther'+str(number)+'_R'
            for node in (source,other,port,port_other):
                cmds.createNode('transform',name=node)
                for axis in 'YZ':cmds.addAttr(node,ln='qRotate'+axis,at='double',keyable=True)
            for node in (source,port):
                cmds.setAttr(node+'.qRotateY',values[0]);cmds.setAttr(node+'.qRotateZ',values[2])
            for node in (other,port_other):cmds.setAttr(node+'.qRotateZ',values[1])
            # Other is discovered, but the original graph samples Source.Z.
            expression='asCreateCustomBlendedAttribute {"'+source+'.qRotateY","'+other+'.qRotateZ"} "Comparison";'
            mel.eval(expression)
            with host.transaction('Port original blended graph'):
                host.create_original_blended_attribute((port+'.qRotateY',port_other+'.qRotateZ'),'Comparison')
            for suffix in ('MPD','SetRange','Clamp','PlusMinusAverage'):
                assert cmds.nodeType(source+'Comparison'+suffix)==cmds.nodeType(port+'Comparison'+suffix)
            for axis in 'XY':
                actual=cmds.listConnections(port+'ComparisonMPD.input1'+axis,s=True,d=False,p=True)[0]
                native=cmds.listConnections(source+'ComparisonMPD.input1'+axis,s=True,d=False,p=True)[0]
                def incoming(plug):
                    node=plug.rsplit('.',1)[0]
                    return cmds.listConnections(node+'.input[0]',s=True,d=False,p=True)[0]
                assert incoming(actual).replace(port,source)==incoming(native)
                assert cmds.getAttr(port+'ComparisonSetRange.dv'+axis)==cmds.getAttr(source+'ComparisonSetRange.dv'+axis)
                assert cmds.getAttr(port+'ComparisonMPD.input2'+axis)==cmds.getAttr(source+'ComparisonMPD.input2'+axis)
            differences=[]
            for y,z,other_z in ((0,0,0),(20,7,35),(-30,10,80),(5,-15,-90),(40,40,1)):
                for node in (source,port):
                    cmds.setAttr(node+'.qRotateY',y);cmds.setAttr(node+'.qRotateZ',z)
                for node in (other,port_other):cmds.setAttr(node+'.qRotateZ',other_z)
                cmds.dgdirty(allPlugs=True)
                differences.append(abs(cmds.getAttr(source+'.Comparison')-cmds.getAttr(port+'.Comparison')))
            assert max(differences)<1e-7,differences
            report['cases'].append({'discovered_values':values,'graph_dv':[cmds.getAttr(port+'ComparisonSetRange.dv'+a) for a in 'XY'],'samples':len(differences),'maximum_error':max(differences)})
        report['status']='passed_source_graph_parity'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'blended-parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'blended-parity.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
