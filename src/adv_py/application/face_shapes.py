"""Build semantic expression and viseme controls from explicit target meshes."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.character_registry import CharacterRegistration, CharacterRegistryError
from adv_py.core.face_shapes import (
    FaceMeshSnapshot, FaceTarget, validate_face_targets,
)


@dataclass(frozen=True, slots=True)
class FaceBuildPlan:
    registration: CharacterRegistration
    neutral: FaceMeshSnapshot
    targets: tuple[tuple[FaceTarget, FaceMeshSnapshot], ...]
    head_joint: str
    control_path: str
    deformer_name: str


@dataclass(frozen=True, slots=True)
class FaceBinding:
    control_path: str
    deformer_name: str
    channels: tuple[tuple[str, str, str], ...]
    max_geometry_delta: float


@dataclass(frozen=True, slots=True)
class FaceBuildResult:
    plan: FaceBuildPlan
    binding: FaceBinding


class FaceBuildHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot: ...
    def face_names_available(self, control_path: str, deformer_name: str) -> bool: ...
    def build_face_shapes(self, plan: FaceBuildPlan) -> None: ...
    def capture_face_binding(self, plan: FaceBuildPlan) -> FaceBinding: ...


class BuildFaceBlendShapes:
    """One owned face control, one blendShape, and explicit user target meshes."""

    def __init__(self, host: FaceBuildHost):
        self._host = host

    def plan(self, neutral_mesh: str, targets: tuple[FaceTarget, ...], *,
             control_name: str = "AdvPy_FaceControls",
             deformer_name: str = "AdvPy_FaceBlendShape") -> FaceBuildPlan:
        import re

        if (not isinstance(targets, tuple)
                or any(not isinstance(target, FaceTarget) for target in targets)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", control_name)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", deformer_name)):
            raise CharacterRegistryError("面部构建名称或目标清单无效")
        registration = self._host.read_character_registration()
        heads = tuple(joint.path for joint in registration.body
                      if joint.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == "Head_M")
        if len(heads) != 1:
            raise CharacterRegistryError("面部构建要求唯一的 Head_M 绑定关节")
        neutral = self._host.capture_face_mesh(neutral_mesh)
        captured = tuple((target, self._host.capture_face_mesh(target.mesh))
                         for target in targets)
        validate_face_targets(neutral, captured)
        control_path = heads[0] + "|" + control_name
        if not self._host.face_names_available(control_path, deformer_name):
            raise CharacterRegistryError("面部控制或 BlendShape 名称已存在")
        return FaceBuildPlan(registration, neutral, captured, heads[0],
                             control_path, deformer_name)

    def apply(self, neutral_mesh: str, targets: tuple[FaceTarget, ...], **options) -> FaceBuildResult:
        plan = self.plan(neutral_mesh, targets, **options)
        with self._host.transaction("Build expression and viseme face rig"):
            if self.plan(neutral_mesh, targets, **options) != plan:
                raise CharacterRegistryError("面部目标或角色登记在构建前发生变化")
            self._host.build_face_shapes(plan)
            binding = self._host.capture_face_binding(plan)
            expected = tuple((target.name, target.kind.value,
                              f"{plan.deformer_name}.weight[{index}]")
                             for index, (target, _) in enumerate(plan.targets))
            if (binding.control_path != plan.control_path
                    or binding.deformer_name != plan.deformer_name
                    or binding.channels != expected
                    or binding.max_geometry_delta <= 1e-7):
                raise RuntimeError("面部控制、变形权重或实际网格形变复检失败")
        return FaceBuildResult(plan, binding)
