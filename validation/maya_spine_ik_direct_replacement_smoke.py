"""Direct spline-control replacement of a bent original-Skin character."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import maya.standalone


def main(mode, folder):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost, MayaOriginalSkinSpineMigrationHost
        from adv_py.application import ReplaceRegisteredSpineCharacter

        mesh = '|source:SourceMesh'
        skin = 'source:SourceSkin'
        if mode == 'inspect':
            scene = sys.argv[3] if len(sys.argv)>3 else 'spine-ik-direct-replaced.ma'
            cmds.file(str(folder/scene),open=True,force=True)
            reg = MayaBodyBuildHost(namespace='source').read_character_registration()
            if cmds.namespace(exists='target') or len(reg.spine.body_joints)!=7:
                raise RuntimeError('IK 角色重开登记无效')
            print('IK_REOPEN_OK',flush=True)
            return
        cmds.file(str(folder/'full-spine-replacement-before.ma'),open=True,force=True)
        cmds.undoInfo(state=True)
        source = MayaBodyBuildHost(namespace='source')
        reg = source.read_character_registration()
        channels = {ch.key:ch for ch in reg.channels}
        for frame in (1,5,10):
            for key,value in (('spine.spline.spineIkFk',1.),
                              ('spine.spline.1.translateY',(frame-1)*.025)):
                ch=channels[key]
                source._cmds.setKeyframe(ch.node,attribute=ch.attribute,
                                         time=frame,value=value)
        frames=tuple(sorted({*range(1,11),*(i+.5 for i in range(1,10))}))
        def points(frame):
            enabled=cmds.undoInfo(query=True,state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                cmds.currentTime(frame,edit=True)
            finally:
                cmds.undoInfo(stateWithoutFlush=enabled)
            return tuple(tuple(cmds.xform(mesh+f'.vtx[{i}]',query=True,
                worldSpace=True,translation=True)) for i in range(4))
        before={frame:points(frame) for frame in frames}
        cmds.currentTime(1,edit=True)
        cmds.file(rename=str(folder/'spine-ik-direct-before.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
        service=ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target'))
        try:
            service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                          spine_mode='ik',max_mesh_error=1.,max_body_error=.00001)
        except Exception as exc:
            body_rejected=('IK 迁移身体空间误差超限' in str(exc)
                           and 'frame=1' not in str(exc)
                           and cmds.namespace(exists='target'))
        else:
            body_rejected=False
        if not body_rejected:
            raise RuntimeError('IK 身体弯曲误差上限未按预期回滚')
        try:
            service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                          spine_mode='ik',max_mesh_error=0.,max_body_error=1.)
        except Exception as exc:
            rejected = ('IK 迁移原网格误差超限' in str(exc)
                        and cmds.namespace(exists='target')
                        and len(source.read_character_registration().spine.body_joints)==5)
        else:
            rejected=False
        if not rejected:
            raise RuntimeError('IK 零误差上限未按预期回滚')
        result=service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                             spine_mode='ik',max_mesh_error=.001)
        error=max(abs(a-b) for frame in frames
                  for left,right in zip(before[frame],points(frame))
                  for a,b in zip(left,right))
        promoted=(not cmds.namespace(exists='target')
                  and len(source.read_character_registration().spine.body_joints)==7)
        cmds.undo()
        print('UNDO_STATE',cmds.namespace(exists='target'),
              len(source.read_character_registration().spine.body_joints),flush=True)
        undo=(cmds.namespace(exists='target')
              and len(source.read_character_registration().spine.body_joints)==5)
        cmds.redo()
        redo=(not cmds.namespace(exists='target')
              and len(source.read_character_registration().spine.body_joints)==7)
        report=dict(rejected=rejected,body_rejected=body_rejected,
                    promoted=promoted,undo=undo,redo=redo,
                    max_mesh_error=error,frames=result.frames,groups=result.fk_groups)
        print('IK_DIRECT',json.dumps(report),flush=True)
        if not all((body_rejected,promoted,undo,redo,error<=.001,result.frames==10,
                    result.fk_groups==0)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder/'spine-ik-direct-replaced.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main(sys.argv[1],Path(sys.argv[2]).resolve())
