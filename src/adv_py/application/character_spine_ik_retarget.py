"""Direct registered Spline IK take transfer with original-mesh error gate."""
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
    max_mesh_error: float


class RetargetCharacterSpineIk:
    """Transfer equivalent spline controls; reject visible mesh divergence."""

    def __init__(self, host):
        self._host = host

    def plan(self, source_namespace, skins, frames, *, max_mesh_error):
        if (isinstance(max_mesh_error, bool)
                or not isinstance(max_mesh_error, (int, float))
                or not isfinite(max_mesh_error) or max_mesh_error < 0):
            raise CharacterRegistryError('IK 网格误差上限须为非负有限厘米数值')
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
        all_frames = tuple(sorted({*frames,
            *((a+b)/2 for a,b in zip(frames,frames[1:]))}))
        channels, meshes = host.capture_registered_spine_ik_take(
            source_namespace, source, tuple(mesh for _,mesh in skins), all_frames)
        mode = 'spine.spline.spineIkFk'
        if any(abs(dict(row)[mode]-1.) > 1e-8 for row in channels):
            raise CharacterRegistryError('IK 跨段数迁移要求整个采样区间保持 Spline IK 模式')
        return RegisteredSpineIkTake(source,target,all_frames,channels,
                                     meshes,float(max_mesh_error))

    def apply_in_transaction(self, take, source_namespace, skins):
        host = self._host
        if (host.read_source_character_registration(source_namespace)
                != take.source_registration
                or host.read_character_registration() != take.target_registration):
            raise CharacterRegistryError('IK 迁移角色登记在写入前发生变化')
        host.write_registered_spine_ik_take(take)
        self.verify_meshes(take, skins)

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
