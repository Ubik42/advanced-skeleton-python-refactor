"""Body game-engine switch: restrictions encoded by ADV 6.925's Body UI.

Root Motion and Game Engine Scaling are separate commands. The Preparation
switch does not request either command during the ordinary Body build.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BodyOperation(str, Enum):
    DELTA_MUSH = "delta_mush"
    DEFORM3 = "deform3"
    SQUASH_CONTROLLER = "squash_controller"
    SKIN_CONTROL = "skin_control"
    CLUSTER_CONTROL = "cluster_control"
    SOFT_MOD_CONTROL = "soft_mod_control"


_DISABLED_IN_GAME_ENGINE = frozenset((
    BodyOperation.DELTA_MUSH,
    BodyOperation.DEFORM3,
    BodyOperation.SQUASH_CONTROLLER,
    BodyOperation.CLUSTER_CONTROL,
    BodyOperation.SOFT_MOD_CONTROL,
))


@dataclass(frozen=True, slots=True)
class BodyGameEnginePolicy:
    enabled: bool

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("Body gameEngine 必须为布尔值")

    def allows(self, operation: BodyOperation) -> bool:
        if not isinstance(operation, BodyOperation):
            raise ValueError("未知 Body 操作")
        return not self.enabled or operation not in _DISABLED_IN_GAME_ENGINE

    def require(self, operation: BodyOperation) -> None:
        if not self.allows(operation):
            raise ValueError("Body Game Engine 模式下不可执行：" + operation.value)

    @property
    def disabled_operations(self) -> tuple[BodyOperation, ...]:
        return (tuple(operation for operation in BodyOperation
                      if operation in _DISABLED_IN_GAME_ENGINE)
                if self.enabled else ())
