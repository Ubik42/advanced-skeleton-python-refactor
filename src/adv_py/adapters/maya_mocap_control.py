"""Maya root-motion calibration and transactional Global-control keying."""
from adv_py.core.character_registry import CharacterRegistryError
from .maya_body import MayaBodyBuildHost
from .maya_mocap import MayaMocapSourceReader


class MayaMocapControlHost(MayaBodyBuildHost):
    def capture_mocap_source(self,root_name):
        return MayaMocapSourceReader().capture_mocap_source(root_name)

    def write_mocap_root_control_keys(self,plan):
        from maya.api.OpenMaya import MMatrix
        from adv_py.application.mocap_control_retarget import MocapRootControlSample
        self._require_transaction()
        self.preflight_character_keyframe(plan.registration)
        c=self._cmds
        channels={channel.key:channel for channel in plan.registration.channels}
        controls=tuple(channels[f'global.{kind}{axis}'] for kind in ('translate','rotate') for axis in 'XYZ')
        nodes={channel.node for channel in controls}
        if len(nodes)!=1:raise CharacterRegistryError('全局控制通道分散在多个节点')
        control=next(iter(nodes));body_root=plan.registration.body_root
        source_root=plan.source.root
        def matrix(node):return MMatrix(c.xform(node,query=True,worldSpace=True,matrix=True))
        def error(left,right):return max(abs(a-b) for a,b in zip(left,right))
        def rigid(transform):
            rows=tuple(tuple(transform[index+offset] for offset in range(3)) for index in (0,4,8))
            return all(abs(sum(a*b for a,b in zip(left,right))-(1. if i==j else 0.))<1e-4
                       for i,left in enumerate(rows) for j,right in enumerate(rows))
        samples=[]
        self._transaction_changed=True
        with self._character_sampling_time(preserve_modified=False) as seek:
            seek(plan.reference_frame)
            reference=matrix(source_root)
            inverse=reference.inverse()
            for frame in plan.frames:
                seek(frame)
                delta=inverse*matrix(source_root)
                if not rigid(delta):
                    raise CharacterRegistryError('动捕根部包含缩放或剪切，不能转移到 Global 控制器：frame='+str(frame))
                wanted_body=matrix(body_root)*delta
                wanted_control=matrix(control)*delta
                pose=self.capture_character_pose(plan.registration)
                with self._character_static_controls(plan.registration,pose):
                    c.xform(control,worldSpace=True,matrix=list(wanted_control))
                    values=tuple(float(c.getAttr(ch.node+'.'+ch.attribute)) for ch in controls)
                    actual=matrix(body_root)
                    if error(actual,wanted_body)>1e-4:
                        raise CharacterRegistryError('动捕根部矩阵不能由全局控制器精确表达：frame='+str(frame))
                samples.append(MocapRootControlSample(frame,values,tuple(wanted_body)))
            for sample in samples:
                for channel,value in zip(controls,sample.control_values):
                    c.setKeyframe(channel.node,attribute=channel.attribute,time=sample.frame,value=value,
                                  inTangentType='linear',outTangentType='linear')
            for sample in samples:
                seek(sample.frame)
                if error(matrix(body_root),sample.body_root_matrix)>1e-4:
                    raise RuntimeError('动捕根部控制曲线验收失败：frame='+str(sample.frame))
        return tuple(samples)

    def write_mocap_spine_control_keys(self,plan):
        from math import sqrt
        from maya.api.OpenMaya import MMatrix,MTransformationMatrix
        from adv_py.application.mocap_control_retarget import MocapSpineControlSample
        self._require_transaction()
        registration=plan.root.registration
        self.preflight_character_keyframe(registration)
        c=self._cmds
        spine=registration.spine
        body=spine.body_joints
        controls=spine.fk_controls
        sources=(plan.root.source.root,plan.source_spine,plan.source_chest)
        channels={channel.node+'.'+channel.attribute for channel in registration.channels}
        if any(control+'.rotate'+axis not in channels for control in controls[1:] for axis in 'XYZ'):
            raise CharacterRegistryError('FK 脊柱控制器旋转通道不完整')
        def matrix(node):return MMatrix(c.xform(node,query=True,worldSpace=True,matrix=True))
        def error(left,right):return max(abs(a-b) for a,b in zip(left,right))
        def rotation(value):return MTransformationMatrix(value).rotation().asMatrix()
        def rotated_local(original,delta):
            direction=rotation(original)*delta
            data=list(direction)
            for offset in (0,4,8):
                size=sqrt(sum(original[offset+axis]**2 for axis in range(3)))
                if size<1e-8:raise CharacterRegistryError('目标脊柱包含退化缩放')
                for axis in range(3):data[offset+axis]*=size
            data[12:15]=[original[12],original[13],original[14]]
            return MMatrix(data)
        samples=[]
        self._transaction_changed=True
        with self._character_sampling_time(preserve_modified=False) as seek:
            seek(plan.root.reference_frame)
            reference=tuple(matrix(path) for path in sources)
            relative_reference=tuple(rotation(reference[index]*reference[index-1].inverse())
                                     for index in (1,2))
            for frame in plan.root.frames:
                seek(frame)
                if abs(float(c.getAttr(spine.blend_plug)))>1e-8:
                    raise CharacterRegistryError('动捕脊柱转移要求采样帧处于 Spine FK 模式：frame='+str(frame))
                current_source=tuple(matrix(path) for path in sources)
                deltas=tuple(relative_reference[index-1].inverse()*
                    rotation(current_source[index]*current_source[index-1].inverse()) for index in (1,2))
                pose=self.capture_character_pose(registration)
                wanted=[]
                with self._character_static_controls(registration,pose):
                    for index,delta in zip((1,2),deltas):
                        parent=matrix(body[index-1]);actual=matrix(body[index])
                        local=actual*parent.inverse()
                        desired=rotated_local(local,delta)*parent
                        control=controls[index]
                        target=matrix(control)*actual.inverse()*desired
                        self._spine_set_world_rotation(control,target)
                        evaluated=matrix(body[index])
                        if error(evaluated,desired)>1e-4:
                            raise CharacterRegistryError('动捕脊柱姿态不能由 FK 控制器精确表达：'
                                +str((frame,body[index],error(evaluated,desired))))
                        wanted.append(tuple(desired))
                    values=tuple(float(c.getAttr(control+'.rotate'+axis))
                                 for control in controls[1:] for axis in 'XYZ')
                samples.append(MocapSpineControlSample(frame,values,tuple(wanted)))
            for sample in samples:
                for control,values in zip(controls[1:],(sample.control_values[:3],sample.control_values[3:])):
                    for axis,value in zip('XYZ',values):
                        c.setKeyframe(control,attribute='rotate'+axis,time=sample.frame,value=value,
                                      inTangentType='linear',outTangentType='linear')
            for sample in samples:
                seek(sample.frame)
                if any(error(matrix(path),wanted)>1e-4 for path,wanted in zip(body[1:],sample.body_matrices)):
                    raise RuntimeError('动捕脊柱控制曲线验收失败：frame='+str(sample.frame))
        return tuple(samples)
