from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class SkinBindMethod(str, Enum):
    CLOSEST_DISTANCE = "closest_distance"
    CLOSEST_IN_HIERARCHY = "closest_in_hierarchy"
    HEAT_MAP = "heat_map"
    GEODESIC_VOXEL = "geodesic_voxel"


class SkinWeightNormalization(str, Enum):
    NONE = "none"
    INTERACTIVE = "interactive"
    POST = "post"


class SkinningMethod(str, Enum):
    CLASSIC_LINEAR = "classic_linear"
    DUAL_QUATERNION = "dual_quaternion"
    WEIGHT_BLENDED = "weight_blended"


class SkinWeightDistribution(str, Enum):
    DISTANCE = "distance"
    NEIGHBORS = "neighbors"


class SkinBindValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeodesicBindPreferences:
    falloff: float = 0.2
    resolution: int = 256
    post_voxel_check: bool = True
    maximum_influences: int = -1

    def __post_init__(self) -> None:
        if (isinstance(self.falloff, bool)
                or not isinstance(self.falloff, (int, float))
                or not isfinite(self.falloff)
                or not 0.0 <= self.falloff <= 1.0
                or type(self.resolution) is not int
                or self.resolution < 2
                or self.resolution & (self.resolution - 1)
                or type(self.post_voxel_check) is not bool
                or type(self.maximum_influences) is not int
                or self.maximum_influences != -1
                and not 1 <= self.maximum_influences <= 256):
            raise SkinBindValidationError("Geodesic Voxel 参数无效")


@dataclass(frozen=True, slots=True)
class SmoothBindPreferences:
    bind_method: SkinBindMethod = SkinBindMethod.CLOSEST_IN_HIERARCHY
    normalization: SkinWeightNormalization = SkinWeightNormalization.POST
    skinning_method: SkinningMethod = SkinningMethod.DUAL_QUATERNION
    maintain_maximum_influences: bool = False
    remove_unused_influences: bool = False
    weight_distribution: SkinWeightDistribution = SkinWeightDistribution.DISTANCE
    maximum_influences: int = 3

    def __post_init__(self) -> None:
        if (not isinstance(self.bind_method, SkinBindMethod)
                or not isinstance(self.normalization, SkinWeightNormalization)
                or not isinstance(self.skinning_method, SkinningMethod)
                or not isinstance(self.weight_distribution,
                                  SkinWeightDistribution)
                or type(self.maintain_maximum_influences) is not bool
                or type(self.remove_unused_influences) is not bool
                or type(self.maximum_influences) is not int
                or not 1 <= self.maximum_influences <= 256):
            raise SkinBindValidationError("Smooth Bind 选项无效")


@dataclass(frozen=True, slots=True)
class SkinBindPlan:
    mesh_path: str
    influence_paths: tuple[str, ...]
    skin_name: str
    maximum_influences: int
    maintain_maximum_influences: bool
    bind_method: SkinBindMethod
    normalization: SkinWeightNormalization
    skinning_method: SkinningMethod = SkinningMethod.CLASSIC_LINEAR
    remove_unused_influences: bool = False
    weight_distribution: SkinWeightDistribution = SkinWeightDistribution.DISTANCE
    geodesic: GeodesicBindPreferences | None = None


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
    skinning_method: SkinningMethod | None = SkinningMethod.CLASSIC_LINEAR
    geodesic_source: str | None = None
    weight_distribution: SkinWeightDistribution | None = SkinWeightDistribution.DISTANCE
    geodesic: GeodesicBindPreferences | None = None
    component_membership_complete: bool = True


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
    maintain_maximum_influences: bool = True,
    bind_method: SkinBindMethod = SkinBindMethod.CLOSEST_DISTANCE,
    normalization: SkinWeightNormalization = SkinWeightNormalization.INTERACTIVE,
    skinning_method: SkinningMethod = SkinningMethod.CLASSIC_LINEAR,
    remove_unused_influences: bool = False,
    weight_distribution: SkinWeightDistribution = SkinWeightDistribution.DISTANCE,
    geodesic: GeodesicBindPreferences | None = None,
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
        or not 1 <= maximum_influences <= 256
    ):
        raise SkinBindValidationError("Skin Bind 最大影响数须为 1 至 256 的整数")
    if not isinstance(maintain_maximum_influences, bool):
        raise SkinBindValidationError("Skin Bind 最大影响数开关必须是布尔值")
    if not isinstance(bind_method, SkinBindMethod):
        raise SkinBindValidationError("Skin Bind 绑定方法无效")
    if not isinstance(normalization, SkinWeightNormalization):
        raise SkinBindValidationError("Skin Bind 权重归一化模式无效")
    if not isinstance(skinning_method, SkinningMethod):
        raise SkinBindValidationError("Skin Bind 蒙皮计算方法无效")
    if type(remove_unused_influences) is not bool:
        raise SkinBindValidationError("Skin Bind 未使用影响关节选项无效")
    if not isinstance(weight_distribution, SkinWeightDistribution):
        raise SkinBindValidationError("Skin Bind 权重分布方法无效")
    if geodesic is not None and not isinstance(geodesic,
                                              GeodesicBindPreferences):
        raise SkinBindValidationError("Geodesic Voxel 参数类型无效")
    if bind_method is not SkinBindMethod.GEODESIC_VOXEL and geodesic is not None:
        raise SkinBindValidationError("非 Geodesic Skin 不接受体素参数")
    return SkinBindPlan(
        mesh_path.strip(),
        tuple(path.strip() for path in influence_paths),
        skin_name.strip(),
        maximum_influences,
        maintain_maximum_influences,
        bind_method,
        normalization,
        skinning_method,
        remove_unused_influences,
        weight_distribution,
        geodesic,
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
            snapshot.component_membership_complete,
            "component_membership_incomplete",
            "新建 Skin 没有覆盖网格全部顶点",
        ),
        (
            ((bool(snapshot.influence_paths)
              and set(snapshot.influence_paths).issubset(
                  set(plan.influence_paths)))
             if plan.remove_unused_influences else
             (set(snapshot.influence_paths) == set(plan.influence_paths)
              and len(snapshot.influence_paths) == len(plan.influence_paths))),
            "influence_mismatch",
            "skinCluster influence 集合不一致",
        ),
        (
            snapshot.maximum_influences == plan.maximum_influences
            and snapshot.maintain_maximum_influences
                == plan.maintain_maximum_influences,
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
        (
            snapshot.skinning_method is plan.skinning_method,
            "skinning_method_mismatch",
            "蒙皮计算方法不一致",
        ),
        (
            snapshot.weight_distribution is plan.weight_distribution,
            "weight_distribution_mismatch",
            "权重分布方法不一致",
        ),
        (
            plan.bind_method is not SkinBindMethod.GEODESIC_VOXEL
            or snapshot.geodesic_source is not None,
            "geodesic_bind_missing",
            "Geodesic Voxel 权重求解节点缺失",
        ),
        (
            plan.bind_method is not SkinBindMethod.GEODESIC_VOXEL
            or snapshot.geodesic == (plan.geodesic or
                GeodesicBindPreferences(
                    maximum_influences=plan.maximum_influences)),
            "geodesic_settings_mismatch",
            "Geodesic Voxel 参数不一致",
        ),
    )
    for passed, code, message in checks:
        if not passed:
            issues.append(SkinBindIssue(code, message, plan.skin_name))
    return tuple(issues)
