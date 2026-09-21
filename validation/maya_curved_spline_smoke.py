"""Curved Fit spine: spline controls, bind-pose calibration and real skin."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(folder):
    folder.mkdir(parents=True,exist_ok=True);maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (CreateFitSkeleton,BuildVariableBodySourceFit,
            EditFitJointPositions,OrientSimpleFitChain,BuildOrientedBodySkeleton,BuildBodyCharacterRig,
            RegisterBodyCharacter,BindSkin,ResolveBodyCharacter,EnableBodyCharacterSplineAnimation,
            BakeBodyCharacterSpineMode,RebuildBodyCharacter)
        from adv_py.core.fit_position import FitJointPositionEdit,FitJointPositionPatch
        from adv_py.core.fit_orientation import FitOrientationRequest
        from adv_py.core.variable_body_fit import variable_axial_description
        reports=[]
        for count,axis in ((4,'z'),(8,'y')):
            c.file(new=True,force=True);c.undoInfo(state=True);c.upAxis(axis=axis,rotateView=False)
            c.namespace(addNamespace='hero');host=MayaBodyBuildHost(namespace='hero')
            CreateFitSkeleton(host).apply();BuildVariableBodySourceFit(host).apply(spine_segments=count)
            fit=host.capture_fit_hierarchy('|FitSkeleton')
            offsets=(.25,-.3,.21) if count==4 else (.13,.12,-.2,-.1,.17,.08,-.12)
            lateral=1
            edits=[]
            for i,offset in enumerate(offsets,1):
                joint=next(row for row in fit.joints if row.short_name==f'Spine{i}')
                values=list(joint.local_position);values[lateral]+=offset
                edits.append(FitJointPositionEdit(joint.path,tuple(values)))
            EditFitJointPositions(host).apply(FitJointPositionPatch(tuple(edits)),fit.container)
            OrientSimpleFitChain(host).apply(FitOrientationRequest(tuple(f'Spine{i}' for i in range(1,count))))
            body=BuildOrientedBodySkeleton(host).apply().snapshot
            matrices=lambda:tuple(tuple(c.xform(host.scene_address(j.path),q=True,ws=True,matrix=True)) for j in body.joints)
            error=lambda a,b:max(abs(x-y) for left,right in zip(a,b) for x,y in zip(left,right))
            before=matrices()
            result=BuildBodyCharacterRig(host).apply(include_torso=True,include_spine_ik=True,
                include_head_aim=True,include_control_spaces=True,axial_description=variable_axial_description(count))
            plan=result.plan.torso.torso.spline
            fk_error=error(before,matrices())
            reg=RegisterBodyCharacter(host).apply(result)
            c.setAttr(host.scene_address(plan.settings)+'.spineIkFk',1.)
            ik_error=error(before,matrices())
            if ik_error>1e-4:
                differences=[(j.name,max(abs(a-b) for a,b in zip(first,last))) for j,first,last in zip(body.joints,before,matrices())]
                print('IK_DIFF',sorted(differences,key=lambda row:-row[1])[:8],flush=True)
            c.undo();ik_undo=host.read_character_registration()==reg
            c.redo();ik_redo=host.read_character_registration()==reg
            joint=next(j for j in body.joints if j.path==plan.body_joints[count//2])
            mesh=c.polyCube(name='hero:CurvedProbe',constructionHistory=False)[0]
            c.xform(mesh,ws=True,t=joint.world_position)
            mesh=host._cmds.identity.to_local(c.ls(mesh,long=True)[0])
            BindSkin(host).apply(mesh,(joint.path,),skin_name='AdvPy_CurvedProbeSkin',maximum_influences=1)
            points=lambda:tuple(c.xform(host.scene_address(mesh)+'.vtx[*]',q=True,ws=True,t=True))
            original=points();control=plan.targets[count//2+1]
            c.setAttr(host.scene_address(control)+'.translateX',.35)
            moved=max(abs(a-b) for a,b in zip(original,points()))
            expected=points();neutral_recovered=0.
            c.setAttr(host.scene_address(control)+'.translateX',0.)
            neutral_recovered=max(abs(a-b) for a,b in zip(original,points()))
            c.setAttr(host.scene_address(control)+'.translateX',.35)
            filename=(folder/f'curved-{count}.ma').resolve();c.file(rename=str(filename));c.file(save=True,type='mayaAscii',force=True)
            c.file(str(filename),open=True,force=True);ResolveBodyCharacter(host).execute()
            reopen=max(abs(a-b) for a,b in zip(expected,points()))
            c.setAttr(host.scene_address(plan.settings)+'.volume',0.)
            EnableBodyCharacterSplineAnimation(host).apply()
            animated=matrices()
            BakeBodyCharacterSpineMode(host).execute(1,1,'fk')
            fk_match=error(animated,matrices())
            c.setAttr(host.scene_address(control)+'.translateX',.1)
            BakeBodyCharacterSpineMode(host).execute(1,1,'ik')
            ik_match=error(animated,matrices())
            matched=matrices();c.file(save=True,type='mayaAscii',force=True)
            c.file(str(filename),open=True,force=True);ResolveBodyCharacter(host).execute()
            matched_reopen=error(matched,matrices())
            if count==4:
                RebuildBodyCharacter(host).apply('replacement')
                rebuilt=error(matched,matrices())
            else:rebuilt=0.
            row=dict(segments=count,targets=len(plan.targets),fk_error=fk_error,ik_error=ik_error,
                     undo=ik_undo,redo=ik_redo,skin_displacement=moved,neutral_recovered=neutral_recovered,reopen_error=reopen,
                     fk_match=fk_match,ik_match=ik_match,matched_reopen=matched_reopen,rebuilt=rebuilt)
            row['passed']=all((ik_undo,ik_redo)) and len(plan.targets)==count+2 and max(fk_error,ik_error,neutral_recovered,reopen,fk_match,ik_match,matched_reopen,rebuilt)<1e-4 and moved>.001
            reports.append(row);print(json.dumps(row),flush=True)
        (folder/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
        return 0 if all(row['passed'] for row in reports) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1])))
