from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_control_spaces import (
    SPACE_TOLERANCE, BodyControlSpacesPlan, BodyControlSpaceSpec, control_space_pose_error,
)

ControlSpacePose = tuple[tuple[str, tuple[float, ...]], ...]


class BodyControlSpaceHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_control_space_switch(self, spec: BodyControlSpaceSpec) -> str: ...
    def capture_control_space_pose(self, plan: BodyControlSpacesPlan) -> ControlSpacePose: ...
    def capture_control_space_mode(self, spec: BodyControlSpaceSpec) -> str: ...
    def switch_control_space(self, spec: BodyControlSpaceSpec, mode: str) -> None: ...


class SwitchBodyControlSpace:
    """Rebind one owned space group at the current time without writing animation."""

    def __init__(self, host: BodyControlSpaceHost):
        self._host = host

    def execute(self, plan: BodyControlSpacesPlan, key: str, mode: str) -> ControlSpacePose:
        spec = plan.space(key)
        spec.source(mode)
        previous = self._host.preflight_control_space_switch(spec)
        before = self._host.capture_control_space_pose(plan)
        control_space_pose_error(before, before)
        if previous == mode:
            return before
        with self._host.transaction("Switch control space " + key):
            if self._host.preflight_control_space_switch(spec) != previous:
                raise RuntimeError("控制空间在提交前变化")
            if control_space_pose_error(before, self._host.capture_control_space_pose(plan)) > SPACE_TOLERANCE:
                raise RuntimeError("控制空间姿态在提交前变化")
            self._host.switch_control_space(spec, mode)
            after = self._host.capture_control_space_pose(plan)
            if (self._host.capture_control_space_mode(spec) != mode
                    or control_space_pose_error(before, after) > SPACE_TOLERANCE):
                raise RuntimeError("控制空间切换改变世界姿态，已回滚")
        return after
