"""Original-name weighted Part joints along shoulder, elbow and hip segments."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class LimbPartSegmentSpec:
    stem: str
    side: str
    start: str
    end: str
    part1: str
    part2: str
    part1_name: str
    part2_name: str
    translation_name: str
    first_translation_name: str
    scale_blend_name: str
    twist_source: str
    twist_compose_name: str
    twist_decompose_name: str
    twist_project_name: str
    up_twist_source: str | None
    up_twist1_name: str | None
    up_twist2_name: str | None
    up_fk_compose_name: str | None
    up_fk_decompose_name: str | None
    up_fk_project_name: str | None
    up_blend_name: str | None
    twist1_name: str
    twist2_name: str
    twist1_sum_name: str
    twist2_sum_name: str
    twist1_comp_name: str
    twist2_comp_name: str
    positions: tuple[tuple[float, float, float], ...]


def plan_limb_parts(body: BodySkeletonSnapshot) -> tuple[LimbPartSegmentSpec, ...]:
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("Body 关节名称不唯一")
    result = []
    for side in ("R", "L"):
        for stem, end_stem in (
                ("Shoulder", "Elbow"),
                ("Elbow", "Wrist"),
                ("Hip", "Knee")):
            start = by_name.get(f"{stem}_{side}")
            end = by_name.get(f"{end_stem}_{side}")
            if start is None or end is None or end.parent_path != start.path:
                raise ValueError("四肢分段需要直接父子 Body 端点："
                                 f"{stem}_{side} → {end_stem}_{side}")
            prefix = f"AdvPy_{stem}Part_{side}"
            up_label = {"Elbow": "LowerArm", "Hip": "UpperLeg"}.get(stem)
            name1, name2 = (f"{stem}Part{index}_{side}" for index in (1, 2))
            path1 = start.path + "|" + name1
            positions = tuple(tuple(a + (b - a) * fraction for a, b in zip(
                start.world_position, end.world_position))
                for fraction in (1.0 / 3.0, 2.0 / 3.0))
            result.append(LimbPartSegmentSpec(stem, side, start.path, end.path,
                path1, path1 + "|" + name2, name1, name2,
                prefix + "TranslateThird", prefix + "TranslateFirst",
                prefix + "ScaleBlend",
                start.path + ".rotate", prefix + "TwistCompose",
                prefix + "TwistDecompose", prefix + "TwistProject",
                (f"AdvPy_{up_label}TwistProject_{side}.outputRotateX"
                 if up_label else None),
                prefix + "UpTwist1" if up_label else None,
                prefix + "UpTwist2" if up_label else None,
                prefix + "UpFkCompose" if up_label else None,
                prefix + "UpFkDecompose" if up_label else None,
                prefix + "UpFkProject" if up_label else None,
                prefix + "UpBlend" if up_label else None,
                prefix + "Twist1", prefix + "Twist2",
                prefix + "Twist1Sum", prefix + "Twist2Sum",
                prefix + "Twist1Comp", prefix + "Twist2Comp", positions))
    return tuple(result)
