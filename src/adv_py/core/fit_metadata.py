from __future__ import annotations

from dataclasses import dataclass


class FitJointValidationError(ValueError):
    """Raised when Fit joint input cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class FitJointMetadata:
    """Portable values that affect how one fit joint is interpreted."""

    joint: str
    twist_joints: int | None = None
    bendy_controls: int | None = None
    inbetween_joints: int | None = None
    untwister: bool = False
    no_mirror: bool = False
    no_mirror_left: bool = False
    child_of_part: int | None = None
    global_weight: float | None = None
    global_translate: bool = False
    world_orient_up: str | None = None
    world_orient_forward: str | None = None
    ik_local_mode: str | None = None


@dataclass(frozen=True, slots=True)
class FitJointIssue:
    joint: str
    code: str
    message: str


def audit_fit_joint(metadata: FitJointMetadata) -> tuple[FitJointIssue, ...]:
    issues: list[FitJointIssue] = []

    for field_name, value, label in (
        ("twist_joints", metadata.twist_joints, "Twist 关节数量"),
        ("bendy_controls", metadata.bendy_controls, "Bendy 控制器数量"),
        ("inbetween_joints", metadata.inbetween_joints, "Inbetween 关节数量"),
    ):
        if value is not None and value < 0:
            issues.append(
                FitJointIssue(
                    metadata.joint,
                    f"negative_{field_name}",
                    f"{label}不能小于 0",
                )
            )

    if metadata.twist_joints is not None and metadata.inbetween_joints is not None:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "mixed_subdivision_modes",
                "同一 Fit joint 不能同时启用 Twist 与 Inbetween",
            )
        )
    if metadata.bendy_controls is not None and metadata.twist_joints is None:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "bendy_without_twist",
                "Bendy 控制器设置需要 Twist 模式",
            )
        )
    if metadata.untwister and metadata.inbetween_joints is None:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "untwister_without_inbetween",
                "UnTwister 设置需要 Inbetween 模式",
            )
        )
    if metadata.no_mirror_left and not metadata.no_mirror:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "left_rule_without_no_mirror",
                "noMirrorLeft 需要同时启用 noMirror",
            )
        )
    if metadata.child_of_part is not None and not 1 <= metadata.child_of_part <= 10:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "child_of_part_out_of_range",
                "childOfPart 必须位于 1 到 10",
            )
        )
    if metadata.global_weight is not None and not 0.0 <= metadata.global_weight <= 10.0:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "global_weight_out_of_range",
                "global 权重必须位于 0 到 10",
            )
        )
    return tuple(issues)
