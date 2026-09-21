"""Variable spline spine, FK/IK, stretch, global scale and real skin."""
import sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(folder, reopen=False, rebuild=False):
    folder.mkdir(parents=True,exist_ok=True);maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import CreateFitSkeleton,BuildVariableBodySourceFit,BuildOrientedBodySkeleton,BuildBodyCharacterRig,BindSkin
        from adv_py.core.variable_body_fit import variable_axial_description
        from adv_py.adapters.maya_spline import audit
        from adv_py.application import (RegisterBodyCharacter, ResolveBodyCharacter,
            CaptureBodyCharacterAnimation, ApplyBodyCharacterAnimation, save_character_animation, load_character_animation)
        from adv_py.core.character_pose import character_pose_error
        reports=[]
        if reopen or rebuild:
            for count in (1,4,8):
                c.file(str((folder/f'spline-{count}.ma').resolve()),open=True,force=True)
                c.undoInfo(state=True)
                host=MayaBodyBuildHost(namespace='hero')
                registration=ResolveBodyCharacter(host).execute()
                expected=load_character_animation(folder/f'animation-{count}.json')
                rebuild_checks = True
                if rebuild:
                    from adv_py.application.character_rebuild import RebuildBodyCharacter
                    original_keys=host.capture_character_key_state(registration)
                    original_ids=tuple(n.uuid for n in registration.nodes)
                    result=RebuildBodyCharacter(host).apply('replacement')
                    current=ResolveBodyCharacter(host).execute()
                    rebuild_checks=tuple(n.uuid for n in current.nodes)!=original_ids
                    c.undo()
                    restored=ResolveBodyCharacter(host).execute()
                    rebuild_checks=rebuild_checks and tuple(n.uuid for n in restored.nodes)==original_ids and host.capture_character_key_state(restored)==original_keys
                    c.redo()
                    registration=ResolveBodyCharacter(host).execute()
                    rebuild_checks=rebuild_checks and tuple(n.uuid for n in registration.nodes)==tuple(n.uuid for n in current.nodes)
                if rebuild and count==4:
                    class FailingPromotion(MayaBodyBuildHost):
                        def promote_character_rebuild(self, staged):
                            super().promote_character_rebuild(staged)
                            raise RuntimeError('Injected failure after spline promotion')
                    before_failure=ResolveBodyCharacter(host).execute()
                    before_failure_keys=host.capture_character_key_state(before_failure)
                    try:
                        RebuildBodyCharacter(FailingPromotion(namespace='hero')).apply('replacement')
                    except RuntimeError as exc:
                        if 'Injected failure' not in str(exc):raise
                        rebuild_checks=rebuild_checks and ResolveBodyCharacter(host).execute()==before_failure and host.capture_character_key_state(before_failure)==before_failure_keys
                    else:rebuild_checks=False
                actual=CaptureBodyCharacterAnimation(host).execute(1,21,5)
                body_error=max(character_pose_error(a,b) for (_,a),(_,b) in zip(expected.samples,actual.samples))
                wanted=json.loads((folder/f'points-{count}.json').read_text(encoding='utf-8'))
                with host._character_sampling_time() as seek:
                    mesh_error=0.
                    for frame,points in wanted:
                        seek(frame)
                        current=c.xform('hero:SplineProbe.vtx[*]',q=True,ws=True,t=True)
                        mesh_error=max(mesh_error,max(abs(a-b) for a,b in zip(points,current)))
                ApplyBodyCharacterAnimation(host).apply(expected)
                if rebuild:c.file(save=True,type='mayaAscii',force=True)
                row=dict(segments=count,body_error=body_error,mesh_error=mesh_error,continued_editing=True,
                         passed=rebuild_checks and body_error<1e-4 and mesh_error<1e-4)
                if rebuild:row["rebuild_undo_redo_and_rollback"] = rebuild_checks
                reports.append(row)
            (folder/('rebuild.json' if rebuild else 'reopen.json')).write_text(json.dumps(reports,indent=2),encoding='utf-8')
            print(json.dumps(reports));return 0 if all(r['passed'] for r in reports) else 1
        for count,axis in ((1,'z'),(4,'z'),(8,'y')):
            c.file(new=True,force=True);c.undoInfo(state=True);c.upAxis(axis=axis,rotateView=False);c.namespace(addNamespace='hero')
            host=MayaBodyBuildHost(namespace='hero');CreateFitSkeleton(host).apply()
            BuildVariableBodySourceFit(host).apply(spine_segments=count,with_hand=count==4)
            body=BuildOrientedBodySkeleton(host).apply().snapshot
            options=dict(include_torso=True,include_spine_ik=True,include_head_aim=True,include_control_spaces=True,axial_description=variable_axial_description(count))
            matrices=lambda:tuple(tuple(c.xform(host.scene_address(j.path),q=True,ws=True,matrix=True)) for j in body.joints)
            error=lambda a,b:max(abs(x-y) for left,right in zip(a,b) for x,y in zip(left,right))
            before=matrices();result=BuildBodyCharacterRig(host).apply(**options);plan=result.plan.torso.torso.spline
            neutral=error(before,matrices());c.undo();undone=not c.objExists('hero:AdvPy_SplineMechanisms');c.redo();audit(host,plan)
            rollback=True
            if count==4:
                c.undo();original_nodes=set(host._cmds.ls(long=True))
                class FailingHost(MayaBodyBuildHost):
                    def capture_body_torso(self,torso):
                        super().capture_body_torso(torso)
                        raise RuntimeError('injected spline verification failure')
                try:BuildBodyCharacterRig(FailingHost(namespace='hero')).apply(**options)
                except RuntimeError as exc:
                    if 'injected spline' not in str(exc):raise
                    rollback=set(host._cmds.ls(long=True))==original_nodes and error(before,matrices())<1e-4
                else:rollback=False
                result=BuildBodyCharacterRig(host).apply(**options);plan=result.plan.torso.torso.spline
            c.setAttr('hero:AdvPy_SplineRatio.input2X',99.)
            try:audit(host,plan)
            except ValueError:tamper=True
            else:tamper=False
            c.setAttr('hero:AdvPy_SplineRatio.input2X',sum(plan.lengths))
            registration=RegisterBodyCharacter(host).apply(result)
            settings=host.scene_address(plan.settings)
            c.setAttr(settings+'.spineIkFk',1.)
            ik_neutral=error(before,matrices())
            joint=next(j for j in body.joints if j.path==plan.body_joints[max(1,count//2)])
            mesh=c.polyCube(name='hero:SplineProbe',constructionHistory=False)[0];c.xform(mesh,ws=True,t=joint.world_position)
            mesh=host._cmds.identity.to_local(c.ls(mesh,long=True)[0]);BindSkin(host).apply(mesh,(joint.path,),skin_name='AdvPy_SplineProbeSkin',maximum_influences=1)
            points=lambda:tuple(c.xform(host.scene_address(mesh)+'.vtx[*]',q=True,ws=True,t=True))
            original=points();length=sum(plan.lengths);c.setAttr(settings+'.translateX',length*.5)
            ratio=c.getAttr('hero:AdvPy_SplineClamp.outputR')
            endpoint=c.xform(host.scene_address(plan.body_joints[-1]),q=True,ws=True,t=True)
            target=c.xform(settings,q=True,ws=True,t=True);end_error=max(abs(a-b) for a,b in zip(endpoint,target))
            volume=c.getAttr('hero:AdvPy_SplineVolume.outputX')
            global_plug=host.scene_address(result.plan.global_control.control_path+'.'+result.plan.global_control.scale_attribute)
            c.setAttr(global_plug,2.);scaled_ratio=c.getAttr('hero:AdvPy_SplineClamp.outputR')
            expected_scale=(2.,2.*volume,2.*volume)
            scale_error=0.
            for node in plan.body_joints[1:]:
                matrix=c.xform(host.scene_address(node),q=True,ws=True,matrix=True)
                actual_scale=tuple(sum(v*v for v in matrix[k:k+3])**.5 for k in (0,4,8))
                scale_error=max(scale_error,max(abs(a-b) for a,b in zip(actual_scale,expected_scale)))
            c.setAttr(settings+'.stretch',0.);rest_lengths=tuple(c.getAttr(host.scene_address(j.path)+'.translateX') for j in plan.joints[len(plan.body_joints)+1:])
            c.setAttr(global_plug,1.);c.setAttr(settings+'.stretch',1.);c.setAttr(settings+'.translateX',0.)
            c.setAttr(host.scene_address(plan.targets[1])+'.translateY',1.)
            deformed=points();displacement=max(abs(a-b) for a,b in zip(original,deformed))
            c.setAttr(settings+'.spineIkFk',0.);fk_return=error(before,matrices())
            for frame,weight,bend in ((1,0.,0.),(11,1.,1.),(21,.5,-.5)):
                host._cmds.setKeyframe(plan.settings,attribute='spineIkFk',time=frame,value=weight)
                host._cmds.setKeyframe(plan.targets[1],attribute='translateY',time=frame,value=bend)
            def sample():
                with host._character_sampling_time() as seek:
                    rows=[]
                    for frame in (1.,6.,11.,16.,21.):seek(frame);rows.append(points())
                    return rows
            expected=sample()
            clip=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            save_character_animation(clip,folder/f'animation-{count}.json')
            ApplyBodyCharacterAnimation(host).apply(clip)
            restored=CaptureBodyCharacterAnimation(host).execute(1,21,5)
            animation_error=max(character_pose_error(a,b) for (_,a),(_,b) in zip(clip.samples,restored.samples))
            (folder/f'points-{count}.json').write_text(json.dumps(list(zip((1,6,11,16,21),expected))),encoding='utf-8')
            filename=folder/f'spline-{count}.ma';c.file(rename=str(filename.resolve()));c.file(save=True,type='mayaAscii',force=True)
            c.file(str(filename.resolve()),open=True,force=True);audit(host,plan)
            ResolveBodyCharacter(host).execute()
            reopened=error(expected,sample())
            report={'segments':count,'neutral_error':neutral,'ik_neutral_error':ik_neutral,'undo':undone,'stretch_ratio':ratio,
                'world_scale_error':scale_error,'animation_error':animation_error,'endpoint_error':end_error,'volume':volume,'scaled_ratio':scaled_ratio,'stretch_off_lengths':rest_lengths,
                'bend_displacement':displacement,'fk_return_error':fk_return,'tamper_rejected':tamper,'failure_rollback':rollback,'reopen_error':reopened}
            report['passed']=scale_error<1e-5 and animation_error<1e-4 and neutral<1e-4 and ik_neutral<1e-4 and undone and abs(ratio-1.5)<1e-4 and end_error<1e-3 and abs(volume-1/math.sqrt(1.5))<1e-4 and abs(scaled_ratio-ratio)<1e-4 and all(abs(a-b)<1e-5 for a,b in zip(rest_lengths,plan.lengths)) and displacement>.01 and fk_return<1e-4 and tamper and rollback and reopened<1e-4
            reports.append(report);print(json.dumps(report))
        (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
        return 0 if all(row['passed'] for row in reports) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),reopen="--reopen" in sys.argv[2:],rebuild="--rebuild" in sys.argv[2:]))
