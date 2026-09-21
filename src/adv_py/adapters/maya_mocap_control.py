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
