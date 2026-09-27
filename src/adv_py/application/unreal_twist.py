"""ADV Unreal IK twist hierarchy switch."""
from __future__ import annotations

from typing import Protocol


class UnrealTwistHost(Protocol):
    def transaction(self, label: str): ...
    def preflight_twist(self, enable: bool) -> None: ...
    def set_twist_hierarchy(self, enable: bool) -> int: ...


class SetUnrealTwistHierarchy:
    def __init__(self, host: UnrealTwistHost):
        self.host = host

    def apply(self, enable: bool) -> int:
        if not isinstance(enable, bool):
            raise ValueError("Unreal Twist 开关须为布尔值")
        self.host.preflight_twist(enable)
        with self.host.transaction("切换 Unreal Twist 关节层级"):
            return self.host.set_twist_hierarchy(enable)
