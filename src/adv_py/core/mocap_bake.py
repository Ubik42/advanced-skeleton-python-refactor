from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .mocap_connection import MocapBodyConnectionPlan, MocapTargetPose, mocap_target_poses_match
from .mocap_mapping import MocapMappingValidationError


@dataclass(frozen=True, slots=True)
class MocapBodyBakePlan:
    connection: MocapBodyConnectionPlan
    frames: tuple[int, ...]

    @property
    def channels(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (spec.target_path, attribute)
            for spec in self.connection.constraints
            for attribute in spec.target_attributes
        )


@dataclass(frozen=True, slots=True)
class MocapBodySample:
    frame: int
    values: tuple[float, ...]
    poses: tuple[MocapTargetPose, ...]


def plan_mocap_body_bake(
    connection: MocapBodyConnectionPlan,
    start_frame: int,
    end_frame: int,
    sample_by: int = 1,
) -> MocapBodyBakePlan:
    if any(type(value) is not int for value in (start_frame, end_frame, sample_by)):
        raise MocapMappingValidationError("MoCap bake 范围和步长必须是整数")
    if start_frame > end_frame or sample_by < 1:
        raise MocapMappingValidationError("MoCap bake 范围或步长无效")
    if (end_frame - start_frame) % sample_by:
        raise MocapMappingValidationError("MoCap bake 步长必须准确落在结束帧")
    if start_frame < connection.mapping.start_time or end_frame > connection.mapping.end_time:
        raise MocapMappingValidationError("MoCap bake 范围必须位于来源动画范围内")
    if (end_frame - start_frame) // sample_by + 1 > 100000:
        raise MocapMappingValidationError("MoCap bake 单次采样不得超过 100000 帧")
    return MocapBodyBakePlan(connection, tuple(range(start_frame, end_frame + 1, sample_by)))


def validate_mocap_samples(plan: MocapBodyBakePlan, samples: tuple[MocapBodySample, ...]) -> None:
    paths = tuple(spec.target_path for spec in plan.connection.constraints)
    if tuple(sample.frame for sample in samples) != plan.frames:
        raise MocapMappingValidationError("MoCap bake 采样帧与计划不一致")
    for sample in samples:
        if (
            len(sample.values) != len(plan.channels)
            or not all(isfinite(value) for value in sample.values)
            or tuple(pose.target_path for pose in sample.poses) != paths
            or any(len(pose.world_matrix) != 16 or not all(isfinite(v) for v in pose.world_matrix)
                   for pose in sample.poses)
        ):
            raise MocapMappingValidationError("MoCap bake 采样通道、矩阵或数值无效")


def verify_mocap_bake_samples(
    plan: MocapBodyBakePlan,
    expected: tuple[MocapBodySample, ...],
    actual: tuple[MocapBodySample, ...],
) -> None:
    validate_mocap_samples(plan, expected)
    validate_mocap_samples(plan, actual)
    for left, right in zip(expected, actual):
        if (any(abs(a - b) > 1e-5 for a, b in zip(left.values, right.values))
                or not mocap_target_poses_match(left.poses, right.poses)):
            raise MocapMappingValidationError(f"MoCap bake 第 {left.frame} 帧读回复检失败")
