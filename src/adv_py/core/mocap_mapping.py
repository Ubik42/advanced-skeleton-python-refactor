from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import (
    BodySkeletonProvenance,
    BodySkeletonSnapshot,
    audit_body_provenance,
)
from .mocap_source import (
    MocapSourceSnapshot,
    audit_mocap_source,
    summarize_mocap_source,
)


class MocapMappingValidationError(ValueError):
    """Raised when an explicit MoCap-to-Body mapping is unsafe."""


@dataclass(frozen=True, slots=True)
class MocapJointMapping:
    source_name: str
    target_name: str
    transfer_translation: bool = False
    transfer_rotation: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_name, str)
            or not self.source_name
            or ":" in self.source_name
            or "|" in self.source_name
        ):
            raise MocapMappingValidationError("MoCap 来源映射名必须是可移植短名")
        if (
            not isinstance(self.target_name, str)
            or not self.target_name
            or ":" in self.target_name
            or "|" in self.target_name
        ):
            raise MocapMappingValidationError("Body 目标映射名必须是可移植短名")
        if (
            not isinstance(self.transfer_translation, bool)
            or not isinstance(self.transfer_rotation, bool)
            or not (self.transfer_translation or self.transfer_rotation)
        ):
            raise MocapMappingValidationError("映射至少要传递平移或旋转")


@dataclass(frozen=True, slots=True)
class MocapMappingIssue:
    code: str
    message: str
    names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedMocapJointMapping:
    source_name: str
    source_path: str
    target_name: str
    target_path: str
    transfer_translation: bool
    transfer_rotation: bool
    animated_attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MocapBodyMappingPlan:
    source_root: str
    target_root: str
    source_namespace: str
    start_time: float
    end_time: float
    entries: tuple[ResolvedMocapJointMapping, ...]


def audit_mocap_body_mapping(
    source: MocapSourceSnapshot,
    body: BodySkeletonSnapshot,
    mappings: tuple[MocapJointMapping, ...],
    expected_body_provenance: BodySkeletonProvenance,
) -> tuple[MocapMappingIssue, ...]:
    issues = [
        MocapMappingIssue(
            f"source_{issue.code}",
            issue.message,
            issue.nodes,
        )
        for issue in audit_mocap_source(source)
    ]
    issues.extend(
        MocapMappingIssue(
            f"body_{issue.code}",
            issue.message,
            () if issue.joint is None else (issue.joint,),
        )
        for issue in audit_body_provenance(
            expected_body_provenance,
            body.provenance,
        )
    )

    source_by_name = _unique_paths_by_name(
        ((joint.name, joint.path) for joint in source.joints),
        "duplicate_source_name",
        "MoCap 来源名不唯一",
        issues,
    )
    target_by_name = _unique_paths_by_name(
        ((joint.name, joint.path) for joint in body.joints),
        "duplicate_target_name",
        "Body 目标名不唯一",
        issues,
    )
    if len(body.joints) != expected_body_provenance.body_joint_count:
        issues.append(MocapMappingIssue(
            "body_joint_count",
            "Body 实际关节数量与 owned provenance 不一致",
            (str(len(body.joints)), str(expected_body_provenance.body_joint_count)),
        ))
    if not mappings:
        issues.append(MocapMappingIssue(
            "empty_mapping", "MoCap→Body 映射不能为空"
        ))
        return tuple(issues)

    source_specs: dict[str, MocapJointMapping] = {}
    target_specs: dict[str, MocapJointMapping] = {}
    for mapping in mappings:
        if mapping.source_name in source_specs:
            issues.append(MocapMappingIssue(
                "duplicate_source_mapping",
                f"MoCap 来源被重复映射：{mapping.source_name}",
                (mapping.source_name,),
            ))
        else:
            source_specs[mapping.source_name] = mapping
        if mapping.target_name in target_specs:
            issues.append(MocapMappingIssue(
                "duplicate_target_mapping",
                f"Body 目标被重复映射：{mapping.target_name}",
                (mapping.target_name,),
            ))
        else:
            target_specs[mapping.target_name] = mapping
        if mapping.source_name not in source_by_name:
            issues.append(MocapMappingIssue(
                "missing_source",
                f"MoCap 来源关节不存在：{mapping.source_name}",
                (mapping.source_name,),
            ))
        if mapping.target_name not in target_by_name:
            issues.append(MocapMappingIssue(
                "missing_target",
                f"Body 目标关节不存在：{mapping.target_name}",
                (mapping.target_name,),
            ))

    source_root = next(
        (joint for joint in source.joints if joint.path == source.root),
        None,
    )
    target_root = next(
        (joint for joint in body.joints if joint.path == body.root),
        None,
    )
    if target_root is None:
        issues.append(MocapMappingIssue(
            "body_missing_root", "Body 根关节不在目标快照中", (body.root,)
        ))
    root_mapping = (
        None if source_root is None else source_specs.get(source_root.name)
    )
    if source_root is not None and target_root is not None:
        if root_mapping is None or root_mapping.target_name != target_root.name:
            issues.append(MocapMappingIssue(
                "missing_root_mapping",
                "MoCap 根必须显式映射到 Body 根",
                (source_root.name, target_root.name),
            ))
        elif not (
            root_mapping.transfer_translation and root_mapping.transfer_rotation
        ):
            issues.append(MocapMappingIssue(
                "incomplete_root_channels",
                "MoCap 根映射必须同时传递平移与旋转",
                (source_root.name, target_root.name),
            ))
    for mapping in mappings:
        if mapping is not root_mapping and mapping.transfer_translation:
            issues.append(MocapMappingIssue(
                "non_root_translation",
                "只有 MoCap 根映射可以传递平移",
                (mapping.source_name, mapping.target_name),
            ))

    if (
        len(source_specs) == len(mappings)
        and len(target_specs) == len(mappings)
        and all(name in source_by_name for name in source_specs)
        and all(name in target_by_name for name in target_specs)
    ):
        _audit_mapping_topology(
            source,
            body,
            mappings,
            source_by_name,
            target_by_name,
            issues,
        )
    return tuple(issues)


def plan_mocap_body_mapping(
    source: MocapSourceSnapshot,
    body: BodySkeletonSnapshot,
    mappings: tuple[MocapJointMapping, ...],
    expected_body_provenance: BodySkeletonProvenance,
) -> MocapBodyMappingPlan:
    issues = audit_mocap_body_mapping(
        source,
        body,
        mappings,
        expected_body_provenance,
    )
    if issues:
        raise MocapMappingValidationError(
            "MoCap→Body 映射失败：" + "；".join(issue.message for issue in issues)
        )
    summary = summarize_mocap_source(source)
    source_by_name = {joint.name: joint.path for joint in source.joints}
    target_by_name = {joint.name: joint.path for joint in body.joints}
    attributes_by_path: dict[str, list[str]] = {}
    for channel in source.channels:
        attributes_by_path.setdefault(channel.joint_path, []).append(channel.attribute)
    entries = tuple(
        ResolvedMocapJointMapping(
            source_name=mapping.source_name,
            source_path=source_by_name[mapping.source_name],
            target_name=mapping.target_name,
            target_path=target_by_name[mapping.target_name],
            transfer_translation=mapping.transfer_translation,
            transfer_rotation=mapping.transfer_rotation,
            animated_attributes=tuple(sorted(
                attributes_by_path.get(source_by_name[mapping.source_name], ())
            )),
        )
        for mapping in mappings
    )
    return MocapBodyMappingPlan(
        source_root=source.root,
        target_root=body.root,
        source_namespace=summary.namespace,
        start_time=summary.start_time,
        end_time=summary.end_time,
        entries=entries,
    )


def _unique_paths_by_name(
    pairs,
    code: str,
    message: str,
    issues: list[MocapMappingIssue],
) -> dict[str, str]:
    paths_by_name: dict[str, list[str]] = {}
    for name, path in pairs:
        paths_by_name.setdefault(name, []).append(path)
    for name, paths in paths_by_name.items():
        if len(paths) > 1:
            issues.append(MocapMappingIssue(
                code,
                f"{message}：{name}",
                tuple(paths),
            ))
    return {
        name: paths[0]
        for name, paths in paths_by_name.items()
        if len(paths) == 1
    }


def _audit_mapping_topology(
    source: MocapSourceSnapshot,
    body: BodySkeletonSnapshot,
    mappings: tuple[MocapJointMapping, ...],
    source_by_name: dict[str, str],
    target_by_name: dict[str, str],
    issues: list[MocapMappingIssue],
) -> None:
    source_parent = {joint.path: joint.joint_parent for joint in source.joints}
    target_parent = {joint.path: joint.parent_path for joint in body.joints}
    mapping_by_source_path = {
        source_by_name[mapping.source_name]: mapping for mapping in mappings
    }
    mapping_by_target_path = {
        target_by_name[mapping.target_name]: mapping for mapping in mappings
    }
    for mapping in mappings:
        source_path = source_by_name[mapping.source_name]
        target_path = target_by_name[mapping.target_name]
        source_ancestor = _nearest_mapped_ancestor(
            source_parent[source_path], source_parent, mapping_by_source_path
        )
        target_ancestor = _nearest_mapped_ancestor(
            target_parent[target_path], target_parent, mapping_by_target_path
        )
        expected_target_ancestor = (
            None if source_ancestor is None else target_by_name[
                mapping_by_source_path[source_ancestor].target_name
            ]
        )
        if target_ancestor != expected_target_ancestor:
            issues.append(MocapMappingIssue(
                "topology_mismatch",
                f"映射祖先顺序不一致：{mapping.source_name} → {mapping.target_name}",
                (mapping.source_name, mapping.target_name),
            ))


def _nearest_mapped_ancestor(
    current: str | None,
    parents: dict[str, str | None],
    mapped_paths: dict[str, MocapJointMapping],
) -> str | None:
    seen: set[str] = set()
    while current is not None:
        if current in seen:
            return None
        seen.add(current)
        if current in mapped_paths:
            return current
        current = parents.get(current)
    return None
