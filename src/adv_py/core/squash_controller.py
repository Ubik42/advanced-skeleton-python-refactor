"""Scene-independent contract for ADV Body Squash Controller."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


LATTICE_DIVISIONS = (2, 11, 2)
IK_JOINT_COUNT = 11
CURVE_HANDLE_COUNT = 5
VOLUME_EXPONENTS = (.600, .730, .820, .860, .870,
                    .860, .820, .730, .600)


@dataclass(frozen=True, slots=True)
class SquashSelection:
    vertices: tuple[str, ...]
    mesh: str
    bounds: tuple[float, float, float, float, float, float]
    parent_joint: str
    side: str
    one_joint_prop: bool
    game_engine: bool


@dataclass(frozen=True, slots=True)
class SquashPlan:
    name: str
    side: str
    mesh: str
    vertices: tuple[str, ...]
    parent_joint: str
    center: tuple[float, float, float]
    falloff_radius: float
    axis_sign: int
    one_joint_prop: bool

    @property
    def control(self) -> str:
        return self.name + self.side

    @property
    def nodes(self) -> tuple[str, ...]:
        prefix, side = self.name, self.side
        fixed = ("Attach", "WS", "Offset", "Base", "Ffd",
                 "FfdLattice", "FfdBase", "FfdSet", "IKHandle",
                 "IKEffector", "IKCurve", "IKSC", "BendMPDT",
                 "BendMPDR", "IKCurveInfo", "IKCurveInfoNormalize",
                 "IKCurveInfoMainScale", "IKCurveInfoBaseScale",
                 "IKScale", "IKStretch", "LimitsClamp",
                 "SquashCondition", "StretchCondition",
                 "squashVolume1Over", "TopVolumeUC",
                 "IKClusterHandle4Offset")
        names = [self.control]
        names.extend(prefix + token + side for token in fixed)
        names.extend(prefix + "IKX%d%s" % (index, side)
                     for index in range(IK_JOINT_COUNT))
        names.extend(prefix + "IKCluster%d%s" % (index, side)
                     for index in range(CURVE_HANDLE_COUNT))
        names.extend(prefix + "IKClusterHandle%d%s" % (index, side)
                     for index in range(CURVE_HANDLE_COUNT))
        names.extend(prefix + "squashVolumePow%d%s" % (index, side)
                     for index in range(1, 10))
        names.extend(prefix + "BlendTwo%d%s" % (index, side)
                     for index in range(1, 10))
        if side == "_L":
            names.append(prefix + "IKTwistReverse" + side)
        return tuple(names)


def plan_squash_controller(selection: SquashSelection,
                           base_name: str) -> SquashPlan:
    if selection.game_engine:
        raise ValueError("ADV Game Engine 模式下不能创建 Squash Controller")
    if not selection.vertices:
        raise ValueError("须先选择受 Squash 影响的网格顶点")
    if len(set(selection.vertices)) != len(selection.vertices):
        raise ValueError("Squash 顶点选择包含重复项")
    if not selection.mesh or any(not item.startswith(selection.mesh + ".vtx[")
                                 for item in selection.vertices):
        raise ValueError("Squash 顶点须属于同一件网格")
    if selection.side not in ("_R", "_L", "_M"):
        raise ValueError("Squash 父关节侧别须为 _R、_L 或 _M")
    if (not base_name or "_" in base_name or not base_name[0].isalpha()
            or not base_name.isalnum()):
        raise ValueError("Squash 名称须以字母开头且不含下划线")
    if not selection.parent_joint:
        raise ValueError("Squash 缺少变形关节父级")
    bounds = selection.bounds
    if len(bounds) != 6 or not all(isfinite(value) for value in bounds):
        raise ValueError("Squash 包围框不是六个有限数值")
    if (any(bounds[i + 3] < bounds[i] for i in range(3))
            or all(bounds[i + 3] == bounds[i] for i in range(3))):
        raise ValueError("Squash 包围框须具有非零范围")
    radius = sum(bounds[i + 3] - bounds[i] for i in range(3)) / 3.0
    center = tuple((bounds[i] + bounds[i + 3]) / 2.0 for i in range(3))
    side_sign = -1 if selection.side == "_L" else 1
    return SquashPlan(base_name, selection.side, selection.mesh,
                      selection.vertices, selection.parent_joint,
                      center, radius, side_sign,
                      selection.one_joint_prop)
