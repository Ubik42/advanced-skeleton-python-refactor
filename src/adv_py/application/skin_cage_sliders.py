"""Create and remove SkinCage sliders as complete scene operations."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.skin_cage_sliders import SkinCageSlider, plan_skin_cage_sliders


class SliderHost(Protocol):
    def capture_slider_rows(self) -> tuple[tuple[str, str, str, int, str], ...]: ...
    def preflight_sliders(self, plan: tuple[SkinCageSlider, ...],
                          *, creating: bool, include_controller: bool) -> None: ...
    def ensure_partial_joints(self, plan: tuple[SkinCageSlider, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create_slider(self, spec: SkinCageSlider,
                      *, include_controller: bool) -> bool: ...
    def delete_slider(self, spec: SkinCageSlider) -> None: ...
    def finish_slider_delete(self) -> None: ...
    def slider_delete_time_scope(self): ...
    def slider_sampling_scope(self): ...
    def capture_sliders(self, spec: SkinCageSlider,
                        *, present: bool) -> bool: ...


class CreateSkinCageSliders:
    def __init__(self, host: SliderHost) -> None:
        self.host = host

    def execute(self, *, include_controller: bool = False) -> int:
        plan = plan_skin_cage_sliders(self.host.capture_slider_rows())
        self.host.preflight_sliders(
            plan, creating=True, include_controller=include_controller)
        with self.host.transaction("创建 SkinCage Sliders"):
            created = []
            with self.host.slider_sampling_scope():
                for spec in plan:
                    if self.host.create_slider(spec, include_controller=include_controller) is not False:
                        created.append(spec)
            for spec in created:
                if not self.host.capture_sliders(spec, present=True):
                    raise RuntimeError("SkinCage Sliders 创建后状态不完整：" + spec.profile)
        return len(created)



class DeleteSkinCageSliders:
    def __init__(self, host: SliderHost) -> None:
        self.host = host

    def execute(self) -> int:
        plan = plan_skin_cage_sliders(self.host.capture_slider_rows())
        self.host.preflight_sliders(
            plan, creating=False, include_controller=False)
        with self.host.transaction("删除 SkinCage Sliders"):
            with self.host.slider_delete_time_scope(), self.host.slider_sampling_scope():
                for spec in plan:
                    self.host.delete_slider(spec)
            self.host.finish_slider_delete()
            for spec in plan:
                if not self.host.capture_sliders(spec, present=False):
                    raise RuntimeError("SkinCage Sliders 删除后仍有残留："
                                       + spec.profile)
        return len(plan)
