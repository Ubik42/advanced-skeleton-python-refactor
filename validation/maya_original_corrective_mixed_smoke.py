"""Native mixed QRotation corrective create/edit/mirror/cancel lifecycle."""
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
    curves=cmds.listConnections('AdvPy_Global.tx',s=True,d=False,type='animCurve') or []
    if curves:cmds.delete(curves)
    cmds.setAttr('AdvPy_Global.tx',0)
    host=MayaCorrectiveShapesHost();controller=MayaPanelController()
    with host.transaction('Mixed Body neutral'):host.go_to_original_corrective_build_pose();host.set_original_corrective_all_fk()
    meshes=[]
    for side,offset in [('R',-5),('L',5)]:
        mesh=cmds.polyCube(name='MixedArm'+side,width=8,height=4,depth=4,subdivisionsX=4,subdivisionsY=2,subdivisionsZ=2)[0]
        position=cmds.xform('Shoulder_'+side,q=True,ws=True,t=True)
        cmds.xform(mesh,ws=True,t=(position[0]+offset,position[1],position[2]))
        cmds.makeIdentity(mesh,apply=True,translate=True);meshes.append(mesh)
    mesh=cmds.polyUnite(meshes,name='MixedArmProxy',constructionHistory=False)[0]
    leftovers=[node for node in meshes if cmds.objExists(node)]
    if leftovers:cmds.delete(leftovers)
    skin=cmds.skinCluster('Shoulder_R','Shoulder_L',mesh,name='MixedArmSkin',toSelectedBones=True)[0]
    # Explicit spatial weights keep both symmetric regions on their own arm.
    vertices=cmds.ls(mesh+'.vtx[*]',flatten=True)
    for vertex in vertices:
        x=cmds.pointPosition(vertex,w=True)[0]
        cmds.skinPercent(skin,vertex,transformValue=[('Shoulder_R',int(x<0)),('Shoulder_L',int(x>=0))])
    right='AdvPy_Shoulder_RFK';left='AdvPy_Shoulder_LFK'
    pose=(0,20,35)
    report={'status':'running','soft_mods':soft,'stages':[]}
    def points(node=mesh):
        cmds.dgdirty(allPlugs=True)
        return tuple(cmds.xform(node+'.vtx[*]',q=True,ws=True,t=True))
    def same(a,b):return len(a)==len(b) and max(abs(x-y) for x,y in zip(a,b))<.003
    try:
        neutral=points()
        cmds.setAttr(right+'.rotate',*pose,type='double3')
        before=points()
        cmds.select(mesh,r=True)
        result=controller.original_corrective_shapes(':','create',q_rotations=True,use_soft_mods=soft,mirror=True)
        assert '_' in result['driver'].rsplit('.',1)[1],result
        target=result['target']
        cmds.dgdirty(allPlugs=True)
        attr=result['driver'].rsplit('.',1)[1]
        assert cmds.objExists(right+'.'+attr)
        restore=cmds.getAttr('Shoulder_R'+attr+'SetRange.setQRotatesCmd')
        assert right+'.rotateY' in restore and right+'.rotateZ' in restore,restore
        report['stages'].append('registered_mixed_qrotation_and_pose_commands')
        index=next(i for i in range(len(before)//3) if before[i*3]<0)
        if soft:
            mod,handle=cmds.softMod(target,falloffMode=1,falloffAroundSelection=False)
            center=cmds.pointPosition(target+'.vtx['+str(index)+']',w=True)
            cmds.setAttr(mod+'.falloffCenter',*center,type='double3');cmds.setAttr(mod+'.falloffRadius',2)
            cmds.setAttr(handle+'.tz',.2)
        else:cmds.move(0,0,.2,target+'.vtx['+str(index)+']',r=True,ws=True)
        sculpt=points(target)
        applied=controller.original_corrective_shapes(':','apply',q_rotations=True,use_soft_mods=soft,mirror=True)
        assert applied['mirrored'],applied
        cmds.setAttr(right+'.rotate',*pose,type='double3')
        assert same(points(),sculpt),'Right mixed corrective did not reproduce sculpt'
        records=controller.original_corrective_targets(':',edit=True)
        assert len(records)==1,records
        edited=controller.original_corrective_shapes(':','edit',target=records[0],q_rotations=True,use_soft_mods=soft,mirror=True)
        assert max(abs(a-b) for a,b in zip(cmds.getAttr(right+'.rotate')[0],pose))<.003
        assert same(points(edited['target']),sculpt),'Mixed edit did not restore original pose/sculpt'
        controller.original_corrective_shapes(':','apply',q_rotations=True,use_soft_mods=soft,mirror=True)
        cmds.setAttr(right+'.rotate',*pose,type='double3')
        assert same(points(),sculpt),'Mixed reapply changed sculpt'
        result=controller.original_corrective_shapes(':','batch',q_rotations=True,use_soft_mods=soft,mirror=True)
        assert len(result)==1,result
        cmds.setAttr(right+'.rotate',*pose,type='double3')
        assert same(points(),sculpt),'Mixed batch changed sculpt'
        report['stages'].append('mixed_reapply_and_batch')
        edited=controller.original_corrective_shapes(':','edit',target=records[0],q_rotations=True,use_soft_mods=soft,mirror=True)
        assert same(points(edited['target']),sculpt)
        controller.original_corrective_shapes(':','cancel',q_rotations=True,use_soft_mods=soft,mirror=True)
        assert not cmds.objExists(edited['target'])
        cmds.setAttr(right+'.rotate',*pose,type='double3')
        assert same(points(),sculpt),'Cancel changed applied corrective'
        report['stages'].append('apply_mirror_edit_cancel')
        # Evaluate the actual opposite-side SDK and compare its delta with the
        # source sculpt reflected about the original world-X mirror plane.
        cmds.setAttr(right+'.rotate',0,0,0,type='double3')
        cmds.setAttr(left+'.rotate',*pose,type='double3')
        mirrored=points()
        aliases=cmds.aliasAttr(mesh+'Corrective',q=True)[::2]
        mirror_alias=next(alias for alias in aliases if alias.startswith('Shoulder_L__'))
        assert cmds.getAttr(mesh+'Corrective.'+mirror_alias)>.99
        cmds.setAttr(mesh+'Corrective.envelope',0);base_mirrored=points();cmds.setAttr(mesh+'Corrective.envelope',1)
        assert not same(mirrored,base_mirrored),'Left SDK has no actual geometry deformation'
        report['mirror_max_displacement']=max(abs(a-b) for a,b in zip(mirrored,base_mirrored))
        mirror_error=0.
        for i in range(len(neutral)//3):
            if neutral[i*3]>=0:continue
            reflected=(-neutral[i*3],neutral[i*3+1],neutral[i*3+2])
            j=min(range(len(neutral)//3),key=lambda n:sum((neutral[n*3+a]-reflected[a])**2 for a in range(3)))
            assert max(abs(neutral[j*3+a]-reflected[a]) for a in range(3))<.003
            expected_delta=tuple((sculpt[i*3+a]-before[i*3+a])*(-1 if a==0 else 1) for a in range(3))
            actual_delta=tuple(mirrored[j*3+a]-base_mirrored[j*3+a] for a in range(3))
            mirror_error=max(mirror_error,max(abs(a-b) for a,b in zip(expected_delta,actual_delta)))
        report['mirror_reflected_vertex_delta_error']=mirror_error
        assert mirror_error<.003,('Reflected sculpt mismatch',mirror_error)
        saved=output/'mixed-corrective.mb';cmds.file(rename=str(saved));cmds.file(save=True,type='mayaBinary',force=True)
        cmds.file(str(saved),open=True,force=True,executeScriptNodes=False)
        assert same(points(),mirrored)
        report['stages'].append('actual_mirror_deformation_save_reopen')
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();raise
    finally:
        (output/'mixed.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.file(rename=str(output/'mixed-current.mb'));cmds.file(save=True,type='mayaBinary',force=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),'--soft' in sys.argv)
