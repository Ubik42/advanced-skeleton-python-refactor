"""Plan 6.925 Fit-driven Part joints before any DCC node is created."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace

from .body_skeleton import (
    BodyJointSpec, BodySkeletonSnapshot, FitDeformProfile,
    BodyJointState,
)
from .fit_metadata import FitJointMetadata
from .fit_symmetry import FitBuildSide, FitSymmetryInstance


Vector3 = tuple[float, float, float]


class FitPartValidationError(ValueError):
    """A Fit source cannot produce an unambiguous Part hierarchy."""


@dataclass(frozen=True, slots=True)
class FitPartJointSpec:
    source_joint: str
    start_body: str
    end_body: str
    side: FitBuildSide
    index: int
    count: int
    path: str
    name: str
    parent_path: str
    world_position: Vector3
    deform_profile: FitDeformProfile
    skin_enabled: bool = True
    rotation_order: int = 0
    segment_scale_compensate: bool = True

    @property
    def start_body_name(self) -> str:
        return self.start_body.rsplit("|", 1)[-1]

    @property
    def end_body_name(self) -> str:
        return self.end_body.rsplit("|", 1)[-1]

    @property
    def parent_name(self) -> str:
        return self.parent_path.rsplit("|", 1)[-1]


@dataclass(frozen=True, slots=True)
class FitPartReparentSpec:
    child_body: str
    child_name: str
    parent_part: str
    parent_part_name: str
    reason: str
    segment_parts: tuple[str, ...] = ()
    segment_index: int = 0


@dataclass(frozen=True, slots=True)
class FitPartJointState:
    name: str
    parent_name: str
    world_position: Vector3
    deform_profile: FitDeformProfile
    skin_enabled: bool = True
    rotation_order: int = 0
    segment_scale_compensate: bool = True
    path: str = ""


@dataclass(frozen=True, slots=True)
class FitPartChildState:
    name: str
    parent_name: str
    path: str = ""


@dataclass(frozen=True, slots=True)
class FitPartHierarchySnapshot:
    joints: tuple[FitPartJointState, ...]
    children: tuple[FitPartChildState, ...]
    body_paths: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FitPartFinalPaths:
    body_paths: tuple[tuple[str, str], ...]
    part_paths: tuple[tuple[str, str], ...]
    body_rewrites: tuple[tuple[str, str], ...]

    def remap_body_reference(self, reference: str) -> str:
        """Rewrite a pre-Part Body DAG path or attribute plug by longest match."""
        for before, after in sorted(self.body_rewrites,
                                    key=lambda pair: len(pair[0]), reverse=True):
            if reference == before or reference.startswith((before + "|",
                                                           before + ".")):
                return after + reference[len(before):]
        return reference


def rebase_body_snapshot_after_parts(
    before: BodySkeletonSnapshot,
    paths: FitPartFinalPaths,
) -> BodySkeletonSnapshot:
    """Express the same bind pose with its post-reparent DAG identities."""
    rewrites = dict(paths.body_rewrites)
    if len(rewrites) != len(paths.body_rewrites) or (
            set(rewrites) != {joint.path for joint in before.joints}):
        raise FitPartValidationError("Part 路径映射与原 Body 快照不一致")
    joints = []
    for joint in before.joints:
        path = rewrites[joint.path]
        parent = path.rsplit("|", 1)[0] or None
        joints.append(replace(joint, path=path, parent_path=parent))
    if before.root not in rewrites:
        raise FitPartValidationError("Part 路径映射缺少 Body 根关节")
    return replace(before, root=rewrites[before.root], joints=tuple(joints))


def rebase_plan_paths_after_parts(value: object,
                                  paths: FitPartFinalPaths) -> object:
    """Rebase immutable rig plans after the physical Body DAG changes.

    Fit source paths are outside the Body rewrite map and remain untouched.
    Body snapshots and symmetry instances need a new immediate parent, which
    cannot be obtained by merely replacing the old parent path's prefix.
    """
    if isinstance(value, BodySkeletonSnapshot):
        if {joint.path for joint in value.joints} == {
                before for before, _ in paths.body_rewrites}:
            return rebase_body_snapshot_after_parts(value, paths)
    if isinstance(value, FitSymmetryInstance):
        output = paths.remap_body_reference(value.output_path)
        return replace(value, output_path=output,
                       parent_output_path=output.rsplit("|", 1)[0] or None)
    if isinstance(value, BodyJointSpec):
        output = paths.remap_body_reference(value.path)
        return replace(value, path=output,
                       parent_path=output.rsplit("|", 1)[0] or None)
    if isinstance(value, BodyJointState):
        output = paths.remap_body_reference(value.path)
        return replace(value, path=output,
                       parent_path=output.rsplit("|", 1)[0] or None)
    if isinstance(value, str):
        return paths.remap_body_reference(value)
    if isinstance(value, tuple):
        return tuple(rebase_plan_paths_after_parts(item, paths)
                     for item in value)
    if isinstance(value, list):
        return [rebase_plan_paths_after_parts(item, paths) for item in value]
    if isinstance(value, dict):
        return {rebase_plan_paths_after_parts(key, paths):
                rebase_plan_paths_after_parts(item, paths)
                for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        changes = {field.name: rebase_plan_paths_after_parts(
            getattr(value, field.name), paths) for field in fields(value)}
        return replace(value, **changes)
    return value


def plan_fit_part_final_paths(
    body_specs: tuple[BodyJointSpec, ...],
    parts: tuple[FitPartJointSpec, ...],
    reparents: tuple[FitPartReparentSpec, ...],
) -> FitPartFinalPaths:
    """Resolve the DAG after every Part and ChildOfPart reparent operation."""
    body_names = [spec.name for spec in body_specs]
    part_names = [spec.name for spec in parts]
    names = body_names + part_names
    if len(set(names)) != len(names):
        raise FitPartValidationError("Body／Part 名称必须全局唯一")
    parents: dict[str, str | None] = {}
    for spec in body_specs:
        parents[spec.name] = (
            spec.parent_path.rsplit("|", 1)[-1]
            if spec.parent_path else None)
    for spec in parts:
        parents[spec.name] = spec.parent_name
    for spec in reparents:
        if spec.child_name not in body_names or spec.parent_part_name not in part_names:
            raise FitPartValidationError("Part 改挂包含未知关节")
        parents[spec.child_name] = spec.parent_part_name
    if sum(parent is None for parent in parents.values()) != 1:
        raise FitPartValidationError("Part 最终层级必须恰有一个根关节")

    resolved: dict[str, str] = {}
    visiting: set[str] = set()

    def resolve(name: str) -> str:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            raise FitPartValidationError("Part 改挂会产生层级循环：" + name)
        visiting.add(name)
        parent = parents[name]
        if parent is not None and parent not in parents:
            raise FitPartValidationError("Part 最终层级父关节不存在：" + name)
        path = (resolve(parent) + "|" if parent else "|") + name
        visiting.remove(name)
        resolved[name] = path
        return path

    for name in names:
        resolve(name)
    return FitPartFinalPaths(
        tuple((name, resolved[name]) for name in body_names),
        tuple((name, resolved[name]) for name in part_names),
        tuple((spec.path, resolved[spec.name]) for spec in body_specs),
    )


def audit_fit_part_hierarchy(
    parts: tuple[FitPartJointSpec, ...],
    reparents: tuple[FitPartReparentSpec, ...],
    snapshot: FitPartHierarchySnapshot,
    *,
    tolerance: float = 1e-4,
    final_paths: FitPartFinalPaths | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    states = {state.name: state for state in snapshot.joints}
    children = {state.name: state for state in snapshot.children}
    if len(states) != len(snapshot.joints) or len(children) != len(snapshot.children):
        issues.append("Part 快照存在重名关节")
    if set(states) != {part.name for part in parts}:
        issues.append("Part 关节集合与构建计划不一致")
    if set(children) != {item.child_name for item in reparents}:
        issues.append("Part 下游关节集合与改挂计划不一致")
    expected_part_paths = dict(final_paths.part_paths) if final_paths else {}
    expected_body_paths = dict(final_paths.body_paths) if final_paths else {}
    if final_paths and dict(snapshot.body_paths) != expected_body_paths:
        issues.append("Body 关节最终路径与 Part 改挂计划不一致")
    for spec in parts:
        state = states.get(spec.name)
        if state is None:
            continue
        if state.parent_name != spec.parent_name:
            issues.append("Part 父级不一致：" + spec.name)
        if final_paths and state.path != expected_part_paths[spec.name]:
            issues.append("Part 最终路径不一致：" + spec.name)
        if state.skin_enabled != spec.skin_enabled:
            issues.append("Part Skin 影响开关不一致：" + spec.name)
        if state.rotation_order != spec.rotation_order:
            issues.append("Part 旋转顺序不一致：" + spec.name)
        if state.segment_scale_compensate != spec.segment_scale_compensate:
            issues.append("Part 分段缩放补偿不一致：" + spec.name)
        if any(abs(a - b) > tolerance for a, b in zip(
                state.world_position, spec.world_position)):
            issues.append("Part 世界位置不一致：" + spec.name)
        if any(abs(a - b) > tolerance for a, b in zip(
                (state.deform_profile.fat, state.deform_profile.fat_front,
                 state.deform_profile.fat_width),
                (spec.deform_profile.fat, spec.deform_profile.fat_front,
                 spec.deform_profile.fat_width))):
            issues.append("Part 体积参数不一致：" + spec.name)
    final_reparents = {spec.child_name: spec for spec in reparents}
    for spec in final_reparents.values():
        state = children.get(spec.child_name)
        if state is not None and state.parent_name != spec.parent_part_name:
            issues.append("Part 下游关节父级不一致：" + spec.child_name)
        if (final_paths and state is not None
                and state.path != expected_body_paths[spec.child_name]):
            issues.append("Part 下游关节最终路径不一致：" + spec.child_name)
    return tuple(issues)


def plan_fit_part_joints(
    instances: tuple[FitSymmetryInstance, ...],
    metadata: tuple[FitJointMetadata, ...],
    body_specs: tuple[BodyJointSpec, ...],
) -> tuple[FitPartJointSpec, ...]:
    """Expand each Fit twistJoints value into a side-specific Part chain.

    The result describes weighted influence joints only. Their rotation,
    translation, scale and skin connections belong to the build host.
    """
    by_source = {item.joint: item for item in metadata}
    by_path = {item.path: item for item in body_specs}
    if len(by_source) != len(metadata) or len(by_path) != len(body_specs):
        raise FitPartValidationError("Fit 元数据或 Body 关节路径重复")
    if set(by_path) != {item.output_path for item in instances}:
        raise FitPartValidationError("Part 计划需要完整的 Body 对称展开规格")
    children: dict[str, list[FitSymmetryInstance]] = {}
    for instance in instances:
        if instance.parent_output_path is not None:
            children.setdefault(instance.parent_output_path, []).append(instance)

    parts: list[FitPartJointSpec] = []
    used_paths: set[str] = set(by_path)
    for start in instances:
        source = by_source.get(start.source_joint)
        if source is None:
            raise FitPartValidationError("Fit 关节缺少 twistJoints 元数据："
                                         + start.source_joint)
        count = source.twist_joints or 0
        if count < 0 or count > 10:
            raise FitPartValidationError("Fit twistJoints 必须在 0 到 10 之间："
                                         + start.source_joint)
        if count == 0:
            continue
        candidates = [child for child in children.get(start.output_path, ())
                      if child.side is start.side]
        end = _select_downstream(start, candidates)
        if end is None:
            # The original asRlaChild skips a terminal joint with no
            # same-side child even when twistJoints is present.
            continue
        start_body = by_path[start.output_path]
        end_body = by_path[end.output_path]
        parent = start.output_path
        stem = start.output_name.rsplit("_", 1)[0]
        for index in range(1, count + 1):
            fraction = index / (count + 1)
            name = f"{stem}Part{index}_{start.side.value}"
            path = parent + "|" + name
            if path in used_paths:
                raise FitPartValidationError("Part 关节路径重复：" + path)
            used_paths.add(path)
            position = tuple(a + (b - a) * fraction for a, b in zip(
                start_body.world_position, end_body.world_position))
            parts.append(FitPartJointSpec(
                start.source_joint, start.output_path, end.output_path,
                start.side, index, count, path, name, parent, position,
                start_body.deform_profile.interpolate(
                    end_body.deform_profile, fraction),
                start_body.skin_enabled,
                start_body.rotation_order,
                start_body.segment_scale_compensate))
            parent = path
    return tuple(parts)


def plan_fit_part_reparents(
    instances: tuple[FitSymmetryInstance, ...],
    metadata: tuple[FitJointMetadata, ...],
    parts: tuple[FitPartJointSpec, ...],
) -> tuple[FitPartReparentSpec, ...]:
    """Describe the 6.925 end-child and ChildOfPart parenting passes.

    Paths here identify nodes before reparenting. The host must resolve each
    node once and retain its handle while DAG paths change during the pass.
    """
    part_by_start_index = {(item.start_body, item.index): item
                           for item in parts}
    source_by_joint = {item.joint: item for item in metadata}
    instance_by_path = {item.output_path: item for item in instances}
    assignments: list[FitPartReparentSpec] = []
    chain_by_end: dict[str, tuple[str, ...]] = {}
    for part in parts:
        if part.index != part.count:
            continue
        end = instance_by_path[part.end_body]
        chain = tuple(part_by_start_index[(part.start_body, index)].name
                      for index in range(1, part.count + 1))
        chain_by_end[end.output_path] = chain
        assignments.append(FitPartReparentSpec(
            end.output_path, end.output_name, part.path, part.name,
            "end_of_chain", chain, part.count))
    for child in instances:
        source = source_by_joint.get(child.source_joint)
        if source is None:
            raise FitPartValidationError("Fit 关节缺少 ChildOfPart 元数据："
                                         + child.source_joint)
        index = source.child_of_part or 0
        if index == 0:
            continue
        if child.parent_output_path is None:
            raise FitPartValidationError("Fit 根关节不能指定 ChildOfPart")
        parent = part_by_start_index.get((child.parent_output_path, index))
        if parent is None:
            raise FitPartValidationError("ChildOfPart 指向不存在的父级 Part："
                                         + child.output_name)
        assignments.append(FitPartReparentSpec(
            child.output_path, child.output_name, parent.path, parent.name,
            "child_of_part", chain_by_end.get(child.output_path, ()),
            index if child.output_path in chain_by_end else 0))
    return tuple(assignments)


def _select_downstream(
    start: FitSymmetryInstance,
    candidates: list[FitSymmetryInstance],
) -> FitSymmetryInstance | None:
    if not candidates:
        return None
    # asRlaChild in 6.925 takes the first same-side child, then applies
    # these named branch preferences. Preserve input hierarchy order.
    preference = next((target for key, target in (
        ("Head", "Head"), ("Ankle", "Toes"), ("Toes", "Toes"),
        ("Root", "Spine")) if key in start.output_name), None)
    if preference is not None:
        for child in candidates:
            if preference in child.output_name:
                return child
    return candidates[0]
