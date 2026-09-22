"""Generated non-4-to-6 variable-spine character replacement with original Skin."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(mode,folder):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost,MayaOriginalSkinSpineMigrationHost
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        from adv_py.application import (CreateFitSkeleton,BuildVariableBodySourceFit,
            BuildOrientedBodySkeleton,BuildBodyCharacterRig,RegisterBodyCharacter,
            ReplaceRegisteredSpineCharacter)
        from adv_py.core.variable_body_fit import variable_axial_description

        source_count,target_count=((4,8) if '4to8' in mode else (8,4))
        stem=f'spine-{source_count}-to-{target_count}'
        skin='source:SourceSkin';mesh='|source:SourceMesh'
        frames=tuple(1+i*.25 for i in range(37))
        def points():
            old=cmds.currentTime(query=True)
            undo=cmds.undoInfo(query=True,state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                rows={}
                for frame in frames:
                    cmds.currentTime(frame,edit=True)
                    rows[frame]=tuple(tuple(cmds.xform(mesh+f'.vtx[{i}]',
                        query=True,worldSpace=True,translation=True))
                        for i in range(4))
                return rows
            finally:
                cmds.currentTime(old,edit=True)
                cmds.undoInfo(stateWithoutFlush=undo)
        if mode.startswith('inspect'):
            scene=sys.argv[3] if len(sys.argv)>3 else stem+'-replaced.ma'
            cmds.file(str(folder/(stem+'-before.ma')),open=True,force=True)
            before=points()
            cmds.file(str(folder/scene),open=True,force=True)
            reg=MayaBodyBuildHost(namespace='source').read_character_registration()
            after=points()
            error=max(abs(a-b) for frame in frames
                for old,new in zip(before[frame],after[frame])
                for a,b in zip(old,new))
            if (cmds.namespace(exists='target')
                    or len(reg.spine.body_joints)!=target_count+1
                    or error>.08):
                raise RuntimeError('变段数角色替换重开无效')
            print('TOPOLOGY_REOPEN',json.dumps(dict(source=source_count,
                target=target_count,mesh_error=error)),flush=True)
            return

        cmds.file(new=True,force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis='z',rotateView=False)
        registrations={}
        for namespace,count in (('source',source_count),('target',target_count)):
            cmds.namespace(addNamespace=namespace)
            host=MayaBodyBuildHost(namespace=namespace)
            CreateFitSkeleton(host).apply()
            BuildVariableBodySourceFit(host).apply(spine_segments=count)
            BuildOrientedBodySkeleton(host).apply()
            rig=BuildBodyCharacterRig(host).apply(include_torso=True,
                include_spine_ik=True,include_control_spaces=True,
                axial_description=variable_axial_description(count))
            registrations[namespace]=RegisterBodyCharacter(host).apply(rig)
        source=MayaBodyBuildHost(namespace='source')
        source_reg=registrations['source']
        source_spine=tuple(source.scene_address(path)
                           for path in source_reg.spine.body_joints)
        shoulder=next(source.scene_address(row.path) for row in source_reg.body
                      if row.path.rsplit('|',1)[-1].endswith('Shoulder_R'))
        created=cmds.polyPlane(name='source:SourceMesh',width=2.,height=2.,
            subdivisionsX=1,subdivisionsY=1,constructionHistory=False)[0]
        if cmds.ls(created,long=True)!=[mesh]:
            raise RuntimeError('来源网格路径与验收合同不符')
        cmds.skinCluster(*source_spine,shoulder,mesh,name=skin,
            toSelectedBones=True,maximumInfluences=source_count+2)
        for index in range(4):
            cmds.skinPercent(skin,mesh+f'.vtx[{index}]',
                transformValue=((source_spine[1],.5),(shoulder,.5))
                if index==0 else ((source_spine[-1],1.),))
        channels={ch.key:ch for ch in source_reg.channels}
        for frame,amount in ((1,0.),(5,1.),(10,2.)):
            for key,value in (('global.translateX',amount*3.),
                              ('torso.TorsoSpine1_MFK.rotateZ',amount*3.),
                              ('arm.fk.ShoulderFK_R.rotateZ',amount*4.)):
                ch=channels[key]
                source._cmds.setKeyframe(ch.node,attribute=ch.attribute,
                    time=frame,value=value)
        wanted=points()
        cmds.currentTime(1,edit=True)
        mesh_uuid=cmds.ls(mesh,uuid=True)[0]
        skin_uuid=cmds.ls(skin,uuid=True)[0]
        skin_host=MayaOriginalSpinePromotionHost()
        original_weights=skin_host.capture_all_skin_weights(skin,mesh)
        cmds.file(rename=str(folder/(stem+'-before.ma')))
        cmds.file(save=True,type='mayaAscii',force=True)
        service=ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target'))
        try:
            service.apply('source','target',skin,mesh,start_frame=1,
                end_frame=10,max_mesh_error=.05)
        except Exception as exc:
            rejected=('FK 迁移原网格误差超限' in str(exc)
                      and cmds.namespace(exists='target')
                      and cmds.ls(mesh_uuid,long=True)==[mesh]
                      and cmds.ls(skin_uuid)==[skin]
                      and skin_host.capture_all_skin_weights(skin,mesh)
                      ==original_weights
                      and len(source.read_character_registration().spine.body_joints)
                      ==source_count+1)
        else:rejected=False
        if not rejected:raise RuntimeError('FK 网格误差门槛未整体回滚')
        result=service.apply('source','target',skin,mesh,start_frame=1,
            end_frame=10,max_mesh_error=.08)
        actual=points()
        error=max(abs(a-b) for frame in frames
            for old,new in zip(wanted[frame],actual[frame])
            for a,b in zip(old,new))
        promoted=(not cmds.namespace(exists='target')
                  and cmds.ls(mesh_uuid,long=True)==[mesh]
                  and cmds.ls(skin_uuid)==[skin]
                  and len(skin_host.capture_all_skin_weights(skin,mesh)
                          .influence_paths)==target_count+2
                  and len(source.read_character_registration().spine.body_joints)
                  ==target_count+1)
        cmds.undo()
        undone=(cmds.namespace(exists='target')
                and skin_host.capture_all_skin_weights(skin,mesh)==original_weights
                and len(source.read_character_registration().spine.body_joints)
                ==source_count+1)
        cmds.redo()
        redone=(not cmds.namespace(exists='target')
                and len(source.read_character_registration().spine.body_joints)
                ==target_count+1)
        report=dict(source=source_count,target=target_count,rejected=rejected,
                    promoted=promoted,
                    undo=undone,redo=redone,mesh_error=error,
                    frames=result.frames,vertices=result.vertices)
        print('TOPOLOGY',json.dumps(report),flush=True)
        if not all((rejected,promoted,undone,redone,result.frames==10,
                    result.vertices==4,error<=.08)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder/(stem+'-replaced.ma')))
        cmds.file(save=True,type='mayaAscii',force=True)
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]).resolve())
