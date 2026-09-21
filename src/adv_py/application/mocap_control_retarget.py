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


class MocapRootControlHost(Protocol):
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_mocap_source(self,root_name: str) -> MocapSourceSnapshot: ...
    def preflight_character_keyframe(self,registration: CharacterRegistration) -> None: ...
    def capture_character_key_state(self,registration: CharacterRegistration) -> tuple: ...
    def transaction(self,label: str): ...
    def write_mocap_root_control_keys(self,plan: MocapRootControlPlan) -> tuple[MocapRootControlSample,...]: ...


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
