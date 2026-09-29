"""Resolve the Ankle-to-Toes topology shared by Leg and Foot planning."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class LegQToesSideTopology:
    suffix: str
    ankle_path: str
    toes_path: str
    toes_end_path: str
    qtoes_path: str | None
    intermediate_paths: tuple[str, ...]
    intermediate_names: tuple[str, ...]
    hybrid: bool


@dataclass(frozen=True, slots=True)
class LegQToesTopology:
    joint_names: tuple[str, ...]
    sides: tuple[LegQToesSideTopology, ...]


def plan_leg_qtoes_topology(body: BodySkeletonSnapshot) -> LegQToesTopology:
    """Read bilateral toe chains once for mechanisms and Foot Roll planning."""
    by_name = {joint.name: joint for joint in body.joints}
    by_path = {joint.path: joint for joint in body.joints}
    if len(by_name) != len(body.joints) or len(by_path) != len(body.joints):
        raise ValueError("Leg QToes 来源关节名称或路径重复")
    sides = []
    for suffix in ("R", "L"):
        ankle = by_name.get("Ankle_" + suffix)
        toes = by_name.get("Toes_" + suffix)
        toes_end = by_name.get("ToesEnd_" + suffix)
        if ankle is None or toes is None or toes_end is None:
            raise ValueError("Leg QToes 需要双侧 Ankle／Toes／ToesEnd")
        marked = [joint for joint in body.joints
                  if joint.path.startswith(ankle.path + "|")
                  and "QToes" in joint.label.text]
        if len(marked) > 1:
            raise ValueError("同侧存在多个 QToes 标记：" + suffix)
        qtoes = marked[0] if marked else None
        hybrid = qtoes is not None and qtoes.parent_path != ankle.path
        chain = []
        current = toes
        visited = set()
        while current.path != ankle.path:
            if current.path in visited or current.parent_path is None:
                raise ValueError("脚趾主链存在循环或未连接到 Ankle：" + suffix)
            visited.add(current.path)
            chain.append(current)
            current = by_path.get(current.parent_path)
            if current is None:
                raise ValueError("脚趾主链缺少 Body 父关节：" + suffix)
        chain.reverse()
        if qtoes is not None and qtoes not in chain:
            raise ValueError("QToes 标记不在 Ankle→Toes 主链：" + suffix)
        if toes_end.parent_path != toes.path:
            raise ValueError("脚趾主链要求 ToesEnd 紧接 Toes：" + suffix)
        intermediate = tuple(chain[:-1])
        names = tuple(joint.name.removesuffix("_" + suffix)
                      for joint in intermediate)
        if any(not name or not name[0].isalpha() or not name.isalnum()
               for name in names):
            raise ValueError("脚趾中间关节名称不适合 Leg 机制链：" + suffix)
        sides.append(LegQToesSideTopology(
            suffix=suffix,
            ankle_path=ankle.path,
            toes_path=toes.path,
            toes_end_path=toes_end.path,
            qtoes_path=qtoes.path if qtoes else None,
            intermediate_paths=tuple(joint.path for joint in intermediate),
            intermediate_names=names,
            hybrid=hybrid,
        ))
    if sides[0].intermediate_names != sides[1].intermediate_names:
        raise ValueError("左右 QToes 中间关节链名称或顺序不一致")
    return LegQToesTopology(
        joint_names=(("Hip", "Knee", "Ankle")
                     + sides[0].intermediate_names + ("Toes", "ToesEnd")),
        sides=tuple(sides),
    )


def plan_leg_joint_names(body: BodySkeletonSnapshot) -> tuple[str, ...]:
    """Return bilateral mechanism names, retaining intervening QToes joints."""
    return plan_leg_qtoes_topology(body).joint_names
