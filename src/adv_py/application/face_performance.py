"""Apply a portable sampled face performance to one registered character."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.character_registry import CharacterRegistration, CharacterRegistryError
from adv_py.core.face_performance import FacePerformance


@dataclass(frozen=True, slots=True)
class FacePerformancePlan:
    registration: CharacterRegistration
    control_path: str
    performance: FacePerformance
    curve_state: tuple


class FacePerformanceHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def read_face_manifest(self, control_path: str) -> tuple: ...
    def preflight_face_performance(self, control_path: str,
                                   performance: FacePerformance) -> None: ...
    def capture_face_curve_state(self, control_path: str,
                                 performance: FacePerformance) -> tuple: ...
    def write_face_performance(self, plan: FacePerformancePlan) -> None: ...
    def sample_face_performance(self, control_path: str,
                                performance: FacePerformance) -> tuple: ...
    def verify_face_curve_boundary(self, plan: FacePerformancePlan) -> None: ...


class ApplyFacePerformance:
    def __init__(self, host: FacePerformanceHost):
        self._host = host

    def plan(self, control_path: str,
             performance: FacePerformance) -> FacePerformancePlan:
        if not isinstance(performance, FacePerformance):
            raise CharacterRegistryError("面部动画必须是已校验的 FacePerformance")
        registration = self._host.read_character_registration()
        heads = tuple(joint.path for joint in registration.body
                      if joint.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == "Head_M")
        if len(heads) != 1 or not control_path.startswith(heads[0] + "|"):
            raise CharacterRegistryError("面部控制不属于当前角色头部")
        manifest = self._host.read_face_manifest(control_path)
        selected = set(performance.channels)
        if tuple(channel for channel in manifest if channel in selected) != performance.channels:
            raise CharacterRegistryError("面部动画通道不属于场景清单或顺序不一致")
        self._host.preflight_face_performance(control_path, performance)
        return FacePerformancePlan(registration, control_path, performance,
            self._host.capture_face_curve_state(control_path, performance))

    def apply(self, control_path: str,
              performance: FacePerformance) -> FacePerformancePlan:
        plan = self.plan(control_path, performance)
        with self._host.transaction("Apply sampled expression and viseme animation"):
            if self.plan(control_path, performance) != plan:
                raise CharacterRegistryError("面部动画或角色输入在写入前发生变化")
            self._host.write_face_performance(plan)
            actual = self._host.sample_face_performance(control_path, performance)
            if (tuple(frame for frame, _ in actual) != performance.frames
                    or any(len(values) != len(expected) or
                           any(abs(value - reference) > 1e-8
                               for value, reference in zip(values, expected))
                           for (_, values), (_, expected) in zip(actual, performance.samples))):
                raise RuntimeError("面部动画采样值回读不一致")
            self._host.verify_face_curve_boundary(plan)
        return plan
