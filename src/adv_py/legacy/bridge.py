from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


SAFE_NAME = re.compile(r"^[A-Za-z_]\w*$")


def _mel_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(_mel_literal(item) for item in value) + "}"
    raise TypeError(f"不支持传入 MEL 的值类型：{type(value).__name__}")


@dataclass(frozen=True)
class LegacyMelBridge:
    """Small, explicit compatibility seam; available only inside Maya."""

    source_path: Path

    def source(self) -> None:
        from maya import mel  # type: ignore[import-not-found]

        path = self.source_path.resolve().as_posix().replace('"', '\\"')
        mel.eval(f'source "{path}";')

    def call(self, procedure: str, *args: Any) -> Any:
        if not SAFE_NAME.fullmatch(procedure):
            raise ValueError(f"非法 MEL 过程名：{procedure!r}")
        from maya import mel  # type: ignore[import-not-found]

        arguments = ", ".join(_mel_literal(arg) for arg in args)
        return mel.eval(f"{procedure}({arguments});")

