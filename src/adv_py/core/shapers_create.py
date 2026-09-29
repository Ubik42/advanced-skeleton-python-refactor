"""Plan the FK-controller loop branch of AdvancedSkeleton Shapers creation."""
from __future__ import annotations

from dataclasses import dataclass
import re


_PYTHON_FK = re.compile(r"AdvPy_(.+)FK_([MRL])$")
_ORIGINAL_FK = re.compile(r"FK(.+)_([MRL])$")


@dataclass(frozen=True, slots=True)
class ShapersFkLoopOptions:
    loop_controls: int = 4
    snap_vertices: bool = True
    mirror: bool = True

    def __post_init__(self) -> None:
        if (type(self.loop_controls) is not int or self.loop_controls < 3
                or type(self.snap_vertices) is not bool
                or type(self.mirror) is not bool):
            raise ValueError("Shapers 闭环参数无效")


@dataclass(frozen=True, slots=True)
class ShapersFkLoop:
    control: str
    deform_joint: str
    fit_stem: str
    side: str


def plan_shapers_fk_loops(
    controls: tuple[str, ...], options: ShapersFkLoopOptions,
) -> tuple[ShapersFkLoop, ...]:
    if len(controls) != 1:
        raise ValueError("当前 FK 闭环路径一次选择一个 FK 控制器")
    control = controls[0]
    leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    match = _PYTHON_FK.fullmatch(leaf) or _ORIGINAL_FK.fullmatch(leaf)
    if match is None:
        raise ValueError("请选择 Body FK 控制器")
    stem, side = match.groups()
    if not stem or stem.endswith("Offset") or stem.endswith("Extra"):
        raise ValueError("请选择 FK 控制曲线，而非接收层")
    prefix = control.rsplit("|", 1)[-1].removesuffix(leaf)
    loops = [ShapersFkLoop(control, prefix + stem + "_" + side, stem,
                           "_" + side)]
    if options.mirror and side in ("R", "L"):
        opposite = "L" if side == "R" else "R"
        mirror_leaf = leaf[:-1] + opposite
        loops.append(ShapersFkLoop(prefix + mirror_leaf,
                                   prefix + stem + "_" + opposite,
                                   stem, "_" + opposite))
    return tuple(loops)
