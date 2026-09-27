"""Map original 6.925 eyelid influences onto a rebuilt face rig."""
from __future__ import annotations

from dataclasses import dataclass
from array import array
from math import isfinite
import re
from typing import Sequence

from .dense_skin_transfer import DenseSkinWeights


_LID = re.compile(r"^((?:upper|lower)Lid(?:Main|Outer))(\d+)(_[RL])$")
_AUX = re.compile(r"^lowerLidOuterJoint_([RL])$")


def face_influence_base(name: str) -> str:
    return name.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


@dataclass(frozen=True, slots=True)
class FaceSourceSkinMapping:
    segment_targets: tuple[tuple[int, str], ...]
    auxiliary_sources: tuple[tuple[str, int], ...]
    approximated_segments: int


def plan_face_source_skin_mapping(
    source_influences: tuple[str, ...],
    target_influences: tuple[str, ...],
    *,
    simpler_eyelid: bool,
) -> FaceSourceSkinMapping:
    if type(simpler_eyelid) is not bool:
        raise ValueError("眼睑构建模式必须是布尔值")
    target_by_base = {face_influence_base(name): name
                      for name in target_influences}
    if len(target_by_base) != len(target_influences):
        raise ValueError("目标影响关节名称不唯一")
    lid_targets = {name: path for name, path in target_by_base.items()
                   if _LID.fullmatch(name)}
    if not lid_targets:
        raise ValueError("目标 Skin 没有眼睑分段关节")
    segments = []
    auxiliary = {}
    seen_lids = set()
    approximated = 0
    for index, source_path in enumerate(source_influences):
        name = face_influence_base(source_path)
        match = _LID.fullmatch(name)
        if match:
            if name in seen_lids:
                raise ValueError("来源眼睑影响关节重名：" + name)
            seen_lids.add(name)
            target = lid_targets.get(name)
            if target is None:
                candidates = [(abs(int(_LID.fullmatch(other).group(2)) -
                                   int(match.group(2))), other)
                              for other in lid_targets
                              if (other.startswith(match.group(1)) and
                                  other.endswith(match.group(3)))]
                if not candidates:
                    raise ValueError("目标缺少眼睑分段：" + name)
                target = lid_targets[min(candidates)[1]]
                approximated += 1
            segments.append((index, target))
        else:
            aux_match = _AUX.fullmatch(name)
            if aux_match:
                side = aux_match.group(1)
                if side in auxiliary:
                    raise ValueError("原版外围关节重名")
                auxiliary[side] = index
    if not segments:
        raise ValueError("来源不是已绑定的原版眼睑 Skin")
    if simpler_eyelid and set(auxiliary) != {"R", "L"}:
        raise ValueError("简化眼睑来源需要双侧眼下外围影响关节")
    return FaceSourceSkinMapping(
        tuple(segments), tuple(sorted(auxiliary.items())), approximated)


def transfer_face_source_skin_weights(
    source_values: Sequence[float],
    source_influence_count: int,
    before: DenseSkinWeights,
    target: DenseSkinWeights,
    source_to_target: tuple[tuple[int, str], ...],
) -> DenseSkinWeights:
    """Keep original lid mass and redistribute the rest over existing skin."""
    if (type(source_influence_count) is not int
            or source_influence_count < 1
            or before.vertex_count != target.vertex_count
            or len(source_values) != before.vertex_count * source_influence_count
            or len(before.values) != before.vertex_count *
                len(before.influence_names) * 8
            or len(target.values) != target.vertex_count *
                len(target.influence_names) * 8):
        raise ValueError("原版与目标眼睑 Skin 权重维度不符")
    target_index = {name: index for index, name in
                    enumerate(target.influence_names)}
    old_index = {name: index for index, name in
                 enumerate(before.influence_names)}
    if (len(target_index) != len(target.influence_names)
            or len(old_index) != len(before.influence_names)
            or not set(old_index) <= set(target_index)):
        raise ValueError("目标 Skin 影响关节集合与原目标不一致")
    target_by_base = {face_influence_base(name): name
                      for name in target.influence_names}
    if len(target_by_base) != len(target_index) or "Head_M" not in target_by_base:
        raise ValueError("目标 Skin 缺少唯一 Head_M 影响关节")
    if (not source_to_target
            or len({index for index, _ in source_to_target}) !=
                len(source_to_target)
            or any(
            type(source_index) is not int
            or not 0 <= source_index < source_influence_count
            or name not in target_index
            for source_index, name in source_to_target)):
        raise ValueError("眼睑来源与目标影响关节映射无效")
    width = len(target.influence_names)
    old_width = len(before.influence_names)
    old = memoryview(before.values).cast("d")
    values = array("d", [0.] * (before.vertex_count * width))
    lid_columns = {target_index[name] for _, name in source_to_target}
    non_lid = [(target_index[name], old_index[name])
               for name in before.influence_names
               if target_index[name] not in lid_columns]
    head_index = target_index[target_by_base["Head_M"]]
    if head_index in lid_columns:
        raise ValueError("Head_M 不能用作眼睑影响关节")
    for vertex in range(before.vertex_count):
        mass = 0.
        for source_index, name in source_to_target:
            raw_amount = source_values[
                vertex * source_influence_count + source_index]
            if not isfinite(raw_amount):
                raise ValueError(f"原版顶点 {vertex} 的眼睑权重非有限数值")
            amount = max(0., raw_amount)
            values[vertex * width + target_index[name]] += amount
            mass += amount
        if mass > 1. + 1e-5:
            raise ValueError(f"原版顶点 {vertex} 的眼睑权重超过 1")
        remaining = max(0., 1. - mass)
        old_remaining = sum(max(0., old[vertex * old_width + index])
                            for _, index in non_lid)
        if old_remaining > 1e-8:
            for new_index, source_index in non_lid:
                values[vertex * width + new_index] = (
                    remaining * max(0., old[
                        vertex * old_width + source_index]) / old_remaining)
        else:
            values[vertex * width + head_index] += remaining
    return DenseSkinWeights(target.skin_name, before.vertex_count,
                            target.influence_names, values.tobytes())
