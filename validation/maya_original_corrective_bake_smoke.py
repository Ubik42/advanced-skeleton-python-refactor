"""Source six-axis Body bake: actual source/destination mesh equality."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def create_bake_fixture(cmds,host):
    curves=cmds.listConnections('AdvPy_Global.tx',s=True,d=False,type='animCurve') or []
    if curves:cmds.delete(curves)
    cmds.setAttr('AdvPy_Global.tx',0)
    with host.transaction('Bake build pose'):
        host.go_to_original_corrective_build_pose();host.set_original_corrective_all_fk()
    control='AdvPy_Wrist_RFK'
    location=cmds.xform('Wrist_R',query=True,worldSpace=True,translation=True)
    for name in ('BakeSource','BakeDestination'):
        cmds.polyCube(name=name,width=8,height=4,depth=4,subdivisionsX=4,subdivisionsY=2,subdivisionsZ=2)
        cmds.xform(name,worldSpace=True,translation=(location[0]-5,location[1],location[2]))
        cmds.makeIdentity(name,apply=True,translate=True)
    sculpt=cmds.duplicate('BakeSource',name='BakeSourceSculpt')[0]
    cmds.move(0,0,.2,sculpt+'.vtx[*]',relative=True,objectSpace=True)
    bs=cmds.blendShape(sculpt,'BakeSource',name='BakeSourceDeformation')[0]
    cmds.delete(sculpt)
    # Give the source an actual symmetric rotation-driven deformation. The
    # six source samples must be reproduced by the baked destination SDKs.
    node=cmds.createNode('multiplyDivide',name='BakeSourceDriver')
    cmds.setAttr(node+'.operation',3);cmds.setAttr(node+'.input2X',2)
    cmds.connectAttr(control+'.rotateZ',node+'.input1X')
    scale=cmds.createNode('multDoubleLinear',name='BakeSourceDriverScale')
    cmds.setAttr(scale+'.input2',1/8100.)
    cmds.connectAttr(node+'.outputX',scale+'.input1');cmds.connectAttr(scale+'.output',bs+'.w[0]')
    for name in ('BakeSource','BakeDestination'):
        cmds.skinCluster('Wrist_R',name,name=name+'Skin',toSelectedBones=True)
    return control


def main(scene,output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    controller=MayaPanelController();host=MayaCorrectiveShapesHost()
    control=create_bake_fixture(cmds,host)
    def points(name):
        cmds.dgdirty(allPlugs=True)
        return tuple(cmds.xform(name+'.vtx[*]',q=True,ws=True,t=True))
    def same(a,b):return max(abs(x-y) for x,y in zip(a,b))<.003
    report={'status':'running','stages':[]}
    try:
        cmds.setAttr(control+'.rz',12)
        previous=cmds.getAttr(control+'.rotate')[0]
        cmds.select(control,replace=True)
        result=controller.original_corrective_shapes(':','bake',source='BakeSource',destination='BakeDestination',axes=(True,)*6,q_rotations=True,mirror=False)
        print('BAKED',result,flush=True)
        assert len(result)==6,result
        assert cmds.getAttr(control+'.rotate')[0]==previous
        assert cmds.ls(selection=True)==[control]
        cmds.undo();assert not cmds.objExists('BakeDestinationCorrective')
        cmds.redo();assert len(controller.original_corrective_targets(':'))==6
        report['stages'].append('single_undo_redo')
        targets=controller.original_corrective_targets(':')
        assert len(targets)==6,targets
        for axis in 'xyz':
            for amount in (90,-90):
                cmds.setAttr(control+'.rotate',0,0,0,type='double3')
                cmds.setAttr(control+'.r'+axis,amount)
                assert same(points('BakeSource'),points('BakeDestination')),(axis,amount,points('BakeSource')[:3],points('BakeDestination')[:3],cmds.getAttr('Wrist_R.qRotate'+axis.upper()))
        cmds.setAttr(control+'.rotate',0,0,0,type='double3')
        assert same(points('BakeSource'),points('BakeDestination'))
        report['stages'].append('six_axis_actual_deformation_pose_selection_restore')
        saved=output/'body-baked-correctives.mb'
        cmds.file(rename=str(saved));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(saved),open=True,force=True,executeScriptNodes=False)
        cmds.setAttr(control+'.rz',90)
        assert same(points('BakeSource'),points('BakeDestination'))
        report['stages'].append('save_reopen')
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'bake.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'bake-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
