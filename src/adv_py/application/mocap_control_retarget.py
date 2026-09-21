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


@dataclass(frozen=True,slots=True)
class MocapDistalControlPlan:
    upper: MocapUpperControlPlan
    source_joints: tuple[str,...]
    source_parents: tuple[str,...]
    target_joints: tuple[str,...]
    target_parents: tuple[str,...]
    controls: tuple[str,...]
    mode_plugs: tuple[str,...]


@dataclass(frozen=True,slots=True)
class MocapDistalControlSample:
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
    def write_mocap_distal_control_keys(self,plan: MocapDistalControlPlan) -> tuple[MocapDistalControlSample,...]: ...
    def sample_character_animation(self,registration: CharacterRegistration,frames: tuple[float,...]) -> tuple: ...
    def character_time_unit(self) -> str: ...
    def match_character_limb_samples(self,registration: CharacterRegistration,frames: tuple[float,...],
                                      limb: str,side,mode: str,pose_tolerance: float=1e-4) -> tuple: ...
    def match_character_spine_samples(self,registration: CharacterRegistration,
                                      frames: tuple[float,...],mode: str) -> tuple: ...
    def write_character_animation(self,registration: CharacterRegistration,samples: tuple) -> None: ...


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


class RetargetMocapFullFkToCharacter:
    """Retarget the standard FK body, toes, and optional five-digit hands."""
    DIGITS=('Thumb','Index','Middle','Ring','Pinky')
    def __init__(self,host: MocapRootControlHost):self._host=host

    def _preset_options(self,source_root,preset):
        from adv_py.core.mocap_preset import MocapMappingPreset
        from .mocap_mapping import InspectMocapBodyMapping
        if not isinstance(preset,MocapMappingPreset):
            raise CharacterRegistryError('全身 FK 动捕映射需要版本化预设')
        reg=self._host.read_character_registration()
        if len(reg.body) not in (30,70) or len(reg.body)!=preset.expected_body_joint_count:
            raise CharacterRegistryError('全身 FK 动捕需要 30 或 70 关节角色及匹配的预设')
        root=reg.body_root.rsplit('|',1)[-1]
        required={root,'Spine1_M','Chest_M','Neck_M','Head_M','Scapula_R','Scapula_L'}|{
            part+'_'+side for part in ('Shoulder','Elbow','Wrist','Hip','Knee','Ankle','Toes')
            for side in ('R','L')}
        if len(reg.body)==70:
            required|={f'{digit}{segment}_{side}' for digit in self.DIGITS
                       for segment in (1,2,3) for side in ('R','L')}
        by_target={row.target_name:row for row in preset.mappings}
        if set(by_target)!=required or len(preset.mappings)!=len(required):
            raise CharacterRegistryError('全身 FK 动捕预设的目标关节集合不完整或包含多余项')
        if (not by_target[root].transfer_translation
                or any(not row.transfer_rotation for row in preset.mappings)
                or any(row.transfer_translation for name,row in by_target.items() if name!=root)):
            raise CharacterRegistryError('全身 FK 动捕预设仅允许根部平移，所有关节须传递旋转')
        InspectMocapBodyMapping(self._host).execute(source_root,preset.mappings,
            body_root_name=reg.body_root,source_container=reg.container,
            expected_body_joint_count=preset.expected_body_joint_count).require_valid()
        limbs=tuple(MocapLimbSource(limb,side,*(by_target[part+'_'+side].source_name for part in parts))
            for limb,parts in (('arm',('Shoulder','Elbow','Wrist')),
                               ('leg',('Hip','Knee','Ankle'))) for side in ('R','L'))
        upper=dict(source_spine=by_target['Spine1_M'].source_name,
            source_chest=by_target['Chest_M'].source_name,
            source_neck=by_target['Neck_M'].source_name,
            source_head=by_target['Head_M'].source_name,
            source_scapula_right=by_target['Scapula_R'].source_name,
            source_scapula_left=by_target['Scapula_L'].source_name,source_limbs=limbs)
        distal={name:by_target[name].source_name for name in required if name.startswith('Toes_')
                or (len(reg.body)==70 and any(name.startswith(digit) for digit in self.DIGITS))}
        return upper,distal

    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        upper,distal=self._preset_options(source_root,preset)
        return self.plan(source_root,**upper,source_distal=distal,start_frame=start_frame,
            end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        upper,distal=self._preset_options(source_root,preset)
        return self.apply(source_root,**upper,source_distal=distal,start_frame=start_frame,
            end_frame=end_frame,sample_by=sample_by,reference_frame=reference_frame)

    def plan(self,source_root,*,source_distal,source_spine,source_chest,source_neck,
             source_head,source_scapula_right,source_scapula_left,source_limbs,
             start_frame,end_frame,sample_by=1,reference_frame=None):
        upper=RetargetMocapUpperAndFourLimbsToCharacter(self._host).plan(source_root,
            source_spine=source_spine,source_chest=source_chest,source_neck=source_neck,
            source_head=source_head,source_scapula_right=source_scapula_right,
            source_scapula_left=source_scapula_left,source_limbs=source_limbs,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
            reference_frame=reference_frame)
        reg=upper.four_limbs.spine.root.registration
        if len(reg.body) not in (30,70):
            raise CharacterRegistryError('全身 FK 动捕仅支持标准 30 / 70 关节角色')
        names=[f'Toes_{side}' for side in ('R','L')]
        if len(reg.body)==70:
            names.extend(f'{digit}{segment}_{side}' for side in ('R','L')
                for digit in self.DIGITS for segment in (1,2,3))
        if (not isinstance(source_distal,dict) or set(source_distal)!=set(names)
                or any(not isinstance(value,str) or not value for value in source_distal.values())
                or len(set(source_distal.values()))!=len(source_distal)):
            raise CharacterRegistryError('末端动捕来源须准确覆盖脚趾及角色已有的五指控制关节')
        source_by_name={joint.name:joint for joint in upper.four_limbs.spine.root.source.joints}
        target_by_name={joint.path.rsplit('|',1)[-1]:joint for joint in reg.body}
        channels={channel.key:channel for channel in reg.channels}
        if any(name not in source_by_name for name in source_distal.values()):
            raise CharacterRegistryError('末端动捕来源关节缺失')
        used={upper.four_limbs.spine.root.source.root,upper.four_limbs.spine.source_spine,
              upper.four_limbs.spine.source_chest,*upper.source_joints}
        used.update(path for limb in upper.four_limbs.limbs for path in limb.source_joints)
        if any(source_by_name[name].path in used for name in source_distal.values()):
            raise CharacterRegistryError('末端动捕来源不得复用躯干或四肢关节')
        sources=[];targets=[];controls=[]
        for name in names:
            source=source_by_name.get(source_distal[name]);target=target_by_name.get(name)
            if source is None or target is None:
                raise CharacterRegistryError('末端动捕来源或 Body 关节缺失：'+name)
            part,side=name.rsplit('_',1)
            if part=='Toes':
                parent_name='Ankle_'+side
                channel_prefix=f'leg.fk.ToesFK_{side}'
            else:
                segment=int(part[-1]);digit=part[:-1]
                parent_name=(f'Wrist_{side}' if segment==1 else f'{digit}{segment-1}_{side}')
                channel_prefix=f'hand.fk.{part}FK_{side}'
            expected_source_parent=(next(limb.source_joints[2] for limb in upper.four_limbs.limbs
                if limb.limb==('leg' if part=='Toes' else 'arm') and limb.side==side)
                if part=='Toes' or part.endswith('1') else source_by_name[source_distal[parent_name]].path)
            if (source.joint_parent!=expected_source_parent
                    or target.parent!=target_by_name[parent_name].path):
                raise CharacterRegistryError('末端动捕父子链与角色不一致：'+name)
            group=tuple(channels.get(channel_prefix+'.rotate'+axis) for axis in 'XYZ')
            if any(row is None for row in group) or len({row.node for row in group})!=1:
                raise CharacterRegistryError('末端 FK 控制旋转通道不完整：'+name)
            sources.append(source);targets.append(target);controls.append(group[0].node)
        modes=tuple(next(limb.blend_plug for limb in upper.four_limbs.limbs
            if limb.limb=='leg' and limb.side==side) for side in ('R','L'))
        return MocapDistalControlPlan(upper,tuple(row.path for row in sources),
            tuple(row.joint_parent for row in sources),tuple(row.path for row in targets),
            tuple(row.parent for row in targets),tuple(controls),modes)

    def apply(self,source_root,**options):
        plan=self.plan(source_root,**options)
        with self._host.transaction('Retarget MoCap full FK body'):
            if self.plan(source_root,**options)!=plan:
                raise CharacterRegistryError('动捕或角色状态在全身 FK 写入前发生变化')
            four=plan.upper.four_limbs
            root=self._host.write_mocap_root_control_keys(four.spine.root)
            spine=self._host.write_mocap_spine_control_keys(four.spine)
            upper=self._host.write_mocap_upper_control_keys(plan.upper)
            limbs=tuple(self._host.write_mocap_limb_control_keys(limb) for limb in four.limbs)
            distal=self._host.write_mocap_distal_control_keys(plan)
            if any(tuple(sample.frame for sample in group)!=four.spine.root.frames
                   for group in (root,spine,upper,*limbs,distal)):
                raise RuntimeError('动捕全身 FK 采样不完整')
        return root,spine,upper,limbs,distal


class RetargetMocapFullLimbIkToCharacter:
    """Retarget full FK motion, then match all four limbs to IK in one edit."""
    _spine_ik=False
    def __init__(self,host: MocapRootControlHost):self._host=host

    def _require_limb_animation(self,plan):
        reg=plan.upper.four_limbs.spine.root.registration
        required={f'{limb}.fkLength.{side}.{index}' for limb in ('arm','leg')
                  for side in ('R','L') for index in (0,1)}
        required.update(f'{limb}.ikOrientation.{side}.{segment}.rotate{axis}'
            for limb in ('arm','leg') for side in ('R','L')
            for segment in ('upper','lower') for axis in 'XYZ')
        if not required.issubset({channel.key for channel in reg.channels}):
            raise CharacterRegistryError('四肢 IK 动捕须先启用完整四肢动画通道登记')

    def plan_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        plan=RetargetMocapFullFkToCharacter(self._host).plan_with_preset(source_root,preset,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
            reference_frame=reference_frame)
        self._require_limb_animation(plan)
        return plan

    def apply_with_preset(self,source_root,preset,*,start_frame,end_frame,sample_by=1,reference_frame=None):
        full=RetargetMocapFullFkToCharacter(self._host)
        upper_options,distal=full._preset_options(source_root,preset)
        return self.apply(source_root,**upper_options,source_distal=distal,
            start_frame=start_frame,end_frame=end_frame,sample_by=sample_by,
            reference_frame=reference_frame)

    def plan(self,source_root,**options):
        plan=RetargetMocapFullFkToCharacter(self._host).plan(source_root,**options)
        self._require_limb_animation(plan)
        return plan

    def apply(self,source_root,**options):
        from adv_py.core.character_animation import CharacterAnimation,validate_character_animation
        from adv_py.core.fit_symmetry import FitBuildSide
        from .character_animation import verify_character_animation_write
        plan=self.plan(source_root,**options)
        root=plan.upper.four_limbs.spine.root
        reg=root.registration
        host=self._host
        label=('Retarget MoCap spine and four limb IK' if self._spine_ik
               else 'Retarget MoCap full body and four IK limbs')
        with host.transaction(label):
            if self.plan(source_root,**options)!=plan:
                raise CharacterRegistryError('动捕或角色状态在四肢 IK 写入前发生变化')
            four=plan.upper.four_limbs
            root_samples=host.write_mocap_root_control_keys(root)
            spine_samples=host.write_mocap_spine_control_keys(four.spine)
            upper_samples=host.write_mocap_upper_control_keys(plan.upper)
            limb_samples=tuple(host.write_mocap_limb_control_keys(limb) for limb in four.limbs)
            distal_samples=host.write_mocap_distal_control_keys(plan)
            if any(tuple(sample.frame for sample in group)!=root.frames
                   for group in (root_samples,spine_samples,upper_samples,*limb_samples,distal_samples)):
                raise RuntimeError('动捕 FK 基础采样不完整')
            reference=host.sample_character_animation(reg,root.frames)
            unit=host.character_time_unit()
            spine_conversion=None
            if self._spine_ik:
                keys=host.capture_character_key_state(reg)
                samples=host.match_character_spine_samples(reg,root.frames,'ik')
                if host.capture_character_key_state(reg)!=keys or host.character_time_unit()!=unit:
                    raise RuntimeError('动捕脊柱 IK 匹配采样改变了原曲线或时间')
                spine_conversion=CharacterAnimation(unit,samples)
                validate_character_animation(spine_conversion,reg)
                host.write_character_animation(reg,samples)
                verify_character_animation_write(host,reg,spine_conversion,keys)
            conversions=[]
            for limb in ('arm','leg'):
                for side in ('R','L'):
                    keys=host.capture_character_key_state(reg)
                    samples=host.match_character_limb_samples(reg,root.frames,limb,
                        FitBuildSide(side),'ik',pose_tolerance=1e-3)
                    if host.capture_character_key_state(reg)!=keys or host.character_time_unit()!=unit:
                        raise RuntimeError('动捕四肢匹配采样改变了原曲线或时间')
                    animation=CharacterAnimation(unit,samples)
                    validate_character_animation(animation,reg)
                    host.write_character_animation(reg,samples)
                    verify_character_animation_write(host,reg,animation,keys)
                    conversions.append(animation)
            actual=host.sample_character_animation(reg,root.frames)
            error=max(abs(a-b) for (_,before),(_,after) in zip(reference,actual)
                for (_,left),(_,right) in zip(before.body_frames,after.body_frames)
                for a,b in zip(left,right))
            if error>1e-3:
                raise RuntimeError('动捕四肢 IK 转换改变了采样帧 Body 世界姿态：'+str(error))
        result=(root_samples,spine_samples,upper_samples,limb_samples,distal_samples,tuple(conversions))
        return (*result,spine_conversion) if self._spine_ik else result


class RetargetMocapFullIkToCharacter(RetargetMocapFullLimbIkToCharacter):
    """Retarget a standard two-segment spine and four limbs to IK controls."""
    _spine_ik=True
