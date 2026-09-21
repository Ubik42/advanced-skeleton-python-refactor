"""Transfer a calibrated MoCap root path onto registered character controls."""
from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from adv_py.core.character_animation import character_sample_frames
from adv_py.core.character_registry import CharacterRegistration,CharacterRegistryError
from adv_py.core.mocap_source import MocapSourceSnapshot,audit_mocap_source,summarize_mocap_source


@dataclass(frozen=True,slots=True)
class MocapRootControlPlan:
    registration: CharacterRegistration
    source: MocapSourceSnapshot
    frames: tuple[float,...]
    reference_frame: float
    character_key_state: tuple


@dataclass(frozen=True,slots=True)
class MocapRootControlSample:
    frame: float
    control_values: tuple[float,...]
    body_root_matrix: tuple[float,...]


@dataclass(frozen=True,slots=True)
class MocapSpineControlPlan:
    root: MocapRootControlPlan
    source_spine: str
    source_chest: str


@dataclass(frozen=True,slots=True)
class MocapSpineControlSample:
    frame: float
    control_values: tuple[float,...]
    body_matrices: tuple[tuple[float,...],tuple[float,...]]


@dataclass(frozen=True,slots=True)
class MocapLimbControlPlan:
    spine: MocapSpineControlPlan
    limb: str
    side: str
    source_joints: tuple[str,str,str]
    source_parents: tuple[str,str,str]
    target_joints: tuple[str,str,str]
    target_parents: tuple[str,str,str]
    controls: tuple[str,str,str]
    blend_plug: str


@dataclass(frozen=True,slots=True)
class MocapLimbControlSample:
    frame: float
    control_values: tuple[float,...]
    body_matrices: tuple[tuple[float,...],tuple[float,...],tuple[float,...]]


@dataclass(frozen=True,slots=True)
class MocapLimbSource:
    limb: str
    side: str
    upper: str
    middle: str
    end: str


@dataclass(frozen=True,slots=True)
class MocapFourLimbControlPlan:
    spine: MocapSpineControlPlan
    limbs: tuple[MocapLimbControlPlan,...]


@dataclass(frozen=True,slots=True)
class MocapUpperControlPlan:
    four_limbs: MocapFourLimbControlPlan
    source_joints: tuple[str,str,str,str]
    source_parents: tuple[str,str,str,str]
    target_joints: tuple[str,str,str,str]
    target_parents: tuple[str,str,str,str]
    controls: tuple[str,str,str,str]
    head_aim_plug: str | None


@dataclass(frozen=True,slots=True)
class MocapUpperControlSample:
    frame: float
    control_values: tuple[float,...]
    body_matrices: tuple[tuple[float,...],...]


class MocapRootControlHost(Protocol):
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_mocap_source(self,root_name: str) -> MocapSourceSnapshot: ...
    def preflight_character_keyframe(self,registration: CharacterRegistration) -> None: ...
    def capture_character_key_state(self,registration: CharacterRegistration) -> tuple: ...
    def transaction(self,label: str): ...
    def write_mocap_root_control_keys(self,plan: MocapRootControlPlan) -> tuple[MocapRootControlSample,...]: ...
    def write_mocap_spine_control_keys(self,plan: MocapSpineControlPlan) -> tuple[MocapSpineControlSample,...]: ...
    def write_mocap_limb_control_keys(self,plan: MocapLimbControlPlan) -> tuple[MocapLimbControlSample,...]: ...
    def write_mocap_upper_control_keys(self,plan: MocapUpperControlPlan) -> tuple[MocapUpperControlSample,...]: ...


class RetargetMocapRootToCharacter:
    """Write whole-body root motion as editable Global control curves."""
    def __init__(self,host: MocapRootControlHost):self._host=host

    def plan(self,source_root,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        if not isinstance(source_root,str) or not source_root.strip():
            raise CharacterRegistryError('动捕来源根关节必须明确指定')
        frames=character_sample_frames(start_frame,end_frame,sample_by)
        if reference_frame is not None and (not isinstance(reference_frame,(int,float))
                                            or isinstance(reference_frame,bool) or not isfinite(reference_frame)):
            raise CharacterRegistryError('动捕校准帧必须是有限数值')
        reference=float(frames[0] if reference_frame is None else reference_frame)
        if not frames[0]<=reference<=frames[-1]:
            raise CharacterRegistryError('动捕校准帧必须位于写入区间')
        registration=self._host.read_character_registration()
        self._host.preflight_character_keyframe(registration)
        source=self._host.capture_mocap_source(source_root)
        issues=audit_mocap_source(source)
        if issues:
            raise CharacterRegistryError('动捕来源无效：'+'；'.join(issue.message for issue in issues))
        summary=summarize_mocap_source(source)
        if frames[0]<summary.start_time or frames[-1]>summary.end_time:
            raise CharacterRegistryError('动捕写入范围超出来源关键帧')
        if any(source.root==joint.path or source.root.startswith(joint.path+'|') for joint in registration.body):
            raise CharacterRegistryError('动捕来源不能位于当前角色 Body 内')
        required={f'global.{name}{axis}' for name in ('translate','rotate') for axis in 'XYZ'}
        if not required.issubset({channel.key for channel in registration.channels}):
            raise CharacterRegistryError('角色缺少全局平移或旋转控制通道')
        return MocapRootControlPlan(registration,source,frames,reference,
                                    self._host.capture_character_key_state(registration))

    def apply(self,source_root,**options):
        plan=self.plan(source_root,**options)
        with self._host.transaction('Retarget MoCap root to character controls'):
            if (self._host.read_character_registration()!=plan.registration
                    or self._host.capture_mocap_source(source_root)!=plan.source
                    or self._host.capture_character_key_state(plan.registration)!=plan.character_key_state):
                raise CharacterRegistryError('动捕写入前来源或角色动画发生变化')
            samples=self._host.write_mocap_root_control_keys(plan)
            if tuple(sample.frame for sample in samples)!=plan.frames:
                raise RuntimeError('动捕控制器写入采样不完整')
        return samples


class RetargetMocapSpineToCharacter:
    """Calibrate root and two FK spine joints in a single character edit."""
    def __init__(self,host: MocapRootControlHost):self._host=host

    def plan(self,source_root,*,source_spine,source_chest,start_frame,end_frame,sample_by=1,reference_frame=None):
        if (not isinstance(source_spine,str) or not source_spine or not isinstance(source_chest,str)
                or not source_chest or source_spine==source_chest):
            raise CharacterRegistryError('动捕脊柱与胸部映射名必须分别明确指定')
        root=RetargetMocapRootToCharacter(self._host).plan(source_root,start_frame=start_frame,
            end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)
        registration=root.registration
        from adv_py.core.body_spine import BodySpinePlan
        if not isinstance(registration.spine,BodySpinePlan):
            raise CharacterRegistryError('当前动捕脊柱转移要求标准双段 Spine FK 角色')
        by_name={joint.name:joint for joint in root.source.joints}
        if (source_spine not in by_name or source_chest not in by_name
                or by_name[source_spine].joint_parent!=root.source.root
                or by_name[source_chest].joint_parent!=by_name[source_spine].path):
            raise CharacterRegistryError('动捕脊柱映射须为根→脊柱→胸部的直接关节链')
        control_paths=set(registration.spine.fk_controls[1:])
        writable={(channel.node,channel.attribute) for channel in registration.channels}
        if any((control,'rotate'+axis) not in writable for control in control_paths for axis in 'XYZ'):
            raise CharacterRegistryError('角色 FK 脊柱控制旋转通道未登记')
        return MocapSpineControlPlan(root,by_name[source_spine].path,by_name[source_chest].path)

    def apply(self,source_root,**options):
        plan=self.plan(source_root,**options)
        with self._host.transaction('Retarget MoCap root and spine to controls'):
            if self.plan(source_root,**options)!=plan:
                raise CharacterRegistryError('动捕或角色状态在脊柱写入前发生变化')
            root_samples=self._host.write_mocap_root_control_keys(plan.root)
            spine_samples=self._host.write_mocap_spine_control_keys(plan)
            if (tuple(sample.frame for sample in root_samples)!=plan.root.frames
                    or tuple(sample.frame for sample in spine_samples)!=plan.root.frames):
                raise RuntimeError('动捕脊柱控制器采样不完整')
        return root_samples,spine_samples


class RetargetMocapLimbToCharacter:
    """Transfer one FK arm or leg with root and standard spine in one edit."""
    def __init__(self,host: MocapRootControlHost):self._host=host

    def plan(self,source_root,*,source_spine,source_chest,limb,side,source_upper,
             source_middle,source_end,start_frame,end_frame,sample_by=1,reference_frame=None):
        if limb not in ('arm','leg') or side not in ('R','L'):
            raise CharacterRegistryError('动捕四肢须明确选择 arm/leg 与 R/L')
        spine=RetargetMocapSpineToCharacter(self._host).plan(source_root,source_spine=source_spine,
            source_chest=source_chest,start_frame=start_frame,end_frame=end_frame,
            sample_by=sample_by,reference_frame=reference_frame)
        registration=spine.root.registration
        names=(source_upper,source_middle,source_end)
        if any(not isinstance(name,str) or not name for name in names) or len(set(names))!=3:
            raise CharacterRegistryError('动捕四肢三个来源关节必须分别指定')
        source_by_name={joint.name:joint for joint in spine.root.source.joints}
        if any(name not in source_by_name for name in names):
            raise CharacterRegistryError('动捕四肢来源关节缺失')
        source=tuple(source_by_name[name] for name in names)
        if (source[0].joint_parent is None or source[1].joint_parent!=source[0].path
                or source[2].joint_parent!=source[1].path):
            raise CharacterRegistryError('动捕四肢映射须为直接父子关节链')
        parts=('Shoulder','Elbow','Wrist') if limb=='arm' else ('Hip','Knee','Ankle')
        target_by_name={joint.path.rsplit('|',1)[-1]:joint for joint in registration.body}
        target_names=tuple(part+'_'+side for part in parts)
        if any(name not in target_by_name for name in target_names):
            raise CharacterRegistryError('角色 Body 四肢链缺失')
        targets=tuple(target_by_name[name] for name in target_names)
        if (targets[0].parent is None or targets[1].parent!=targets[0].path
                or targets[2].parent!=targets[1].path):
            raise CharacterRegistryError('角色 Body 四肢父子链无效')
        by_key={channel.key:channel for channel in registration.channels}
        controls=[]
        for part in parts:
            group=tuple(by_key.get(f'{limb}.fk.{part}FK_{side}.rotate{axis}') for axis in 'XYZ')
            if any(channel is None for channel in group) or len({channel.node for channel in group})!=1:
                raise CharacterRegistryError('角色 FK 四肢控制旋转通道不完整')
            controls.append(group[0].node)
        blend=by_key.get(f'{limb}.settings.{limb}IkFk_{side}')
        if blend is None:raise CharacterRegistryError('角色四肢 FK/IK 模式通道缺失')
        return MocapLimbControlPlan(spine,limb,side,tuple(joint.path for joint in source),
            tuple(joint.joint_parent for joint in source),tuple(joint.path for joint in targets),
            tuple(joint.parent for joint in targets),tuple(controls),blend.node+'.'+blend.attribute)

    def apply(self,source_root,**options):
        plan=self.plan(source_root,**options)
        with self._host.transaction('Retarget MoCap root spine and '+plan.limb+' to controls'):
            if self.plan(source_root,**options)!=plan:
                raise CharacterRegistryError('动捕或角色状态在四肢写入前发生变化')
            root_samples=self._host.write_mocap_root_control_keys(plan.spine.root)
            spine_samples=self._host.write_mocap_spine_control_keys(plan.spine)
            limb_samples=self._host.write_mocap_limb_control_keys(plan)
            if any(tuple(sample.frame for sample in group)!=plan.spine.root.frames
                   for group in (root_samples,spine_samples,limb_samples)):
                raise RuntimeError('动捕四肢控制器采样不完整')
        return root_samples,spine_samples,limb_samples


class RetargetMocapFourLimbsToCharacter:
    """Apply root, FK spine, and both FK arms and legs atomically."""
    def __init__(self,host: MocapRootControlHost):self._host=host

    def _preset_options(self,source_root,preset):
        from adv_py.core.mocap_preset import MocapMappingPreset
        from .mocap_mapping import InspectMocapBodyMapping
        if not isinstance(preset,MocapMappingPreset):
            raise CharacterRegistryError('控制 Rig 动捕映射需要版本化预设')
        registration=self._host.read_character_registration()
        if len(registration.body)!=preset.expected_body_joint_count:
            raise CharacterRegistryError('动捕预设的 Body 关节数与角色不一致')
        target_root=registration.body_root.rsplit('|',1)[-1]
        required={target_root,'Spine1_M','Chest_M'}|{
            part+'_'+side for part in ('Shoulder','Elbow','Wrist','Hip','Knee','Ankle')
            for side in ('R','L')}
        by_target={row.target_name:row for row in preset.mappings}
        if set(by_target)!=required or len(preset.mappings)!=len(required):
            raise CharacterRegistryError('控制 Rig 预设须准确覆盖根、双段脊柱与左右四肢 15 个关节')
        if (not by_target[target_root].transfer_translation
                or any(not row.transfer_rotation for row in preset.mappings)
                or any(row.transfer_translation for name,row in by_target.items() if name!=target_root)):
            raise CharacterRegistryError('控制 Rig 预设要求根部平移与全关节旋转，其他关节不得传递平移')
        InspectMocapBodyMapping(self._host).execute(source_root,preset.mappings,
            body_root_name=registration.body_root,source_container=registration.container,
            expected_body_joint_count=preset.expected_body_joint_count).require_valid()
        limbs=tuple(MocapLimbSource(limb,side,*(by_target[part+'_'+side].source_name for part in parts))
            for limb,parts in (('arm',('Shoulder','Elbow','Wrist')),
                               ('leg',('Hip','Knee','Ankle'))) for side in ('R','L'))
        return by_target['Spine1_M'].source_name,by_target['Chest_M'].source_name,limbs

    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        spine,chest,limbs=self._preset_options(source_root,preset)
        return self.plan(source_root,source_spine=spine,source_chest=chest,source_limbs=limbs,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        spine,chest,limbs=self._preset_options(source_root,preset)
        return self.apply(source_root,source_spine=spine,source_chest=chest,source_limbs=limbs,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)

    def plan(self,source_root,*,source_spine,source_chest,source_limbs,start_frame,end_frame,
             sample_by=1,reference_frame=None):
        if (not isinstance(source_limbs,(tuple,list)) or len(source_limbs)!=4
                or any(not isinstance(row,MocapLimbSource) for row in source_limbs)
                or {(row.limb,row.side) for row in source_limbs}!={
                    ('arm','R'),('arm','L'),('leg','R'),('leg','L')}):
            raise CharacterRegistryError('整段动捕须明确映射左右手臂与左右腿')
        service=RetargetMocapLimbToCharacter(self._host)
        limbs=tuple(service.plan(source_root,source_spine=source_spine,source_chest=source_chest,
            limb=row.limb,side=row.side,source_upper=row.upper,source_middle=row.middle,
            source_end=row.end,start_frame=start_frame,end_frame=end_frame,
            sample_by=sample_by,reference_frame=reference_frame) for row in source_limbs)
        if any(row.spine!=limbs[0].spine for row in limbs[1:]):
            raise CharacterRegistryError('四肢映射的来源或角色登记不一致')
        all_source=tuple(path for limb in limbs for path in limb.source_joints)
        if len(set(all_source))!=len(all_source):
            raise CharacterRegistryError('动捕四肢来源关节不得复用')
        return MocapFourLimbControlPlan(limbs[0].spine,limbs)

    def apply(self,source_root,**options):
        plan=self.plan(source_root,**options)
        with self._host.transaction('Retarget MoCap root spine and four limbs'):
            if self.plan(source_root,**options)!=plan:
                raise CharacterRegistryError('动捕或角色状态在全身写入前发生变化')
            root_samples=self._host.write_mocap_root_control_keys(plan.spine.root)
            spine_samples=self._host.write_mocap_spine_control_keys(plan.spine)
            limb_samples=tuple(self._host.write_mocap_limb_control_keys(limb) for limb in plan.limbs)
            if any(tuple(sample.frame for sample in group)!=plan.spine.root.frames
                   for group in (root_samples,spine_samples,*limb_samples)):
                raise RuntimeError('动捕四肢采样不完整')
        return root_samples,spine_samples,limb_samples


class RetargetMocapUpperAndFourLimbsToCharacter:
    """Add neck, head, and scapula FK to the four-limb retarget transaction."""
    def __init__(self,host: MocapRootControlHost):self._host=host

    def _preset_options(self,source_root,preset):
        from adv_py.core.mocap_preset import MocapMappingPreset
        from .mocap_mapping import InspectMocapBodyMapping
        if not isinstance(preset,MocapMappingPreset):
            raise CharacterRegistryError('上半身动捕映射需要版本化预设')
        registration=self._host.read_character_registration()
        if len(registration.body)!=preset.expected_body_joint_count:
            raise CharacterRegistryError('动捕预设的 Body 关节数与角色不一致')
        target_root=registration.body_root.rsplit('|',1)[-1]
        required={target_root,'Spine1_M','Chest_M','Neck_M','Head_M','Scapula_R','Scapula_L'}|{
            part+'_'+side for part in ('Shoulder','Elbow','Wrist','Hip','Knee','Ankle')
            for side in ('R','L')}
        by_target={row.target_name:row for row in preset.mappings}
        if set(by_target)!=required or len(preset.mappings)!=len(required):
            raise CharacterRegistryError('上半身控制预设须准确覆盖 19 个目标关节')
        if (not by_target[target_root].transfer_translation
                or any(not row.transfer_rotation for row in preset.mappings)
                or any(row.transfer_translation for name,row in by_target.items() if name!=target_root)):
            raise CharacterRegistryError('上半身控制预设要求根部平移与全关节旋转，其他关节不得平移')
        InspectMocapBodyMapping(self._host).execute(source_root,preset.mappings,
            body_root_name=registration.body_root,source_container=registration.container,
            expected_body_joint_count=preset.expected_body_joint_count).require_valid()
        limbs=tuple(MocapLimbSource(limb,side,*(by_target[part+'_'+side].source_name for part in parts))
            for limb,parts in (('arm',('Shoulder','Elbow','Wrist')),
                               ('leg',('Hip','Knee','Ankle'))) for side in ('R','L'))
        return dict(source_spine=by_target['Spine1_M'].source_name,
            source_chest=by_target['Chest_M'].source_name,
            source_neck=by_target['Neck_M'].source_name,
            source_head=by_target['Head_M'].source_name,
            source_scapula_right=by_target['Scapula_R'].source_name,
            source_scapula_left=by_target['Scapula_L'].source_name,source_limbs=limbs)

    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        return self.plan(source_root,**self._preset_options(source_root,preset),
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        return self.apply(source_root,**self._preset_options(source_root,preset),
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)

    def plan(self,source_root,*,source_spine,source_chest,source_neck,source_head,
             source_scapula_right,source_scapula_left,source_limbs,start_frame,end_frame,
             sample_by=1,reference_frame=None):
        four=RetargetMocapFourLimbsToCharacter(self._host).plan(source_root,
            source_spine=source_spine,source_chest=source_chest,source_limbs=source_limbs,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
            reference_frame=reference_frame)
        names=(source_neck,source_head,source_scapula_right,source_scapula_left)
        if any(not isinstance(name,str) or not name for name in names) or len(set(names))!=4:
            raise CharacterRegistryError('动捕头颈和左右肩胛来源须分别指定')
        source_by_name={joint.name:joint for joint in four.spine.root.source.joints}
        if any(name not in source_by_name for name in names):
            raise CharacterRegistryError('动捕头颈或肩胛来源关节缺失')
        source=tuple(source_by_name[name] for name in names)
        chest=four.spine.source_chest
        if (source[0].joint_parent!=chest or source[1].joint_parent!=source[0].path
                or source[2].joint_parent!=chest or source[3].joint_parent!=chest):
            raise CharacterRegistryError('动捕头颈与肩胛须位于胸部对应的直接关节链')
        scapula_by_side={'R':source[2].path,'L':source[3].path}
        if any(limb.source_parents[0]!=scapula_by_side[limb.side]
               for limb in four.limbs if limb.limb=='arm'):
            raise CharacterRegistryError('动捕手臂起点须位于对应的肩胛来源关节下')
        reg=four.spine.root.registration
        targets=('Neck_M','Head_M','Scapula_R','Scapula_L')
        target_by_name={joint.path.rsplit('|',1)[-1]:joint for joint in reg.body}
        if any(name not in target_by_name for name in targets):
            raise CharacterRegistryError('角色 Body 头颈或肩胛关节缺失')
        target=tuple(target_by_name[name] for name in targets)
        chest_target=target_by_name['Chest_M'].path
        if (target[0].parent!=chest_target or target[1].parent!=target[0].path
                or target[2].parent!=chest_target or target[3].parent!=chest_target):
            raise CharacterRegistryError('角色 Body 头颈或肩胛父子关系无效')
        channels={channel.key:channel for channel in reg.channels}
        controls=[]
        for name in targets:
            group=tuple(channels.get(f'torso.Torso{name}FK.rotate{axis}') for axis in 'XYZ')
            if any(channel is None for channel in group) or len({channel.node for channel in group})!=1:
                raise CharacterRegistryError('角色上半身 FK 控制旋转通道不完整')
            controls.append(group[0].node)
        aim=channels.get('head.aim.headAim')
        return MocapUpperControlPlan(four,tuple(joint.path for joint in source),
            tuple(joint.joint_parent for joint in source),tuple(joint.path for joint in target),
            tuple(joint.parent for joint in target),tuple(controls),
            None if aim is None else aim.node+'.'+aim.attribute)

    def apply(self,source_root,**options):
        plan=self.plan(source_root,**options)
        with self._host.transaction('Retarget MoCap root spine upper body and four limbs'):
            if self.plan(source_root,**options)!=plan:
                raise CharacterRegistryError('动捕或角色状态在上半身写入前发生变化')
            root_samples=self._host.write_mocap_root_control_keys(plan.four_limbs.spine.root)
            spine_samples=self._host.write_mocap_spine_control_keys(plan.four_limbs.spine)
            upper_samples=self._host.write_mocap_upper_control_keys(plan)
            limb_samples=tuple(self._host.write_mocap_limb_control_keys(limb)
                               for limb in plan.four_limbs.limbs)
            if any(tuple(sample.frame for sample in group)!=plan.four_limbs.spine.root.frames
                   for group in (root_samples,spine_samples,upper_samples,*limb_samples)):
                raise RuntimeError('动捕上半身或四肢采样不完整')
        return root_samples,spine_samples,upper_samples,limb_samples
