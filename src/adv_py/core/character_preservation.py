"""Immutable retained scene data for character rebuild handoff."""
from dataclasses import asdict, dataclass
from .character_registry import CharacterRegistration, CharacterRegistryError, canonical, digest, finite
from .character_pose import CharacterPose


@dataclass(frozen=True)
class PreservedCurve:
    node: str
    uuid: str
    node_type: str
    input: str
    outputs: tuple[str, ...]
    times: tuple[float, ...]
    values: tuple[float, ...]
    in_tangents: tuple[str, ...]
    out_tangents: tuple[str, ...]
    in_angles: tuple[float, ...]
    out_angles: tuple[float, ...]
    in_weights: tuple[float, ...]
    out_weights: tuple[float, ...]
    tangent_locks: tuple[bool, ...]
    weight_locks: tuple[bool, ...]
    breakdown_times: tuple[float, ...]
    weighted: bool
    pre_infinity: int
    post_infinity: int


@dataclass(frozen=True)
class PreservedSkin:
    node: str
    uuid: str
    meshes: tuple[tuple[str, str, int], ...]
    settings: tuple[tuple[str, float], ...]
    influences: tuple[tuple[int, str, tuple[float, ...], str], ...]
    weights: tuple[tuple[int, tuple[tuple[int, float], ...]], ...]
    blend_weights: tuple[tuple[int, float], ...]
    connections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PreservedDeformer:
    node: str
    uuid: str
    node_type: str
    mesh_stack: tuple[tuple[str, int], ...]
    settings: tuple[tuple[str, float | tuple[float, ...]], ...]
    aliases: tuple[str, ...]
    connections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PreservedExtension:
    path: str
    uuid: str
    node_type: str
    parent: str | None
    matrix: tuple[float, ...] | None
    attributes: tuple[tuple[str, str, object, bool, bool, tuple], ...]
    connections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RebuildOwnership:
    # Logical role, original UUID, replacement UUID, native node type.
    nodes: tuple[tuple[str,str,str,str], ...]
    connections: tuple[tuple[str,str], ...]
    shapes: tuple[tuple[str,tuple[float,...],tuple,tuple[float,...]], ...] = ()


@dataclass(frozen=True)
class CharacterPreservation:
    registration: CharacterRegistration
    pose: CharacterPose
    current_time: float
    time_unit: str
    namespace: str | None
    curves: tuple[PreservedCurve, ...]
    skins: tuple[PreservedSkin, ...]
    extensions: tuple[PreservedExtension, ...]
    properties: tuple[PreservedExtension, ...] = ()
    deformers: tuple[PreservedDeformer, ...] = ()

    @property
    def content_digest(self):
        validate_preservation(self)
        return digest(asdict(self))


def validate_preservation(snapshot):
    finite(snapshot.current_time)
    # Reject non-finite data at every level, including retained custom values.
    try:canonical(asdict(snapshot))
    except (ValueError,TypeError) as exc:raise CharacterRegistryError('重建保留数据包含不可序列化或非有限数值') from exc
    for rows in (snapshot.curves,snapshot.skins,snapshot.extensions,snapshot.properties,snapshot.deformers):
        if len({r.uuid for r in rows})!=len(rows):raise CharacterRegistryError('重建保留对象身份重复')
    for curve in snapshot.curves:
        count=len(curve.times)
        if any(len(getattr(curve,field))!=count for field in ('values','in_tangents','out_tangents',
                'in_angles','out_angles','in_weights','out_weights','tangent_locks','weight_locks')):
            raise CharacterRegistryError('动画曲线键或切线快照不完整')
        if any(a>=b for a,b in zip(curve.times,curve.times[1:])):
            raise CharacterRegistryError('动画曲线时间不递增')
        if any(t not in curve.times for t in curve.breakdown_times):
            raise CharacterRegistryError('动画 breakdown 标记没有对应关键帧')
    for skin in snapshot.skins:
        indices=[i for i,_,_,_ in skin.influences]
        if not indices or len(set(indices))!=len(indices) or any(len(m)!=16 for _,_,m,_ in skin.influences):
            raise CharacterRegistryError('蒙皮影响索引或绑定矩阵不完整')
        for _,weights in skin.weights:
            if any(i not in indices or value<0 for i,value in weights):
                raise CharacterRegistryError('蒙皮权重引用未知影响或包含负值')
    for deformer in snapshot.deformers:
        if (deformer.node_type not in ('blendShape','deltaMush','wrap')
                or not deformer.mesh_stack
                or len(set(deformer.mesh_stack))!=len(deformer.mesh_stack)):
            raise CharacterRegistryError('生产变形器类型或网格顺序无效')
    return snapshot


def validate_rebuild_layout(before, after, tolerance=1e-6):
    """Same-topology replacement contract; shape changes require a migration."""
    if (tuple((c.key,c.attribute,c.minimum,c.maximum) for c in before.channels)!=
            tuple((c.key,c.attribute,c.minimum,c.maximum) for c in after.channels)
            or tuple((j.path,j.parent) for j in before.body)!=tuple((j.path,j.parent) for j in after.body)
            or before.spaces!=after.spaces):
        raise CharacterRegistryError('重建角色的拓扑或控制语义变化，需要明确迁移计划')
    if any(abs(a-b)>tolerance for x,y in zip(before.body,after.body) for a,b in zip(x.matrix,y.matrix)):
        raise CharacterRegistryError('重建绑定布局变化，需要蒙皮与动画迁移计划')


def character_transfer_error(before,after):
    from .body_control_spaces import control_space_pose_error
    if not before or tuple(row[0] for row in before)!=tuple(row[0] for row in after):
        raise CharacterRegistryError('交接复检帧不一致')
    error=0.
    for left,right in zip(before,after):
        finite(left[0])
        error=max(error,*(control_space_pose_error(tuple(left[i]),tuple(right[i])) for i in (1,2)))
        for i in (3,4):
            if tuple(k for k,_ in left[i])!=tuple(k for k,_ in right[i]):
                raise CharacterRegistryError('交接复检蒙皮或附件身份不一致')
            for (_,a),(_,b) in zip(left[i],right[i]):
                if len(a)!=len(b):raise CharacterRegistryError('交接复检向量不完整')
                error=max(error,max((abs(finite(x)-finite(y)) for x,y in zip(a,b)),default=0.))
    return error
