"""One FK-to-IK event through an original-Skin topology replacement."""
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

        mesh='|source:SourceMesh';skin='source:SourceSkin'
        if mode=='inspect':
            scene=sys.argv[3] if len(sys.argv)>3 else 'spine-hybrid-replaced.ma'
            times=tuple(1+i*.25 for i in range(37))+(4.999,)
            def mesh_points():
                result={}
                for frame in times:
                    cmds.currentTime(frame,edit=True)
                    result[frame]=tuple(tuple(cmds.xform(mesh+f'.vtx[{i}]',
                        q=True,ws=True,t=True)) for i in range(4))
                return result
            cmds.file(str(folder/'spine-hybrid-before.ma'),open=True,force=True)
            source_points=mesh_points()
            cmds.file(str(folder/scene),open=True,force=True)
            reg=MayaBodyBuildHost(namespace='source').read_character_registration()
            if cmds.namespace(exists='target') or len(reg.spine.body_joints)!=7:
                raise RuntimeError('混合脊柱角色重开无效')
            target_points=mesh_points()
            error=max(abs(a-b) for frame in times
                for left,right in zip(source_points[frame],target_points[frame])
                for a,b in zip(left,right))
            def jump(rows):
                return max(abs(a-b) for left,right in zip(rows[4.999],rows[5.])
                           for a,b in zip(left,right))
            if error>.03 or abs(jump(source_points)-jump(target_points))>.0002:
                raise RuntimeError('混合脊柱重开后的网格或切换边界超限')
            print('HYBRID_REOPEN_OK',json.dumps(dict(error=error,
                source_boundary=jump(source_points),
                target_boundary=jump(target_points))),flush=True)
            return
        cmds.file(str(folder/'full-spine-replacement-before.ma'),open=True,force=True)
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
                time=frame,value=value,
                inTangentType='linear',outTangentType='linear')
        frames=tuple(1+i*.25 for i in range(37))
        def points(frame):
            undo=cmds.undoInfo(query=True,state=True)
            cmds.undoInfo(stateWithoutFlush=False)
            try:cmds.currentTime(frame,edit=True)
            finally:cmds.undoInfo(stateWithoutFlush=undo)
            return tuple(tuple(cmds.xform(mesh+f'.vtx[{i}]',q=True,
                ws=True,t=True)) for i in range(4))
        wanted={frame:points(frame) for frame in frames}
        source_boundary=(points(4.999),points(5.))
        points(1)
        cmds.file(rename=str(folder/'spine-hybrid-before.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
        service=ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace='target'))
        try:
            service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                          spine_mode='hybrid',max_mesh_error=.02,max_body_error=1.)
        except Exception as exc:
            rejected=('原网格误差超限' in str(exc) and cmds.namespace(exists='target'))
        else:rejected=False
        if not rejected:raise RuntimeError('混合脊柱网格超限未回滚')
        result=service.apply('source','target',skin,mesh,start_frame=1,end_frame=10,
                             spine_mode='hybrid',max_mesh_error=.03,
                             max_body_error=.001)
        actual={frame:points(frame) for frame in frames}
        target_boundary=(points(4.999),points(5.))
        def distance(pair):
            return max(abs(a-b) for left,right in zip(*pair)
                       for a,b in zip(left,right))
        error=max(abs(a-b) for frame in frames
                  for left,right in zip(wanted[frame],actual[frame])
                  for a,b in zip(left,right))
        promoted=(not cmds.namespace(exists='target')
                  and len(source.read_character_registration().spine.body_joints)==7)
        cmds.undo()
        undo=(cmds.namespace(exists='target')
              and len(source.read_character_registration().spine.body_joints)==5)
        cmds.redo()
        redo=(not cmds.namespace(exists='target')
              and len(source.read_character_registration().spine.body_joints)==7)
        report=dict(rejected=rejected,promoted=promoted,undo=undo,redo=redo,
                    max_mesh_error=error,frames=result.frames,
                    source_boundary=distance(source_boundary),
                    target_boundary=distance(target_boundary))
        print('HYBRID',json.dumps(report),flush=True)
        if not all((rejected,promoted,undo,redo,error<=.03,result.frames==10,
                    distance(target_boundary)<.002,
                    abs(distance(target_boundary)-distance(source_boundary))<.0002)):
            raise RuntimeError(report)
        cmds.file(rename=str(folder/'spine-hybrid-replaced.ma'))
        cmds.file(save=True,type='mayaAscii',force=True)
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':main(sys.argv[1],Path(sys.argv[2]).resolve())
