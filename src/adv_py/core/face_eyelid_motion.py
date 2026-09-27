"""Dimensioned motion coefficients for the current eyelid build graph."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class EyeLidMotionPlan:
    eye_radius_cm: float
    yaw_depth_full_angle_deg: float = 18.5
    yaw_depth_radius_fraction: float = .14
    yaw_edge_start_angle_deg: float = 18.5
    yaw_edge_full_angle_deg: float = 26.5
    yaw_edge_upper_radius_fraction: float = .49
    yaw_edge_lower_radius_fraction: float = .35
    yaw_blink_eye_back_radius_fraction: float = .07
    stationary_mid_gaze_full_angle_deg: float = 30.
    stationary_mid_gaze_depth_radius_fraction: float = .027
    stationary_lower_main_seal_radius_fraction: float = .0054

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field) for field in
                       self.__dataclass_fields__)
        if (any(not isinstance(value, (int, float)) or isinstance(value, bool)
                or not isfinite(value) for value in values)
                or self.eye_radius_cm <= 0
                or self.yaw_depth_full_angle_deg <= 0
                or self.yaw_edge_start_angle_deg < 0
                or self.yaw_edge_full_angle_deg
                <= self.yaw_edge_start_angle_deg
                or self.stationary_mid_gaze_full_angle_deg <= 0
                or any(value < 0 for value in values[2:])):
            raise ValueError("眼睑运动计划需要正眼球半径和有效角度／比例")

    @property
    def yaw_depth_slope_cm_per_degree(self) -> float:
        return (self.eye_radius_cm * self.yaw_depth_radius_fraction
                / self.yaw_depth_full_angle_deg)

    @property
    def yaw_depth_limit_cm(self) -> float:
        return self.eye_radius_cm * self.yaw_depth_radius_fraction

    @property
    def yaw_edge_span_deg(self) -> float:
        return self.yaw_edge_full_angle_deg - self.yaw_edge_start_angle_deg

    def yaw_edge_slope_cm_per_degree(self, arc: str) -> float:
        if arc not in ("upper", "lower"):
            raise ValueError("眼睑弧必须是 upper 或 lower")
        fraction = (self.yaw_edge_upper_radius_fraction if arc == "upper"
                    else self.yaw_edge_lower_radius_fraction)
        return self.eye_radius_cm * fraction / self.yaw_edge_span_deg

    @property
    def yaw_blink_eye_back_slope_cm_per_degree(self) -> float:
        return (-self.eye_radius_cm
                * self.yaw_blink_eye_back_radius_fraction
                / self.yaw_edge_span_deg)

    @property
    def yaw_blink_eye_back_limit_cm(self) -> float:
        return self.eye_radius_cm * self.yaw_blink_eye_back_radius_fraction

    @property
    def stationary_mid_gaze_slope_cm_per_degree(self) -> float:
        return (self.eye_radius_cm
                * self.stationary_mid_gaze_depth_radius_fraction
                / self.stationary_mid_gaze_full_angle_deg)

    def stationary_outer_offset_cm(self, arc: str,
                                   side_sign: int) -> tuple[float, float]:
        if arc not in ("upper", "lower") or side_sign not in (-1, 1):
            raise ValueError("固定眼孔偏移需要上下弧及左右符号")
        horizontal, vertical = ((.029, .077) if arc == "upper"
                                else (.058, -.024))
        return (self.eye_radius_cm * horizontal * side_sign,
                self.eye_radius_cm * vertical)

    @property
    def stationary_lower_main_seal_cm(self) -> float:
        return self.eye_radius_cm * self.stationary_lower_main_seal_radius_fraction
