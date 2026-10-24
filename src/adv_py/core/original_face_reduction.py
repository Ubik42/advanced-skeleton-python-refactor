"""Selection policy for native Custom Face Joint Reduce, MEL 76148–76400."""
from dataclasses import dataclass
from fnmatch import fnmatchcase
from math import dist


@dataclass(frozen=True, slots=True)
class CustomFaceReduction:
    kind: str
    every: int
    parent: str
    setup: str
    holder: str
    marker: str
    reported_count: int
    all_joints: tuple[str, ...]
    kept: tuple[str, ...]
    removed: tuple[str, ...]


def custom_face_reduction(kind, every, joints, existing, current_count):
    if kind not in ('EyeLid', 'Lip') or type(every) is not int or every not in (2, 3, 4, 5):
        raise ValueError('请选择 EyeLid 或 Lip，以及每隔 2、3、4、5 个保留一个')
    lid_lip, main = ('Lid', 'Main') if kind == 'EyeLid' else ('Lip', 'Joint')
    all_joints = tuple(joint for joint in joints if fnmatchcase(joint, '*' + lid_lip + '*')
        and not fnmatchcase(joint, '*Base*') and joint not in ('LipJoints_M', 'EyeLidJoints_M'))
    removed = set()
    for side in ('_R', '_L'):
        for upper_lower in ('upper', 'lower'):
            for suffix in ((main, 'Outer') if kind == 'EyeLid' else (main,)):
                for index in range(1, 999):
                    name = upper_lower + lid_lip + suffix + str(index) + side
                    if not existing(name):
                        break
                    if index % every:
                        removed.add(name)
    return CustomFaceReduction(kind, every, 'EyeLidJoints_M' if kind == 'EyeLid' else 'LipJoints_M',
        lid_lip + 'Setup', lid_lip + 'JointReducedNoLongerDeformJoints',
        'asReduceEyeLidJoints' if kind == 'EyeLid' else 'asReduceLipJoints',
        int(current_count / every), all_joints,
        tuple(joint for joint in all_joints if joint not in removed),
        tuple(joint for joint in all_joints if joint in removed))


def reduction_balance_threshold(weights):
    """Native sort[-2]; do not add a new normalization/top-two policy."""
    return sorted(weights)[-2] if len(weights) >= 2 else None


def original_lip_anchor_indices(positions, anchors, previous=(0, 0, 0)):
    """MEL's three strict minima initialized to 999, in native joint order."""
    indices = list(previous)
    minima = [999., 999., 999.]
    for index, position in enumerate(positions):
        for slot, anchor in enumerate(anchors):
            distance = dist(position, anchor)
            if distance < minima[slot]:
                minima[slot] = distance
                indices[slot] = index
    return tuple(indices)


def original_lip_anchor_letter(index, indices):
    # Native uses three separate if statements. C overwrites B and A when
    # their nearest joints coincide; introducing three new joints is wrong.
    result = None
    for letter, selected in zip('ABC', indices):
        if index == selected:
            result = letter
    return result


def original_lid_anchor_indices(positions, anchors, previous=(0, 0, 0)):
    shifted = original_lip_anchor_indices(positions[1:-1], anchors,
                                         tuple(index - 1 for index in previous))
    return tuple(index + 1 for index in shifted)


def original_lid_nearest_pair(position, controls, previous=(0, 0)):
    indices = list(previous)
    minima = [999., 999.]
    for index, control in enumerate(controls):
        value = dist(position, control)
        if value < minima[0]:
            minima[0] = value
            indices[0] = index
    for index, control in enumerate(controls):
        if index == indices[0]:
            continue
        value = dist(position, control)
        if value < minima[1]:
            minima[1] = value
            indices[1] = index
    return indices[0], indices[1], minima[1] / sum(minima)


def original_lid_contact(upper_lower, difference):
    return difference <= 0 if upper_lower == 'upper' else difference >= 0
