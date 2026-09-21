"""Head aim with FK correction, keyed blend, skin, persistence and rebuild."""
import sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(folder,reopen=False):
    folder.mkdir(parents=True,exist_ok=True)
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import CreateFitSkeleton,BuildVariableBodySourceFit,BuildOrientedBodySkeleton,BuildBodyCharacterRig,BindSkin,RegisterBodyCharacter,RebuildBodyCharacter
        from adv_py.core.variable_body_fit import variable_axial_description
        from adv_py.adapters.maya_head_aim import audit
        if reopen:
            c.file(str((folder/'head-2.ma').resolve()),open=True,force=True);c.undoInfo(state=True)
            host=MayaBodyBuildHost(namespace='hero');reg=host.read_character_registration()
            c.currentTime(11,edit=True,update=True)
            baseline=host.capture_character_pose(reg)
            target=host.scene_address(next(ch.node for ch in reg.channels if ch.key=='head.aim.target.translateX'))
            control=host.scene_address(next(ch.node for ch in reg.channels if ch.key=='head.aim.headAim'))
            origin=c.xform(control,q=True,ws=True,t=True)
            c.undoInfo(openChunk=True,chunkName='Invalid aim probe')
            source=c.connectionInfo(target+'.translateX',sourceFromDestination=True)
            c.disconnectAttr(source,target+'.translateX');c.xform(target,ws=True,t=origin)
            try:host.capture_character_pose(reg)
            except ValueError:rejected=True
            else:rejected=False
            c.undoInfo(closeChunk=True);c.undo()
            report={'invalid_pose_rejected':rejected,'undo_restores_pose':host.capture_character_pose(reg)==baseline,
                'animation_samples':len(host.sample_character_animation(reg,(1.,6.,11.,16.,21.)))==5}
            (folder/'read.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
            return 0 if all(report.values()) else 1
        reports=[]
        for count,axis in ((2,'z'),(4,'z'),(8,'y')):
            c.file(new=True,force=True);c.undoInfo(state=True);c.upAxis(axis=axis,rotateView=False);c.namespace(addNamespace='hero')
            host=MayaBodyBuildHost(namespace='hero');CreateFitSkeleton(host).apply()
            BuildVariableBodySourceFit(host).apply(spine_segments=count,with_hand=False)
            body=BuildOrientedBodySkeleton(host).apply().snapshot
            result=BuildBodyCharacterRig(host).apply(include_torso=True,include_spine_ik=count==2,include_control_spaces=True,
                include_head_aim=True,axial_description=variable_axial_description(count))
            plan=result.plan.torso.torso.head_aim
            head=next(j for j in body.joints if j.name=='Head_M')
            if count==2:RegisterBodyCharacter(host).apply(result)
            mesh=c.polyCube(name='hero:HeadProbe',constructionHistory=False)[0];c.xform(mesh,ws=True,t=head.world_position)
            mesh=host._cmds.identity.to_local(c.ls(mesh,long=True)[0]);BindSkin(host).apply(mesh,(head.path,),skin_name='AdvPy_HeadSkin',maximum_influences=1)
            target=host.scene_address(plan.target);control=host.scene_address(plan.head_control)
            points=lambda:tuple(c.xform(host.scene_address(mesh)+'.vtx[*]',q=True,ws=True,t=True))
            before=points();c.setAttr(target+'.translateX',2.)
            disabled=max(abs(a-b) for a,b in zip(before,points()))
            c.setAttr(control+'.headAim',1.);audit(host,plan.head_control,plan.target)
            m=c.xform(host.scene_address(head.path),q=True,ws=True,matrix=True)
            goal=c.xform(target,q=True,ws=True,t=True);direction=[b-a for a,b in zip(m[12:15],goal)]
            gaze=tuple(sum(plan.aim_axis[i]*m[4*i+j] for i in range(3)) for j in range(3))
            length=math.sqrt(sum(v*v for v in direction));alignment=sum(a*b for a,b in zip(gaze,direction))/length
            aimed=points();c.setAttr(control+'.rotateZ',12.);corrected=points()
            correction=max(abs(a-b) for a,b in zip(aimed,corrected));c.setAttr(control+'.rotateZ',0.)
            displacement=max(abs(a-b) for a,b in zip(before,aimed))
            local=c.getAttr(target+'.translate')[0]
            origin=c.xform(host.scene_address(plan.pivot),q=True,ws=True,t=True)
            c.xform(target,ws=True,t=origin)
            try:audit(host,plan.head_control,plan.target)
            except ValueError:singular=True
            else:singular=False
            c.setAttr(target+'.translate',*local,type='double3')
            for frame,weight in ((1,0.),(11,1.),(21,.5)):
                host._cmds.setKeyframe(plan.head_control,attribute='headAim',time=frame,value=weight)
                host._cmds.setKeyframe(plan.target,attribute='translateX',time=frame,value=frame*.1)
            def sample():
                rows=[]
                with host._character_sampling_time() as seek:
                    for frame in (1.,6.,11.,16.,21.):
                        seek(frame);audit(host,plan.head_control,plan.target);rows.append(points())
                return rows
            expected=sample();rebuild=True
            if count==2:
                rebuilt=RebuildBodyCharacter(host).apply('replacement');actual=sample()
                rebuild=max(abs(a-b) for row,other in zip(expected,actual) for a,b in zip(row,other))<1e-4
                c.undo();actual=sample()
                rebuild &= max(abs(a-b) for row,other in zip(expected,actual) for a,b in zip(row,other))<1e-4
                c.redo();host.read_character_registration();sample()
            filename=folder/f'head-{count}.ma';c.file(rename=str(filename.resolve()));c.file(save=True,type='mayaAscii',force=True)
            c.file(str(filename.resolve()),open=True,force=True);actual=sample()
            error=max(abs(a-b) for row,other in zip(expected,actual) for a,b in zip(row,other))
            report={'segments':count,'disabled_error':disabled,'aim_alignment':alignment,'aim_displacement':displacement,'fk_correction':correction,
                'singular_target_rejected':singular,'rebuild_preserved':rebuild,'reopen_error':error}
            report['passed']=disabled<1e-4 and alignment>.9999 and displacement>.01 and correction>.01 and singular and rebuild and error<1e-4
            print(json.dumps(report));reports.append(report)
        (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
        return 0 if all(row['passed'] for row in reports) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),'--reopen' in sys.argv))
