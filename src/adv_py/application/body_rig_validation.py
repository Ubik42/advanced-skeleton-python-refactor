from __future__ import annotations

from adv_py.core.body_skeleton import BodySkeletonSnapshot


def body_bind_pose_matches(
    expected: BodySkeletonSnapshot,
    actual: BodySkeletonSnapshot,
    *,
    tolerance: float = 1e-4,
) -> bool:
    """Compare a Body snapshot without requiring adapter-specific object identity."""
    if expected.root != actual.root or expected.provenance != actual.provenance:
        return False
    wanted = {joint.path: joint for joint in expected.joints}
    current = {joint.path: joint for joint in actual.joints}
    if set(wanted) != set(current):
        return False
    for path, before in wanted.items():
        after = current[path]
        if (
            before.name,
            before.parent_path,
            before.side,
            before.label,
        ) != (
            after.name,
            after.parent_path,
            after.side,
            after.label,
        ):
            return False
        vectors = ((before.world_position, after.world_position),)
        vectors += tuple(zip(before.world_axes, after.world_axes))
        if any(
            any(abs(a - b) > tolerance for a, b in zip(left, right))
            for left, right in vectors
        ):
            return False
        if any(abs(value) > tolerance for value in after.rotation):
            return False
    return True
