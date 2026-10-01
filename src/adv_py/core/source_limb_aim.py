"""Original QToes and LegAim branches (MEL 82470–82719).

The plans refer to the already built source graph. Insertions return explicit
DAG rewrites so callers keep every control, receiver and follow reference.
"""
from dataclasses import dataclass

from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True, slots=True)
class SourceFootAimSpec:
    label: str
    side: str
    stem: str
    control: str
    pole: str
    start: str
    start_driver: str
    end_body: str
    end_fit: str
    offset: str
    roll_offset: str
    lift_offset: str
    align_toes: str | None
    parent: str
    main: str
    main_scale: str
    start_position: tuple[float, float, float]
    aim_path: str
    unoffset_path: str
    target_path: str
    lift_path: str
    use_offset_parent_matrix: bool

    @property
    def attributes(self):
        return ('toesAim', 'liftRoll')

    @property
    def paths(self):
        return (self.aim_path, self.unoffset_path, self.target_path, self.lift_path,self.start)


@dataclass(frozen=True, slots=True)
class SourceLegAimSpec:
    label: str
    side: str
    stem: str
    control: str
    offset: str
    fk_control: str
    target: str
    blend: str
    sign: float
    aim_path: str
    distance_start: str
    distance_end: str
    parent: str

    @property
    def paths(self):
        return (self.aim_path, self.distance_start, self.distance_end)


def plan_source_foot_aim(body, limb, ik, foot, main, *,use_offset_parent_matrix=True,instances=()):
    """QToes activates this branch, including simple non-hybrid QToes."""
    by_path = {joint.path: joint for joint in body.joints}
    end = next(joint for joint in limb.mechanisms.joints if joint.path == ik.chain[-1])
    qtoes = [joint for joint in body.joints if joint.path.startswith(end.source_joint+'|')
             and joint.label is not None and 'QToes' in joint.label.text]
    if not qtoes:
        return None
    if len(qtoes) != 1:
        raise FitSkeletonValidationError('来源 Foot QToes 标记不唯一')
    # MEL uses the first Foot child, not the last intermediate or Toes node.
    tails = [joint for joint in limb.mechanisms.joints if joint.side is ik.side
             and joint.role.value == 'ik' and joint.source_joint.startswith(end.source_joint+'|')]
    first = next((joint for joint in tails if not any(
        joint.source_joint.startswith(other.source_joint+'|') for other in tails)), None)
    if first is None:
        raise FitSkeletonValidationError('来源 QToes 缺少 Foot 子链')
    source_name = by_path[first.source_joint].name.rsplit('_', 1)[0]
    # Planner aliases Ankle/Toes; intermediate marker names remain source names.
    pivot = next((pivot for pivot in foot.pivots if pivot.roll_control_name
                  and (getattr(pivot.role, 'value', pivot.role) == 'qtoes'
                       if first.source_joint == qtoes[0].path
                       else getattr(pivot.role, 'value', pivot.role) == 'segment:'+by_path[first.source_joint].name)), None)
    if pivot is None:
        raise FitSkeletonValidationError('来源 QToes 首子关节缺少 RollOffset：'+source_name)
    lift = next(pivot for pivot in foot.pivots if pivot.roll_control_name)
    start = next(joint for joint in limb.mechanisms.joints if joint.path == ik.chain[0])
    stem = 'AdvPy_'+limb.label+'_FootAim_'+ik.side.value
    parent = limb.ik.root_path
    toe_source = next(joint.source_joint for joint in limb.mechanisms.joints
                      if joint.path == foot.toe_driver_path)
    toe_fk = next(joint.path for joint in limb.mechanisms.joints
                  if joint.source_joint == toe_source and joint.role.value == 'fk')
    from .source_fit_identity import source_fit_reference
    end_fit = source_fit_reference(by_path[end.source_joint].name,instances) or end.source_joint
    return SourceFootAimSpec(limb.label, ik.side.value, stem, ik.wrist_control_path,
        ik.pole_control_path, limb.mechanisms.root_path+'|'+stem+'_Start',ik.chain[0],end.source_joint,end_fit,ik.wrist_offset_path,
        pivot.roll_offset_path, lift.roll_offset_path,
        next((helper.path for helper in foot.align_helpers
              if helper.parent_path == toe_fk), None),
        parent, main.control_path, main.effective_scale_source('Y'), start.world_position,
        pivot.roll_offset_path+'|'+stem+'_ToesAim',
        pivot.roll_offset_path+'|'+stem+'_ToesAim|'+stem+'_UnOffset',
        parent+'|'+stem+'_Target', lift.roll_offset_path+'|'+stem+'_LiftRoll',use_offset_parent_matrix)


def plan_source_leg_aim(body, fk, limb, ik, *,non_symmetry=False):
    by_path = {joint.path: joint for joint in body.joints}
    start = next(joint for joint in limb.mechanisms.joints if joint.path == ik.chain[0])
    parent = by_path[start.source_joint].parent_path
    while parent in by_path and 'Part' in by_path[parent].name:
        parent = by_path[parent].parent_path
    if parent not in by_path or by_path[parent].label is None or 'LegAim' not in by_path[parent].label.text:
        return None
    control = next((control for control in fk.controls if control.driven_joint == parent
                    or control.side is by_path[parent].side
                    and by_path[parent].name.rsplit('_',1)[0] in control.fit_joint_names), None)
    if control is None:
        raise FitSkeletonValidationError('来源 LegAim 父关节缺少 FK 控制器')
    side = next(side for side in limb.blend.sides if side.side is ik.side)
    stem = 'AdvPy_'+limb.label+'_LegAim_'+ik.side.value
    # Under non-symmetry the original b2 is -1, including the source side.
    sign = -1. if ik.side.value == 'L' or non_symmetry else 1.
    return SourceLegAimSpec(limb.label, ik.side.value, stem, ik.wrist_control_path,
        control.offset_path, control.control_path, ik.wrist_control_path,
        limb.blend.settings_path+'.'+side.attribute, sign,
        control.offset_path+'|'+stem+'_Aim', limb.ik.root_path+'|'+stem+'_DistanceStart',
        limb.ik.root_path+'|'+stem+'_DistanceEnd', limb.ik.root_path)


def pre_aim_control_path(path):
    """Saved policy is read before the source LegAim insertion is recreated."""
    return '|'.join(part for part in path.split('|')
                    if not (part.startswith('AdvPy_') and '_LegAim_' in part and part.endswith('_Aim')))


def decode_source_limb_aim(text):
    """Closed graph data shared by registration, rebuilding and Root Motion."""
    from dataclasses import fields
    import re
    from .character_registry import safe_json, exact, path, identifier, finite, CharacterRegistryError
    record = exact(safe_json(text),('version','role','spec','nodes','edges','values'))
    if type(record['version']) is not int or record['version']!=1 or record['role'] not in ('foot','leg'):
        raise CharacterRegistryError('来源瞄准图版本或类别无效')
    kind = SourceFootAimSpec if record['role']=='foot' else SourceLegAimSpec
    spec = exact(record['spec'],(field.name for field in fields(kind)))
    for name,value in spec.items():
        if name in ('label','stem'):
            identifier(value)
        elif name=='side':
            if value not in ('R','L','M'):
                raise CharacterRegistryError('来源瞄准侧别无效')
        elif name=='sign':
            if finite(value) not in (-1.,1.):
                raise CharacterRegistryError('来源瞄准符号无效')
        elif name=='use_offset_parent_matrix':
            if type(value) is not bool:
                raise CharacterRegistryError('来源瞄准 OPM 设置无效')
        elif name=='start_position':
            if not isinstance(value,list) or len(value)!=3:
                raise CharacterRegistryError('来源瞄准起始位置无效')
            for component in value:finite(component)
        elif name not in ('blend','main_scale'):
            if value is not None or name!='align_toes':path(value)
    plug_pattern = re.compile(r'^(?:\|[A-Za-z_][A-Za-z0-9_:]*\|?)*[A-Za-z_][A-Za-z0-9_:]*\.[A-Za-z_][A-Za-z0-9_.\[\]]*$')
    def plug(value):
        if not isinstance(value,str) or not plug_pattern.fullmatch(value):
            raise CharacterRegistryError('来源瞄准连接属性无效')
    for name in ('blend','main_scale'):
        if name in spec:plug(spec[name])
    allowed={'unitConversion','multiplyDivide','multDoubleLinear','multDL','plusMinusAverage',
             'clamp','multMatrix','blendMatrix','aimMatrix','pickMatrix','decomposeMatrix','distanceBetween'}
    if not isinstance(record['nodes'],list) or not 1<=len(record['nodes'])<=64:
        raise CharacterRegistryError('来源瞄准驱动节点数量无效')
    names=[]
    for row in record['nodes']:
        if not isinstance(row,list) or len(row)!=2 or row[1] not in allowed:
            raise CharacterRegistryError('来源瞄准节点类别无效')
        identifier(row[0])
        if '.' in row[0] or not row[0].startswith(spec['stem']+'_'):
            raise CharacterRegistryError('来源瞄准节点归属无效')
        names.append(row[0])
    if len(set(names))!=len(names):
        raise CharacterRegistryError('来源瞄准节点身份重复')
    destinations=[]
    if not isinstance(record['edges'],list) or len(record['edges'])>256:
        raise CharacterRegistryError('来源瞄准连接数量无效')
    for row in record['edges']:
        if not isinstance(row,list) or len(row)!=2:
            raise CharacterRegistryError('来源瞄准连接记录无效')
        for value in row:plug(value)
        destinations.append(row[1])
    if len(set(destinations))!=len(destinations):
        raise CharacterRegistryError('来源瞄准输入重复')
    if not isinstance(record['values'],list) or len(record['values'])>128:
        raise CharacterRegistryError('来源瞄准常量数量无效')
    value_plugs=[]
    for row in record['values']:
        if not isinstance(row,list) or len(row)!=2:
            raise CharacterRegistryError('来源瞄准常量记录无效')
        plug(row[0])
        value_plugs.append(row[0])
        if isinstance(row[1],list):
            if len(row[1]) not in (3,16):
                raise CharacterRegistryError('来源瞄准向量或矩阵维数无效')
            for value in row[1]:finite(value)
        elif not isinstance(row[1],bool):finite(row[1])
    if len(set(value_plugs))!=len(value_plugs) or set(value_plugs)&set(destinations):
        raise CharacterRegistryError('来源瞄准常量与输入冲突')
    return record
