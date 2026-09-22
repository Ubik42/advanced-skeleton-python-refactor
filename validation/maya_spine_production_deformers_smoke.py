"""Changed-spine replacement with BlendShape, Skin, DeltaMush and Wrap."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import maya.standalone


def main(mode,folder):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c,mel
        from adv_py.adapters import MayaBodyBuildHost,MayaOriginalSkinSpineMigrationHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        mesh='|source:SourceMesh';skin='source:SourceSkin'
        blend='source:ProductionBlend';mush='source:SourceDeltaMush'
        wrap='source:ProductionWrap';driver='source:WrapDriver'
        base='source:WrapDriverBase'
        frames=tuple(1+i*.25 for i in range(37))
        def points(frame):
            old=c.currentTime(query=True)
            undo=c.undoInfo(query=True,state=True)
            c.undoInfo(stateWithoutFlush=False)
            try:
                c.currentTime(frame,edit=True)
                return tuple(tuple(c.xform(mesh+f'.vtx[{i}]',
                    query=True,worldSpace=True,translation=True)) for i in range(4))
            finally:
                c.currentTime(old,edit=True)
                c.undoInfo(stateWithoutFlush=undo)
        def state():
            history=tuple(c.listHistory(mesh,pruneDagObjects=True) or ())
            uuids=tuple(c.ls(node,uuid=True)[0]
                        for node in (mesh,blend,skin,mush,wrap,driver,base))
            attributes=tuple(c.getAttr(plug) for plug in
                (blend+'.weight[0]',mush+'.smoothingIterations',
                 wrap+'.envelope',wrap+'.maxDistance',wrap+'.autoWeightThreshold'))
            return history,uuids,attributes
        if mode=='inspect':
            scene=sys.argv[3] if len(sys.argv)>3 else 'spine-deformers-replaced.ma'
            c.file(str(folder/scene),open=True,force=True)
            reg=MayaBodyBuildHost(namespace='source').read_character_registration()
            if c.namespace(exists='target') or len(reg.spine.body_joints)!=7:
                raise RuntimeError('复杂变形器角色重开无效')
            expected=json.loads((folder/'spine-deformers-baseline.json').read_text(
                encoding='utf8'))
            actual={str(frame):points(frame) for frame in frames}
            error=max(abs(a-b) for frame in frames
                for left,right in zip(expected['samples'][str(frame)],actual[str(frame)])
                for a,b in zip(left,right))
            before=points(1)
            c.move(.1,driver+'.vtx[0]',relative=True,moveX=True)
            after=points(1)
            wrap_effect=max(abs(a-b) for left,right in zip(before,after)
                            for a,b in zip(left,right))
            if (json.loads(json.dumps(state()))!=expected['state']
                    or error>.1 or wrap_effect<.001):
                raise RuntimeError(('复杂变形器重开误差超限',error,wrap_effect))
            print('DEFORMER_REOPEN_OK',json.dumps(dict(
                mesh_error=error,wrap_effect=wrap_effect)),flush=True)
            return

        c.file(str(folder/'full-spine-replacement-before.ma'),open=True,force=True)
        c.undoInfo(state=True)
        c.currentTime(1,edit=True)
        target=c.duplicate(mesh,name='source:BlendTarget')[0]
        c.move(.3,target+'.vtx[0]',relative=True,moveX=True)
        blend=c.blendShape(target,mesh,frontOfChain=True,
                           name='source:ProductionBlend')[0]
        c.setAttr(blend+'.weight[0]',.6)
        c.delete(target)
        driver=c.duplicate(mesh,name='source:WrapDriver')[0]
        c.select(mesh,driver,replace=True)
        c.namespace(setNamespace=':source')
        try:mel.eval('CreateWrap')
        finally:c.namespace(setNamespace=':')
        wraps=c.ls(type='wrap') or []
        if len(wraps)!=1:raise RuntimeError('Wrap 未生成唯一节点：'+repr(wraps))
        wrap=c.rename(wraps[0],'source:ProductionWrap')
        driver_path=(c.ls(driver,long=True,type='transform') or [None])[0]
        base_path=(c.ls('source:WrapDriverBase',long=True,
                        type='transform') or [None])[0]
        if not driver_path or not base_path:
            raise RuntimeError('Wrap 独立驱动资产缺失')
        c.setAttr(wrap+'.envelope',.2)
        c.setAttr(wrap+'.maxDistance',100.)
        c.setAttr(wrap+'.autoWeightThreshold',False)
        c.setAttr(driver+'.inflType',1)
        c.move(.15,driver+'.vtx[0]',relative=True,moveX=True)
        samples={frame:points(frame) for frame in frames}
        wanted=state()
        (folder/'spine-deformers-baseline.json').write_text(json.dumps(dict(
            state=wanted,samples=samples),indent=2),encoding='utf8')
        c.file(rename=str(folder/'spine-deformers-before.ma'))
        c.file(save=True,type='mayaAscii',force=True)
        service=ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target'))
        try:
            service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                retained_assets=('|source:AdvPy_CharacterControls',))
        except Exception as exc:
            rig_asset_rejected=('保留资产不能包含原 Rig' in str(exc)
                and c.namespace(exists='target') and state()==wanted)
        else:rig_asset_rejected=False
        if not rig_asset_rejected:
            raise RuntimeError('原 Rig 不能作为显式保留资产')
        try:
            service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                max_mesh_error=.01,retained_assets=(driver_path,base_path))
        except Exception as exc:
            mesh_rejected=('FK 迁移原网格误差超限' in str(exc)
                and c.namespace(exists='target') and state()==wanted
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints)==5)
        else:mesh_rejected=False
        if not mesh_rejected:raise RuntimeError('生产变形链网格误差拒绝未回滚')
        from adv_py.adapters.maya_spine_original_promotion import MayaOriginalSpinePromotionHost
        class FailedPromotionHost(MayaOriginalSpinePromotionHost):
            def apply_original_spine_promotion(self,plan):
                super().apply_original_spine_promotion(plan)
                raise RuntimeError('Injected deformer promotion failure')
        class FailedHost(MayaOriginalSkinSpineMigrationHost):
            def original_skin_handoff_host(self):
                return FailedPromotionHost()
        try:
            ReplaceRegisteredSpineCharacter(
                FailedHost(namespace='target')).apply('source','target',
                skin,mesh,start_frame=1,end_frame=10,
                max_mesh_error=.1,retained_assets=(driver_path,base_path))
        except RuntimeError as exc:
            if 'Injected deformer promotion failure' not in str(exc):raise
            rollback=(c.namespace(exists='target') and state()==wanted
                      and len(MayaBodyBuildHost(namespace='source')
                              .read_character_registration().spine.body_joints)==5
                      and all(points(frame)==samples[frame] for frame in frames))
        else:rollback=False
        if not rollback:raise RuntimeError('复杂变形器接管后故障未整体回滚')
        result=service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
            max_mesh_error=.1,retained_assets=(driver_path,base_path))
        actual=state()
        error=max(abs(a-b) for frame in samples
            for left,right in zip(samples[frame],points(frame))
            for a,b in zip(left,right))
        promoted=(not c.namespace(exists='target') and wanted==actual
                  and len(MayaBodyBuildHost(namespace='source')
                          .read_character_registration().spine.body_joints)==7)
        c.undo()
        undone=(c.namespace(exists='target') and state()==wanted
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints)==5)
        c.redo()
        redone=(not c.namespace(exists='target') and state()==wanted
                and len(MayaBodyBuildHost(namespace='source')
                        .read_character_registration().spine.body_joints)==7)
        report=dict(history_preserved=wanted==actual,error=error,
                    mesh_rejected=mesh_rejected,
                    rig_asset_rejected=rig_asset_rejected,
                    rollback=rollback,promoted=promoted,undo=undone,redo=redone,
                    frames=result.frames)
        print('DEFORMER_TOPOLOGY',json.dumps(report),flush=True)
        if not all((rig_asset_rejected,mesh_rejected,rollback,
                    promoted,undone,redone,error<=.1,
                    result.frames==10)):
            raise RuntimeError(report)
        c.file(rename=str(folder/'spine-deformers-replaced.ma'))
        c.file(save=True,type='mayaAscii',force=True)
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]).resolve())
