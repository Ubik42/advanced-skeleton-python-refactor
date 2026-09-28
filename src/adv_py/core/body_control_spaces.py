from dataclasses import dataclass
from math import isfinite

from .fit_settings import FitSkeletonValidationError

SPACE_TOLERANCE = 1e-4


@dataclass(frozen=True, slots=True)
class BodyControlSpaceSpec:
    key: str
    targets: tuple[str, ...]
    body_source: str
    global_source: str
    rotation_only: bool
    initial_mode: str
    body_target_sources: tuple[str, ...] = ()

    @property
    def constraint_names(self):
        return tuple(f"AdvPy_Space_{self.key}_{index}" for index in range(len(self.targets)))

    @property
    def attributes(self):
        return tuple(kind + axis for kind in (("rotate",) if self.rotation_only else ("translate", "rotate")) for axis in "XYZ")

    def source(self, mode: str, index: int | None = None) -> str:
        if mode not in ("body", "global"):
            raise FitSkeletonValidationError("控制空间必须是 body 或 global")
        if index is not None and not 0 <= index < len(self.targets):
            raise FitSkeletonValidationError("控制空间目标索引无效")
        if self.body_target_sources and len(self.body_target_sources) != len(self.targets):
            raise FitSkeletonValidationError("控制空间目标来源数量不一致")
        if mode == "global":
            return self.global_source
        if index is not None and self.body_target_sources:
            return self.body_target_sources[index]
        return self.body_source

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.global_source, self.body_source,
                                    *self.body_target_sources)))


@dataclass(frozen=True, slots=True)
class BodyControlSpacesPlan:
    body_root: str
    spaces: tuple[BodyControlSpaceSpec, ...]

    @property
    def node_names(self):
        return tuple(name for spec in self.spaces for name in spec.constraint_names)

    def space(self, key: str) -> BodyControlSpaceSpec:
        found = tuple(spec for spec in self.spaces if spec.key == key)
        if len(found) != 1:
            raise FitSkeletonValidationError(f"控制空间标识不存在或不唯一：{key}")
        return found[0]


def plan_body_control_spaces(body, torso, arm, leg, global_control,
                             pole_aim=()):
    joints = {j.name: j.path for j in body.joints}
    heads = tuple(spec for spec in torso.controls.controls if spec.driven_joint == joints.get("Head_M"))
    if len(heads) != 1 or "Neck_M" not in joints:
        raise FitSkeletonValidationError("空间计划需要完整 Torso 头颈控制")
    neck_controls = tuple(spec for spec in torso.controls.controls
                          if spec.driven_joint == joints["Neck_M"])
    if len(neck_controls) != 1:
        raise FitSkeletonValidationError("空间计划需要唯一 Neck FK 控制")
    spaces = [BodyControlSpaceSpec("head", (heads[0].offset_path,),
        neck_controls[0].control_path, global_control.control_path,
        True, "body")]
    pole_aim_by_side = {spec.side: spec.target_path for spec in pole_aim}
    if pole_aim and (len(pole_aim_by_side) != len(pole_aim)
                     or set(pole_aim_by_side) != {limb.side for limb in leg.ik.limbs}):
        raise FitSkeletonValidationError("Leg PoleAim 必须覆盖每一侧且不可重复")
    for module, label, source in ((arm, "hand", joints["Chest_M"]), (leg, "foot", body.root)):
        for limb in module.ik.limbs:
            goal = limb.wrist_offset_path if label == "hand" else limb.ankle_offset_path
            pole_source = (pole_aim_by_side.get(limb.side, source)
                           if label == "foot" else source)
            spaces.append(BodyControlSpaceSpec(
                f"{label}_{limb.side.value}", (goal, limb.pole_offset_path), source,
                global_control.control_path, False,
                "body" if label == "foot" and pole_aim else "global",
                (source, pole_source),
            ))
    targets = [target for spec in spaces for target in spec.targets]
    if len(set(targets)) != len(targets):
        raise FitSkeletonValidationError("空间计划不能重复驱动同一 offset")
    return BodyControlSpacesPlan(body.root, tuple(spaces))


def control_space_pose_error(before, after):
    if (not before or tuple(p for p, _ in before) != tuple(p for p, _ in after)
            or any(len(m) != 16 or not all(isfinite(v) for v in m) for _, m in before + after)):
        raise FitSkeletonValidationError("控制空间姿态快照不完整或数值无效")
    return max(abs(a-b) for (_, old), (_, new) in zip(before, after) for a, b in zip(old, new))
