"""Native curve-based corrective lifecycle through public Body entry points."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(scene,output,bake=False):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    output.mkdir(parents=True,exist_ok=True)
    cmds.file(str(scene),open=True,force=True,executeScriptNodes=False)
    controller=MayaPanelController();host=MayaCorrectiveShapesHost()
    curves=cmds.listConnections('AdvPy_Global.tx',s=True,d=False,type='animCurve') or []
    if curves:cmds.delete(curves)
    with host.transaction('Curve source pose'):host.go_to_original_corrective_build_pose();host.set_original_corrective_all_fk()
    mesh=cmds.polyCube(name='CurveArmProxy',width=8,height=.5,depth=.5,subdivisionsX=32,subdivisionsY=2,subdivisionsZ=2)[0]
    position=cmds.xform('Wrist_R',q=True,ws=True,t=True)
    cmds.xform(mesh,ws=True,t=(position[0]+1,position[1],position[2]));cmds.makeIdentity(mesh,apply=True,translate=True)
    cmds.skinCluster('ElbowPart1_R','ElbowPart2_R','Wrist_R',mesh,name='CurveArmSkin',toSelectedBones=True)
    report={'status':'running','stages':[]}
    def points(node):
        cmds.dgdirty(allPlugs=True)
        return tuple(cmds.xform(node+'.cv[*]',q=True,ws=True,t=True))
    try:
        result=controller.original_corrective_shapes(':','curve_create',source=mesh,fk_control='AdvPy_Wrist_RFK')
        print('CURVE_CREATE',result,flush=True)
        assert result['curves']>=2,result
        mesh=cmds.rename(mesh,'CurveArmProxyRenamed')
        names=cmds.ls('deformationCurve*',type='transform')
        assert len(names)==result['curves']
        assert cmds.getAttr('curveDeformationSetup.curvesBound')
        neutral={name:points(name) for name in names}
        controller.original_corrective_shapes(':','curve_unbind')
        assert not cmds.ls('deformationCurve*SC',type='skinCluster')
        controller.original_corrective_shapes(':','curve_rebind')
        assert len(cmds.ls('deformationCurve*SC',type='skinCluster'))==len(names)
        report['stages'].append('create_unbind_rebind')
        registration=host.original_corrective_body_registration()
        channels={row.key:row for row in registration.channels}
        mode_plugs={limb.label+limb.side:channels[limb.blend_key].node+'.'+channels[limb.blend_key].attribute for limb in registration.source_limbs}
        # Infer the selected branch from its registered Body joints, not names.
        selected_modes={channels[limb.blend_key].node+'.'+channels[limb.blend_key].attribute for limb in registration.source_limbs if any(host._original_restore_leaf(row.body)=='Wrist_R' for row in limb.joints)}
        unrelated=[plug for plug in mode_plugs.values() if plug not in selected_modes]
        for plug in unrelated:cmds.setAttr(plug,.7)
        for plug in selected_modes:cmds.setAttr(plug,1)
        result=controller.original_corrective_shapes(':','curve_animate')
        assert all(abs(cmds.getAttr(plug)-.7)<1e-6 for plug in unrelated)
        assert all(cmds.getAttr(plug)==0 for plug in selected_modes)
        assert result in (10,80)
        cmds.currentTime(10)
        moved={name:points(name) for name in names}
        assert any(max(abs(a-b) for a,b in zip(neutral[name],moved[name]))>.001 for name in names)
        report['stages'].append('actual_curve_deformation')
        cmds.optionVar(intValue=('deformationUseComponentTags',1))
        result=controller.original_corrective_shapes(':','curve_mesh')
        assert cmds.optionVar(q='deformationUseComponentTags')==1
        print('CURVE_MESH',result,flush=True)
        assert cmds.objExists('CorrectiveWrap') and cmds.objExists('CorrectiveSC')
        assert cmds.polyEvaluate('Corrective',vertex=True)>0
        def mesh_points():
            cmds.dgdirty(allPlugs=True)
            return cmds.xform('Corrective.vtx[*]',q=True,ws=True,t=True)
        baseline=mesh_points()
        cmds.move(0,.3,0,names[0]+'.cv[4]',relative=True)
        edited=mesh_points()
        error=max(abs(a-b) for a,b in zip(baseline,edited))
        assert error>.001,('Wrap did not follow curve edit',error)
        cmds.move(0,-.3,0,names[0]+'.cv[4]',relative=True)
        restored=mesh_points()
        assert max(abs(a-b) for a,b in zip(baseline,restored))<.003
        report['wrap_edit_displacement']=error
        report['local_vertices']=cmds.polyEvaluate('Corrective',vertex=True)
        report['stages'].append('loft_skin_wrap_local_mesh')
        saved_mesh_points=mesh_points()
        controller.original_corrective_shapes(':','curve_original');assert cmds.getAttr(mesh+'.v')
        controller.original_corrective_shapes(':','curve_new');assert not cmds.getAttr(mesh+'.v')
        saved=output/'curve-corrective.mb'
        cmds.file(rename=str(saved));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(saved),open=True,force=True,executeScriptNodes=False)
        cmds.currentTime(10)
        for name in names:assert max(abs(a-b) for a,b in zip(points(name),moved[name]))<.003
        assert max(abs(a-b) for a,b in zip(mesh_points(),saved_mesh_points))<.003
        report['stages'].append('save_reopen')
        if bake:
            # Sculpt actual skinned curves, then sample the complete local
            # deformation mesh before the original four-direction bake.
            cmds.move(0,.15,0,names[0]+'.cv[4]',relative=True)
            if cmds.objExists('CorrectiveDeleteComponent'):cmds.delete('CorrectiveDeleteComponent')
            expected_mesh={}
            original_time=cmds.currentTime(q=True)
            for frame in (10,30,50,70):
                cmds.currentTime(frame);expected_mesh[frame]=mesh_points()
            cmds.currentTime(original_time)
            setup_uuid=cmds.ls('curveDeformationSetup',uuid=True)[0]
            animation_uuids={node:cmds.ls(node,uuid=True)[0] for node in cmds.listConnections('AdvPy_Wrist_RFK',s=True,d=False,type='animCurveTA') or []}
            result=controller.original_corrective_shapes(':','curve_bake',q_rotations=True,use_soft_mods=False,mirror=False)
            assert len(result)==4,result
            assert len(controller.original_corrective_targets(':'))==4
            baked_uuid=cmds.ls(mesh+'Corrective',uuid=True)[0]
            cmds.undo()
            assert cmds.ls('curveDeformationSetup',uuid=True)==[setup_uuid]
            assert not cmds.objExists(mesh+'Corrective')
            assert all(cmds.ls(node,uuid=True)==[uuid] for node,uuid in animation_uuids.items())
            cmds.redo()
            assert not cmds.objExists('curveDeformationSetup')
            assert cmds.ls(mesh+'Corrective',uuid=True)==[baked_uuid]
            assert len(controller.original_corrective_targets(':'))==4
            report['stages'].append('four_direction_curve_bake_single_undo_redo')
        else:controller.original_corrective_shapes(':','curve_cleanup')
        assert not cmds.objExists('curveDeformationSetup')
        assert cmds.objExists(mesh) and cmds.getAttr(mesh+'.v')
        assert not cmds.objExists('SkinCage')
        assert not cmds.listConnections('AdvPy_Wrist_RFK',s=True,d=False,type='animCurveTA')
        if bake:
            for frame,pose in ((10,(0,90,0)),(30,(0,-90,0)),(50,(0,0,90)),(70,(0,0,-90))):
                cmds.setAttr('AdvPy_Wrist_RFK.rotate',*pose,type='double3');cmds.dgdirty(allPlugs=True)
                actual=cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True)
                assert len(actual)==len(expected_mesh[frame])
                error=max(abs(a-b) for a,b in zip(actual,expected_mesh[frame]))
                assert error<.003,(frame,'Baked curve geometry',error)
            report['stages'].append('four_direction_actual_baked_geometry')
            baked_saved=output/'curve-baked.mb';cmds.file(rename=str(baked_saved));cmds.file(save=True,type='mayaBinary',force=True)
            cmds.file(str(baked_saved),open=True,force=True,executeScriptNodes=False)
            for frame,pose in ((10,(0,90,0)),(30,(0,-90,0)),(50,(0,0,90)),(70,(0,0,-90))):
                cmds.setAttr('AdvPy_Wrist_RFK.rotate',*pose,type='double3');cmds.dgdirty(allPlugs=True)
                actual=cmds.xform(mesh+'.vtx[*]',q=True,ws=True,t=True)
                assert max(abs(a-b) for a,b in zip(actual,expected_mesh[frame]))<.003
            report['stages'].append('baked_geometry_save_reopen')
        report['stages'].append('cleanup_preserves_source')
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'curves.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'curve-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),'--bake' in sys.argv)
