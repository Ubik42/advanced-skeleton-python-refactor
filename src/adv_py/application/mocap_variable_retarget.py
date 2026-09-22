"""Retarget an explicitly mapped variable-spine character through FK controls."""
from dataclasses import dataclass

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.mocap_preset import MocapMappingPreset

from .mocap_control_retarget import MocapRootControlPlan,RetargetMocapRootToCharacter
from .mocap_mapping import InspectMocapBodyMapping


@dataclass(frozen=True,slots=True)
class MocapFkGroupPlan:
    root: MocapRootControlPlan
    label: str
    source_joints: tuple[str,...]
    source_parents: tuple[str,...]
    target_joints: tuple[str,...]
    target_parents: tuple[str,...]
    controls: tuple[str,...]
    zero_plugs: tuple[str,...]


@dataclass(frozen=True,slots=True)
class MocapFkGroupSample:
    frame: float
    control_values: tuple[float,...]
    body_matrices: tuple[tuple[float,...],...]


@dataclass(frozen=True,slots=True)
class MocapVariableFullPlan:
    root: MocapRootControlPlan
    groups: tuple[MocapFkGroupPlan,...]


class RetargetMocapVariableFullFkToCharacter:
    """Write mapped variable-spine, upper-body, limb and distal FK motion."""
    DIGITS=('Thumb','Index','Middle','Ring','Pinky')
    def __init__(self,host):self._host=host

    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,
                         reference_frame=None,substeps=1):
        if not isinstance(preset,MocapMappingPreset):
            raise CharacterRegistryError('可变脊柱动捕需要版本化映射预设')
        root=RetargetMocapRootToCharacter(self._host).plan(source_root,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
            reference_frame=reference_frame,substeps=substeps)
        reg=root.registration
        if not isinstance(reg.spine,BodySplinePlan):
            raise CharacterRegistryError('此入口要求已登记的可变脊柱 Spline 角色')
        if len(reg.body)!=preset.expected_body_joint_count:
            raise CharacterRegistryError('动捕预设的 Body 关节数与角色不一致')
        short=lambda path:path.rsplit('|',1)[-1].rsplit(':',1)[-1]
        target_by_name={short(joint.path):joint for joint in reg.body}
        source_by_name={joint.name:joint for joint in root.source.joints}
        root_name=short(reg.body_root)
        spine_names=tuple(short(path) for path in reg.spine.body_joints[1:])
        upper_names=('Neck_M','Head_M','Scapula_R','Scapula_L')
        limbs=tuple(tuple(part+'_'+side for part in parts) for parts in
            (('Shoulder','Elbow','Wrist'),('Hip','Knee','Ankle')) for side in ('R','L'))
        distal_names=tuple('Toes_'+side for side in ('R','L'))
        has_hand=any(name.startswith('Thumb1_') for name in target_by_name)
        if has_hand:
            distal_names+=tuple(f'{digit}{segment}_{side}' for side in ('R','L')
                for digit in self.DIGITS for segment in (1,2,3))
        required={root_name,*spine_names,*upper_names,*distal_names}
        required.update(name for limb in limbs for name in limb)
        by_target={row.target_name:row for row in preset.mappings}
        if set(by_target)!=required or len(preset.mappings)!=len(required):
            raise CharacterRegistryError('可变脊柱动捕预设的 FK 目标关节集合不完整或含多余项')
        if (not by_target[root_name].transfer_translation
                or any(not row.transfer_rotation for row in preset.mappings)
                or any(row.transfer_translation for name,row in by_target.items() if name!=root_name)):
            raise CharacterRegistryError('动捕预设仅允许根部平移，所有关节须传递旋转')
        InspectMocapBodyMapping(self._host).execute(source_root,preset.mappings,
            body_root_name=reg.body_root,source_container=reg.container,
            expected_body_joint_count=preset.expected_body_joint_count).require_valid()
        if any(name not in source_by_name for name in (row.source_name for row in preset.mappings)):
            raise CharacterRegistryError('动捕预设引用了不存在的来源关节')
        if source_by_name[by_target[root_name].source_name].path!=root.source.root:
            raise CharacterRegistryError('动捕预设根部须对应指定的来源根关节')
        channels={channel.key:channel for channel in reg.channels}
        def plug(key):
            channel=channels.get(key)
            if channel is None:raise CharacterRegistryError('角色控制通道缺失：'+key)
            return channel.node+'.'+channel.attribute
        def control(prefix):
            group=tuple(channels.get(prefix+'.rotate'+axis) for axis in 'XYZ')
            if any(row is None for row in group) or len({row.node for row in group})!=1:
                raise CharacterRegistryError('角色 FK 控制旋转通道不完整：'+prefix)
            return group[0].node
        def make_group(label,names,zero_plugs):
            sources=[];targets=[];controls=[]
            for name in names:
                target=target_by_name.get(name)
                source=source_by_name[by_target[name].source_name]
                if target is None or target.parent is None or source.joint_parent is None:
                    raise CharacterRegistryError('角色或动捕关节父级缺失：'+name)
                parent_name=short(target.parent)
                if parent_name not in by_target or source.joint_parent!=source_by_name[
                        by_target[parent_name].source_name].path:
                    raise CharacterRegistryError('来源关节父链与 Body 不一致：'+name)
                if name in spine_names or name in upper_names:
                    key=f'torso.Torso{name}FK'
                elif name.startswith(('Shoulder_','Elbow_','Wrist_')):
                    key='arm.fk.'+name.replace('_','FK_',1)
                elif name.startswith(('Hip_','Knee_','Ankle_','Toes_')):
                    key='leg.fk.'+name.replace('_','FK_',1)
                else:
                    key='hand.fk.'+name.replace('_','FK_',1)
                sources.append(source);targets.append(target);controls.append(control(key))
            return MocapFkGroupPlan(root,label,tuple(row.path for row in sources),
                tuple(row.joint_parent for row in sources),tuple(row.path for row in targets),
                tuple(row.parent for row in targets),tuple(controls),tuple(zero_plugs))
        groups=[make_group('variable spine',spine_names,(plug('spine.spline.spineIkFk'),))]
        aim=channels.get('head.aim.headAim')
        groups.append(make_group('upper body',upper_names,()
            if aim is None else (aim.node+'.'+aim.attribute,)))
        for limb,names in zip(('arm','arm','leg','leg'),limbs):
            side=names[0].rsplit('_',1)[-1]
            groups.append(make_group(limb+' '+side,names,
                (plug(f'{limb}.settings.{limb}IkFk_{side}'),)))
        groups.append(make_group('toes and fingers',distal_names,
            tuple(plug(f'leg.settings.legIkFk_{side}') for side in ('R','L'))))
        return MocapVariableFullPlan(root,tuple(groups))

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,
                          reference_frame=None):
        options=dict(start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
                     reference_frame=reference_frame)
        plan=self.plan_with_preset(source_root,preset,**options)
        with self._host.transaction('Retarget variable-spine MoCap to full FK'):
            if self.plan_with_preset(source_root,preset,**options)!=plan:
                raise CharacterRegistryError('可变脊柱动捕或角色状态在写入前发生变化')
            root_samples=self._host.write_mocap_root_control_keys(plan.root)
            group_samples=tuple(self._host.write_mocap_fk_group_keys(group) for group in plan.groups)
            if any(tuple(sample.frame for sample in group)!=plan.root.frames
                   for group in (root_samples,*group_samples)):
                raise RuntimeError('可变脊柱动捕 FK 采样不完整')
        return root_samples,group_samples


class RetargetMocapVariableSplineIkToCharacter(RetargetMocapVariableFullFkToCharacter):
    """Convert mapped variable FK spine motion to Spline IK atomically."""
    _spine_ik=True
    _limb_ik=False
    _ik_limbs=()
    _mixed=False
    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,
                         reference_frame=None):
        plan=super().plan_with_preset(source_root,preset,start_frame=start_frame,
            end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)
        keys={row.key for row in plan.root.registration.channels}
        if self._spine_ik and ('spine.spline.1.translateX' not in keys
                or 'spine.spline.spineIkFk' not in keys):
            raise CharacterRegistryError('Spline IK 动捕须先启用可变脊柱动画通道登记')
        if self._ik_limbs:
            required={f'{limb}.fkLength.{side}.{index}' for limb,side in self._ik_limbs
                      for index in (0,1)}
            required.update(f'{limb}.ikOrientation.{side}.{segment}.rotate{axis}'
                for limb,side in self._ik_limbs
                for segment in ('upper','lower') for axis in 'XYZ')
            if not required.issubset(keys):
                raise CharacterRegistryError('可变脊柱全身 IK 动捕须先启用四肢动画通道登记')
        return plan

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,
                          reference_frame=None):
        from adv_py.core.character_animation import CharacterAnimation,validate_character_animation
        from adv_py.core.fit_symmetry import FitBuildSide
        from .character_animation import verify_character_animation_write
        options=dict(start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
                     reference_frame=reference_frame)
        plan=self.plan_with_preset(source_root,preset,**options)
        host=self._host
        reg=plan.root.registration
        label=('Retarget variable-spine MoCap with mixed modes' if self._mixed else
               'Retarget variable-spine MoCap to full IK' if self._limb_ik else
               'Retarget variable-spine MoCap to Spline IK')
        with host.transaction(label):
            if self.plan_with_preset(source_root,preset,**options)!=plan:
                raise CharacterRegistryError('可变脊柱动捕或角色状态在 Spline IK 写入前发生变化')
            root_samples=host.write_mocap_root_control_keys(plan.root)
            group_samples=tuple(host.write_mocap_fk_group_keys(group) for group in plan.groups)
            if any(tuple(sample.frame for sample in group)!=plan.root.frames
                   for group in (root_samples,*group_samples)):
                raise RuntimeError('可变脊柱动捕 FK 采样不完整')
            reference=host.sample_character_animation(reg,plan.root.frames)
            unit=host.character_time_unit()
            keys=host.capture_character_key_state(reg)
            animation=None
            if self._spine_ik:
                samples=host.match_character_spine_samples(reg,plan.root.frames,'ik')
                if host.capture_character_key_state(reg)!=keys or host.character_time_unit()!=unit:
                    raise RuntimeError('Spline IK 匹配采样改变了原曲线或时间')
                animation=CharacterAnimation(unit,samples)
                validate_character_animation(animation,reg)
                host.write_character_animation(reg,samples)
                verify_character_animation_write(host,reg,animation,keys)
            limb_conversions=[]
            for limb,side in self._ik_limbs:
                keys=host.capture_character_key_state(reg)
                samples=host.match_character_limb_samples(reg,plan.root.frames,limb,
                    FitBuildSide(side),'ik',pose_tolerance=1e-3)
                if host.capture_character_key_state(reg)!=keys or host.character_time_unit()!=unit:
                    raise RuntimeError('可变脊柱动捕四肢匹配采样改变了原曲线或时间')
                conversion=CharacterAnimation(unit,samples)
                validate_character_animation(conversion,reg)
                host.write_character_animation(reg,samples)
                verify_character_animation_write(host,reg,conversion,keys)
                limb_conversions.append(conversion)
            actual=host.sample_character_animation(reg,plan.root.frames)
            error=max(abs(a-b) for (_,before),(_,after) in zip(reference,actual)
                for (_,left),(_,right) in zip(before.body_frames,after.body_frames)
                for a,b in zip(left,right))
            if error>(1e-3 if self._ik_limbs else 1e-4):
                raise RuntimeError('动捕 Spline IK 转换改变了采样帧 Body 世界姿态：'+str(error))
        result=(root_samples,group_samples,animation)
        if self._mixed:return (*result,tuple(limb_conversions))
        return (*result,tuple(limb_conversions)) if self._limb_ik else result


class RetargetMocapVariableFullIkToCharacter(RetargetMocapVariableSplineIkToCharacter):
    """Retarget a variable Spline spine and all four limbs to IK controls."""
    _limb_ik=True
    _ik_limbs=(('arm','R'),('arm','L'),('leg','R'),('leg','L'))


class RetargetMocapVariableMixedToCharacter(RetargetMocapVariableSplineIkToCharacter):
    """Retarget an explicitly selected FK/IK mode for the spine and each limb."""
    _mixed=True

    def __init__(self,host,*,spine_mode,limb_modes):
        super().__init__(host)
        expected=(('arm','R'),('arm','L'),('leg','R'),('leg','L'))
        if spine_mode not in ('fk','ik'):
            raise CharacterRegistryError('混合动捕的脊柱模式必须为 fk 或 ik')
        if (not isinstance(limb_modes,dict) or set(limb_modes)!=set(expected)
                or any(mode not in ('fk','ik') for mode in limb_modes.values())):
            raise CharacterRegistryError('混合动捕须逐条指定四肢的 fk 或 ik 模式')
        self._spine_ik=spine_mode=='ik'
        self._ik_limbs=tuple(pair for pair in expected if limb_modes[pair]=='ik')


@dataclass(frozen=True,slots=True)
class MocapVariableScheduledPlan:
    full_fk: MocapVariableFullPlan
    spine_ik_frames: tuple[float,...]
    limb_ik_frames: tuple[tuple[str,str,tuple[float,...]],...]
    mode_keys: tuple[str,...]
    boundary: tuple
    replace_existing_modes: bool


class RetargetMocapVariableScheduledToCharacter(RetargetMocapVariableFullFkToCharacter):
    """Apply explicit FK/IK mode events over one mapped variable-body take."""
    LIMBS=(('arm','R'),('arm','L'),('leg','R'),('leg','L'))

    def __init__(self,host,*,spine_events,limb_events,replace_existing_modes=False):
        super().__init__(host)
        if type(replace_existing_modes) is not bool:
            raise CharacterRegistryError('已有模式覆盖选项必须是布尔值')
        self._replace_existing_modes=replace_existing_modes
        if not isinstance(limb_events,dict) or set(limb_events)!=set(self.LIMBS):
            raise CharacterRegistryError('事件动捕须逐条指定四肢模式事件')
        self._spine_events=self._events(spine_events)
        self._limb_events=tuple((limb,side,self._events(limb_events[(limb,side)]))
            for limb,side in self.LIMBS)

    @staticmethod
    def _events(events):
        if (not isinstance(events,(tuple,list)) or not events
                or any(not isinstance(row,(tuple,list)) or len(row)!=2
                       or type(row[0]) is not int or row[1] not in ('fk','ik')
                       for row in events)):
            raise CharacterRegistryError('模式事件须为非空的 (整数帧, fk/ik) 序列')
        result=tuple((int(frame),mode) for frame,mode in events)
        if any(left[0]>=right[0] or left[1]==right[1]
               for left,right in zip(result,result[1:])):
            raise CharacterRegistryError('模式事件帧须递增且模式必须变化')
        return result

    @staticmethod
    def _ik_frames(events,frames):
        if events[0][0]!=frames[0] or any(frame not in frames for frame,_ in events):
            raise CharacterRegistryError('模式事件首帧和后续事件须位于动捕采样帧')
        selected=[]
        event_index=0
        for frame in frames:
            if event_index+1<len(events) and frame>=events[event_index+1][0]:
                event_index+=1
            if events[event_index][1]=='ik':selected.append(frame)
        return tuple(selected)

    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,
                         reference_frame=None):
        full=super().plan_with_preset(source_root,preset,start_frame=start_frame,
            end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)
        frames=full.root.frames
        spine_frames=self._ik_frames(self._spine_events,frames)
        limb_frames=tuple((limb,side,self._ik_frames(events,frames))
            for limb,side,events in self._limb_events)
        keys={channel.key for channel in full.root.registration.channels}
        if spine_frames and not {'spine.spline.1.translateX',
                                'spine.spline.spineIkFk'}.issubset(keys):
            raise CharacterRegistryError('脊柱 IK 事件要求先启用 Spline 动画登记')
        for limb,side,selected in limb_frames:
            if selected:
                required={f'{limb}.fkLength.{side}.{index}' for index in (0,1)}
                required.update(f'{limb}.ikOrientation.{side}.{segment}.rotate{axis}'
                    for segment in ('upper','lower') for axis in 'XYZ')
                if not required.issubset(keys):
                    raise CharacterRegistryError('四肢 IK 事件要求先启用四肢动画登记')
        mode_keys=('spine.spline.spineIkFk',)+tuple(
            f'{limb}.settings.{limb}IkFk_{side}' for limb,side in self.LIMBS)
        boundary=self._host.preflight_mocap_mode_schedule(
            full.root.registration,mode_keys,frames,
            replace_existing_modes=self._replace_existing_modes)
        return MocapVariableScheduledPlan(full,spine_frames,limb_frames,mode_keys,
            boundary,self._replace_existing_modes)

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,
                          reference_frame=None):
        from adv_py.core.character_animation import CharacterAnimation,validate_character_animation
        from adv_py.core.fit_symmetry import FitBuildSide
        from .character_animation import verify_character_animation_write

        options=dict(start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
                     reference_frame=reference_frame)
        plan=self.plan_with_preset(source_root,preset,**options)
        host=self._host
        reg=plan.full_fk.root.registration
        frames=plan.full_fk.root.frames
        with host.transaction('Retarget variable-spine MoCap mode events'):
            if self.plan_with_preset(source_root,preset,**options)!=plan:
                raise CharacterRegistryError('事件动捕或角色状态在写入前发生变化')
            host.write_mocap_mode_base_keys(reg,plan.boundary,frames,
                replace_existing_modes=plan.replace_existing_modes)
            root_samples=host.write_mocap_root_control_keys(plan.full_fk.root)
            groups=tuple(host.write_mocap_fk_group_keys(group) for group in plan.full_fk.groups)
            if any(tuple(sample.frame for sample in group)!=frames
                   for group in (root_samples,*groups)):
                raise RuntimeError('事件动捕 FK 基础采样不完整')
            reference=host.sample_character_animation(reg,frames)
            unit=host.character_time_unit()
            conversions=[]
            selected=(('spine','',plan.spine_ik_frames),*plan.limb_ik_frames)
            for limb,side,ik_frames in selected:
                if not ik_frames:
                    continue
                keys=host.capture_character_key_state(reg)
                samples=(host.match_character_spine_samples(reg,ik_frames,'ik')
                    if limb=='spine' else host.match_character_limb_samples(
                        reg,ik_frames,limb,FitBuildSide(side),'ik',pose_tolerance=1e-3))
                if host.capture_character_key_state(reg)!=keys or host.character_time_unit()!=unit:
                    raise RuntimeError('事件模式匹配采样改变了原曲线或时间')
                conversion=CharacterAnimation(unit,samples)
                validate_character_animation(conversion,reg)
                host.write_character_animation(reg,samples)
                verify_character_animation_write(host,reg,conversion,keys)
                conversions.append((limb,side,conversion))
            host.set_mocap_mode_step_tangents(reg,plan.mode_keys,frames)
            actual=host.sample_character_animation(reg,frames)
            error=max(abs(a-b) for (_,before),(_,after) in zip(reference,actual)
                for (_,left),(_,right) in zip(before.body_frames,after.body_frames)
                for a,b in zip(left,right))
            if error>1e-3:
                raise RuntimeError('事件动捕改变了采样帧 Body 世界姿态：'+str(error))
        return root_samples,groups,tuple(conversions)
