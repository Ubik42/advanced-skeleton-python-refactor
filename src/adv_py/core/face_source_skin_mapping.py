"""Map original 6.925 eyelid influences onto a rebuilt face rig."""
from __future__ import annotations

from dataclasses import dataclass
import re


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
