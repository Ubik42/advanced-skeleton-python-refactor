"""Turn timed phoneme labels into a portable, viseme-only weight clip."""
from __future__ import annotations

from dataclasses import dataclass

from .face_performance import FacePerformance
from .face_shapes import FaceShapeKind


@dataclass(frozen=True, slots=True)
class PhonemeCue:
    symbol: str
    start: int
    end: int

    def __post_init__(self):
        if (not isinstance(self.symbol, str) or not self.symbol
                or len(self.symbol) > 64 or type(self.start) is not int
                or type(self.end) is not int or self.end <= self.start):
            raise ValueError("音素标签或半开时间区间无效")


def _smoothstep(position: float) -> float:
    return position * position * (3. - 2. * position)


def phoneme_cues_to_performance(
    manifest: tuple[tuple[str, FaceShapeKind], ...],
    time_unit: str,
    cues: tuple[PhonemeCue, ...],
    mapping: tuple[tuple[str, str], ...],
    *,
    transition_frames: int = 2,
) -> FacePerformance:
    """Sample coarticulation around non-overlapping, half-open phoneme cues.

    A cue maps to one viseme. Adjacent cues overlap only through their smooth
    transition envelopes; weights are normalized when several envelopes meet.
    Unselected expression channels are intentionally absent from the clip.
    """
    if (not isinstance(cues, tuple) or not 1 <= len(cues) <= 2048
            or any(not isinstance(cue, PhonemeCue) for cue in cues)
            or any(left.end > right.start for left, right in zip(cues, cues[1:]))
            or type(transition_frames) is not int
            or not 1 <= transition_frames <= 48
            or not isinstance(manifest, tuple)
            or not isinstance(mapping, tuple)):
        raise ValueError("音素序列、过渡帧数或面部清单无效")
    labels = [label for label, _ in mapping]
    if (not mapping or len(set(labels)) != len(labels)
            or any(not isinstance(label, str) or not label
                   or not isinstance(target, str) for label, target in mapping)):
        raise ValueError("音素映射含重复或无效标签")
    lookup = dict(mapping)
    kinds = dict(manifest)
    if (len(kinds) != len(manifest)
            or any(kinds.get(target) != FaceShapeKind.VISEME
                   for _, target in mapping)
            or any(cue.symbol not in lookup for cue in cues)):
        raise ValueError("音素映射缺项或引用了非口型目标")
    selected = {lookup[cue.symbol] for cue in cues}
    channels = tuple((name, kind) for name, kind in manifest if name in selected)
    first = cues[0].start - transition_frames
    last = cues[-1].end + transition_frames
    frame_count = last - first + 1
    if frame_count > 10000:
        raise ValueError("音素片段超过 10000 个采样帧")
    indices = {name: index for index, (name, _) in enumerate(channels)}
    weights = [[0.] * len(channels) for _ in range(frame_count)]
    for cue in cues:
        index = indices[lookup[cue.symbol]]
        for frame in range(cue.start - transition_frames,
                           cue.end + transition_frames + 1):
            fade_in = min(1., max(0., (frame - cue.start + transition_frames)
                                  / (2. * transition_frames)))
            fade_out = min(1., max(0., (cue.end + transition_frames - frame)
                                   / (2. * transition_frames)))
            value = min(_smoothstep(fade_in), _smoothstep(fade_out))
            weights[frame - first][index] += value
    samples = []
    for offset, row in enumerate(weights):
        total = sum(row)
        scale = max(1., total)
        samples.append((first + offset, tuple(value / scale for value in row)))
    return FacePerformance(channels, time_unit, tuple(samples))
