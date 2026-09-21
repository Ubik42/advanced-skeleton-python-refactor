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


class MocapRootControlHost(Protocol):
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_mocap_source(self,root_name: str) -> MocapSourceSnapshot: ...
    def preflight_character_keyframe(self,registration: CharacterRegistration) -> None: ...
    def capture_character_key_state(self,registration: CharacterRegistration) -> tuple: ...
    def transaction(self,label: str): ...
    def write_mocap_root_control_keys(self,plan: MocapRootControlPlan) -> tuple[MocapRootControlSample,...]: ...
    def write_mocap_spine_control_keys(self,plan: MocapSpineControlPlan) -> tuple[MocapSpineControlSample,...]: ...


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
