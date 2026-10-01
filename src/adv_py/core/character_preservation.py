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
    component_memberships: tuple[tuple[str, tuple[int, ...] | None], ...] = ()
    influence_locks: tuple[tuple[int, str, bool, bool], ...] = ()


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
    # Editable controller geometry is retained independently of the new
    # default shape topology, as in MEL's oldShape.local -> newShape.create.
    # Role, degree, form, homogeneous CVs, knots. Solver curves stay audited
    # against their generated topology and are never overwritten here.
    curve_geometry: tuple[tuple[str,int,int,tuple,tuple[float,...]], ...] = ()
    # Original extra controller shapes survive as native objects. Their
    # destination transform is paired by UUID; no curve reconstruction occurs.
    retained_shapes: tuple[tuple[str,str,str,tuple], ...] = ()
    # A newly generated default shape can be absent on the edited old control.
    created_shapes: tuple[tuple[str,str], ...] = ()


@dataclass(frozen=True)
class PreservedControlState:
    node: str
    uuid: str
    # Attribute, locked, keyable, displayed in the Channel Box.
    channels: tuple[tuple[str,bool,bool,bool], ...] = ()
    # Native transformLimits flag, min/max values, enabled min/max.
    limits: tuple[tuple[str,tuple[float,float],tuple[bool,bool]], ...] = ()


@dataclass(frozen=True)
class PreservedSelectionSet:
    node: str
    uuid: str
    # Native member UUID and optional component address, independent of DAG
    # names and of the namespace used by the replacement stage.
    members: tuple[tuple[str,str], ...]
    parents: tuple[str, ...] = ()
    connections: tuple[tuple[str,str], ...] = ()


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
    control_states: tuple[PreservedControlState, ...] = ()
    selection_sets: tuple[PreservedSelectionSet, ...] = ()

    @property
    def content_digest(self):
        validate_preservation(self)
        return digest(asdict(self))


def validate_preservation(snapshot):
    finite(snapshot.current_time)
    # Reject non-finite data at every level, including retained custom values.
    try:canonical(asdict(snapshot))
    except (ValueError,TypeError) as exc:raise CharacterRegistryError('重建保留数据包含不可序列化或非有限数值') from exc
    for rows in (snapshot.curves,snapshot.skins,snapshot.extensions,snapshot.properties,snapshot.deformers,snapshot.control_states,snapshot.selection_sets):
        if len({r.uuid for r in rows})!=len(rows):raise CharacterRegistryError('重建保留对象身份重复')
    for row in snapshot.selection_sets:
        if (not row.node or not row.uuid or len(set(row.members))!=len(row.members)
                or any(not uuid or component and not component.startswith('.')
                       for uuid,component in row.members)
                or len(set(row.parents))!=len(row.parents)):
            raise CharacterRegistryError('重建用户选择集成员或父级身份无效')
    for row in snapshot.control_states:
        if (not row.node or not row.uuid
                or len({a[0] for a in row.channels})!=len(row.channels)
                or any(attr not in tuple(kind+axis for kind in ('translate','rotate','scale') for axis in 'XYZ')
                       or any(type(value) is not bool for value in (locked,keyable,visible))
                       for attr,locked,keyable,visible in row.channels)
                or len({a[0] for a in row.limits})!=len(row.limits)
                or any(flag not in tuple(kind+axis for kind in 'trs' for axis in 'xyz')
                       or len(values)!=2 or len(enabled)!=2
                       or any(type(value) is not bool for value in enabled)
                       for flag,values,enabled in row.limits)):
            raise CharacterRegistryError('重建控制器锁定、显示或限制状态无效')
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
        lock_indices=[index for index,_,_,_ in skin.influence_locks]
        if (len(set(lock_indices))!=len(lock_indices)
                or len({path for _,path,_,_ in skin.influence_locks})
                != len(lock_indices)
                or any(index not in indices or not path
                       or type(value) is not bool or type(locked) is not bool
                       for index,path,value,locked in skin.influence_locks)):
            raise CharacterRegistryError('蒙皮影响关节锁定状态无效')
        for _,weights in skin.weights:
            if any(i not in indices or value<0 for i,value in weights):
                raise CharacterRegistryError('蒙皮权重引用未知影响或包含负值')
        if skin.component_memberships:
            counts={path:count for path,_,count in skin.meshes}
            if (len(skin.component_memberships)!=len(counts)
                    or {path for path,_ in skin.component_memberships}
                    != set(counts)):
                raise CharacterRegistryError('蒙皮变形集与几何体不一致')
            for path,members in skin.component_memberships:
                if members is not None and (
                        any(type(index) is not int
                            or index<0 or index>=counts[path]
                            for index in members)
                        or tuple(sorted(set(members)))!=members):
                    raise CharacterRegistryError('蒙皮变形集顶点索引无效')
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
