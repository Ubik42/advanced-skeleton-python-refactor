from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from typing import Protocol

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.character_pose import (
    CharacterPose, POSE_TOLERANCE, validate_character_pose, character_pose_error,
    encode_character_pose, decode_character_pose,
)


class CharacterPoseHost(Protocol):
    def transaction(self,label: str) -> AbstractContextManager[None]: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def preflight_character_pose(self,registration: CharacterRegistration) -> None: ...
    def capture_character_pose(self,registration: CharacterRegistration) -> CharacterPose: ...
    def write_character_pose(self,registration: CharacterRegistration,pose: CharacterPose) -> None: ...


@dataclass(frozen=True)
class CharacterPoseApplyPlan:
    registration: CharacterRegistration
    before: CharacterPose
    target: CharacterPose


class CaptureBodyCharacterPose:
    def __init__(self,host: CharacterPoseHost): self._host=host

    def execute(self):
        registration=self._host.read_character_registration()
        self._host.preflight_character_pose(registration)
        pose=self._host.capture_character_pose(registration)
        validate_character_pose(pose,registration)
        return pose


class ApplyBodyCharacterPose:
    def __init__(self,host: CharacterPoseHost): self._host=host

    def plan(self,pose):
        pose=decode_character_pose(encode_character_pose(pose))
        registration=self._host.read_character_registration()
        validate_character_pose(pose,registration)
        self._host.preflight_character_pose(registration)
        before=self._host.capture_character_pose(registration)
        validate_character_pose(before,registration)
        return CharacterPoseApplyPlan(registration,before,pose)

    def apply(self,pose):
        plan=self.plan(pose)
        if plan.before==plan.target:
            return plan.before
        with self._host.transaction("Apply complete static character pose"):
            if self._host.read_character_registration()!=plan.registration:
                raise RuntimeError("角色登记在姿态提交前变化")
            self._host.preflight_character_pose(plan.registration)
            if self._host.capture_character_pose(plan.registration)!=plan.before:
                raise RuntimeError("角色姿态在提交前变化")
            self._host.write_character_pose(plan.registration,plan.target)
            self._host.read_character_registration()
            result=self._host.capture_character_pose(plan.registration)
            validate_character_pose(result,plan.registration)
            if character_pose_error(plan.target,result)>POSE_TOLERANCE:
                raise RuntimeError("全身姿态复检不一致，已回滚")
        return result


def save_character_pose(pose,destination):
    """Atomically publish a new file; never replace an existing destination."""
    target=Path(destination).expanduser().absolute()
    text=encode_character_pose(pose)
    if target.exists(): raise FileExistsError(target)
    if not target.parent.is_dir(): raise FileNotFoundError(target.parent)
    fd,temporary=tempfile.mkstemp(prefix=".character-pose-",suffix=".tmp",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as stream:
            stream.write(text+"\n");stream.flush();os.fsync(stream.fileno())
        if decode_character_pose(Path(temporary).read_text(encoding="utf-8"))!=pose:
            raise RuntimeError("姿态临时文件复检失败")
        # Same-directory hard-link publication is atomic and fails if a racer
        # created the destination. An existence check plus replace could overwrite it.
        os.link(temporary,target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def load_character_pose(source):
    path=Path(source).expanduser()
    if path.stat().st_size>2_000_000: raise ValueError("姿态文件过大")
    return decode_character_pose(path.read_text(encoding="utf-8"))
