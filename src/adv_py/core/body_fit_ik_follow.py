"""Map Fit ikFollow on limb ends to registered IK control receivers."""
from __future__ import annotations

from .body_fit_follow import BodyFitFollowSpec
from .fit_metadata import FitJointMetadata


def plan_body_fit_ik_follow(
    metadata: tuple[FitJointMetadata, ...], arm_ik: tuple,
    leg_ik: tuple, body_joints: tuple,
) -> tuple[BodyFitFollowSpec, ...]:
    by_name = {joint.name.rsplit(":", 1)[-1]: joint.path
               for joint in body_joints}
    if len(by_name) != len(body_joints):
        raise ValueError("IK Follow Body 关节短名重复")
    by_source = {}
    for limb in arm_ik:
        by_source.setdefault(
            limb.chain[-1].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            .rsplit("_", 1)[0],
            []).append((limb, limb.wrist_control_path,
                        limb.wrist_offset_path))
    for limb in leg_ik:
        by_source.setdefault(
            limb.chain[-1].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            .rsplit("_", 1)[0],
            []).append((limb, limb.ankle_control_path,
                        limb.ankle_offset_path))
    result = []
    used = set()
    for item in metadata:
        if item.ik_follow is None:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        limbs = by_source.get(source_name, ())
        if not limbs:
            raise ValueError("IK Follow 来源尚无已构建的 IK 末端控制器："
                             + source_name)
        for limb, control, offset in limbs:
            side = limb.side.value
            source_body = limb.chain[-1]
            if source_body not in by_name.values():
                raise ValueError("IK Follow 来源 Body 末端关节缺失："
                                 + source_body)
            target = (by_name.get(item.ik_follow + "_" + side)
                      or by_name.get(item.ik_follow + "_M"))
            if target is None:
                raise ValueError("IK Follow 目标 Body 关节缺失："
                                 + item.ik_follow + "_" + side)
            if target == source_body or target.startswith(source_body + "|"):
                raise ValueError("IK Follow 目标依赖自身 IK：" + target)
            if control in used:
                raise ValueError("IK Follow 控制器重复：" + control)
            used.add(control)
            prefix = offset + "|"
            if not control.startswith(prefix):
                raise ValueError("IK Follow 控制器不在 IK Offset 下")
            receiver = prefix + control[len(prefix):].split("|", 1)[0]
            leaf = control.rsplit("|", 1)[-1]
            namespace = leaf.split(":", 1)[0] + ":" if ":" in leaf else ""
            stem = namespace + "AdvPy_IkFollow" + source_name + "_" + side
            result.append(BodyFitFollowSpec(
                source_joint=item.joint, source_body=source_body,
                fk_control=control, fk_offset=offset, receiver=receiver,
                primary_target=target, opposite_target=None,
                world_target=False, primary_matrix=stem + "PrimaryMM",
                opposite_matrix=None, blend_matrix=stem + "BM",
                delta_matrix=stem + "DeltaMM",
                receiver_matrix=stem + "ReceiverMM",
                primary_weight=stem + "Weight",
                opposite_weight=None, world_weight=None,
                control_attribute="ikFollow"))
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("IK Follow 节点名称重复")
    return tuple(result)
