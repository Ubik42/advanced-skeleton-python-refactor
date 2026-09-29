"""Configure the 6.925 Shapers plug-in from the Body panel."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from adv_py.core.shapers_plugin import ShapersPluginPlan


@dataclass(frozen=True, slots=True)
class ShapersSetupResult:
    selected_file: Path
    module_file: Path
    loaded: bool
    restart_required: bool
    autoload: bool


@dataclass(frozen=True, slots=True)
class ShapersPluginStatus:
    root: Path | None
    loaded_file: Path | None
    mode: str
    autoload: bool


class ShapersSetupHost(Protocol):
    def make_plan(self, root: Path, mode: str,
                  autoload: bool) -> ShapersPluginPlan: ...
    def configure(self, plan: ShapersPluginPlan) -> ShapersSetupResult: ...


class SetupShapersPlugin:
    def __init__(self, host: ShapersSetupHost) -> None:
        self.host = host

    def apply(self, root: Path, *, mode: str = "automatic",
              autoload: bool = True) -> ShapersSetupResult:
        plan = self.host.make_plan(root, mode, autoload)
        plan.require_file()
        result = self.host.configure(plan)
        if (result.selected_file != plan.selected_file
                or result.autoload != autoload
                or not result.module_file.is_file()
                or not result.loaded and not result.restart_required):
            raise RuntimeError("Shapers 插件设置读回不一致")
        return result
