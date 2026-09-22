"""Long multi-joint FBX import, complete keys, bounded poses and undo."""
from __future__ import annotations

import json
from math import sin
from pathlib import Path
import sys
import tempfile
from time import monotonic

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

import maya.standalone


def main(report:Path)->int:
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.adapters import MayaMocapClipHost
        from adv_py.application import ImportMocapFbx

        report.parent.mkdir(parents=True,exist_ok=True)
        c.file(new=True,force=True)
        c.undoInfo(state=True)
        c.upAxis(axis='y',rotateView=False)
        c.currentUnit(linear='cm',time='film')
        if not c.pluginInfo('fbxmaya',query=True,loaded=True):
            c.loadPlugin('fbxmaya',quiet=True)
        paths={}
        def joint(name,parent=None):
            node=c.createNode('joint',name=name,skipSelect=True,
                **({'parent':paths[parent]} if parent else {}))
            if parent:c.setAttr(node+'.translateY',2.)
            paths[name]=c.ls(node,long=True)[0]
            return name
        joint('Hips')
        parent='Hips'
        for index in range(1,5):parent=joint('Spine'+str(index),parent)
        parent=joint('Neck',parent)
        joint('Head',parent)
        for side in ('R','L'):
            parent='Spine4'
            for part in ('Shoulder','Elbow','Wrist'):
                parent=joint(part+'_'+side,parent)
            parent='Hips'
            for part in ('Hip','Knee','Ankle','Toe'):
                parent=joint(part+'_'+side,parent)
        assert len(paths)==21
        for frame in range(1,302):
            c.setKeyframe(paths['Hips'],attribute='translateX',
                time=frame,value=(frame-1)*.03)
            for index,(name,path) in enumerate(paths.items()):
                if name=='Hips':continue
                c.setKeyframe(path,attribute='rotateZ',time=frame,
                    value=sin(frame*.025+index*.3)*(3.+index*.1))
        with tempfile.TemporaryDirectory(prefix='advpy-multi-long-',
                                         dir=report.parent.resolve()) as directory:
            folder=Path(directory)
            source=folder/'multi_joint_long.fbx'
            c.select(paths['Hips'],replace=True)
            c.file(str(source),force=True,options='v=0;',type='FBX export',
                   exportSelected=True)
            c.file(new=True,force=True)
            start=monotonic()
            result=ImportMocapFbx(MayaMocapClipHost()).apply(source,
                namespace='LongMulti')
            seconds=monotonic()-start
            clip=result.clip
            by_name={row.name:row for row in clip.joints}
            root='|LongMulti:Hips'
            late=float(c.getAttr(root+'.translateX',time=299))
            c.undo()
            removed=not c.objExists(root)
            c.redo()
            restored=c.objExists(root)
            c.file(rename=str(folder/'reopened.ma'))
            c.file(save=True,type='mayaAscii',force=True)
            c.file(folder/'reopened.ma',open=True,force=True)
            reopened=float(c.getAttr(root+'.translateX',time=299))
            checks={
                'twenty_one_joints_rebuilt':len(clip.joints)==21
                    and len(result.snapshot.joints)==21,
                'all_joint_curves_have_301_keys':all(
                    len(channel.keys)==301 for row in clip.joints
                    for channel in row.channels)
                    and sum(len(row.channels) for row in clip.joints)==21,
                'bounded_world_samples_cover_exteriors':len(clip.samples)==603
                    and (clip.samples[0][0],clip.samples[-1][0])==(.5,301.5),
                'late_motion_restored':abs(late-(299-1)*.03)<1e-4
                    and abs(reopened-late)<1e-6,
                'undo_redo_restore_import':removed and restored,
                'reopened_child_animation':len(c.keyframe(
                    '|LongMulti:Hips|LongMulti:Spine1.rotateZ',query=True,
                    timeChange=True) or [])==301,
            }
            payload={**checks,'status':'passed' if all(checks.values()) else 'failed',
                     'import_seconds':round(seconds,3),'clip_bytes':len(source.read_bytes())}
        report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',
                          encoding='utf-8')
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1])))
