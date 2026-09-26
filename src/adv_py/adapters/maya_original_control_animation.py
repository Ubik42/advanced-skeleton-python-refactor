"""Carry direct time-keyed original FK control curves into the replacement rig."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class OriginalControlCurve:
    source_curve: str
    clone_name: str
    target_plug: str


def _target_control(name: str) -> str | None:
    central = re.fullmatch(r"FK(Root|Spine1|Chest|Neck|Head)_M", name)
    if central:
        return f"AdvPy_Torso{central.group(1)}_MFK"
    scapula = re.fullmatch(r"FKScapula_([RL])", name)
    if scapula:
        return f"AdvPy_TorsoScapula_{scapula.group(1)}FK"
    limb = re.fullmatch(
        r"FK(Shoulder|Elbow|Wrist|Hip|Knee|Ankle|Toes)_([RL])", name)
    if limb:
        return f"AdvPy_{limb.group(1)}FK_{limb.group(2)}"
    finger = re.fullmatch(
        r"FK(Thumb|Index|Middle|Ring|Pinky)Finger([123])_([RL])",
        name)
    if finger:
        return (f"AdvPy_{finger.group(1)}{finger.group(2)}"
                f"FK_{finger.group(3)}")
    return None


def plan_original_control_animation(cmds, rig_root: str
                                    ) -> tuple[OriginalControlCurve, ...]:
    """Reject keyed controls without a known target before removing the rig."""
    controls = cmds.listRelatives(rig_root, allDescendents=True,
                                 type="transform", fullPath=True) or []
    plans = []
    for path in controls:
        if not cmds.listRelatives(path, shapes=True, type="nurbsCurve"):
            continue
        name = path.rsplit("|", 1)[-1]
        target = _target_control(name)
        for attribute in cmds.listAttr(path, keyable=True) or []:
            plug = path + "." + attribute
            sources = cmds.listConnections(plug, source=True,
                destination=False, plugs=True,
                skipConversionNodes=True) or []
            direct = [source for source in sources if cmds.nodeType(
                source.split(".", 1)[0]) in
                ("animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU")]
            if not direct:
                if (sources and cmds.keyframe(plug, query=True,
                                              keyframeCount=True)):
                    raise ValueError("原版控制器动画由复杂驱动图输入，不能直接迁移："
                                     + name + "." + attribute)
                continue
            if len(direct) != 1 or len(sources) != 1:
                raise ValueError("原版控制器通道有多个动画输入：" + plug)
            if target is None:
                raise ValueError("带键原版控制器尚无新 Rig 对应入口："
                                 + name)
            curve = direct[0].split(".", 1)[0]
            clock = cmds.listConnections(curve + ".input", source=True,
                destination=False, plugs=True) or []
            if clock and clock != ["time1.outTime"]:
                raise ValueError("原版动画曲线使用非标准时间驱动：" + curve)
            clone = f"AdvPy_OriginalKey_{name}_{attribute}"
            if cmds.objExists(clone):
                raise ValueError("迁移动画曲线名称已被占用：" + clone)
            plans.append(OriginalControlCurve(
                curve, clone,
                target + "." + attribute))
    return tuple(plans)


def clone_original_control_animation(cmds,
    plans: tuple[OriginalControlCurve, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((cmds.duplicate(plan.source_curve,
        name=plan.clone_name, inputConnections=True)[0], plan.target_plug)
        for plan in plans)


def connect_original_control_animation(cmds,
    clones: tuple[tuple[str, str], ...]) -> None:
    for curve, target in clones:
        if not cmds.objExists(target) or cmds.listConnections(target,
            source=True, destination=False):
            raise ValueError("新 Rig 控制通道不可用于原版动画：" + target)
        cmds.connectAttr(curve + ".output", target)
