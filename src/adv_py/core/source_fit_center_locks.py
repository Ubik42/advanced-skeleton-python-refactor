"""asFitModeLockCenterJoints's world sampler and plane rotation locks."""
from math import isfinite

from .fit_hierarchy import fit_build_scale


def source_fit_center_locks(hierarchy, parent_frames, primary_axis, secondary_axis):
    """Return exact locked channels for enabled Center Joints.

    The MEL sampler tests each local unit POINT in world space against .5;
    it does not test a normalized parent axis or subtract parent translation.
    Keep that distinction for translated, scaled or sheared Fit parents.
    """
    tolerance = .01*fit_build_scale(hierarchy)
    result = []
    for joint in hierarchy.joints:
        locked = []
        if abs(joint.world_position[0]) <= tolerance:
            frame = parent_frames.get(joint.dag_parent)
            if (not isinstance(frame, (tuple, list)) or len(frame) != 16
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           or not isfinite(value) for value in frame)):
                raise ValueError('Fit 中心关节缺少有限的父级世界矩阵：'+joint.path)
            for axis, offset in zip('xyz', (0, 4, 8)):
                world_x = frame[offset]+frame[12]
                if world_x > .5 or world_x < -.5:
                    locked.append('t'+axis)
            for first, second in (('X', 'Y'), ('X', 'Z'), ('Y', 'Z')):
                if ((primary_axis.endswith(first) and secondary_axis.endswith(second))
                        or (primary_axis.endswith(second) and secondary_axis.endswith(first))):
                    locked.extend(('r'+first.lower(), 'r'+second.lower()))
        result.append((joint.path, tuple(locked)))
    return tuple(result)
