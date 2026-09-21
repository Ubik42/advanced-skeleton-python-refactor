"""Exercise isolated FBX import above the 2000-pose verification threshold."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import maya.standalone


def main(output):
    maya.standalone.initialize(name='python')
    try:
        from maya import cmds
        from adv_py.adapters import MayaMocapClipHost
        from adv_py.application import ImportMocapFbx
        cmds.file(new=True,force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis='y',rotateView=False)
        cmds.currentUnit(linear='cm',time='film')
        if not cmds.pluginInfo('fbxmaya',query=True,loaded=True):cmds.loadPlugin('fbxmaya',quiet=True)
        root=cmds.createNode('joint',name='Hips',skipSelect=True)
        for frame in range(1,1102):
            cmds.setKeyframe(root,attribute='translateX',time=frame,value=frame*.25)
        with tempfile.TemporaryDirectory(prefix='advpy-long-mocap-') as directory:
            source=Path(directory)/'long_take.fbx'
            cmds.select(root,replace=True)
            cmds.file(str(source),force=True,options='v=0;',type='FBX export',exportSelected=True)
            cmds.file(new=True,force=True)
            result=ImportMocapFbx(MayaMocapClipHost()).apply(source,namespace='LongTake')
            checks={
                'source_has_1101_keys':len(result.clip.joints[0].channels[0].keys)==1101,
                'bounded_world_samples':len(result.clip.samples)==2000,
                'both_endpoints_verified':(result.clip.samples[0][0],result.clip.samples[-1][0])==(1.,1101.),
                'full_curve_restored':len(cmds.keyframe('|LongTake:Hips.translateX',query=True,timeChange=True) or [])==1101,
                'late_motion_restored':abs(cmds.getAttr('|LongTake:Hips.translateX',time=1099)-274.75)<1e-4,
            }
        payload={**checks,'status':'passed' if all(checks.values()) else 'failed'}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        return 0 if all(checks.values()) else 1
    finally:maya.standalone.uninitialize()


if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
