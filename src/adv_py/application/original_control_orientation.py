"""Application boundary for the literal ADV Control Orient operations."""
from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.original_control_orientation import OriginalControlOrientOptions


class OriginalControlOrientationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager: ...
    def confirm_original_control_build_pose(self) -> int: ...
    def set_original_control_orientation(self, controls, options) -> tuple[str, ...]: ...
    def detach_original_control_orientation(self) -> tuple[str, ...]: ...
    def attach_original_control_orientation(self, *, mirror: bool = True) -> int: ...


class SetOriginalControlOrientations:
    def __init__(self, host: OriginalControlOrientationHost):
        self._host = host

    def apply(self, controls: tuple[str, ...], options: OriginalControlOrientOptions):
        with self._host.transaction('Set original control orientations'):
            if not self._host.confirm_original_control_build_pose():
                return ()
            return self._host.set_original_control_orientation(controls, options)


class DetachOriginalControlOrientations:
    def __init__(self, host: OriginalControlOrientationHost):
        self._host = host

    def apply(self):
        with self._host.transaction('Detach original control orientations'):
            if not self._host.confirm_original_control_build_pose():
                return ()
            return self._host.detach_original_control_orientation()


class AttachOriginalControlOrientations:
    def __init__(self, host: OriginalControlOrientationHost):
        self._host = host

    def apply(self, *, mirror=True):
        with self._host.transaction('Attach original control orientations'):
            return self._host.attach_original_control_orientation(mirror=mirror)
