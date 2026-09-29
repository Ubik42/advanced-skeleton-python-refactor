"""Resolve the variable Ankle-to-Toes chain used by ADV QToes IKHybrid."""
from __future__ import annotations

from .body_skeleton import BodySkeletonSnapshot


def plan_leg_joint_names(body: BodySkeletonSnapshot) -> tuple[str, ...]:
    """Return bilateral mechanism names, retaining intervening QToes joints."""
    by_name = {joint.name: joint for joint in body.joints}
    by_path = {joint.path: joint for joint in body.joints}
    if len(by_name) != len(body.joints) or len(by_path) != len(body.joints):
        raise ValueError("Leg QToes 来源关节名称或路径重复")
    intermediate_by_side = []
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
        if not marked or marked[0].parent_path == ankle.path:
            intermediate_by_side.append(())
            continue
        chain = []
        current = toes
        visited = set()
        while current.path != ankle.path:
            if current.path in visited or current.parent_path is None:
                raise ValueError("QToes 脚趾链存在循环或未连接到 Ankle：" + suffix)
            visited.add(current.path)
            chain.append(current)
            current = by_path.get(current.parent_path)
            if current is None:
                raise ValueError("QToes 脚趾链缺少 Body 父关节：" + suffix)
        chain.reverse()
        if marked[0] not in chain:
            raise ValueError("QToes 标记不在 Ankle→Toes 主链：" + suffix)
        if toes_end.parent_path != toes.path:
            raise ValueError("QToes 主链要求 ToesEnd 紧接 Toes：" + suffix)
        intermediates = tuple(joint.name.removesuffix("_" + suffix)
                              for joint in chain[:-1])
        if (not intermediates
                or any(not name or not name[0].isalpha()
                       or not name.isalnum() for name in intermediates)):
            raise ValueError("QToes 中间关节名称不适合 Leg 机制链：" + suffix)
        intermediate_by_side.append(intermediates)
    if intermediate_by_side[0] != intermediate_by_side[1]:
        raise ValueError("左右 QToes 中间关节链名称或顺序不一致")
    return (("Hip", "Knee", "Ankle") + intermediate_by_side[0]
            + ("Toes", "ToesEnd"))
