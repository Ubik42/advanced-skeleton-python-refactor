"""Apply portable resampled spine world frames to native Maya joints."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

import maya.standalone


def main(report:Path)->int:
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds as c
        from adv_py.core import resample_spine_world_matrices
        c.file(new=True,force=True)
        c.undoInfo(state=True)
        source=[];parent=None
        for index in range(4):
            node=c.createNode('joint',name='SourceSpine'+str(index),skipSelect=True,
                **({'parent':parent} if parent else {}))
            if index:c.setAttr(node+'.translateY',1.+index*.25)
            parent=c.ls(node,long=True)[0]
            source.append(parent)
        for frame,motion in ((1,0.),(3,1.)):
            c.setKeyframe(source[0],attribute='translateX',time=frame,value=motion)
            for index,path in enumerate(source):
                c.setKeyframe(path,attribute='rotateZ',time=frame,
                              value=(index+1)*(5.+motion*8.))
        source_samples={}
        for frame in (1.,2.,3.):
            c.currentTime(frame,edit=True,update=True)
            source_samples[frame]=tuple(tuple(c.xform(path,query=True,
                worldSpace=True,matrix=True)) for path in source)
        targets=[];parent=None
        c.undoInfo(openChunk=True,chunkName='Create resampled probe spine')
        try:
            for index in range(6):
                node=c.createNode('joint',name='TargetSpine'+str(index),
                    skipSelect=True,**({'parent':parent} if parent else {}))
                parent=c.ls(node,long=True)[0]
                targets.append(parent)
            errors=[]
            for frame in (1.,2.,3.):
                c.currentTime(frame,edit=True,update=True)
                planned=resample_spine_world_matrices(source_samples[frame],
                    (0.,.2,.4,.6,.8,1.))
                for path,matrix in zip(targets,planned):
                    c.xform(path,worldSpace=True,matrix=matrix)
                    for attribute in ('translateX','translateY','translateZ',
                                      'rotateX','rotateY','rotateZ'):
                        c.setKeyframe(path,attribute=attribute,time=frame)
                    actual=c.xform(path,query=True,worldSpace=True,matrix=True)
                    errors.append(max(abs(a-b) for a,b in zip(actual,matrix)))
        finally:
            c.undoInfo(closeChunk=True)
        native_error=max(errors)
        source_unchanged=all(max(abs(a-b) for path,matrix in zip(source,
            source_samples[frame]) for a,b in zip(c.xform(path,query=True,
            worldSpace=True,matrix=True),matrix))<1e-5 for frame in (3.,))
        c.undo()
        removed=not c.objExists(targets[0]) and all(c.objExists(path) for path in source)
        c.redo()
        restored=all(c.objExists(path) for path in targets)
        checks={'three_frames_six_joint_native_match':native_error<1e-4,
            'source_character_unchanged':source_unchanged,
            'single_undo_redo':removed and restored}
        payload={**checks,'status':'passed' if all(checks.values()) else 'failed',
                 'max_matrix_error':native_error}
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',
                          encoding='utf-8')
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1])))
