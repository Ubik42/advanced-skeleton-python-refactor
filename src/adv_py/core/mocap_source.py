from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


MOCAP_TRANSFORM_ATTRIBUTES = (
    "translateX",
    "translateY",
    "translateZ",
    "rotateX",
    "rotateY",
    "rotateZ",
)


class MocapSourceValidationError(ValueError):
    """Raised when a captured MoCap skeleton is not safe to match."""


class MocapDriverKind(str, Enum):
    ANIMATION_CURVE = "animation_curve"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class MocapJointSnapshot:
    path: str
    name: str
    namespace: str
    joint_parent: str | None


@dataclass(frozen=True, slots=True)
class MocapChannelSnapshot:
    joint_path: str
    attribute: str
    driver_kind: MocapDriverKind
    driver_path: str
    key_times: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class MocapSourceSnapshot:
    root: str
    joints: tuple[MocapJointSnapshot, ...]
    channels: tuple[MocapChannelSnapshot, ...]


@dataclass(frozen=True, slots=True)
class MocapSourceIssue:
    code: str
    message: str
    nodes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MocapSourceSummary:
    namespace: str
    joint_count: int
    animated_joint_count: int
    channel_count: int
    start_time: float
    end_time: float
    portable_joint_names: tuple[str, ...]


def audit_mocap_source(
    snapshot: MocapSourceSnapshot,
) -> tuple[MocapSourceIssue, ...]:
    issues: list[MocapSourceIssue] = []
    joints_by_path: dict[str, MocapJointSnapshot] = {}
    names: dict[str, list[str]] = {}

    if not snapshot.joints:
        return (MocapSourceIssue("no_joints", "MoCap 来源骨架没有关节"),)

    for joint in snapshot.joints:
        if not joint.path:
            issues.append(MocapSourceIssue("empty_path", "MoCap 关节路径不能为空"))
            continue
        if joint.path in joints_by_path:
            issues.append(MocapSourceIssue(
                "duplicate_path", "MoCap 骨架包含重复关节路径", (joint.path,)
            ))
            continue
        joints_by_path[joint.path] = joint
        if not joint.name or ":" in joint.name or "|" in joint.name:
            issues.append(MocapSourceIssue(
                "invalid_name", "MoCap 可移植关节名无效", (joint.path,)
            ))
        names.setdefault(joint.name, []).append(joint.path)

    root = joints_by_path.get(snapshot.root)
    if root is None:
        issues.append(MocapSourceIssue(
            "missing_root", "MoCap 显式根关节不在骨架快照中", (snapshot.root,)
        ))
    elif root.joint_parent is not None:
        issues.append(MocapSourceIssue(
            "root_has_joint_parent", "MoCap 显式根关节仍有 joint 父级", (root.path,)
        ))

    namespaces = {joint.namespace for joint in joints_by_path.values()}
    if len(namespaces) != 1:
        issues.append(MocapSourceIssue(
            "mixed_namespaces",
            "MoCap 来源骨架必须归属同一个 namespace",
            tuple(sorted(joints_by_path)),
        ))

    for joint in joints_by_path.values():
        if joint.path == snapshot.root:
            continue
        if joint.joint_parent not in joints_by_path:
            issues.append(MocapSourceIssue(
                "broken_joint_parent",
                "MoCap 关节之间存在非 joint 层或父链缺失",
                (joint.path,) if joint.joint_parent is None else (
                    joint.path,
                    joint.joint_parent,
                ),
            ))

    cycle_nodes: set[str] = set()
    for start in joints_by_path:
        seen: set[str] = set()
        current = start
        while current in joints_by_path and current != snapshot.root:
            if current in seen:
                cycle_nodes.update(seen)
                break
            seen.add(current)
            parent = joints_by_path[current].joint_parent
            if parent is None:
                break
            current = parent
    if cycle_nodes:
        issues.append(MocapSourceIssue(
            "parent_cycle",
            "MoCap 关节父链包含循环",
            tuple(sorted(cycle_nodes)),
        ))

    for name, paths in names.items():
        if name and len(paths) > 1:
            issues.append(MocapSourceIssue(
                "duplicate_portable_name",
                f"MoCap 可移植关节名不唯一：{name}",
                tuple(paths),
            ))

    seen_channels: set[tuple[str, str]] = set()
    for channel in snapshot.channels:
        key = (channel.joint_path, channel.attribute)
        if key in seen_channels:
            issues.append(MocapSourceIssue(
                "duplicate_channel", "MoCap 动画通道重复", (channel.joint_path,)
            ))
        seen_channels.add(key)
        if channel.joint_path not in joints_by_path:
            issues.append(MocapSourceIssue(
                "unknown_channel_joint",
                "MoCap 动画通道引用了骨架外关节",
                (channel.joint_path,),
            ))
        if channel.attribute not in MOCAP_TRANSFORM_ATTRIBUTES:
            issues.append(MocapSourceIssue(
                "unsupported_channel",
                f"MoCap 动画通道不受支持：{channel.attribute}",
                (channel.joint_path,),
            ))
        if channel.driver_kind is not MocapDriverKind.ANIMATION_CURVE:
            issues.append(MocapSourceIssue(
                "unsupported_driver",
                "MoCap 来源通道不是直接 animation curve",
                (channel.driver_path, channel.joint_path),
            ))
        if (
            channel.driver_kind is MocapDriverKind.ANIMATION_CURVE
            and not channel.key_times
        ):
            issues.append(MocapSourceIssue(
                "empty_animation_curve",
                "MoCap animation curve 没有关键帧",
                (channel.driver_path,),
            ))
        elif channel.key_times and (
            any(not math.isfinite(value) for value in channel.key_times)
            or tuple(sorted(set(channel.key_times))) != channel.key_times
        ):
            issues.append(MocapSourceIssue(
                "invalid_key_times",
                "MoCap 关键帧时间必须有限、唯一并升序",
                (channel.driver_path,),
            ))

    if not snapshot.channels:
        issues.append(MocapSourceIssue(
            "no_animation", "MoCap 来源骨架没有直接关键帧动画"
        ))
    return tuple(issues)


def summarize_mocap_source(snapshot: MocapSourceSnapshot) -> MocapSourceSummary:
    issues = audit_mocap_source(snapshot)
    if issues:
        raise MocapSourceValidationError(
            "MoCap 来源检查失败：" + "；".join(issue.message for issue in issues)
        )
    key_times = tuple(
        time
        for channel in snapshot.channels
        for time in channel.key_times
    )
    namespace = next(
        joint.namespace for joint in snapshot.joints if joint.path == snapshot.root
    )
    return MocapSourceSummary(
        namespace=namespace,
        joint_count=len(snapshot.joints),
        animated_joint_count=len({channel.joint_path for channel in snapshot.channels}),
        channel_count=len(snapshot.channels),
        start_time=min(key_times),
        end_time=max(key_times),
        portable_joint_names=tuple(joint.name for joint in snapshot.joints),
    )
