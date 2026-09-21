"""Build a validated MoCap clip with ordinary undoable Maya nodes and keys."""
from adv_py.core.mocap_source import MocapSourceValidationError,audit_mocap_source

from .maya_mocap import MayaMocapSourceReader


class MayaMocapClipHost:
    def __init__(self):
        from maya import cmds
        self._cmds=cmds

    def mocap_scene_units(self):
        c=self._cmds
        return (str(c.upAxis(query=True,axis=True)),str(c.currentUnit(query=True,linear=True)),
                str(c.currentUnit(query=True,time=True)))

    def preflight_mocap_clip_import(self,namespace,clip):
        c=self._cmds
        if not c.undoInfo(query=True,state=True):
            raise MocapSourceValidationError('动捕导入要求启用 Maya Undo')
        if c.namespace(exists=namespace):
            raise MocapSourceValidationError('动捕导入命名空间已存在：'+namespace)
        if c.namespace(query=True,relativeNames=True):
            raise MocapSourceValidationError('动捕导入要求关闭 Maya relativeNames')
        if clip is not None and (clip.up_axis!=str(c.upAxis(query=True,axis=True))
                                 or clip.linear_unit!=str(c.currentUnit(query=True,linear=True))
                                 or clip.time_unit!=str(c.currentUnit(query=True,time=True))):
            raise MocapSourceValidationError('外部动捕与场景的向上轴、长度或时间单位不一致；需要显式转换：'
                +repr((clip.up_axis,clip.linear_unit,clip.time_unit))+' / '
                +repr((c.upAxis(query=True,axis=True),c.currentUnit(query=True,linear=True),c.currentUnit(query=True,time=True))))

    def create_mocap_clip(self,namespace,clip):
        c=self._cmds
        self.preflight_mocap_clip_import(namespace,clip)
        selected=c.ls(selection=True,long=True) or []
        current=float(c.currentTime(query=True))
        previous=c.namespaceInfo(currentNamespace=True,absoluteName=True)
        c.undoInfo(openChunk=True,chunkName='Import isolated MoCap clip')
        try:
            c.namespace(addNamespace=namespace)
            c.namespace(setNamespace=':'+namespace)
            paths={}
            for joint in clip.joints:
                parent={'parent':paths[joint.parent_name]} if joint.parent_name else {}
                node=c.createNode('joint',name=joint.name,skipSelect=True,**parent)
                path=c.ls(node,long=True)[0]
                paths[joint.name]=path
                c.setAttr(path+'.rotateOrder',joint.rotate_order)
                for name,values in (('translate',joint.translate),('rotate',joint.rotate),
                                    ('jointOrient',joint.joint_orient),('scale',joint.scale)):
                    c.setAttr(path+'.'+name,*values,type='double3')
                for channel in joint.channels:
                    for time,value in channel.keys:
                        c.setKeyframe(path,attribute=channel.attribute,time=time,value=value)
            root=paths[clip.joints[0].name]
            snapshot=MayaMocapSourceReader().capture_mocap_source(root)
            issues=audit_mocap_source(snapshot)
            if issues:raise MocapSourceValidationError('重建动捕骨架复检失败：'+'；'.join(issue.message for issue in issues))
            if tuple((row.name,row.namespace) for row in snapshot.joints)!=tuple((row.name,namespace) for row in clip.joints):
                raise MocapSourceValidationError('重建动捕关节身份发生变化')
            for joint in clip.joints:
                path=paths[joint.name]
                for channel in joint.channels:
                    plug=path+'.'+channel.attribute
                    times=tuple(float(value) for value in c.keyframe(plug,query=True,timeChange=True) or [])
                    if times!=tuple(time for time,_ in channel.keys):
                        raise MocapSourceValidationError('重建动捕动画键时间发生变化')
                    if any(abs(float(c.getAttr(plug,time=time))-value)>1e-6 for time,value in channel.keys):
                        raise MocapSourceValidationError('重建动捕动画键值发生变化')
            for time,matrices in clip.samples:
                c.currentTime(time,edit=True,update=True)
                for joint,expected in zip(clip.joints,matrices):
                    actual=c.xform(paths[joint.name],query=True,worldSpace=True,matrix=True)
                    if max(abs(a-b) for a,b in zip(actual,expected))>1e-4:
                        raise MocapSourceValidationError('重建动捕世界姿态与外部 FBX 不一致：'
                            +joint.name+' frame='+str(time))
            c.currentTime(current,edit=True,update=True)
            c.select(selected,replace=True) if selected else c.select(clear=True)
        except Exception:
            c.namespace(setNamespace=previous)
            c.undoInfo(closeChunk=True)
            c.undo()
            c.undoInfo(stateWithoutFlush=False)
            try:
                if c.namespace(exists=namespace):
                    c.namespace(removeNamespace=namespace,deleteNamespaceContent=True)
                c.currentTime(current,edit=True,update=True)
                c.select(selected,replace=True) if selected else c.select(clear=True)
            finally:c.undoInfo(stateWithoutFlush=True)
            raise
        else:
            c.namespace(setNamespace=previous)
            c.undoInfo(closeChunk=True)
        return snapshot
