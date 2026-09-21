"""Run in a separate mayapy process; never imports FBX into the user's scene."""
import sys
from pathlib import Path

script_directory=str(Path(__file__).resolve().parent)
sys.path[:]=[item for item in sys.path if str(Path(item).resolve())!=script_directory]
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import maya.standalone


def read_fbx(source,units):
    from maya import cmds as c
    from adv_py.adapters.maya_mocap import MayaMocapSourceReader
    from adv_py.core.mocap_clip import MocapClip,MocapClipJoint,MocapClipChannel
    from adv_py.core.mocap_source import audit_mocap_source,MocapSourceValidationError

    c.file(new=True,force=True)
    c.upAxis(axis=units[0],rotateView=False)
    c.currentUnit(linear=units[1],time=units[2])
    if not c.pluginInfo('fbxmaya',query=True,loaded=True):c.loadPlugin('fbxmaya',quiet=True)
    c.file(str(source),i=True,type='FBX',ignoreVersion=True,options='fbx')
    joints=c.ls(type='joint',long=True) or []
    joint_set=set(joints)
    roots=[path for path in joints if (c.listRelatives(path,parent=True,fullPath=True) or [None])[0] not in joint_set]
    if len(roots)!=1:raise MocapSourceValidationError('外部 FBX 必须只有一棵关节骨架：'+repr(roots))
    snapshot=MayaMocapSourceReader().capture_mocap_source(roots[0])
    issues=audit_mocap_source(snapshot)
    if issues:raise MocapSourceValidationError('外部 FBX 骨架或动画无效：'+'；'.join(issue.message for issue in issues))
    names={row.path:row.name for row in snapshot.joints}
    channels={row.path:[] for row in snapshot.joints}
    for row in snapshot.channels:
        plug=row.joint_path+'.'+row.attribute
        keys=tuple((float(time),float(c.getAttr(plug,time=time))) for time in row.key_times)
        channels[row.joint_path].append(MocapClipChannel(row.attribute,keys))
    result=[]
    for row in snapshot.joints:
        path=row.path
        vector=lambda name:tuple(float(value) for value in c.getAttr(path+'.'+name)[0])
        result.append(MocapClipJoint(row.name,names[row.joint_parent] if row.joint_parent else None,
                                     vector('translate'),vector('rotate'),vector('jointOrient'),vector('scale'),
                                     int(c.getAttr(path+'.rotateOrder')),tuple(channels[path])))
    frames=sorted({time for joint in result for channel in joint.channels for time,_ in channel.keys})
    if len(frames)>2000:raise MocapSourceValidationError('外部 FBX 关键帧超过当前逐帧验收上限')
    samples=[]
    for frame in frames:
        c.currentTime(frame,edit=True,update=True)
        samples.append((frame,tuple(tuple(float(value) for value in c.xform(row.path,query=True,
                              worldSpace=True,matrix=True)) for row in snapshot.joints)))
    return MocapClip(str(c.upAxis(query=True,axis=True)),str(c.currentUnit(query=True,linear=True)),
                     str(c.currentUnit(query=True,time=True)),tuple(result),tuple(samples))


def main(source,output,units):
    maya.standalone.initialize(name='python')
    try:
        from adv_py.core.mocap_clip import encode_mocap_clip
        output.write_text(encode_mocap_clip(read_fbx(source,units)),encoding='utf8')
    finally:maya.standalone.uninitialize()


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]),tuple(sys.argv[3:6]))
