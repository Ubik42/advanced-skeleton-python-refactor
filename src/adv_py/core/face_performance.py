"""Portable sampled expression and viseme animation."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from .character_registry import canonical, digest, exact, safe_json
from .face_shapes import FaceShapeKind


FACE_PERFORMANCE_FORMAT = "adv_py_face_performance"
FACE_PERFORMANCE_VERSION = 1


@dataclass(frozen=True, slots=True)
class FacePerformance:
    channels: tuple[tuple[str, FaceShapeKind], ...]
    time_unit: str
    samples: tuple[tuple[int, tuple[float, ...]], ...]

    def __post_init__(self):
        if (not isinstance(self.channels, tuple) or not 1 <= len(self.channels) <= 128
                or any(not isinstance(row, tuple) or len(row) != 2
                       or not isinstance(row[0], str)
                       or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", row[0])
                       or not isinstance(row[1], FaceShapeKind)
                       for row in self.channels)
                or len({name for name, _ in self.channels}) != len(self.channels)
                or not isinstance(self.time_unit, str) or not self.time_unit
                or len(self.time_unit) > 32
                or not isinstance(self.samples, tuple)
                or not 2 <= len(self.samples) <= 10000):
            raise ValueError("面部动画通道、时间单位或采样数量无效")
        previous = None
        for row in self.samples:
            if (not isinstance(row, tuple) or len(row) != 2
                    or type(row[0]) is not int
                    or (previous is not None and row[0] <= previous)
                    or not isinstance(row[1], tuple)
                    or len(row[1]) != len(self.channels)
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           or not isfinite(value) or not 0. <= value <= 1.
                           for value in row[1])):
                raise ValueError("面部动画帧、通道值或顺序无效")
            previous = row[0]

    @property
    def frames(self) -> tuple[int, ...]:
        return tuple(frame for frame, _ in self.samples)


def face_performance_to_json(performance: FacePerformance) -> str:
    payload = {
        "channels": [[name, kind.value] for name, kind in performance.channels],
        "time_unit": performance.time_unit,
        "samples": [[frame, list(values)] for frame, values in performance.samples],
    }
    return canonical({"format": FACE_PERFORMANCE_FORMAT,
        "version": FACE_PERFORMANCE_VERSION, "payload": payload,
        "digest": digest(payload)})


def face_performance_from_json(source: str) -> FacePerformance:
    document = exact(safe_json(source, max_bytes=8_000_000),
                     ("format", "version", "payload", "digest"))
    if (document["format"] != FACE_PERFORMANCE_FORMAT
            or type(document["version"]) is not int
            or document["version"] != FACE_PERFORMANCE_VERSION):
        raise ValueError("面部动画文档格式或版本无效")
    payload = exact(document["payload"], ("channels", "time_unit", "samples"))
    if digest(payload) != document["digest"]:
        raise ValueError("面部动画文档摘要不匹配")
    try:
        channels = tuple((row[0], FaceShapeKind(row[1]))
                         for row in payload["channels"])
        samples = tuple((row[0], tuple(row[1])) for row in payload["samples"])
        return FacePerformance(channels, payload["time_unit"], samples)
    except (TypeError, ValueError, KeyError, IndexError) as error:
        raise ValueError("面部动画文档结构无效") from error
