"""Two retained original Skins share one direct Spline IK replacement."""
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
        if mode=='inspect':
            scene=sys.argv[3] if len(sys.argv)>3 else 'spine-ik-multi-replaced.ma'
            cmds.file(str(folder/scene),open=True,force=True)
            reg=MayaBodyBuildHost(namespace='source').read_character_registration()
            if cmds.namespace(exists='target') or len(reg.spine.body_joints)!=7:
                raise RuntimeError('多 Skin IK 角色重开无效')
            print('IK_MULTI_REOPEN_OK',flush=True)
            return
        cmds.file(str(folder/'multi-skin-spine-before.ma'),open=True,force=True)
        cmds.undoInfo(state=True)
        source=MayaBodyBuildHost(namespace='source')
        reg=source.read_character_registration()
        keys={ch.key:ch for ch in reg.channels}
        for frame in (1,5,10):
            for key,value in (('spine.spline.spineIkFk',1.),
                              ('spine.spline.1.translateY',(frame-1)*.025)):
                ch=keys[key]
                source._cmds.setKeyframe(ch.node,attribute=ch.attribute,
                                         time=frame,value=value)
        frames=tuple(sorted({*range(1,11),*(i+.5 for i in range(1,10))}))
        counts=tuple(cmds.polyEvaluate(mesh,vertex=True) for _,mesh in skins)
        def points(frame):
            undo=cmds.undoInfo(query=True,state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:cmds.currentTime(frame,edit=True)
            finally:cmds.undoInfo(stateWithoutFlush=undo)
            return tuple(tuple(tuple(cmds.xform(mesh+f'.vtx[{i}]',query=True,
                worldSpace=True,translation=True)) for i in range(count))
                for (_,mesh),count in zip(skins,counts))
        wanted={frame:points(frame) for frame in frames}
        points(1)
        cmds.file(rename=str(folder/'spine-ik-multi-before.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
        service=ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target'))
        try:
            service.apply_many('source','target',skins,start_frame=1,
                               end_frame=10,spine_mode='ik',max_mesh_error=.001)
        except Exception as exc:
            rejected=('IK 迁移原网格误差超限' in str(exc)
                      and '|source:SecondMesh' in str(exc)
                      and cmds.namespace(exists='target'))
        else:rejected=False
        if not rejected:raise RuntimeError('第二张网格超限未回滚两个 Skin')
        result=service.apply_many('source','target',skins,start_frame=1,
                                  end_frame=10,spine_mode='ik',max_mesh_error=.02)
        actual={frame:points(frame) for frame in frames}
        errors=tuple(max(abs(a-b) for frame in frames
            for left,right in zip(wanted[frame][index],actual[frame][index])
            for a,b in zip(left,right)) for index in range(2))
        takeover=(not cmds.namespace(exists='target')
                  and len(source.read_character_registration().spine.body_joints)==7)
        cmds.undo()
        undo=(cmds.namespace(exists='target')
              and len(source.read_character_registration().spine.body_joints)==5)
        cmds.redo()
        redo=(not cmds.namespace(exists='target')
              and len(source.read_character_registration().spine.body_joints)==7)
        report=dict(rejected=rejected,takeover=takeover,undo=undo,redo=redo,
                    errors=errors,skins=result.skin_count)
        print('IK_MULTI',json.dumps(report),flush=True)
        if not all((rejected,takeover,undo,redo,result.skin_count==2,
                    all(error<=.02 for error in errors))):
            raise RuntimeError(report)
        cmds.file(rename=str(folder/'spine-ik-multi-replaced.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]).resolve())
