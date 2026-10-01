"""Native Body QRotation and persistent multi-SoftMod corrective lifecycle."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene,output,soft=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    cmds.undoInfo(state=True)
    # The saved Body fixture includes a Global animation demo. Source corrective
    # exit disconnects AllSet test animation and returns to build pose; use a
    # static Body fixture so world-space sculpt comparisons share that pose.
    curves=cmds.listConnections('AdvPy_Global.tx',source=True,destination=False,type='animCurve') or []
    if curves:cmds.delete(curves)
    cmds.setAttr('AdvPy_Global.tx',0)
    controller=MayaPanelController();host=MayaCorrectiveShapesHost()
    mesh='CorrectiveArmProxy';control='AdvPy_Shoulder_RFK'
    cmds.polyCube(name=mesh,width=8,height=4,depth=4,subdivisionsX=4,subdivisionsY=2,subdivisionsZ=2)
    location=cmds.xform('Shoulder_R',query=True,worldSpace=True,translation=True)
    cmds.xform(mesh,worldSpace=True,translation=(location[0]-5,location[1],location[2]))
    cmds.makeIdentity(mesh,apply=True,translate=True)
    cmds.skinCluster('Shoulder_R',mesh,name='CorrectiveArmSkin',toSelectedBones=True)
    report={'status':'running','soft_mods':soft,'stages':[]}
    def points(name=mesh):
        cmds.dgdirty(allPlugs=True)
        return tuple(cmds.xform(name+'.vtx[*]',query=True,worldSpace=True,translation=True))
    def same(a,b):return len(a)==len(b) and max(abs(x-y) for x,y in zip(a,b))<.003
    try:
        with host.transaction('Body corrective build pose'):host.go_to_original_corrective_build_pose()
        neutral=points()
        cmds.setAttr(control+'.rz',60)
        posed=points()
        print('BODY_ROT',cmds.getAttr('Shoulder_R.rotate'),flush=True)
        assert not same(neutral,posed),'Body FK must actually deform the proxy'
        index=max(range(len(posed)//3),key=lambda i:max(abs(posed[i*3+a]-neutral[i*3+a]) for a in range(3)))
        cmds.select(mesh,replace=True)
        result=controller.original_corrective_shapes(':','create',q_rotations=True,use_soft_mods=soft,mirror=False)
        print('CREATE',result,flush=True)
        assert 'qRotate' in result['driver'],result
        target=result['target']
        report['sample_vertex']=index;report['driver']=result['driver']
        if soft:
            mods=[]
            for offset in (.12,.08):
                mod,handle=cmds.softMod(target,falloffMode=1,falloffAroundSelection=False)
                center=cmds.xform(target+f'.vtx[{index}]',query=True,worldSpace=True,translation=True)
                cmds.setAttr(mod+'.falloffCenter',*center,type='double3')
                cmds.setAttr(mod+'.falloffRadius',100)
                cmds.setAttr(handle+'.tz',offset)
                mods.append((mod,handle,cmds.ls(mod,uuid=True)[0]))
            expected=points(target)
        else:
            loc=cmds.xform(target+f'.vtx[{index}]',query=True,worldSpace=True,translation=True);loc[2]+=.2
            cmds.xform(target+f'.vtx[{index}]',worldSpace=True,translation=loc)
            expected=points(target)
        assert not same(expected,posed)
        controller.original_corrective_shapes(':','apply',q_rotations=True,use_soft_mods=soft,mirror=False)
        cmds.undo();assert cmds.objExists(target)
        cmds.redo();assert not cmds.objExists(target)
        cmds.setAttr(control+'.rz',60);assert same(points(),expected),(points()[index*3:index*3+3],expected[index*3:index*3+3])
        cmds.setAttr(control+'.rz',0);assert same(points(),neutral),(points()[index*3:index*3+3],neutral[index*3:index*3+3],cmds.getAttr('Shoulder_R.qRotateZ'),cmds.getAttr('CorrectiveArmProxyCorrective.weight')[0])
        report['stages'].append('create_apply_native_undo_redo')
        if soft:
            for mod,handle,uuid in mods:
                assert cmds.ls(mod,uuid=True)==[uuid]
                assert cmds.listRelatives(handle,parent=True)[0].startswith('CorrectiveSoftMods_')
            report['stages'].append('persistent_two_softmods')
        saved=output/'body-corrective.mb'
        cmds.file(rename=str(saved));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(saved),open=True,force=True,executeScriptNodes=False)
        cmds.setAttr(control+'.rz',60);assert same(points(),expected)
        report['stages'].append('save_reopen')
        target_record=controller.original_corrective_targets(':',edit=True)[0]
        edited=controller.original_corrective_shapes(':','edit',target=target_record,q_rotations=True,use_soft_mods=soft,mirror=False)
        print('EDIT',edited,flush=True)
        assert same(points(edited['target']),expected),'Restored sculpt must match existing corrected pose'
        if soft:
            for mod,handle,uuid in mods:assert cmds.ls(mod,uuid=True)==[uuid]
            cmds.setAttr(mods[0][1]+'.tz',.2)
        else:
            loc=cmds.xform(edited['target']+f'.vtx[{index}]',query=True,worldSpace=True,translation=True);loc[2]+=.1
            cmds.xform(edited['target']+f'.vtx[{index}]',worldSpace=True,translation=loc)
        expected=points(edited['target'])
        controller.original_corrective_shapes(':','apply',q_rotations=True,use_soft_mods=soft,mirror=False)
        cmds.setAttr(control+'.rz',60);assert same(points(),expected)
        report['stages'].append('edit_chain_reapply')
        before_pose=cmds.getAttr(control+'.rotate')[0]
        if soft:
            for sm,h,u in mods:
                print('BEFORE_BATCH',sm,cmds.getAttr(h+'.translate'),cmds.listConnections(sm+'.input[0].inputGeometry',s=True,d=False),cmds.listConnections(sm+'.outputGeometry[0]',s=False,d=True),flush=True)
        result=controller.original_corrective_shapes(':','batch',q_rotations=True,use_soft_mods=soft,mirror=False)
        assert len(result)==1,result
        cmds.setAttr(control+'.rz',60);assert same(points(),expected),(points()[index*3:index*3+3],expected[index*3:index*3+3])
        report['stages'].append('batch_reapply')
        target_record=controller.original_corrective_targets(':',edit=True)[0]
        controller.original_corrective_shapes(':','delete',target=target_record,q_rotations=True,use_soft_mods=soft,mirror=False)
        cmds.setAttr(control+'.rz',60);assert same(points(),posed)
        report['stages'].append('delete_restores_skin')
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'body-corrective.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'body-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':
    main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),'--soft' in sys.argv)
