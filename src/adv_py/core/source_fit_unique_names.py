"""Name rules from asUniqueNameAll/asUniqueName (MEL 5600–5682)."""
from dataclasses import dataclass
from fnmatch import fnmatchcase
import re


def source_fit_unique_labels(rows):
    """Ordered label-array mutation from asFitModeManualUpdate, 6470–6510.

    Existing duplicate values remain in the array. Every replacement is
    appended; the native loop does not release the old value or reserve a
    different fallback when all 98 candidates are occupied.
    """
    labels = [label for _, label in rows if label]
    changes = []
    for joint, label in rows:
        if (not label or not ('Shoulder' in label or 'Hip' in label
                              or 'Root' in label or label.startswith('0'))
                or labels.count(label) <= 1):
            continue
        candidate = label
        for index in range(1, 99):
            suffix = (chr(ord('A')+index-1) if index <= 26 else '') if label.startswith('0') else str(index)
            candidate = label+suffix
            if candidate not in labels:
                break
        changes.append((joint, candidate))
        labels.append(candidate)
    return tuple(changes)


def legacy_driving_curve_name(name: str) -> str | None:
    """Native compatibility pass removes only the fourth SDK character."""
    leaf = name.rsplit(':', 1)[-1]
    if not re.match(r'^SDK[0-9]', leaf):
        return None
    prefix = name[:-len(leaf)]
    return prefix + 'SDK' + leaf[4:]


def source_fit_unique_order(joints, *, duplicated_index_finger):
    """Reproduce native move-to-front loops, including changing loop indices."""
    ordered = list(joints)
    if duplicated_index_finger:
        for finger in ('Thumb', 'Pinky', 'Ring', 'Middle', 'Cup', 'Index'):
            for index in range(len(ordered)):
                if fnmatchcase(ordered[index].rsplit('|', 1)[-1], '*'+finger+'*'):
                    ordered.insert(0, ordered.pop(index))
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class SourceFitDrivingCopy:
    curve: str
    target: str
    attribute: str


def source_fit_driving_copy(curve, joint_name, renamed_name, suffix, source_plug):
    """Copy a matching SDK and its native Fit multi attribute descriptor."""
    curve_leaf = curve.rsplit(':', 1)[-1]
    joint_leaf = joint_name.rsplit(':', 1)[-1]
    renamed_leaf = renamed_name.rsplit(':', 1)[-1]
    if joint_leaf not in curve_leaf:
        return None
    if not isinstance(suffix, int) or isinstance(suffix, bool) or not 1 <= suffix < 99:
        raise ValueError('Fit 重名驱动数字后缀无效')
    if not isinstance(source_plug, str) or '.' not in source_plug:
        raise ValueError('Fit 驱动曲线缺少输入属性')
    parts = source_plug.split('.', 1)[1].split('[', 1)[0].split('_')
    if len(parts) < 3 or any(not part for part in parts[:3]):
        raise ValueError('Fit 驱动输入属性不符合原版三段命名')
    # Source concatenates the first three tokens; it does not insert a new
    # suffix into every occurrence of the old name or preserve extra tokens.
    attribute = parts[0]+'_'+parts[1]+str(suffix)+'_'+parts[2]
    target = curve[:-len(curve_leaf)] + curve_leaf.replace(joint_leaf, renamed_leaf, 1)
    return SourceFitDrivingCopy(curve, target, attribute)
