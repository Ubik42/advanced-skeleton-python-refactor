"""Hybrid mode events, two retained Skins, and an animated spine attachment."""
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
        from adv_py.application import ReplaceRegisteredSpineCharacter

        skins=(('source:SourceSkin','|source:SourceMesh'),
               ('source:SecondSkin','|source:SecondMesh'))
        frames=tuple(1+i*.25 for i in range(37))+(4.999,)

        def snapshot():
            accessory=(cmds.ls('source:Accessory',long=True) or [None])[0]
            if not accessory:raise RuntimeError('混合迁移附件缺失')
            rows={}
            undo=cmds.undoInfo(query=True,state=True)
            current=cmds.currentTime(query=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                for frame in frames:
                    cmds.currentTime(frame,edit=True)
                    meshes=tuple(tuple(tuple(cmds.xform(mesh+f'.vtx[{i}]',
                        query=True,worldSpace=True,translation=True))
                        for i in range(cmds.polyEvaluate(mesh,vertex=True)))
                        for _,mesh in skins)
                    world=tuple(cmds.xform(accessory,query=True,
                        worldSpace=True,matrix=True))
                    rows[frame]=(meshes,world)
            finally:
                cmds.currentTime(current,edit=True)
                cmds.undoInfo(stateWithoutFlush=undo)
            return rows

        def errors(before,after):
            meshes=tuple(max(abs(a-b) for frame in frames
                for old,new in zip(before[frame][0][index],after[frame][0][index])
                for a,b in zip(old,new)) for index in range(2))
            attachment=max(abs(a-b) for frame in frames
                for a,b in zip(before[frame][1],after[frame][1]))
            return meshes,attachment

        def skin_weights():
            return tuple((tuple(cmds.skinCluster(skin,query=True,influence=True) or ()),
                tuple(tuple(cmds.skinPercent(skin,mesh+f'.vtx[{i}]',
                    query=True,value=True) or ())
                    for i in range(cmds.polyEvaluate(mesh,vertex=True))))
                for skin,mesh in skins)

        if mode=='inspect':
            scene=sys.argv[3] if len(sys.argv)>3 else 'spine-hybrid-full-replaced.ma'
            cmds.file(str(folder/'spine-hybrid-full-before.ma'),open=True,force=True)
            before_accessory=(cmds.ls('source:Accessory',long=True) or [None])[0]
            before_uuid=cmds.ls(before_accessory,uuid=True)[0]
            before_curve=(cmds.listConnections(before_accessory+'.translateX',
                source=True,destination=False,type='animCurve') or [None])[0]
            before_curve_uuid=cmds.ls(before_curve,uuid=True)[0]
            wanted=snapshot()
            cmds.file(str(folder/scene),open=True,force=True)
            reg=MayaBodyBuildHost(namespace='source').read_character_registration()
            if cmds.namespace(exists='target') or len(reg.spine.body_joints)!=7:
                raise RuntimeError('混合多 Skin 角色重开无效')
            accessory=(cmds.ls('source:Accessory',long=True) or [None])[0]
            curve=(cmds.ls(before_curve_uuid) or [None])[0]
            if (cmds.ls(before_uuid,long=True)!=[accessory]
                    or cmds.getAttr(accessory+'.assetCode')!='rig-prop-A'
                    or curve is None
                    or tuple(cmds.keyframe(curve,query=True,timeChange=True)
                             or ())!=(1.,10.)
                    or tuple(cmds.keyframe(curve,query=True,valueChange=True)
                             or ())!=(0.,2.)):
                raise RuntimeError('混合多 Skin 附件或原动画曲线重开无效')
            actual=snapshot()
            mesh_errors,extension_error=errors(wanted,actual)
            if max(mesh_errors)>.2 or extension_error>1e-3:
                raise RuntimeError(('混合多 Skin 重开误差超限',mesh_errors,extension_error))
            print('HYBRID_FULL_REOPEN_OK',json.dumps(dict(
                mesh_errors=mesh_errors,extension_error=extension_error)),flush=True)
            return

        cmds.file(str(folder/'multi-skin-spine-before.ma'),open=True,force=True)
        cmds.undoInfo(state=True)
        source=MayaBodyBuildHost(namespace='source')
        reg=source.read_character_registration()
        channels={ch.key:ch for ch in reg.channels}
        cmds.currentTime(1,edit=True)
        neutral={ch.key:source._cmds.getAttr(ch.node+'.'+ch.attribute)
                 for ch in reg.channels}
        for frame in (1,3,5,10):
            for ch in reg.channels:
                if ch.key=='global.translateX':continue
                source._cmds.setKeyframe(ch.node,attribute=ch.attribute,
                    time=frame,value=neutral[ch.key],
                    inTangentType='linear',outTangentType='linear')
        mode_channel=channels['spine.spline.spineIkFk']
        for frame,value in ((1,0.),(3,0.),(4,0.),(5,1.),(10,1.)):
            source._cmds.setKeyframe(mode_channel.node,
                attribute=mode_channel.attribute,time=frame,value=value,
                inTangentType='linear',outTangentType='step')
        cmds.keyTangent(source.scene_address(mode_channel.node)+'.'
            +mode_channel.attribute,edit=True,outTangentType='step')
        fk=reg.spine.fk_controls[1]
        for frame,value in ((1,0.),(3,15.),(5,0.),(10,0.)):
            source._cmds.setKeyframe(fk,attribute='rotateY',time=frame,
                value=value,inTangentType='linear',outTangentType='linear')
        ik=channels['spine.spline.1.translateY']
        for frame,value in ((1,0.),(5,0.),(10,.225)):
            source._cmds.setKeyframe(ik.node,attribute=ik.attribute,
                time=frame,value=value,inTangentType='linear',outTangentType='linear')
        parent=source.scene_address(reg.spine.fk_controls[3])
        accessory=cmds.createNode('transform',name='source:Accessory',parent=parent)
        cmds.createNode('locator',name='source:AccessoryShape',parent=accessory)
        cmds.addAttr(accessory,longName='assetCode',dataType='string')
        cmds.setAttr(accessory+'.assetCode','rig-prop-A',type='string')
        cmds.setKeyframe(accessory,attribute='translateX',time=1,value=0.)
        cmds.setKeyframe(accessory,attribute='translateX',time=10,value=2.)
        accessory=(cmds.ls(accessory,long=True) or [None])[0]
        accessory_uuid=cmds.ls(accessory,uuid=True)[0]
        original_curve=(cmds.listConnections(accessory+'.translateX',
            source=True,destination=False,type='animCurve') or [None])[0]
        original_curve_uuid=cmds.ls(original_curve,uuid=True)[0]
        wanted=snapshot()
        original_weights=skin_weights()
        cmds.currentTime(1,edit=True)
        cmds.file(rename=str(folder/'spine-hybrid-full-before.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
        service=ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target'))
        try:
            service.apply_many('source','target',skins,start_frame=1,end_frame=10,
                spine_mode='hybrid',max_mesh_error=.05,max_body_error=1.,
                extensions=(accessory,))
        except Exception as exc:
            rejected=('原网格误差超限' in str(exc)
                      and '|source:SecondMesh' in str(exc)
                      and cmds.namespace(exists='target')
                      and cmds.ls(accessory_uuid,long=True)==[accessory])
        else:rejected=False
        if not rejected:raise RuntimeError('混合多 Skin 误差拒绝未恢复原场景')
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        class FailedPromotionHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_extensions(self,moves):
                super().apply_original_spine_extensions(moves)
                raise RuntimeError('Injected hybrid extension failure')
        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                return FailedPromotionHost()
        try:
            ReplaceRegisteredSpineCharacter(FailedHost(namespace='target')).apply_many(
                'source','target',skins,start_frame=1,end_frame=10,
                spine_mode='hybrid',max_mesh_error=.2,max_body_error=.001,
                extensions=(accessory,))
        except RuntimeError as exc:
            if 'Injected hybrid extension failure' not in str(exc):raise
            restored=snapshot()
            rollback=(cmds.namespace(exists='target')
                      and cmds.ls(accessory_uuid,long=True)==[accessory]
                      and cmds.ls(original_curve_uuid)
                      and skin_weights()==original_weights
                      and all(restored[frame]==wanted[frame] for frame in frames))
        else:rollback=False
        if not rollback:raise RuntimeError('混合附件后期故障未恢复原场景')
        result=service.apply_many('source','target',skins,start_frame=1,end_frame=10,
            spine_mode='hybrid',max_mesh_error=.2,max_body_error=.001,
            extensions=(accessory,))
        moved=(cmds.ls(accessory_uuid,long=True) or [None])[0]
        actual=snapshot()
        mesh_errors,extension_error=errors(wanted,actual)
        takeover=(not cmds.namespace(exists='target')
                  and len(source.read_character_registration().spine.body_joints)==7
                  and moved and moved.startswith('|source:')
                  and cmds.getAttr(moved+'.assetCode')=='rig-prop-A'
                  and cmds.ls(original_curve_uuid)
                  and result.skin_count==2)
        cmds.undo()
        undo=(cmds.namespace(exists='target')
              and cmds.ls(accessory_uuid,long=True)==[accessory]
              and len(source.read_character_registration().spine.body_joints)==5)
        cmds.redo()
        redo=(not cmds.namespace(exists='target')
              and cmds.ls(accessory_uuid,long=True)==[moved]
              and len(source.read_character_registration().spine.body_joints)==7)
        report=dict(rejected=rejected,rollback=rollback,
                    takeover=bool(takeover),undo=undo,redo=redo,
                    mesh_errors=mesh_errors,extension_error=extension_error)
        print('HYBRID_FULL',json.dumps(report),flush=True)
        if not all((rejected,rollback,takeover,undo,redo,max(mesh_errors)<=.2,
                    extension_error<=1e-3)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder/'spine-hybrid-full-replaced.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]).resolve())
