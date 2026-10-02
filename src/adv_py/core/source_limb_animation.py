"""Persist the original RP system's actual FK/IK correspondence.

The binding is graph identity, not a new rig plan: source names, Part receivers,
extra controls and Foot branches remain those created by the source builder.
"""
from dataclasses import dataclass, fields
from math import sqrt


@dataclass(frozen=True, slots=True)
class SourceLimbJointBinding:
    body: str
    fk_driver: str
    ik_driver: str
    control: str
    receiver: str


@dataclass(frozen=True, slots=True)
class SourceLimbHybridBinding:
    control: str
    fk_driver: str


@dataclass(frozen=True,slots=True)
class SourceLimbLengthBinding:
    attribute: str
    start_fk: str
    end_fk: str
    rest_length: float
    fraction: float


@dataclass(frozen=True, slots=True)
class SourceLimbAnimationBinding:
    label: str
    side: str
    blend_key: str
    ik_control: str
    pole_control: str
    align: str
    middle_index: int
    primary_count: int
    joints: tuple[SourceLimbJointBinding, ...]
    reset_controls: tuple[str, ...]
    reset_attributes: tuple[tuple[str, float], ...]
    toe_control: str | None
    toe_align: str | None
    toe_source: str | None
    ik_position_source: str
    hybrid_controls: tuple[SourceLimbHybridBinding, ...]
    reverse_roll: str | None
    reverse_handle: str | None
    lengths: tuple[SourceLimbLengthBinding,...]
    ratio_node: str | None
    dynamics_root: str | None
    global_control: str
    height: float
    leg_aim_control: str | None = None
    ik_scale_axes: tuple[str,str,str] | None = None
    pole_offsets: tuple[str,str] | None = None

    @property
    def paths(self):
        return frozenset((self.ik_control, self.pole_control, self.align,self.ik_position_source,self.global_control,
            *self.reset_controls, *(p for row in self.joints for p in
            (row.body, row.fk_driver, row.ik_driver, row.control, row.receiver)),
            *((self.toe_control,) if self.toe_control else ()),
            *((self.toe_align,) if self.toe_align else ()),
            *((self.toe_source,) if self.toe_source else ()),
            *(p for row in self.hybrid_controls for p in (row.control,row.fk_driver)),
            *(p for row in self.lengths for p in (row.start_fk,row.end_fk)),
            *((self.dynamics_root,) if self.dynamics_root else ()),
            *((self.reverse_roll,) if self.reverse_roll else ()),
            *(self.pole_offsets or ()),
            *((self.leg_aim_control,) if self.leg_aim_control else ())))

    def animation_keys(self,registration):
        controls={self.ik_control,self.pole_control,*self.reset_controls,
                  *(row.control for row in self.joints),
                  *(row.control for row in self.hybrid_controls)}
        if self.toe_control:controls.add(self.toe_control)
        if self.leg_aim_control:controls.add(self.leg_aim_control)
        return frozenset(channel.key for channel in registration.channels
                         if channel.node in controls or channel.key==self.blend_key)


def describe_source_limb_bindings(plan, body):
    """Use final post-Inbetween paths; never reconstruct names from a template."""
    rows = []
    positions = [joint.world_position for joint in body.joints]
    height = plan.global_control.fit_height or max(
        max(p[axis] for p in positions)-min(p[axis] for p in positions) for axis in range(3))
    for limb in plan.limbs:
        for ik in limb.ik.limbs:
            fk = {joint.source_joint: joint.path for joint in limb.mechanisms.joints
                  if joint.side is ik.side and joint.role.value == 'fk'}
            drivers = tuple(joint for joint in limb.mechanisms.joints
                            if joint.side is ik.side and joint.role.value == 'ik')
            primary = [joint for joint in drivers if
                       joint.source_joint.rsplit('|', 1)[-1].rsplit('_', 1)[0]
                       in limb.joint_names]
            ordered = primary + [joint for joint in drivers if joint not in primary]
            joints = []
            for driver in ordered:
                control = next((control for control in plan.fk.controls
                                if control.driven_joint == fk[driver.source_joint]),None)
                joints.append(SourceLimbJointBinding(driver.source_joint,
                    fk[driver.source_joint], driver.path,
                    control.control_path if control else fk[driver.source_joint],
                    (control.source_override_path or control.sub_control_path
                     or control.control_path) if control else fk[driver.source_joint]))
            blend = next(side for side in limb.blend.sides if side.side is ik.side)
            foot = (next(side for side in limb.foot.sides if side.side is ik.side)
                    if limb.foot else None)
            reset = [p for p in (ik.wrist_extra_path, ik.wrist_sub_path,
                                ik.pole_extra_path) if p]
            if ik.ik_local_mode == 'addCtrl':
                reset.extend((ik.source_local_control, ik.source_local_extra))
            toe = toe_align = toe_source = reverse_roll = reverse_handle = None
            hybrid_controls = ()
            position_source = primary[-1].source_joint
            # MEL 10837 initially reads FK; the later positioning pass reads
            # FKX after stretchy/volume are enabled (10924). Keep both roles.
            position_source = next(row.control for row in joints if row.body == position_source)
            align = ik.wrist_align_path
            attributes = ()
            if foot:
                toe_body=next(joint.source_joint for joint in drivers
                              if joint.path==foot.toe_driver_path)
                toe_source=fk[toe_body]
                qtoes=tuple(row for row in joints if any(joint.path==row.body
                    and joint.label is not None and 'QToes' in joint.label.text
                    for joint in body.joints))
                qtoe=qtoes[0] if qtoes else None
                if qtoes:
                    position_source=qtoes[-1].control
                attributes = tuple((attr, foot.attribute_default(attr))
                                   for attr in foot.attributes
                                   if attr not in ('footPivotsVis',))
                reset.extend(p for p in (foot.toe_extra_path, foot.toe_sub_path) if p)
                reset.extend(pivot.roll_control_path for pivot in foot.pivots
                             if pivot.roll_control_path)
                reset.extend(pivot.roll_extra_path for pivot in foot.pivots
                             if pivot.roll_extra_path)
                reset.extend(pivot.control_path for pivot in foot.manual_pivots)
                if foot.hybrid:
                    reset.extend(segment.control_path for segment in foot.hybrid.segments)
                    hybrid_controls = tuple(SourceLimbHybridBinding(segment.control_path,
                        fk[segment.source_path]) for segment in foot.hybrid.segments)
                    align = next((helper.path for helper in foot.align_helpers
                                  if qtoe and helper.parent_path==qtoe.fk_driver),align)
                    reverse_roll = next(pivot.roll_control_path for pivot in foot.pivots
                        if pivot.roll_control_name and getattr(pivot.role,'value',pivot.role)=='qtoes')
                    reverse_handle = foot.handle_name
                else:
                    toe = foot.toe_control_path
                    toe_align = next((helper.path for helper in foot.align_helpers
                                      if helper.parent_path == fk.get(next(
                                          (j.source_joint for j in drivers
                                           if j.path == foot.toe_driver_path), ''))), None)
                if foot.source_aim and qtoe:
                    reverse_roll = next(pivot.roll_control_path for pivot in foot.pivots
                        if getattr(pivot.role,'value',pivot.role)=='qtoes')
                    reverse_handle = foot.handle_name
            leg_aim = next((spec for spec in plan.leg_aim
                            if spec.label==limb.label and spec.side==ik.side.value),None)
            if leg_aim:
                attributes += (('legAim',0.),)
            dynamics=next((spec for spec in plan.rp_dynamics
                           if spec.label==limb.label and spec.side==ik.side.value),None)
            lengths=[]
            if dynamics:
                source_tx = any(node.kind=='multiplyDivide' and
                    node.name=='AdvPy_'+limb.label+'_RP_'+ik.side.value+'_Length1'
                    for node in dynamics.nodes)
                tx_sign=next((dict(node.values)['conversionFactor'] for node in dynamics.nodes
                    if node.name=='AdvPy_'+limb.label+'_RP_'+ik.side.value+'_PoleDistanceSign1'),1.)
                attributes+= (('stretchy',0.),('antiPop',0.),('volume',10.))
                attributes+=tuple((segment.length_attribute,1.) for segment in dynamics.segments)
                attributes+=tuple((segment.fatness_attribute,0.) for segment in dynamics.segments)
                full=(primary[0].path,*(segment.joint for segment in dynamics.segments))
                for left,right in zip(primary,primary[1:]):
                    first,last=full.index(left.path),full.index(right.path)
                    segments=dynamics.segments[first:last]
                    measures=tuple(segment.translation[0]*tx_sign if source_tx else
                        sqrt(sum(v*v for v in segment.translation)) for segment in segments)
                    rest=sum(abs(value) for value in measures)
                    # Source FreeOrient keeps ty/tz fixed. Its Lenght graph
                    # still divides by authored tx (MEL 10934–10942), never
                    # by the vector magnitude. Preserve a zero tx in the
                    # record so matching can report that actual limitation.
                    weights=tuple(abs(value) for value in measures) if rest>1e-8 else tuple(
                        sqrt(sum(v*v for v in segment.translation)) for segment in segments)
                    weight_total=sum(weights)
                    start=(next(row.control for row in joints if row.body==left.source_joint)
                           if source_tx else fk[left.source_joint])
                    end=(next(row.control for row in joints if row.body==right.source_joint)
                         if source_tx else fk[right.source_joint])
                    for segment,segment_length,weight in zip(segments,measures,weights):
                        lengths.append(SourceLimbLengthBinding(segment.length_attribute,
                            start,end,segment_length,weight/weight_total))
            rows.append(SourceLimbAnimationBinding(limb.label, ik.side.value,
                limb.label.lower()+'.'+ik.side.value+'.'+blend.attribute,
                ik.wrist_control_path, ik.pole_control_path, align,
                next(i for i, j in enumerate(primary) if j.path == ik.chain[1]),
                len(primary), tuple(joints), tuple(dict.fromkeys(reset)),
                attributes, toe, toe_align,toe_source,position_source,hybrid_controls,
                reverse_roll,reverse_handle,tuple(lengths),dynamics.ratio if dynamics else None,
                dynamics.start_anchor if dynamics else None,
                plan.global_control.control_path,float(height),leg_aim.fk_control if leg_aim else None,
                _source_scale_axes(plan,limb,ik),_source_pole_offsets(plan,joints,primary,ik)))
    return tuple(rows)


def decode_source_limb_bindings(raw, channels, body, nodes, *, legacy=False):
    from .character_registry import exact, path, identifier, finite, CharacterRegistryError
    channel_map = {channel.key: channel for channel in channels}
    channel_pairs={(channel.node,channel.attribute) for channel in channels}
    node_paths = {node.path for node in nodes}
    body_paths = {joint.path for joint in body}
    if not isinstance(raw, list) or not raw or len(raw) > 128:
        raise CharacterRegistryError('来源 RP 动画系统数量无效')
    result = []
    for row in raw:
        if legacy:
            row = {**exact(row,(field.name for field in fields(SourceLimbAnimationBinding)
                               if field.name not in ('leg_aim_control','ik_scale_axes','pole_offsets'))),
                   'leg_aim_control':None,'ik_scale_axes':None,'pole_offsets':None}
        exact(row, (field.name for field in fields(SourceLimbAnimationBinding)))
        joints = tuple(SourceLimbJointBinding(**{
            key: path(value) for key, value in exact(item,
                (field.name for field in fields(SourceLimbJointBinding))).items()})
            for item in row['joints'])
        primary, middle = row['primary_count'], row['middle_index']
        if (type(primary) is not int or type(middle) is not int
                or not 2 <= primary <= len(joints) <= 256
                or not (middle==0 if primary==2 else 0 < middle < primary-1)
                or row['side'] not in ('R', 'L', 'M')
                or len({j.body for j in joints}) != len(joints)
                or any(j.body not in body_paths for j in joints)):
            raise CharacterRegistryError('来源 RP 动画关节对应关系无效')
        attributes = []
        if row['ik_scale_axes'] is not None and not isinstance(row['ik_scale_axes'],list):
            raise CharacterRegistryError('来源 RP 缩放轴向必须是数组')
        if row['pole_offsets'] is not None and (
                not isinstance(row['pole_offsets'],list) or len(row['pole_offsets'])!=2):
            raise CharacterRegistryError('来源 RP Pole 权重 Offset 记录无效')
        for item in row['reset_attributes']:
            if not isinstance(item, list) or len(item) != 2:
                raise CharacterRegistryError('来源 RP 动画复位属性无效')
            attr = identifier(item[0])
            if '.' in attr:
                raise CharacterRegistryError('来源 RP 复位属性必须是单一属性')
            attributes.append((attr, finite(item[1])))
        binding = SourceLimbAnimationBinding(identifier(row['label']), row['side'],
            identifier(row['blend_key']), path(row['ik_control']),
            path(row['pole_control']), path(row['align']), middle, primary, joints,
            tuple(path(p) for p in row['reset_controls']), tuple(attributes),
            path(row['toe_control']) if row['toe_control'] else None,
            path(row['toe_align']) if row['toe_align'] else None,
            path(row['toe_source']) if row['toe_source'] else None,
            path(row['ik_position_source']),tuple(SourceLimbHybridBinding(**{
                key:path(value) for key,value in exact(item,('control','fk_driver')).items()})
                for item in row['hybrid_controls']),
            path(row['reverse_roll']) if row['reverse_roll'] else None,
            identifier(row['reverse_handle']) if row['reverse_handle'] else None,
            tuple(SourceLimbLengthBinding(identifier(item['attribute']),path(item['start_fk']),
                path(item['end_fk']),finite(item['rest_length']),finite(item['fraction']))
                for item in (exact(item,(f.name for f in fields(SourceLimbLengthBinding)))
                             for item in row['lengths'])),
            identifier(row['ratio_node']) if row['ratio_node'] else None,
            path(row['dynamics_root']) if row['dynamics_root'] else None,
            path(row['global_control']),
            finite(row['height']),path(row['leg_aim_control']) if row['leg_aim_control'] else None,
            tuple(row['ik_scale_axes']) if row['ik_scale_axes'] is not None else None,
            tuple(path(value) for value in row['pole_offsets']) if row['pole_offsets'] is not None else None)
        if (binding.height <= 0 or not binding.paths.issubset(node_paths)
                or binding.blend_key not in channel_map
                or len(set(binding.reset_controls)) != len(binding.reset_controls)
                or len({key for key, _ in attributes}) != len(attributes)
                or bool(binding.reverse_roll)!=bool(binding.reverse_handle)
                or bool(binding.lengths)!=bool(binding.ratio_node)
                or bool(binding.lengths)!=bool(binding.dynamics_root)
                or binding.ik_scale_axes is not None and (
                    len(binding.ik_scale_axes)!=3 or set(binding.ik_scale_axes)!=set('XYZ'))
                or any(not 0<=item.fraction<=1
                       or '.' in item.attribute for item in binding.lengths)):
            raise CharacterRegistryError('来源 RP 动画缺少已登记的节点或模式通道')
        required={(binding.ik_control,kind+axis) for kind in ('translate','rotate','scale') for axis in 'XYZ'}
        required.update((binding.pole_control,'translate'+axis) for axis in 'XYZ')
        required.update((binding.ik_control,attribute) for attribute,_ in binding.reset_attributes)
        required.update((binding.ik_control,row.attribute) for row in binding.lengths)
        if binding.lengths:required.add((binding.pole_control,'lock'))
        if not required.issubset(channel_pairs):
            raise CharacterRegistryError('来源 RP 动画控制属性没有完整登记')
        length_groups={}
        for item in binding.lengths:
            length_groups.setdefault((item.start_fk,item.end_fk),[]).append(item)
        if binding.lengths:
            wanted={(left.fk_driver,right.fk_driver) for left,right in
                    zip(binding.joints[:primary],binding.joints[1:primary])}
            source_wanted={(left.control,right.control) for left,right in
                    zip(binding.joints[:primary],binding.joints[1:primary])}
            if (set(length_groups) not in (wanted,source_wanted)
                    or len({item.attribute for item in binding.lengths})!=len(binding.lengths)):
                raise CharacterRegistryError('来源 RP 长度通道没有覆盖实际主链')
            for items in length_groups.values():
                total=sum(abs(item.rest_length) for item in items)
                if (abs(sum(item.fraction for item in items)-1.)>1e-8
                        or total>1e-8 and any(
                            abs(item.fraction-abs(item.rest_length)/total)>1e-8 for item in items)):
                    raise CharacterRegistryError('来源 RP Part 长度分配不一致')
        result.append(binding)
    if len({(r.label.lower(), r.side) for r in result}) != len(result):
        raise CharacterRegistryError('来源 RP 动画系统身份重复')
    return tuple(result)


def _source_scale_axes(plan,limb,ik):
    from .source_limb_scale import source_limb_scale_axes
    return source_limb_scale_axes(limb.label,use_offset_parent_matrix=plan.source_use_offset_parent_matrix,
        ik_local_mode=ik.ik_local_mode) if plan.source_rp_scale_axes else None


def _source_pole_offsets(plan,joints,primary,ik):
    if len(primary)==2:
        return None
    middle = next(index for index,joint in enumerate(primary) if joint.path==ik.chain[1])
    drivers = (joints[middle].fk_driver,joints[len(primary)-1].fk_driver)
    offsets = tuple(next((control.offset_path for control in plan.fk.controls
                          if control.driven_joint==driver),None) for driver in drivers)
    return offsets if all(offsets) else None


def resolve_source_limb(registration, label, side):
    from .character_registry import CharacterRegistryError
    aliases = {'arm': 'Arm', 'leg': 'Leg'}
    candidates = [row for row in registration.source_limbs
                  if row.side == side and row.label.lower() == label.lower()]
    if not candidates and label in aliases:
        candidates = [row for row in registration.source_limbs
                      if row.side == side and row.label == aliases[label]]
    if len(candidates) != 1:
        raise CharacterRegistryError('来源 RP 系统不存在或名称不唯一：'+label+' '+side)
    return candidates[0]


def source_pole_position(start, middle, end, height, fallback_axis, *,weights=None):
    """asAlignFKIK: length-weighted baseline, middle aim, height/3.333 reach."""
    def length(vector):
        return sqrt(sum(v*v for v in vector))
    first,second = (weights if weights is not None else (
        length(tuple(a-b for a,b in zip(middle,start))),length(tuple(a-b for a,b in zip(end,middle)))))
    if first<0 or second<0:
        raise ValueError('来源 RP Pole 权重不能为负数')
    if first+second <= 1e-8:
        raise ValueError('来源 RP 匹配骨段长度退化')
    baseline = tuple((a*second+b*first)/(first+second) for a, b in zip(start, end))
    direction = tuple(a-b for a, b in zip(middle, baseline))
    distance = length(direction)
    if distance <= 1e-8:
        direction = fallback_axis
    norm = length(direction)
    if norm <= 1e-8:
        raise ValueError('来源 RP 匹配缺少 Pole 方向')
    return tuple(a+v/norm*(height/3.333+distance) for a, v in zip(baseline, direction))
