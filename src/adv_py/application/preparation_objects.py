"""Record and reselect model inputs for the rig preparation panel."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.preparation_objects import (
    PreparationObjectRole, validate_preparation_objects,
)


class PreparationObjectsHost(Protocol):
    def selected_meshes(self) -> tuple[str, ...]: ...
    def read_objects(self, role: PreparationObjectRole) -> tuple[str, ...]: ...
    def write_objects(self, role: PreparationObjectRole,
                      objects: tuple[str, ...]) -> None: ...
    def select_objects(self, objects: tuple[str, ...]) -> None: ...


class RecordPreparationObjects:
    def __init__(self, host: PreparationObjectsHost):
        self.host = host

    def execute(self, role: PreparationObjectRole) -> tuple[str, ...]:
        objects = validate_preparation_objects(role, self.host.selected_meshes())
        self.host.write_objects(role, objects)
        if self.host.read_objects(role) != objects:
            raise RuntimeError("准备模型记录写后读回不一致")
        return objects


class ReselectPreparationObjects:
    def __init__(self, host: PreparationObjectsHost):
        self.host = host

    def execute(self, role: PreparationObjectRole) -> tuple[str, ...]:
        objects = validate_preparation_objects(role, self.host.read_objects(role))
        self.host.select_objects(objects)
        return objects
