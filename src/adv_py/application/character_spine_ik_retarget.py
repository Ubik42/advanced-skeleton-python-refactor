"""Spline-control transfer and FK event matching with spatial error gates."""
from dataclasses import dataclass
from math import isfinite

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterRegistryError


@dataclass(frozen=True, slots=True)
class RegisteredSpineIkTake:
    source_registration: object
    target_registration: object
    frames: tuple[float, ...]
    channels: tuple
    meshes: tuple
    body: tuple
    body_names: tuple[str, ...]
    fk_frames: tuple[float, ...]
    fk_source_frames: tuple[float, ...]
    max_mesh_error: float
    max_body_error: float


class RetargetCharacterSpineIk:
    """Transfer source curves and match stepped FK/IK mode events."""

    def __init__(self, host):
        self._host = host

    def plan(self, source_namespace, skins, frames, *, max_mesh_error,
             max_body_error=None, allow_fk=False):
        if (isinstance(max_mesh_error, bool)
                or not isinstance(max_mesh_error, (int, float))
                or not isfinite(max_mesh_error) or max_mesh_error < 0):
            raise CharacterRegistryError('IK 网格误差上限须为非负有限厘米数值')
        if max_body_error is None:
            max_body_error = max_mesh_error
        if (isinstance(max_body_error, bool)
                or not isinstance(max_body_error, (int, float))
                or not isfinite(max_body_error) or max_body_error < 0):
            raise CharacterRegistryError('IK 身体误差上限须为非负有限厘米数值')
        host = self._host
        source = host.read_source_character_registration(source_namespace)
        target = host.read_character_registration()
        if not isinstance(source.spine, BodySplinePlan) or not isinstance(target.spine, BodySplinePlan):
            raise CharacterRegistryError('IK 跨段数迁移要求两个登记的 Spline 角色')
        if len(source.spine.body_joints) == len(target.spine.body_joints):
            raise CharacterRegistryError('IK 跨段数迁移要求不同脊柱段数')
        if (len(source.spine.positions) != len(target.spine.positions)
                or any(max(abs(a-b) for a,b in zip(left,right)) > 1e-6
                       for left,right in zip(source.spine.positions,target.spine.positions))):
            raise CharacterRegistryError('IK 控制绑定位置不同，不能直接迁移控制动画')
        short = lambda path: path.rsplit('|',1)[-1].rsplit(':',1)[-1]
        source_internal = {short(path) for path in source.spine.body_joints[1:-1]}
        target_internal = {short(path) for path in target.spine.body_joints[1:-1]}
        source_body = {short(row.path):row.matrix for row in source.body
                       if short(row.path) not in source_internal}
        target_body = {short(row.path):row.matrix for row in target.body
                       if short(row.path) not in target_internal}
        if (source_body.keys() != target_body.keys()
                or any(max(abs(a-b) for a,b in zip(matrix,target_body[name])) > 1e-4
                       for name,matrix in source_body.items())):
            raise CharacterRegistryError('IK 直接迁移要求脊柱以外的 Body 绑定矩阵一致')
        source_channels = {ch.key for ch in source.channels}
        target_channels = {ch.key for ch in target.channels}
        if not source_channels.issubset(target_channels):
            raise CharacterRegistryError('目标角色缺少来源控制通道')
        source_ik = {key for key in source_channels if key.startswith('spine.spline.')}
        target_ik = {key for key in target_channels if key.startswith('spine.spline.')}
        if source_ik != target_ik or 'spine.spline.spineIkFk' not in source_ik:
            raise CharacterRegistryError('来源与目标 Spline IK 通道不对应')
        schedule=host.capture_registered_spine_mode_curve(source_namespace,source) if allow_fk else None
        event_times=(tuple(right for left,right,a,b in
            zip(schedule[0],schedule[0][1:],schedule[1],schedule[1][1:])
            if a!=b and frames[0]<right<=frames[-1]) if schedule else ())
        all_frames = tuple(sorted({*frames,
            *(a+(b-a)*fraction/4 for a,b in zip(frames,frames[1:])
              for fraction in (1,2,3)),
            *(event-offset for event in event_times for offset in (.01,.001))}))
        body_names = tuple(source_body)
        channels, meshes, body = host.capture_registered_spine_ik_take(
            source_namespace, source, tuple(mesh for _,mesh in skins),
            body_names, all_frames)
        mode = 'spine.spline.spineIkFk'
        modes = tuple(dict(row)[mode] for row in channels)
        if any(min(abs(value),abs(value-1.)) > 1e-8 for value in modes):
            raise CharacterRegistryError('脊柱迁移不接受采样区间内的 FK/IK 混合权重')
        if not allow_fk and any(abs(value-1.) > 1e-8 for value in modes):
            raise CharacterRegistryError('IK 跨段数迁移要求整个采样区间保持 Spline IK 模式')
        if allow_fk:
            if not any(abs(value) <= 1e-8 for value in modes) or not any(
                    abs(value-1.) <= 1e-8 for value in modes):
                raise CharacterRegistryError('混合脊柱迁移要求同时包含 FK 和 IK 帧')
            if not schedule:
                raise CharacterRegistryError('混合脊柱迁移要求原生模式事件曲线')
            times,values,out_tangents=schedule
            if (any(min(abs(value),abs(value-1.)) > 1e-8 for value in values)
                    or any(tangent != 'step'
                           for index,tangent in enumerate(out_tangents[:-1])
                           if times[index] < frames[-1]
                           and times[index+1] > frames[0])
                    or any(right not in frames for left,right,a,b in
                           zip(times,times[1:],values,values[1:])
                           if a != b and frames[0] < right <= frames[-1])):
                raise CharacterRegistryError('FK/IK 模式事件须为采样整数帧上的阶梯切换')
        fk_pairs=[(frame,frame) for frame,value in zip(all_frames,modes)
                  if abs(value)<=1e-8]
        if allow_fk:
            events=tuple((all_frames[index],modes[index-1],modes[index])
                for index in range(1,len(all_frames))
                if abs(modes[index]-modes[index-1])>1e-8)
            if not events or any(event not in event_times for event,_,_ in events):
                raise CharacterRegistryError('混合脊柱迁移要求整数帧阶梯 FK/IK 事件')
            fk_pairs.extend((event,event-1e-4) for event,before,after in events
                            if abs(before)<=1e-8 and abs(after-1.)<=1e-8)
        fk_frames=tuple(frame for frame,_ in fk_pairs)
        fk_source_frames=tuple(frame for _,frame in fk_pairs)
        return RegisteredSpineIkTake(source,target,all_frames,channels,
            meshes,body,body_names,fk_frames,fk_source_frames,
            float(max_mesh_error),float(max_body_error))

    def apply_in_transaction(self, take, source_namespace, skins):
        host = self._host
        if (host.read_source_character_registration(source_namespace)
                != take.source_registration
                or host.read_character_registration() != take.target_registration):
            raise CharacterRegistryError('IK 迁移角色登记在写入前发生变化')
        host.write_registered_spine_ik_take(take,source_namespace)
        if take.fk_frames:
            host.match_registered_spine_fk_take(take,source_namespace)
        self.verify_body(take)
        self.verify_meshes(take, skins)

    def verify_body(self, take, host=None):
        current = (self._host if host is None else host).capture_registered_spine_body_take(
            take.target_registration, take.body_names, take.frames)
        for frame, expected, actual in zip(take.frames,take.body,current):
            for (name,left),(actual_name,right) in zip(expected,actual):
                if name != actual_name:
                    raise CharacterRegistryError('IK 迁移 Body 关节对应变化：'+name)
                error = max(abs(a-b) for left_point,right_point in zip(left,right)
                            for a,b in zip(left_point,right_point))
                if error > take.max_body_error:
                    raise CharacterRegistryError(
                        'IK 迁移身体空间误差超限：joint='+name
                        +' frame='+str(frame)+' error='+str(error)
                        +' limit='+str(take.max_body_error))

    def verify_meshes(self, take, skins):
        current = self._host.capture_registered_spine_mesh_take(
            tuple(mesh for _,mesh in skins), take.frames)
        for mesh, wanted, actual in zip((mesh for _,mesh in skins), take.meshes, current):
            if len(wanted) != len(actual):
                raise CharacterRegistryError('IK 迁移改变原网格顶点数量：'+mesh)
            for frame, expected_points, current_points in zip(take.frames,wanted,actual):
                if len(expected_points) != len(current_points):
                    raise CharacterRegistryError('IK 迁移改变原网格顶点数量：'+mesh)
                error = max((abs(a-b) for left,right in zip(expected_points,current_points)
                             for a,b in zip(left,right)),default=0.)
                if error > take.max_mesh_error:
                    raise CharacterRegistryError(
                        'IK 迁移原网格误差超限：mesh='+mesh
                        +' frame='+str(frame)+' error='+str(error)
                        +' limit='+str(take.max_mesh_error))
