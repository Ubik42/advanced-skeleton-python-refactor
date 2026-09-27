"""Coordinate equal-topology original eyelid Skin transfer."""
from __future__ import annotations

from array import array
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, Sequence

from adv_py.core.dense_skin_transfer import DenseSkinWeights
from adv_py.core.face_source_skin_mapping import (
    FaceSourceSkinMapping, face_influence_base,
    plan_face_source_skin_mapping, transfer_face_source_skin_weights,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


@dataclass(frozen=True, slots=True)
class FaceSourceSkinCapture:
    source_mesh: str
    target_mesh: str
    target_skin: str
    source_influences: tuple[str, ...]
    source_values: Sequence[float]
    source_blend: tuple[float, ...]
    source_skinning_method: int
    before: DenseSkinWeights
    simpler_eyelid: bool
    maximum_rest_position_error_cm: float
    selected: tuple[str, ...]


class FaceSourceSkinHost(Protocol):
    def capture_face_source_skin(self, source_mesh: str) -> FaceSourceSkinCapture: ...
    def preflight_face_source_auxiliaries(
        self, capture: FaceSourceSkinCapture,
        mapping: FaceSourceSkinMapping,
    ) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_face_source_auxiliary(
        self, side: str, source_joint: str, target_skin: str,
    ) -> None: ...
    def capture_dense_skin(self, skin_name: str) -> DenseSkinWeights: ...
    def apply_dense_skin(self, data: DenseSkinWeights) -> None: ...
    def apply_skin_blend_weights(self, skin_name: str, values: array) -> None: ...
    def set_face_source_skinning_method(self, skin_name: str) -> None: ...
    def restore_face_source_selection(self, selected: tuple[str, ...]) -> None: ...


class TransferOriginalEyeLidSkin:
    def __init__(self, host: FaceSourceSkinHost) -> None:
        self._host = host

    def execute(self, source_mesh: str) -> dict:
        capture = self._host.capture_face_source_skin(source_mesh)
        try:
            mapping = plan_face_source_skin_mapping(
                capture.source_influences, capture.before.influence_names,
                simpler_eyelid=capture.simpler_eyelid)
        except ValueError as error:
            raise FitSkeletonValidationError(str(error)) from error
        self._host.preflight_face_source_auxiliaries(capture, mapping)
        auxiliary = {side: index for side, index in mapping.auxiliary_sources}
        with self._host.transaction("迁移原版眼睑 Skin"):
            try:
                if not capture.simpler_eyelid:
                    for side, index in mapping.auxiliary_sources:
                        self._host.create_face_source_auxiliary(
                            side, capture.source_influences[index],
                            capture.target_skin)
                target = self._host.capture_dense_skin(capture.target_skin)
                target_by_base = {face_influence_base(name): name
                                  for name in target.influence_names}
                if len(target_by_base) != len(target.influence_names):
                    raise FitSkeletonValidationError(
                        "目标 Skin 影响关节名称不唯一")
                source_map = list(mapping.segment_targets)
                for side, index in mapping.auxiliary_sources:
                    name = target_by_base.get("lowerLidOuterJoint_" + side)
                    if name is None:
                        raise FitSkeletonValidationError(
                            "目标眼下外围影响关节缺失")
                    source_map.append((index, name))
                try:
                    transferred = transfer_face_source_skin_weights(
                        capture.source_values,
                        len(capture.source_influences),
                        capture.before, target, tuple(source_map))
                except ValueError as error:
                    raise FitSkeletonValidationError(str(error)) from error
                self._host.apply_dense_skin(transferred)
                if capture.source_skinning_method == 0:
                    blend = array("d", [0.] * capture.before.vertex_count)
                elif capture.source_skinning_method == 1:
                    blend = array("d", [1.] * capture.before.vertex_count)
                else:
                    blend = array("d", capture.source_blend)
                self._host.apply_skin_blend_weights(capture.target_skin, blend)
                self._host.set_face_source_skinning_method(capture.target_skin)
            finally:
                self._host.restore_face_source_selection(capture.selected)
        return {
            "source_mesh": capture.source_mesh,
            "target_mesh": capture.target_mesh,
            "vertex_count": capture.before.vertex_count,
            "mapped_segment_influences": len(mapping.segment_targets),
            "approximated_segments": mapping.approximated_segments,
            "auxiliary_joints": tuple("lowerLidOuterJoint_" + side
                                      for side in sorted(auxiliary)),
            "maximum_rest_position_error_cm": round(
                capture.maximum_rest_position_error_cm, 8),
        }
