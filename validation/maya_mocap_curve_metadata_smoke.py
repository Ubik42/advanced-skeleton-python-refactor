"""Verify native MoCap clip transfer retains Maya key metadata."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

import maya.standalone


def main(report: Path) -> int:
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaMocapClipHost
        from adv_py.core.mocap_clip import MocapClip,MocapClipJoint,MocapClipChannel
        c.file(new=True,force=True)
        c.undoInfo(state=True)
        root=c.createNode('joint',name='Hips',skipSelect=True)
        for frame,value in ((1,0.),(3,4.),(5,0.)):
            c.setKeyframe(root,attribute='translateX',time=frame,value=value)
        curve=c.connectionInfo(root+'.translateX',sourceFromDestination=True).split('.',1)[0]
        c.keyTangent(curve,edit=True,weightedTangents=True)
        c.keyTangent(curve,edit=True,time=(3,3),inTangentType='fixed',outTangentType='fixed')
        c.keyTangent(curve,edit=True,time=(3,3),inAngle=25.,outAngle=-25.,
                     inWeight=1.5,outWeight=1.5)
        c.keyTangent(curve,edit=True,time=(3,3),lock=True,weightLock=True)
        c.keyframe(curve,edit=True,time=(3,3),breakdown=True)
        tangent=lambda flag:tuple(c.keyTangent(curve,query=True,**{flag:True}) or [])
        metadata={name:tangent(name) for name in ('inTangentType','outTangentType',
            'inAngle','outAngle','inWeight','outWeight','lock','weightLock')}
        breakdown=tuple(c.keyframe(curve,query=True,breakdown=True) or [])
        source_midpoints=tuple(float(c.getAttr(root+'.translateX',time=frame))
            for frame in (2.,4.))
        frames=(1.,2.,3.,4.,5.)
        samples=[]
        for frame in frames:
            c.currentTime(frame,edit=True,update=True)
            samples.append((frame,(tuple(c.xform(root,query=True,worldSpace=True,matrix=True)),)))
        channel=MocapClipChannel('translateX',((1.,0.),(3.,4.),(5.,0.)),
            *(metadata[name] for name in ('inTangentType','outTangentType',
              'inAngle','outAngle','inWeight','outWeight')),
            True,0,0,metadata['lock'],metadata['weightLock'],breakdown)
        clip=MocapClip('y','cm','film',(MocapClipJoint('Hips',None,
            (0.,0.,0.),(0.,0.,0.),(0.,0.,0.),(1.,1.,1.),0,(channel,)),),
            tuple(samples))
        c.file(new=True,force=True)
        imported=MayaMocapClipHost().create_mocap_clip('Imported',clip)
        restored=c.connectionInfo('|Imported:Hips.translateX',
            sourceFromDestination=True).split('.',1)[0]
        restored_metadata={name:tuple(c.keyTangent(restored,query=True,
            **{name:True}) or []) for name in metadata}
        restored_breakdown=tuple(c.keyframe(restored,query=True,breakdown=True) or [])
        restored_midpoints=tuple(float(c.getAttr('|Imported:Hips.translateX',time=frame))
            for frame in (2.,4.))
        checks={
            'source_metadata_nontrivial':metadata['lock'][1]
                and metadata['weightLock'][1] and breakdown==(3.,),
            'native_tangents_and_locks_restored':restored_metadata==metadata,
            'native_breakdown_restored':restored_breakdown==breakdown,
            'midpoint_interpolation_restored':max(abs(a-b) for a,b in zip(
                source_midpoints,restored_midpoints))<1e-4,
            'all_sampled_world_poses_restored':len(imported.joints)==1,
        }
        c.undo()
        checks['single_undo_removes_import']=not c.objExists('|Imported:Hips')
        payload={**checks,'status':'passed' if all(checks.values()) else 'failed'}
        if not all(checks.values()):
            payload['details']={'source':metadata,'restored':restored_metadata,
                'breakdown':breakdown,'restored_breakdown':restored_breakdown}
            payload['details']['midpoints']=[source_midpoints,restored_midpoints]
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1])))
