"""Resolve the original Shapers plug-in implementation for one Maya host."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ShapersPluginPlan:
    root: Path
    maya_version: int
    platform: str
    extension: str
    mode: str = "automatic"
    autoload: bool = True

    def __post_init__(self) -> None:
        if (self.mode not in ("automatic", "native", "python")
                or self.maya_version < 2020
                or self.platform not in ("Windows", "macOS", "Linux")
                or self.extension not in (".mll", ".bundle", ".so")
                or type(self.autoload) is not bool):
            raise ValueError("Shapers 插件设置无效")

    @property
    def native_file(self) -> Path:
        return (self.root / "plug-ins" / f"Maya{self.maya_version}"
                / self.platform / ("Shapers" + self.extension))

    @property
    def python_file(self) -> Path:
        return self.root / "Shapers.py"

    @property
    def use_native(self) -> bool:
        return (self.mode == "native"
                or self.mode == "automatic" and self.native_file.is_file())

    @property
    def selected_file(self) -> Path:
        return self.native_file if self.use_native else self.python_file

    @property
    def module_relative_path(self) -> str:
        prefix = "AdvancedSkeletonFiles/div/shapers"
        return (prefix + f"/plug-ins/Maya{self.maya_version}/{self.platform}"
                if self.use_native else prefix)

    def require_file(self) -> Path:
        selected = self.selected_file
        if not selected.is_file():
            raise ValueError("Shapers 插件文件不存在：" + str(selected))
        return selected
