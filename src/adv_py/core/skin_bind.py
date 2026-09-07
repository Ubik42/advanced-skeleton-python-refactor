from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SkinBindMethod(str, Enum):
    CLOSEST_DISTANCE = "closest_distance"


class SkinWeightNormalization(str, Enum):
    INTERACTIVE = "interactive"


class SkinBindValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SkinBindPlan:
    mesh_path: str
    influence_paths: tuple[str, ...]
    skin_name: str
    maximum_influences: int
    bind_method: SkinBindMethod
    normalization: SkinWeightNormalization


@dataclass(frozen=True, slots=True)
class SkinBindInputState:
    mesh_path: str | None
    mesh_shape_paths: tuple[str, ...]
    vertex_count: int
    available_influences: tuple[str, ...]
    existing_skin_clusters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkinBindSnapshot:
    skin_name: str
    geometry_paths: tuple[str, ...]
    influence_paths: tuple[str, ...]
    maximum_influences: int
    maintain_maximum_influences: bool
    bind_method: SkinBindMethod | None
    normalization: SkinWeightNormalization | None


@dataclass(frozen=True, slots=True)
class SkinBindIssue:
    code: str
    message: str
    subject: str | None = None


def plan_skin_bind(
    mesh_path: str,
    influence_paths: tuple[str, ...],
    *,
    skin_name: str = "AdvPy_BodySkin",
    maximum_influences: int = 4,
) -> SkinBindPlan:
    if not isinstance(mesh_path, str) or not mesh_path.strip():
        raise SkinBindValidationError("Skin Bind 需要显式 mesh 路径")
    if (
        not isinstance(skin_name, str)
        or not skin_name.strip()
        or "|" in skin_name
    ):
        raise SkinBindValidationError("Skin Bind 节点名必须是非空短名")
    if not influence_paths or any(
        not isinstance(path, str) or not path.strip()
        for path in influence_paths
    ):
        raise SkinBindValidationError("Skin Bind 需要至少一个显式 influence 路径")
    if len(set(influence_paths)) != len(influence_paths):
        raise SkinBindValidationError("Skin Bind influence 路径不能重复")
    if (
        isinstance(maximum_influences, bool)
        or not isinstance(maximum_influences, int)
        or maximum_influences < 1
    ):
        raise SkinBindValidationError("Skin Bind 最大影响数必须是正整数")
    return SkinBindPlan(
        mesh_path.strip(),
        tuple(path.strip() for path in influence_paths),
        skin_name.strip(),
        maximum_influences,
        SkinBindMethod.CLOSEST_DISTANCE,
        SkinWeightNormalization.INTERACTIVE,
    )


def audit_skin_bind_input(
    plan: SkinBindPlan,
    state: SkinBindInputState,
) -> tuple[SkinBindIssue, ...]:
    issues = []
    if state.mesh_path != plan.mesh_path:
        issues.append(
            SkinBindIssue(
                "mesh_missing",
                "目标 mesh 不存在或名称不唯一",
                plan.mesh_path,
            )
        )
    if len(state.mesh_shape_paths) != 1:
        issues.append(
            SkinBindIssue(
                "mesh_shape_invalid",
                "目标必须包含唯一的非中间 mesh shape",
                plan.mesh_path,
            )
        )
    if state.vertex_count <= 0:
        issues.append(SkinBindIssue("mesh_empty", "目标 mesh 没有可绑定顶点", plan.mesh_path))
    available = set(state.available_influences)
    for path in plan.influence_paths:
        if path not in available:
            issues.append(
                SkinBindIssue(
                    "influence_missing",
                    "Influence joint 不存在、名称不唯一或类型错误",
                    path,
                )
            )
    if state.existing_skin_clusters:
        issues.append(
            SkinBindIssue(
                "already_skinned",
                "目标 mesh 已有 skinCluster，本切片拒绝叠加或改写",
                "、".join(state.existing_skin_clusters),
            )
        )
    return tuple(issues)


def audit_skin_bind_result(
    plan: SkinBindPlan,
    snapshot: SkinBindSnapshot,
) -> tuple[SkinBindIssue, ...]:
    issues = []
    checks = (
        (
            snapshot.skin_name == plan.skin_name,
            "skin_name_mismatch",
            "skinCluster 名称不一致",
        ),
        (
            snapshot.geometry_paths == (plan.mesh_path,),
            "geometry_mismatch",
            "skinCluster 几何体不一致",
        ),
        (
            set(snapshot.influence_paths) == set(plan.influence_paths)
            and len(snapshot.influence_paths) == len(plan.influence_paths),
            "influence_mismatch",
            "skinCluster influence 集合不一致",
        ),
        (
            snapshot.maximum_influences == plan.maximum_influences
            and snapshot.maintain_maximum_influences,
            "maximum_influences_mismatch",
            "最大影响数设置不一致",
        ),
        (
            snapshot.bind_method is plan.bind_method,
            "bind_method_mismatch",
            "绑定方法不一致",
        ),
        (
            snapshot.normalization is plan.normalization,
            "normalization_mismatch",
            "权重归一化模式不一致",
        ),
    )
    for passed, code, message in checks:
        if not passed:
            issues.append(SkinBindIssue(code, message, plan.skin_name))
    return tuple(issues)
