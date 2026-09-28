"""Generic FK layer for the imported FBX hierarchy's deformation joints."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodySkeletonSnapshot
from .fbx_rig_import import FBXRigImportPlan


@dataclass(frozen=True, slots=True)
class FBXRigFKControlSpec:
    control_name: str
    body_joint_path: str
    parent_control_name: str | None
    radius: float


def plan_fbx_rig_fk_controls(
    body: BodySkeletonSnapshot,
    source: FBXRigImportPlan,
) -> tuple[FBXRigFKControlSpec, ...]:
    """Match every planned source transfer to an actual Body joint."""
    by_path = {joint.path: joint for joint in body.joints}
    by_name = {joint.name: joint for joint in body.joints}
    if (len(by_path) != len(body.joints)
            or len(by_name) != len(body.joints)
            or "Root_M" not in by_name):
        raise ValueError("FBX rig Body 骨架缺少唯一 Root 或包含重名关节")
    candidate_names = tuple(link.control_name
                            for link in source.candidate_control_links)
    if len(set(candidate_names)) != len(candidate_names):
        raise ValueError("FBX rig 控制器计划包含重名节点")
    wanted = set(candidate_names)
    result = []
    for joint in sorted(body.joints,
                        key=lambda item: (item.path.count("|"), item.path)):
        control = "FK" + joint.name
        if control not in wanted:
            continue
        parent = by_path.get(joint.parent_path)
        while parent is not None and "FK" + parent.name not in wanted:
            parent = by_path.get(parent.parent_path)
        result.append(FBXRigFKControlSpec(
            control, joint.path,
            "FK" + parent.name if parent is not None else None,
            max(source.scale * .65, .01)))
    if {item.control_name for item in result} != wanted:
        raise ValueError("FBX rig 计划控制器缺少同名 Body 关节："
                         + "、".join(sorted(wanted - {
                             item.control_name for item in result})))
    return tuple(result)
