"""Inspect stored body pose and animation presets for one scene character."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adv_py.core.character_animation import (ANIMATION_FORMAT,
                                              validate_character_animation)
from adv_py.core.character_pose import POSE_FORMAT, validate_character_pose
from adv_py.core.character_registry import safe_json

from .character_animation import ApplyBodyCharacterAnimation, load_character_animation
from .character_pose import ApplyBodyCharacterPose, load_character_pose


@dataclass(frozen=True, slots=True)
class CharacterPresetStatus:
    filename: str
    kind: str
    compatible: bool
    applicable: bool
    reason: str | None


class InspectBodyCharacterPresets:
    def __init__(self, host):
        self._host = host

    def list(self, directory: Path) -> tuple[CharacterPresetStatus, ...]:
        directory = Path(directory)
        if not directory.is_dir():
            raise NotADirectoryError("预设目录不存在：" + str(directory))
        paths = sorted(path for path in directory.iterdir()
                       if path.is_file() and path.suffix.lower() == ".json")
        if len(paths) > 256:
            raise ValueError("单次最多检查 256 个预设")
        registration = self._host.read_character_registration()
        result = []
        for path in paths:
            kind = "unknown"
            compatible = False
            try:
                if path.stat().st_size > 64_000_000:
                    raise ValueError("预设文件超过 64 MB")
                document = safe_json(path.read_text(encoding="utf-8"),
                                     max_bytes=64_000_000)
                format_name = document.get("format") if isinstance(document, dict) else None
                if format_name == POSE_FORMAT:
                    kind = "pose"
                    preset = load_character_pose(path)
                    validate_character_pose(preset, registration)
                    compatible = True
                    ApplyBodyCharacterPose(self._host).plan(preset)
                elif format_name == ANIMATION_FORMAT:
                    kind = "animation"
                    preset = load_character_animation(path)
                    validate_character_animation(preset, registration)
                    compatible = True
                    ApplyBodyCharacterAnimation(self._host).plan(preset)
                else:
                    raise ValueError("不是支持的角色预设格式")
                result.append(CharacterPresetStatus(path.name, kind, True, True, None))
            except (OSError, ValueError, RuntimeError) as error:
                result.append(CharacterPresetStatus(path.name, kind,
                    compatible, False, str(error)))
        return tuple(result)
