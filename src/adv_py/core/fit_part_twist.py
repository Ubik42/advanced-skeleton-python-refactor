"""Host-independent twist distribution for Fit Part chains."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_part import FitPartJointSpec


class FitPartTwistValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FitPartTwistSource:
    start_body: str
    down_twist_plug: str
    up_twist_plug: str | None = None
    subtract_body_twist: bool = True

    def __post_init__(self) -> None:
        if not self.start_body or not self.down_twist_plug:
            raise FitPartTwistValidationError("Part 扭转来源不能为空")
        if not isinstance(self.subtract_body_twist, bool):
            raise FitPartTwistValidationError("Body 扭转补偿开关必须是布尔值")


@dataclass(frozen=True, slots=True)
class FitPartTwistStep:
    part_name: str
    start_body: str
    index: int
    count: int
    default_amount: float
    down_twist_plug: str
    up_twist_plug: str | None
    previous_target_plug: str | None
    amount_node: str
    up_amount_node: str | None
    target_node: str
    difference_node: str

    @property
    def target_plug(self) -> str:
        return self.target_node + ".output1D"

    @property
    def output_plug(self) -> str:
        return self.difference_node + ".output1D"


def plan_fit_part_twist(
    parts: tuple[FitPartJointSpec, ...],
    sources: tuple[FitPartTwistSource, ...],
) -> tuple[FitPartTwistStep, ...]:
    """Plan local Part rotation from cumulative down/up-twist targets.

    For Part i, target(i) = down*amount(i) + up*amount(i) + addition(i).
    Its local X rotation subtracts target(i-1). The first Part optionally
    subtracts the Body's down twist when Body already carries that rotation.
    This describes the non-bendy distribution branch; callers must supply
    the actual rig twist plugs, which are not inferred from joint names.
    """
    by_start: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        by_start.setdefault(part.start_body, []).append(part)
    by_source = {source.start_body: source for source in sources}
    if len(by_source) != len(sources) or set(by_source) != set(by_start):
        raise FitPartTwistValidationError(
            "每条 Fit Part 链必须恰有一个扭转来源")
    part_names = {part.name for part in parts}
    for source in sources:
        for plug in (source.down_twist_plug, source.up_twist_plug):
            if plug and plug.split(".", 1)[0].rsplit("|", 1)[-1] in part_names:
                raise FitPartTwistValidationError(
                    "Part 扭转来源不能由同一批 Part 关节输出")
    steps: list[FitPartTwistStep] = []
    used_nodes: set[str] = set()
    for start_body, chain in by_start.items():
        chain.sort(key=lambda part: part.index)
        count = chain[0].count
        if (len(chain) != count or
                [part.index for part in chain] != list(range(1, count + 1)) or
                any(part.count != count for part in chain)):
            raise FitPartTwistValidationError("Part 链编号或数量不连续："
                                              + start_body)
        source = by_source[start_body]
        previous_target = (source.down_twist_plug
                           if source.subtract_body_twist else None)
        for part in chain:
            stem = part.name.rsplit("_", 1)[0]
            side = part.side.value
            prefix = f"AdvPy_{stem}_{side}_FitTwist"
            amount_node = prefix + "Amount"
            up_amount_node = prefix + "UpAmount" if source.up_twist_plug else None
            target_node = prefix + "Target"
            difference_node = prefix + "Local"
            names = (amount_node, target_node, difference_node)
            names += (up_amount_node,) if up_amount_node else ()
            if any(name in used_nodes for name in names):
                raise FitPartTwistValidationError("Part 扭转节点名称重复")
            used_nodes.update(names)
            step = FitPartTwistStep(
                part.name, start_body, part.index, count,
                part.index / (count + 1), source.down_twist_plug,
                source.up_twist_plug, previous_target, amount_node,
                up_amount_node, target_node, difference_node)
            steps.append(step)
            previous_target = step.target_plug
    return tuple(steps)
