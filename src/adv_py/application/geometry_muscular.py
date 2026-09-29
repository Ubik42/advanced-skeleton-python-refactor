"""Maya-visible Muscular create/delete orchestration."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_muscular import MuscleBoneMatch, plan_muscle_bone_matches


class MuscularHost(Protocol):
    def preflight_muscular_create(self) -> None: ...
    def transaction(self, label: str): ...
    def import_muscular_template(self) -> None: ...
    def imported_bone_names(self) -> tuple[str, ...]: ...
    def skeleton_bone_names(self) -> set[str]: ...
    def match_muscle_bones(self, matches: tuple[MuscleBoneMatch, ...]) -> None: ...
    def fit_muscle_curves(self) -> int: ...
    def transfer_muscle_skin(self) -> int: ...
    def mirror_muscles(self) -> int: ...
    def finish_muscular(self) -> None: ...
    def capture_muscular(self, curve_count: int, mirror_count: int) -> bool: ...
    def muscular_exists(self) -> bool: ...
    def delete_muscular(self) -> None: ...


class CreateMuscular:
    def __init__(self, host: MuscularHost) -> None:
        self.host = host

    def execute(self) -> tuple[int, int]:
        self.host.preflight_muscular_create()
        with self.host.transaction("创建原版 Muscular 几何"):
            self.host.import_muscular_template()
            matches = plan_muscle_bone_matches(
                self.host.imported_bone_names(),
                self.host.skeleton_bone_names())
            self.host.match_muscle_bones(matches)
            curves = self.host.fit_muscle_curves()
            self.host.transfer_muscle_skin()
            mirrored = self.host.mirror_muscles()
            self.host.finish_muscular()
            if not self.host.capture_muscular(curves, mirrored):
                raise RuntimeError("Muscular 创建后曲线或镜像产物不完整")
        return curves, mirrored


class DeleteMuscular:
    def __init__(self, host: MuscularHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.muscular_exists():
            return
        with self.host.transaction("删除原版 Muscular 几何"):
            self.host.delete_muscular()
            if self.host.muscular_exists():
                raise RuntimeError("Muscular 删除后仍有生成物")
