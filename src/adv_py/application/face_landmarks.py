"""Generate an auditable face target mesh from sparse vertex landmarks."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
from typing import Protocol

from adv_py.core.character_registry import CharacterRegistration, CharacterRegistryError
from adv_py.core.face_landmarks import FaceLandmark, deform_face_landmarks
from adv_py.core.face_shapes import FaceMeshSnapshot, FaceTarget


@dataclass(frozen=True, slots=True)
class FaceTargetGenerationPlan:
    registration: CharacterRegistration
    neutral: FaceMeshSnapshot
    target: FaceTarget
    landmarks: tuple[FaceLandmark, ...]
    points: tuple[tuple[float, float, float], ...]
    provenance: str


class FaceTargetGenerationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_face_mesh(self, path: str) -> FaceMeshSnapshot: ...
    def face_target_path_available(self, path: str) -> bool: ...
    def create_face_target(self, plan: FaceTargetGenerationPlan) -> None: ...
    def read_face_target_provenance(self, path: str) -> str: ...


class GenerateFaceTarget:
    def __init__(self, host: FaceTargetGenerationHost):
        self._host = host

    def plan(self, neutral_mesh: str, target: FaceTarget,
             landmarks: tuple[FaceLandmark, ...]) -> FaceTargetGenerationPlan:
        if (not isinstance(target, FaceTarget)
                or target.mesh != "|" + target.mesh.lstrip("|")
                or "|" in target.mesh[1:]
                or neutral_mesh == target.mesh):
            raise CharacterRegistryError("生成目标须位于角色命名空间根部")
        registration = self._host.read_character_registration()
        neutral = self._host.capture_face_mesh(neutral_mesh)
        if not self._host.face_target_path_available(target.mesh):
            raise CharacterRegistryError("面部目标路径已存在：" + target.mesh)
        points = deform_face_landmarks(neutral, landmarks)
        provenance = json.dumps({
            "version": 1,
            "neutral_path": neutral.path,
            "neutral_topology": neutral.topology_digest,
            "neutral_positions": neutral.position_digest,
            "channel": target.name,
            "kind": target.kind.value,
            "landmarks": [[item.vertex, list(item.displacement), item.radius]
                          for item in landmarks],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return FaceTargetGenerationPlan(registration, neutral, target,
                                        landmarks, points, provenance)

    def apply(self, neutral_mesh: str, target: FaceTarget,
              landmarks: tuple[FaceLandmark, ...]) -> FaceTargetGenerationPlan:
        plan = self.plan(neutral_mesh, target, landmarks)
        with self._host.transaction("Generate face target from landmarks"):
            if self.plan(neutral_mesh, target, landmarks) != plan:
                raise CharacterRegistryError("面部标记或中性网格在写入前发生变化")
            self._host.create_face_target(plan)
            self.audit(plan)
        return plan

    def audit(self, plan: FaceTargetGenerationPlan) -> FaceMeshSnapshot:
        """Verify a generated asset after creation, scene reopen, or rig rebuild."""
        result = self._host.capture_face_mesh(plan.target.mesh)
        if (result.topology_digest != plan.neutral.topology_digest
                or result.vertex_count != plan.neutral.vertex_count
                or any(abs(a - b) > 1e-6
                       for actual, expected in zip(result.points, plan.points)
                       for a, b in zip(actual, expected))
                or self._host.read_face_target_provenance(plan.target.mesh)
                   != plan.provenance):
            raise RuntimeError("生成面部目标的拓扑、顶点或来源记录复检失败")
        return result
