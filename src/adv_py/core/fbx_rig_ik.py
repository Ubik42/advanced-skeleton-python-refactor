"""Interpret original FBX rig Hip/Foot and Shoulder/Hand labels as RP limbs."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .body_skeleton import BodySkeletonSnapshot
from .fbx_rig_import import FBXRigImportPlan


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class FBXRigIKLimb:
    kind: str
    side: str
    body_joint_paths: tuple[str, str, str]
    body_joint_names: tuple[str, str, str]
    fk_control_names: tuple[str, str, str]
    ik_control_name: str
    pole_control_name: str
    switch_attribute: str
    pole_position: Vector3


def _pole_position(start: Vector3, middle: Vector3,
                   end: Vector3) -> Vector3:
    line = tuple(end[i] - start[i] for i in range(3))
    length2 = sum(value * value for value in line)
    if length2 < 1e-10:
        raise ValueError("FBX rig IK 首尾关节重合")
    fraction = sum((middle[i] - start[i]) * line[i]
                   for i in range(3)) / length2
    projected = tuple(start[i] + fraction * line[i] for i in range(3))
    bend = tuple(middle[i] - projected[i] for i in range(3))
    bend_length = sqrt(sum(value * value for value in bend))
    if bend_length < 1e-5:
        # Imported bind poses often have a perfectly straight knee or elbow.
        # Choose a stable forward plane, then project it off the chain axis.
        reference = ((0., 0., 1.) if abs(line[2]) < sqrt(length2) * .9
                     else (0., 1., 0.))
        bend = tuple(reference[i] -
                     sum(reference[j] * line[j] for j in range(3))
                     * line[i] / length2 for i in range(3))
        bend_length = sqrt(sum(value * value for value in bend))
    reach = sqrt(length2) * .75
    return tuple(middle[i] + bend[i] * reach / bend_length
                 for i in range(3))


def plan_fbx_rig_ik_limbs(
    body: BodySkeletonSnapshot,
    source: FBXRigImportPlan,
) -> tuple[FBXRigIKLimb, ...]:
    """Create IK only for unambiguous, complete three-joint labeled limbs."""
    by_name = {joint.name: joint for joint in body.joints}
    by_path = {joint.path: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("FBX rig Body 关节短名重复")
    label_names = {label: name for name, label in source.inferred_labels}
    result = []
    for kind, start_label, end_label in (
        ("Leg", "Hip", "Foot"), ("Arm", "Shoulder", "Hand"),
    ):
        start_base = label_names.get(start_label)
        end_base = label_names.get(end_label)
        if start_base is None or end_base is None:
            continue
        pair = []
        for side in ("R", "L"):
            start = by_name.get(start_base + "_" + side)
            end = by_name.get(end_base + "_" + side)
            if start is None or end is None:
                raise ValueError("FBX rig 已标记的 IK 左右关节不完整：" + kind)
            chain = [end]
            current = end
            while current.path != start.path:
                current = by_path.get(current.parent_path)
                if current is None or len(chain) > 3:
                    chain = []
                    break
                chain.append(current)
            if len(chain) != 3:
                pair = []
                break
            chain.reverse()
            positions = tuple(tuple(float(value) for value in joint.world_position)
                              for joint in chain)
            if any(sqrt(sum((positions[index + 1][axis] -
                             positions[index][axis]) ** 2
                            for axis in range(3))) <
                   max(source.scale * .001, 1e-5)
                   for index in (0, 1)):
                pair = []
                break
            pair.append(FBXRigIKLimb(
                kind, side, tuple(joint.path for joint in chain),
                tuple(joint.name for joint in chain),
                tuple("FK" + joint.name for joint in chain),
                "IK" + kind + "_" + side,
                "Pole" + kind + "_" + side,
                kind.lower() + "IKFK_" + side,
                _pole_position(*positions)))
        if len(pair) == 2:
            result.extend(pair)
    paths = [path for limb in result for path in limb.body_joint_paths]
    if len(paths) != len(set(paths)):
        raise ValueError("FBX rig IK 手脚链共享了同一关节")
    return tuple(result)
